"""Tier 1 tests for the attribution module.

Covers:
- BrinsonDecomposition: allocation, selection, interaction effects
- RiskMetrics: Sharpe, Sortino, Calmar, max drawdown, volatility,
  tracking error, information ratio, Jensen's alpha, recovery time
- TrackRecordScorer: composite score computation
- NAVComputation: position-level NAV with cash (mocked DataFlow)
- CounterfactualEngine: what-if scenario analysis (mocked DataFlow)
- Edge cases: zero returns, single period, all negative returns
"""

import json
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from midas.attribution.brinson import BrinsonDecomposition
from midas.attribution.counterfactual import CounterfactualEngine
from midas.attribution.metrics import TRADING_DAYS_PER_YEAR, RiskMetrics
from midas.attribution.nav import NAVComputation
from midas.attribution.track_record import TrackRecordScorer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def brinson():
    return BrinsonDecomposition()


@pytest.fixture
def scorer():
    return TrackRecordScorer()


@pytest.fixture
def mock_db():
    """Create a mock DataFlow for NAV and counterfactual tests."""
    db = MagicMock()
    db.express = MagicMock()
    db.express.list = AsyncMock()
    db.express.read = AsyncMock()
    return db


# ===========================================================================
# Brinson Decomposition
# ===========================================================================


class TestBrinsonDecomposition:
    """Tests for Brinson-Fachler attribution decomposition."""

    def test_basic_decomposition_sums_to_active_return(self, brinson):
        """Allocation + selection + interaction = total active return."""
        w_p = np.array([0.6, 0.4])
        w_b = np.array([0.5, 0.5])
        r_p = np.array([0.10, 0.04])
        r_b = np.array([0.08, 0.02])

        result = brinson.decompose(w_p, w_b, r_p, r_b)

        total = (
            result["allocation_effect"] + result["selection_effect"] + result["interaction_effect"]
        )
        assert abs(total - result["total_active_return"]) < 1e-10

    def test_active_return_equals_portfolio_minus_benchmark(self, brinson):
        """Total active return = portfolio return minus benchmark return."""
        w_p = np.array([0.6, 0.4])
        w_b = np.array([0.5, 0.5])
        r_p = np.array([0.10, 0.04])
        r_b = np.array([0.08, 0.02])

        result = brinson.decompose(w_p, w_b, r_p, r_b)

        portfolio_return = float(np.dot(w_p, r_p))
        benchmark_return = float(np.dot(w_b, r_b))
        expected_active = portfolio_return - benchmark_return

        assert abs(result["total_active_return"] - expected_active) < 1e-10

    def test_allocation_effect_brinson_fachler(self, brinson):
        """Allocation uses (w_p - w_b) * (r_b - R_b_total), not plain (w_p - w_b) * r_b."""
        w_p = np.array([0.7, 0.3])
        w_b = np.array([0.5, 0.5])
        r_p = np.array([0.05, 0.05])
        r_b = np.array([0.05, 0.05])

        result = brinson.decompose(w_p, w_b, r_p, r_b)

        # When r_p == r_b everywhere, selection and interaction are zero.
        # Allocation uses benchmark returns relative to total benchmark return,
        # so it can be non-zero even when r_p == r_b.
        assert abs(result["selection_effect"]) < 1e-10
        assert abs(result["interaction_effect"]) < 1e-10
        # With identical per-category returns, the total benchmark return
        # equals each category return, so allocation must also be zero.
        assert abs(result["allocation_effect"]) < 1e-10

    def test_selection_effect_with_outperformance(self, brinson):
        """Positive selection when portfolio outperforms benchmark in a category."""
        w_p = np.array([0.5, 0.5])
        w_b = np.array([0.5, 0.5])
        r_p = np.array([0.12, 0.04])
        r_b = np.array([0.08, 0.04])

        result = brinson.decompose(w_p, w_b, r_p, r_b)

        # Category 0 outperforms by 4%, category 1 matches.
        # Selection = w_b[0] * (0.12 - 0.08) + w_b[1] * (0.04 - 0.04)
        expected_selection = 0.5 * 0.04
        assert abs(result["selection_effect"] - expected_selection) < 1e-10
        assert result["selection_effect"] > 0

    def test_interaction_effect_nonzero(self, brinson):
        """Interaction is nonzero when both weight and return differ."""
        w_p = np.array([0.7, 0.3])
        w_b = np.array([0.5, 0.5])
        r_p = np.array([0.10, 0.02])
        r_b = np.array([0.06, 0.04])

        result = brinson.decompose(w_p, w_b, r_p, r_b)

        # Interaction = sum of (w_p - w_b) * (r_p - r_b)
        assert result["interaction_effect"] != 0.0

    def test_equal_weights_zero_allocation_and_interaction(self, brinson):
        """When weights match, allocation and interaction are zero."""
        w = np.array([0.4, 0.3, 0.3])
        r_p = np.array([0.10, 0.05, -0.02])
        r_b = np.array([0.08, 0.06, 0.01])

        result = brinson.decompose(w, w, r_p, r_b)

        assert abs(result["allocation_effect"]) < 1e-10
        assert abs(result["interaction_effect"]) < 1e-10
        # Only selection remains: w_b * (r_p - r_b)
        expected_selection = float(np.sum(w * (r_p - r_b)))
        assert abs(result["selection_effect"] - expected_selection) < 1e-10

    def test_per_category_breakdown(self, brinson):
        """Per-category breakdown has correct structure and values."""
        w_p = np.array([0.6, 0.4])
        w_b = np.array([0.5, 0.5])
        r_p = np.array([0.10, 0.04])
        r_b = np.array([0.08, 0.02])
        categories = ["equity", "bonds"]

        result = brinson.decompose(w_p, w_b, r_p, r_b, categories=categories)

        assert len(result["per_category"]) == 2
        cat0 = result["per_category"][0]
        assert cat0["category"] == "equity"
        assert abs(cat0["portfolio_weight"] - 0.6) < 1e-10
        assert abs(cat0["benchmark_weight"] - 0.5) < 1e-10
        assert abs(cat0["portfolio_return"] - 0.10) < 1e-10
        assert abs(cat0["benchmark_return"] - 0.08) < 1e-10

    def test_missing_categories_use_default_labels(self, brinson):
        """Without category labels, default 'category_N' is used."""
        w = np.array([0.5, 0.5])
        r = np.array([0.05, 0.03])

        result = brinson.decompose(w, w, r, r)

        assert result["per_category"][0]["category"] == "category_0"
        assert result["per_category"][1]["category"] == "category_1"

    def test_mismatched_array_lengths_raises(self, brinson):
        """ValueError when arrays have different lengths."""
        w_p = np.array([0.5, 0.5])
        w_b = np.array([0.5])  # wrong length
        r_p = np.array([0.05, 0.03])
        r_b = np.array([0.04, 0.02])

        with pytest.raises(ValueError, match="must have the same length"):
            brinson.decompose(w_p, w_b, r_p, r_b)

    def test_single_category(self, brinson):
        """Single-category decomposition still sums correctly."""
        w_p = np.array([1.0])
        w_b = np.array([1.0])
        r_p = np.array([0.08])
        r_b = np.array([0.06])

        result = brinson.decompose(w_p, w_b, r_p, r_b)

        # With equal weights, only selection contributes
        assert abs(result["allocation_effect"]) < 1e-10
        assert abs(result["interaction_effect"]) < 1e-10
        assert abs(result["selection_effect"] - 0.02) < 1e-10

    def test_negative_benchmark_return_allocation_sign(self, brinson):
        """Brinson-Fachler: over-weighting a negative-return sector has correct sign."""
        w_p = np.array([0.2, 0.8])  # over-weight sector 1
        w_b = np.array([0.5, 0.5])
        r_p = np.array([0.05, -0.02])
        r_b = np.array([0.05, -0.02])

        result = brinson.decompose(w_p, w_b, r_p, r_b)

        # Total benchmark return: 0.5*0.05 + 0.5*(-0.02) = 0.015
        # Sector 1: (w_p - w_b) * (r_b - R_b_total) = 0.3 * (-0.02 - 0.015) = -0.0105
        # Sector 0: (-0.3) * (0.05 - 0.015) = -0.0105
        # Total allocation: -0.021
        assert result["allocation_effect"] < 0


# ===========================================================================
# Risk Metrics
# ===========================================================================


class TestSharpeRatio:
    """Tests for Sharpe ratio computation."""

    def test_positive_returns_positive_sharpe(self):
        returns = np.array([0.01, 0.02, 0.015, 0.005, 0.025])
        sharpe = RiskMetrics.sharpe_ratio(returns)
        assert sharpe > 0

    def test_zero_returns_zero_sharpe(self):
        """Zero standard deviation of returns yields Sharpe of 0.0."""
        returns = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
        sharpe = RiskMetrics.sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_constant_returns_zero_sharpe(self):
        """Constant non-zero returns have zero std, so Sharpe is 0.0."""
        returns = np.array([0.01, 0.01, 0.01, 0.01])
        sharpe = RiskMetrics.sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_sharpe_with_risk_free_rate(self):
        """Excess returns above risk-free rate drive the Sharpe."""
        returns = np.array([0.01, 0.02, 0.015, 0.005, 0.025])
        sharpe_no_rf = RiskMetrics.sharpe_ratio(returns, risk_free_rate=0.0)
        sharpe_with_rf = RiskMetrics.sharpe_ratio(returns, risk_free_rate=0.01)
        # Higher risk-free rate reduces excess returns, lowering Sharpe
        assert sharpe_with_rf < sharpe_no_rf

    def test_sharpe_not_annualized(self):
        """Non-annualized Sharpe does not multiply by sqrt(252)."""
        returns = np.array([0.01, 0.02, -0.01, 0.015, 0.005])
        annualized = RiskMetrics.sharpe_ratio(returns, annualize=True)
        raw = RiskMetrics.sharpe_ratio(returns, annualize=False)
        assert abs(annualized - raw * np.sqrt(252)) < 1e-10

    def test_all_negative_returns_negative_sharpe(self):
        returns = np.array([-0.02, -0.03, -0.01, -0.04, -0.015])
        sharpe = RiskMetrics.sharpe_ratio(returns)
        assert sharpe < 0

    def test_single_period_return_is_nan(self):
        """Single return: np.std(ddof=1) on 1 element is NaN, so Sharpe is NaN."""
        returns = np.array([0.05])
        sharpe = RiskMetrics.sharpe_ratio(returns)
        assert np.isnan(sharpe)


class TestSortinoRatio:
    """Tests for Sortino ratio computation."""

    def test_positive_returns_with_no_downside(self):
        """All positive returns: Sortino should be positive (or inf)."""
        returns = np.array([0.01, 0.02, 0.015, 0.005, 0.025])
        sortino = RiskMetrics.sortino_ratio(returns)
        assert sortino > 0 or sortino == float("inf")

    def test_mixed_returns_sortino(self):
        returns = np.array([0.02, -0.01, 0.03, -0.02, 0.01])
        sortino = RiskMetrics.sortino_ratio(returns)
        assert isinstance(sortino, float)

    def test_all_negative_returns_negative_sortino(self):
        returns = np.array([-0.02, -0.03, -0.01, -0.04, -0.015])
        sortino = RiskMetrics.sortino_ratio(returns)
        assert sortino < 0

    def test_zero_returns_sortino(self):
        """All zero returns: no downside deviation, mean excess is 0, Sortino is 0."""
        returns = np.array([0.0, 0.0, 0.0, 0.0])
        sortino = RiskMetrics.sortino_ratio(returns)
        assert sortino == 0.0

    def test_sortino_with_target_return(self):
        """Target return above all returns should change the Sortino."""
        returns = np.array([0.01, 0.02, -0.01, 0.015, 0.005])
        sortino_zero_target = RiskMetrics.sortino_ratio(returns, target_return=0.0)
        sortino_high_target = RiskMetrics.sortino_ratio(returns, target_return=0.02)
        # Higher target means more returns are "below target", widening downside
        assert sortino_high_target < sortino_zero_target

    def test_sortino_not_annualized(self):
        returns = np.array([0.02, -0.01, 0.03, -0.02, 0.01])
        annualized = RiskMetrics.sortino_ratio(returns, annualize=True)
        raw = RiskMetrics.sortino_ratio(returns, annualize=False)
        assert abs(annualized - raw * np.sqrt(252)) < 1e-10


class TestMaxDrawdown:
    """Tests for max drawdown computation."""

    def test_monotonic_increase_zero_drawdown(self):
        equity = np.array([100.0, 110.0, 120.0, 130.0])
        mdd = RiskMetrics.max_drawdown(equity)
        assert mdd == 0.0

    def test_simple_drawdown(self):
        equity = np.array([100.0, 110.0, 90.0, 95.0])
        mdd = RiskMetrics.max_drawdown(equity)
        # Peak 110, trough 90 => (110-90)/110 = 20/110
        expected = (110.0 - 90.0) / 110.0
        assert abs(mdd - expected) < 1e-10

    def test_drawdown_recovery(self):
        equity = np.array([100.0, 80.0, 110.0])
        mdd = RiskMetrics.max_drawdown(equity)
        # Peak 100, trough 80 => (100-80)/100 = 0.2
        assert abs(mdd - 0.2) < 1e-10

    def test_single_value_zero_drawdown(self):
        """Single equity value: cannot compute drawdown."""
        equity = np.array([100.0])
        mdd = RiskMetrics.max_drawdown(equity)
        assert mdd == 0.0

    def test_empty_array_zero_drawdown(self):
        equity = np.array([])
        mdd = RiskMetrics.max_drawdown(equity)
        assert mdd == 0.0

    def test_later_drawdown_exceeds_earlier(self):
        """Later, deeper drawdown is captured as max."""
        equity = np.array([100.0, 95.0, 105.0, 70.0, 80.0])
        mdd = RiskMetrics.max_drawdown(equity)
        # Peak 105, trough 70 => (105-70)/105 = 35/105
        expected = (105.0 - 70.0) / 105.0
        assert abs(mdd - expected) < 1e-10

    def test_max_drawdown_range(self):
        """Drawdown is always between 0 and 1."""
        equity = np.array([100.0, 50.0, 75.0, 25.0, 80.0])
        mdd = RiskMetrics.max_drawdown(equity)
        assert 0.0 <= mdd <= 1.0


class TestCalmarRatio:
    """Tests for Calmar ratio computation."""

    def test_positive_returns_with_drawdown(self):
        returns = np.array([0.01, -0.02, 0.03, 0.01, 0.02])
        calmar = RiskMetrics.calmar_ratio(returns)
        assert isinstance(calmar, float)

    def test_zero_drawdown_infinite_calmar(self):
        """Monotonic increase means zero drawdown, Calmar is infinite."""
        returns = np.array([0.01, 0.02, 0.015, 0.005])
        calmar = RiskMetrics.calmar_ratio(returns)
        assert calmar == float("inf")

    def test_calmar_not_annualized(self):
        returns = np.array([0.01, -0.02, 0.03, 0.01, 0.02])
        annualized = RiskMetrics.calmar_ratio(returns, annualize=True)
        raw = RiskMetrics.calmar_ratio(returns, annualize=False)
        # Annualized uses mean_return * 252, raw uses mean_return directly
        # Both divide by same max_drawdown
        assert isinstance(annualized, float)
        assert isinstance(raw, float)

    def test_all_negative_returns_negative_calmar(self):
        returns = np.array([-0.01, -0.02, -0.015, -0.005])
        calmar = RiskMetrics.calmar_ratio(returns)
        # Negative return divided by positive drawdown = negative Calmar
        assert calmar < 0


class TestVolatility:
    """Tests for annualized volatility."""

    def test_positive_volatility(self):
        returns = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
        vol = RiskMetrics.volatility(returns)
        assert vol > 0

    def test_zero_returns_zero_volatility(self):
        returns = np.array([0.0, 0.0, 0.0, 0.0])
        vol = RiskMetrics.volatility(returns)
        assert vol == 0.0

    def test_volatility_not_annualized(self):
        returns = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
        annualized = RiskMetrics.volatility(returns, annualize=True)
        raw = RiskMetrics.volatility(returns, annualize=False)
        assert abs(annualized - raw * np.sqrt(252)) < 1e-10

    def test_higher_variance_higher_volatility(self):
        low_var = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
        high_var = np.array([0.05, -0.04, 0.06, -0.05, 0.03])
        assert RiskMetrics.volatility(high_var) > RiskMetrics.volatility(low_var)


class TestTrackingError:
    """Tests for tracking error computation."""

    def test_identical_returns_zero_tracking_error(self):
        returns = np.array([0.01, 0.02, 0.015])
        te = RiskMetrics.tracking_error(returns, returns)
        assert te == 0.0

    def test_positive_tracking_error(self):
        port = np.array([0.02, 0.01, 0.03])
        bench = np.array([0.01, 0.02, 0.015])
        te = RiskMetrics.tracking_error(port, bench)
        assert te > 0

    def test_tracking_error_annualization(self):
        port = np.array([0.02, -0.01, 0.03, -0.02, 0.01])
        bench = np.array([0.01, 0.005, 0.02, -0.005, 0.015])
        annualized = RiskMetrics.tracking_error(port, bench, annualize=True)
        raw = RiskMetrics.tracking_error(port, bench, annualize=False)
        assert abs(annualized - raw * np.sqrt(252)) < 1e-10


class TestInformationRatio:
    """Tests for information ratio computation."""

    def test_identical_returns_nan_ir(self):
        """Identical portfolio and benchmark: zero active return, zero TE => NaN."""
        returns = np.array([0.01, 0.02, 0.015])
        ir = RiskMetrics.information_ratio(returns, returns)
        assert np.isnan(ir)

    def test_positive_active_return_positive_ir(self):
        port = np.array([0.03, 0.02, 0.04])
        bench = np.array([0.01, 0.01, 0.02])
        ir = RiskMetrics.information_ratio(port, bench)
        assert ir > 0

    def test_negative_active_return_negative_ir(self):
        port = np.array([0.01, 0.005, 0.015])
        bench = np.array([0.03, 0.02, 0.04])
        ir = RiskMetrics.information_ratio(port, bench)
        assert ir < 0


class TestJensensAlpha:
    """Tests for Jensen's alpha computation."""

    def test_zero_alpha_when_matching_benchmark(self):
        """When portfolio equals benchmark, alpha is zero."""
        returns = np.array([0.01, 0.02, -0.01, 0.015])
        alpha = RiskMetrics.jensens_alpha(returns, returns)
        assert abs(alpha) < 1e-10

    def test_positive_alpha_when_outperforming(self):
        port = np.array([0.03, 0.02, 0.04, 0.01])
        bench = np.array([0.01, 0.01, 0.02, 0.005])
        alpha = RiskMetrics.jensens_alpha(port, bench)
        assert alpha > 0

    def test_alpha_with_risk_free_rate(self):
        port = np.array([0.03, 0.02, 0.04])
        bench = np.array([0.01, 0.01, 0.02])
        alpha_no_rf = RiskMetrics.jensens_alpha(port, bench, risk_free_rate=0.0)
        alpha_with_rf = RiskMetrics.jensens_alpha(port, bench, risk_free_rate=0.01)
        # Both should be positive since portfolio outperforms
        assert alpha_no_rf > 0
        assert alpha_with_rf > 0

    def test_zero_benchmark_variance_alpha_is_mean_excess_portfolio(self):
        """When benchmark has zero variance, alpha = mean(excess_portfolio).

        Implementation returns mean(port - rf) when var(bench - rf) == 0,
        NOT mean(port - bench).
        """
        port = np.array([0.03, 0.02, 0.04])
        bench = np.array([0.01, 0.01, 0.01])  # constant => zero variance
        alpha = RiskMetrics.jensens_alpha(port, bench, risk_free_rate=0.0)
        # excess_p = port - 0 = port, mean(excess_p) = mean(port) = 0.03
        expected = float(np.mean(port))
        assert abs(alpha - expected) < 1e-10


class TestRecoveryTime:
    """Tests for recovery time computation."""

    def test_no_drawdown_zero_recovery(self):
        equity = np.array([100.0, 110.0, 120.0])
        assert RiskMetrics.recovery_time(equity) == 0

    def test_simple_recovery(self):
        equity = np.array([100.0, 90.0, 95.0, 105.0])
        # Trough at index 1 (90), recovers to 100+ at index 3
        rt = RiskMetrics.recovery_time(equity)
        assert rt == 2  # index 3 - index 1

    def test_never_recovers(self):
        """When equity never recovers to previous peak, returns days to end."""
        equity = np.array([100.0, 90.0, 85.0, 88.0])
        # Trough at index 2 (85), never reaches 100 again
        # Days from trough (index 2) to end (index 3) = 1
        rt = RiskMetrics.recovery_time(equity)
        assert rt == 1

    def test_single_equity_value(self):
        equity = np.array([100.0])
        assert RiskMetrics.recovery_time(equity) == 0

    def test_two_values_drawdown_no_recovery(self):
        equity = np.array([100.0, 90.0])
        rt = RiskMetrics.recovery_time(equity)
        # Trough at index 1, no more data => 0 days to end
        assert rt == 0


# ===========================================================================
# Track Record Scorer
# ===========================================================================


class TestTrackRecordScorer:
    """Tests for composite track record scoring."""

    def test_perfect_metrics_high_score(self, scorer):
        metrics = {
            "sharpe_ratio": 3.0,
            "sortino_ratio": 4.0,
            "max_drawdown": 0.0,
            "win_rate": 1.0,
            "avg_return": 0.3,
        }
        score = scorer.compute_composite(metrics)
        assert 90 <= score <= 100

    def test_terrible_metrics_low_score(self, scorer):
        metrics = {
            "sharpe_ratio": -2.0,
            "sortino_ratio": -2.0,
            "max_drawdown": 0.5,
            "win_rate": 0.0,
            "avg_return": -0.2,
        }
        score = scorer.compute_composite(metrics)
        assert 0 <= score <= 10

    def test_score_between_zero_and_100(self, scorer):
        metrics = {
            "sharpe_ratio": 1.0,
            "sortino_ratio": 1.5,
            "max_drawdown": 0.15,
            "win_rate": 0.55,
            "avg_return": 0.08,
        }
        score = scorer.compute_composite(metrics)
        assert 0 <= score <= 100

    def test_default_values_when_missing_keys(self, scorer):
        """Missing metrics use defaults: sharpe=0, sortino=0, dd=0, win_rate=0.5, avg_return=0."""
        score = scorer.compute_composite({})
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_high_drawdown_reduces_score(self, scorer):
        good = {
            "sharpe_ratio": 1.0,
            "sortino_ratio": 1.5,
            "max_drawdown": 0.05,
            "win_rate": 0.6,
            "avg_return": 0.1,
        }
        bad_dd = good.copy()
        bad_dd["max_drawdown"] = 0.45

        assert scorer.compute_composite(bad_dd) < scorer.compute_composite(good)

    def test_zero_win_rate_reduces_score(self, scorer):
        base = {
            "sharpe_ratio": 1.0,
            "sortino_ratio": 1.5,
            "max_drawdown": 0.1,
            "win_rate": 0.6,
            "avg_return": 0.1,
        }
        low_wr = base.copy()
        low_wr["win_rate"] = 0.0

        assert scorer.compute_composite(low_wr) < scorer.compute_composite(base)

    def test_weights_sum_to_one(self):
        """Verify the internal weight configuration sums to 1.0."""
        from midas.attribution.track_record import _WEIGHTS

        assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-10

    def test_extreme_positive_metrics_capped_at_100(self, scorer):
        """Even with extreme metrics, score cannot exceed 100."""
        metrics = {
            "sharpe_ratio": 100.0,
            "sortino_ratio": 100.0,
            "max_drawdown": 0.0,
            "win_rate": 1.0,
            "avg_return": 5.0,
        }
        score = scorer.compute_composite(metrics)
        assert score <= 100.0


# ===========================================================================
# NAV Computation (mocked DataFlow)
# ===========================================================================


class TestNAVComputation:
    """Tests for daily NAV computation with mocked DataFlow."""

    @pytest.mark.asyncio
    async def test_nav_from_positions(self, mock_db):
        positions = [
            {"market_value": 50000.0, "ticker": "AAPL"},
            {"market_value": 30000.0, "ticker": "GOOG"},
        ]
        mock_db.express.list.return_value = positions

        nav_comp = NAVComputation(mock_db)
        result = await nav_comp.compute_nav("2024-01-15")

        assert result["nav"] == 80000.0
        assert result["positions_value"] == 80000.0
        assert result["positions_count"] == 2
        assert result["as_of_date"] == "2024-01-15"

    @pytest.mark.asyncio
    async def test_nav_no_positions(self, mock_db):
        mock_db.express.list.return_value = []

        nav_comp = NAVComputation(mock_db)
        result = await nav_comp.compute_nav("2024-01-15")

        assert result["nav"] == 0.0
        assert result["positions_value"] == 0.0
        assert result["positions_count"] == 0

    @pytest.mark.asyncio
    async def test_nav_handles_db_error_gracefully(self, mock_db):
        mock_db.express.list.side_effect = Exception("connection failed")

        nav_comp = NAVComputation(mock_db)
        result = await nav_comp.compute_nav("2024-01-15")

        # Should not crash; treats as empty positions
        assert result["nav"] == 0.0
        assert result["positions_count"] == 0

    @pytest.mark.asyncio
    async def test_nav_handles_missing_market_value(self, mock_db):
        positions = [
            {"ticker": "AAPL"},  # no market_value key
            {"ticker": "GOOG", "market_value": None},
            {"ticker": "MSFT", "market_value": 10000.0},
        ]
        mock_db.express.list.return_value = positions

        nav_comp = NAVComputation(mock_db)
        result = await nav_comp.compute_nav("2024-01-15")

        assert result["positions_value"] == 10000.0
        assert result["nav"] == 10000.0

    @pytest.mark.asyncio
    async def test_nav_cash_and_unsettled_defaults(self, mock_db):
        """Cash and unsettled default to 0 until cash module is built."""
        mock_db.express.list.return_value = [
            {"market_value": 50000.0, "ticker": "AAPL"},
        ]

        nav_comp = NAVComputation(mock_db)
        result = await nav_comp.compute_nav("2024-01-15")

        assert result["cash"] == 0.0
        assert result["unsettled"] == 0.0
        # nav = positions_value + cash - unsettled
        assert result["nav"] == 50000.0


# ===========================================================================
# Counterfactual Engine (mocked DataFlow)
# ===========================================================================


class TestCounterfactualEngine:
    """Tests for counterfactual return computation with mocked DataFlow."""

    @pytest.mark.asyncio
    async def test_counterfactual_default_horizons(self, mock_db):
        outcome = {
            "return_1d": 0.02,
            "counterfactual_1d": 0.005,
            "return_5d": 0.04,
            "counterfactual_5d": 0.01,
            "return_21d": 0.08,
            "counterfactual_21d": 0.02,
        }
        mock_db.express.read.return_value = {"outcome_json": json.dumps(outcome)}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-001")

        assert result["decision_id"] == "decision-001"
        assert len(result["counterfactuals"]) == 3

        horizons = [cf["horizon"] for cf in result["counterfactuals"]]
        assert horizons == [1, 5, 21]

    @pytest.mark.asyncio
    async def test_counterfactual_diff_computation(self, mock_db):
        outcome = {
            "return_1d": 0.03,
            "counterfactual_1d": 0.01,
        }
        mock_db.express.read.return_value = {"outcome_json": json.dumps(outcome)}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-002", horizons=[1])

        cf = result["counterfactuals"][0]
        assert abs(cf["executed_return"] - 0.03) < 1e-10
        assert abs(cf["counterfactual_return"] - 0.01) < 1e-10
        assert abs(cf["diff"] - 0.02) < 1e-10

    @pytest.mark.asyncio
    async def test_counterfactual_custom_horizons(self, mock_db):
        outcome = {
            "return_1d": 0.01,
            "counterfactual_1d": 0.005,
            "return_5d": 0.03,
            "counterfactual_5d": 0.01,
        }
        mock_db.express.read.return_value = {"outcome_json": json.dumps(outcome)}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-003", horizons=[1, 5])

        assert len(result["counterfactuals"]) == 2

    @pytest.mark.asyncio
    async def test_counterfactual_missing_outcome_json(self, mock_db):
        """Missing outcome_json defaults to empty dict, returns zero."""
        mock_db.express.read.return_value = {"outcome_json": ""}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-004")

        for cf in result["counterfactuals"]:
            assert cf["executed_return"] == 0.0
            assert cf["counterfactual_return"] == 0.0
            assert cf["diff"] == 0.0

    @pytest.mark.asyncio
    async def test_counterfactual_null_outcome_json(self, mock_db):
        """None outcome_json is handled gracefully."""
        mock_db.express.read.return_value = {"outcome_json": None}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-005")

        for cf in result["counterfactuals"]:
            assert cf["executed_return"] == 0.0

    @pytest.mark.asyncio
    async def test_counterfactual_invalid_json(self, mock_db):
        """Invalid JSON in outcome_json is handled gracefully."""
        mock_db.express.read.return_value = {"outcome_json": "not valid json {"}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-006")

        for cf in result["counterfactuals"]:
            assert cf["executed_return"] == 0.0

    @pytest.mark.asyncio
    async def test_counterfactual_negative_diff_when_counterfactual_wins(self, mock_db):
        """Diff is negative when the counterfactual outperforms the decision."""
        outcome = {
            "return_1d": -0.02,
            "counterfactual_1d": 0.01,
        }
        mock_db.express.read.return_value = {"outcome_json": json.dumps(outcome)}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-007", horizons=[1])

        cf = result["counterfactuals"][0]
        assert cf["diff"] < 0
        assert abs(cf["diff"] - (-0.03)) < 1e-10

    @pytest.mark.asyncio
    async def test_counterfactual_unknown_horizon_returns_zero(self, mock_db):
        """A horizon not in {1, 5, 21} returns zero for both returns."""
        outcome = {
            "return_1d": 0.02,
            "counterfactual_1d": 0.01,
        }
        mock_db.express.read.return_value = {"outcome_json": json.dumps(outcome)}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-008", horizons=[10])

        cf = result["counterfactuals"][0]
        assert cf["horizon"] == 10
        assert cf["executed_return"] == 0.0
        assert cf["counterfactual_return"] == 0.0
        assert cf["diff"] == 0.0

    @pytest.mark.asyncio
    async def test_counterfactual_dict_outcome_json(self, mock_db):
        """outcome_json may already be a dict, not a JSON string."""
        outcome = {
            "return_1d": 0.015,
            "counterfactual_1d": 0.005,
        }
        mock_db.express.read.return_value = {"outcome_json": outcome}

        engine = CounterfactualEngine(mock_db)
        result = await engine.compute_counterfactual("decision-009", horizons=[1])

        cf = result["counterfactuals"][0]
        assert abs(cf["executed_return"] - 0.015) < 1e-10
        assert abs(cf["counterfactual_return"] - 0.005) < 1e-10


# ===========================================================================
# Edge Cases: cross-cutting scenarios
# ===========================================================================


class TestEdgeCases:
    """Edge-case scenarios across the attribution module."""

    def test_single_period_sharpe_is_nan(self):
        """One return observation: np.std(ddof=1) on 1 element is NaN."""
        returns = np.array([0.05])
        assert np.isnan(RiskMetrics.sharpe_ratio(returns))

    def test_single_period_volatility_is_nan(self):
        """One return observation: np.std(ddof=1) on 1 element is NaN."""
        returns = np.array([0.05])
        assert np.isnan(RiskMetrics.volatility(returns))

    def test_two_period_drawdown(self):
        """Minimum equity curve length for a drawdown is 2."""
        equity = np.array([100.0, 80.0])
        mdd = RiskMetrics.max_drawdown(equity)
        assert abs(mdd - 0.2) < 1e-10

    def test_zero_std_sharpe_returns_zero_not_nan(self):
        """Constant returns should return 0.0, not NaN."""
        returns = np.array([0.02, 0.02, 0.02])
        sharpe = RiskMetrics.sharpe_ratio(returns)
        assert sharpe == 0.0
        assert not np.isnan(sharpe)

    def test_large_portfolio_brinson(self):
        """Brinson works correctly with many categories."""
        n = 50
        rng = np.random.default_rng(42)
        w_p = rng.dirichlet(np.ones(n))
        w_b = rng.dirichlet(np.ones(n))
        r_p = rng.normal(0.01, 0.05, n)
        r_b = rng.normal(0.01, 0.05, n)

        bd = BrinsonDecomposition()
        result = bd.decompose(w_p, w_b, r_p, r_b)

        portfolio_return = float(np.dot(w_p, r_p))
        benchmark_return = float(np.dot(w_b, r_b))
        expected_active = portfolio_return - benchmark_return

        assert abs(result["total_active_return"] - expected_active) < 1e-8
        assert len(result["per_category"]) == n

    def test_all_zero_returns_metrics(self):
        """All zero returns produce stable metric values."""
        returns = np.zeros(20)

        assert RiskMetrics.sharpe_ratio(returns) == 0.0
        assert RiskMetrics.sortino_ratio(returns) == 0.0
        assert RiskMetrics.volatility(returns) == 0.0

        equity = np.ones(20)
        assert RiskMetrics.max_drawdown(equity) == 0.0

    def test_high_frequency_returns_annualize_correctly(self):
        """Verify annualization uses TRADING_DAYS_PER_YEAR = 252."""
        returns = np.array([0.001] * 100 + [-0.001] * 100)

        sharpe_ann = RiskMetrics.sharpe_ratio(returns, annualize=True)
        sharpe_raw = RiskMetrics.sharpe_ratio(returns, annualize=False)

        assert TRADING_DAYS_PER_YEAR == 252
        assert abs(sharpe_ann - sharpe_raw * np.sqrt(252)) < 1e-10

    def test_track_record_score_with_all_zero_metrics(self, scorer):
        """All-zero metrics still produce a valid score."""
        metrics = {
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "avg_return": 0.0,
        }
        score = scorer.compute_composite(metrics)
        # sharpe=0 -> score (0+2)/5 = 0.4
        # sortino=0 -> score (0+2)/6 = 0.333
        # max_dd=0 -> score 1.0
        # win_rate=0 -> score 0.0
        # avg_return=0 -> score (0+0.2)/0.5 = 0.4
        # Weighted: 0.25*0.4 + 0.15*0.333 + 0.20*1.0 + 0.20*0.0 + 0.20*0.4
        # = 0.1 + 0.05 + 0.2 + 0.0 + 0.08 = 0.43
        assert abs(score - 43.0) < 1.0  # allow rounding

    def test_negative_returns_drawdown_and_calmar(self):
        """Consistently negative returns produce positive drawdown, negative Calmar."""
        returns = np.array([-0.02, -0.03, -0.01, -0.04])
        equity = np.cumprod(1 + returns)

        mdd = RiskMetrics.max_drawdown(equity)
        assert mdd > 0

        calmar = RiskMetrics.calmar_ratio(returns)
        assert calmar < 0

    def test_brinson_with_zero_weights(self):
        """Category with zero weight in both portfolio and benchmark."""
        w_p = np.array([0.5, 0.5, 0.0])
        w_b = np.array([0.5, 0.5, 0.0])
        r_p = np.array([0.10, 0.04, 0.20])
        r_b = np.array([0.08, 0.02, 0.15])

        bd = BrinsonDecomposition()
        result = bd.decompose(w_p, w_b, r_p, r_b)

        # Category 2 has zero weight so contributes nothing
        cat2 = result["per_category"][2]
        assert abs(cat2["allocation"]) < 1e-10
        assert abs(cat2["selection"]) < 1e-10
        assert abs(cat2["interaction"]) < 1e-10
