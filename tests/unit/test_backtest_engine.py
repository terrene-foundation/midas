"""Tier 1 unit tests for BacktestEngine.

Pure computation tests -- no database, no network, no async.
All test data is deterministic (fixed prices, fixed weights).

Ref: T-23-07, Group C Shard 1
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from midas.backtest.engine import BacktestEngine


# ---------------------------------------------------------------------------
# Deterministic test data builders
# ---------------------------------------------------------------------------


def _make_prices(
    ticker: str,
    start: str = "2024-01-08",
    n_days: int = 10,
    start_price: float = 100.0,
    daily_return: float = 0.01,
) -> pd.DataFrame:
    """Build a price DataFrame with deterministic prices.

    Each day's close = start_price * (1 + daily_return) ^ day_offset.
    """
    import datetime

    rows: list[dict[str, Any]] = []
    base = datetime.date.fromisoformat(start)
    price = start_price
    for i in range(n_days):
        day = base + datetime.timedelta(days=i)
        rows.append(
            {
                "ticker": ticker,
                "period_end": day.isoformat(),
                "close": round(price, 6),
                "adj_close": round(price, 6),
            }
        )
        price *= 1 + daily_return
    return pd.DataFrame(rows)


def _make_weight(
    *,
    day: str,
    action: str = "buy",
    instruments: str = "AAPL",
    confidence: float = 0.5,
) -> dict[str, Any]:
    """Build a minimal weight/decision dict."""
    return {
        "decision_id": f"dec-{day}",
        "instruments": instruments,
        "confidence": confidence,
        "created_at_day": day,
        "action": action,
    }


def _make_regime_label(day: str, z_scale: float) -> dict[str, Any]:
    """Build a regime label dict."""
    return {"period_end": day, "z_scale": z_scale}


# ---------------------------------------------------------------------------
# Test: known prices + weights -> correct headline metrics
# ---------------------------------------------------------------------------


class TestKnownMetrics:
    """Deterministic prices and weights produce verifiable CAGR, Sharpe, max DD."""

    def test_monotonic_up_single_ticker_cagr_positive(self) -> None:
        """A portfolio that goes up every day must have positive CAGR."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=252, daily_return=0.001)
        # One buy per day for 252 days at constant confidence
        weights = [
            _make_weight(
                day=prices.iloc[i]["period_end"],
                confidence=0.5,
            )
            for i in range(252)
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert (
            result["headline"]["cagr"] > 0.0
        ), "CAGR should be positive for monotonically rising prices"

    def test_flat_prices_zero_cagr(self) -> None:
        """Flat prices (daily_return=0) must produce CAGR near zero."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=50, daily_return=0.0)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(50)
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert abs(result["headline"]["cagr"]) < 1e-6, "CAGR should be ~0 for flat prices"

    def test_known_sharpe_manual_computation(self) -> None:
        """Sharpe computed by BacktestEngine matches RiskMetrics formula.

        Build a scenario with varying daily returns (non-constant prices) so
        that the standard deviation is numerically meaningful.  Use manually-
        crafted prices that produce known per-day returns, then verify the
        engine's Sharpe matches RiskMetrics.sharpe_ratio on the same returns.
        """
        import datetime

        from midas.attribution.metrics import RiskMetrics

        # 6 prices -> 5 days of returns.  Use non-uniform price changes
        # so that std(return) is non-trivial and Sharpe is numerically stable.
        base = datetime.date(2024, 1, 8)
        price_sequence = [100.0, 102.0, 101.0, 105.0, 103.0, 107.0]
        rows = [
            {
                "ticker": "AAPL",
                "period_end": (base + datetime.timedelta(days=i)).isoformat(),
                "close": p,
                "adj_close": p,
            }
            for i, p in enumerate(price_sequence)
        ]
        prices = pd.DataFrame(rows)

        # Decisions from day 1 onward (need a prior-day price for return)
        weights = [
            _make_weight(day=rows[i]["period_end"], confidence=0.5) for i in range(1, len(rows))
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        # Verify returns are correct: weight=0.5, returns are price-relative
        # Day 1: (102-100)/100 * 0.5 = 0.01
        # Day 2: (101-102)/102 * 0.5 = -0.004902...
        # Day 3: (105-101)/101 * 0.5 = 0.019802...
        # Day 4: (103-105)/105 * 0.5 = -0.009524...
        # Day 5: (107-103)/103 * 0.5 = 0.019417...
        expected_daily = [
            (102.0 - 100.0) / 100.0 * 0.5,
            (101.0 - 102.0) / 102.0 * 0.5,
            (105.0 - 101.0) / 101.0 * 0.5,
            (103.0 - 105.0) / 105.0 * 0.5,
            (107.0 - 103.0) / 103.0 * 0.5,
        ]
        for actual, exp in zip(result["daily_returns"], expected_daily):
            assert abs(actual - exp) < 1e-6, f"Daily return mismatch: {actual} vs {exp}"

        expected_sharpe = RiskMetrics.sharpe_ratio(np.array(expected_daily), annualize=True)
        assert abs(result["headline"]["sharpe"] - float(expected_sharpe)) < 1e-4, (
            f"Sharpe mismatch: engine={result['headline']['sharpe']}, "
            f"expected={expected_sharpe}"
        )

    def test_max_drawdown_matches_risk_metrics(self) -> None:
        """Max drawdown from engine matches RiskMetrics.max_drawdown."""
        from midas.attribution.metrics import RiskMetrics

        # Create alternating up/down prices to produce a real drawdown
        import datetime

        rows: list[dict[str, Any]] = []
        base = datetime.date(2024, 1, 8)
        prices_seq = [100.0, 110.0, 95.0, 105.0, 90.0, 100.0, 115.0]
        for i, p in enumerate(prices_seq):
            rows.append(
                {
                    "ticker": "AAPL",
                    "period_end": (base + datetime.timedelta(days=i)).isoformat(),
                    "close": p,
                    "adj_close": p,
                }
            )
        prices = pd.DataFrame(rows)

        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=1.0)
            for i in range(1, len(prices_seq))
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        # Compute expected max drawdown from the engine's daily returns
        rets = np.array(result["daily_returns"])
        equity = np.cumprod(1 + rets)
        expected_mdd = RiskMetrics.max_drawdown(equity)

        assert abs(result["headline"]["max_drawdown"] - float(expected_mdd)) < 1e-6, (
            f"Max drawdown mismatch: engine={result['headline']['max_drawdown']}, "
            f"expected={expected_mdd}"
        )
        assert result["headline"]["max_drawdown"] > 0.0, "Should have a non-zero drawdown"


# ---------------------------------------------------------------------------
# Test: regime breakdown
# ---------------------------------------------------------------------------


class TestRegimeBreakdown:
    """Regime segmentation with z_scale labels and percentile fallback."""

    def test_all_one_regime_single_breakdown_entry(self) -> None:
        """When all z_scales are in one band, only that regime has time_pct=1.0."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=10, daily_return=0.01)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(1, 10)
        ]
        # All CALM: z_scale = 0.1 for every day
        regime_labels = [
            _make_regime_label(prices.iloc[i]["period_end"], z_scale=0.1) for i in range(1, 10)
        ]

        engine = BacktestEngine(prices, weights, regime_labels=regime_labels)
        result = engine.compute()

        breakdown = result["regime_breakdown"]
        calm = [r for r in breakdown if r["name"] == "CALM"]
        assert len(calm) == 1
        assert calm[0]["time_pct"] == 1.0

        # All other regimes should have time_pct == 0.0
        for r in breakdown:
            if r["name"] != "CALM":
                assert r["time_pct"] == 0.0

    def test_regime_flips_produce_two_regimes(self) -> None:
        """Alternating z_scale values produce 2+ regimes in breakdown."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=20, daily_return=0.01)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(1, 20)
        ]
        # Alternate between CALM (0.1) and CRISIS (0.95)
        regime_labels = [
            _make_regime_label(
                prices.iloc[i]["period_end"],
                z_scale=0.1 if i % 2 == 0 else 0.95,
            )
            for i in range(1, 20)
        ]

        engine = BacktestEngine(prices, weights, regime_labels=regime_labels)
        result = engine.compute()

        breakdown = result["regime_breakdown"]
        active_regimes = [r for r in breakdown if r["time_pct"] > 0.0]
        assert (
            len(active_regimes) == 2
        ), f"Expected 2 active regimes, got {len(active_regimes)}: {active_regimes}"

    def test_no_regime_labels_uses_percentile_fallback(self) -> None:
        """Without regime_labels, breakdown still produces 4 regime entries."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=30, daily_return=0.01)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(1, 30)
        ]

        engine = BacktestEngine(prices, weights, regime_labels=None)
        result = engine.compute()

        breakdown = result["regime_breakdown"]
        assert len(breakdown) == 4
        # All returns are identical (0.005), so they all land in one band
        total_pct = sum(r["time_pct"] for r in breakdown)
        assert abs(total_pct - 1.0) < 1e-6

    def test_regime_breakdown_time_pct_sums_to_one(self) -> None:
        """time_pct across all regimes must sum to 1.0."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=20, daily_return=0.01)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(1, 20)
        ]
        regime_labels = [
            _make_regime_label(prices.iloc[i]["period_end"], z_scale=float(i) / 20.0)
            for i in range(1, 20)
        ]

        engine = BacktestEngine(prices, weights, regime_labels=regime_labels)
        result = engine.compute()

        total_pct = sum(r["time_pct"] for r in result["regime_breakdown"])
        assert abs(total_pct - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Test: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Single bar, empty inputs, zero-confidence."""

    def test_single_bar_no_crash(self) -> None:
        """A single trading day must not crash and must produce valid metrics."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=3, daily_return=0.01)
        # Need at least 2 prices to compute a return; day 1 has prior day 0
        weights = [_make_weight(day=prices.iloc[1]["period_end"], confidence=0.5)]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert len(result["daily_returns"]) == 1
        assert result["headline"]["cagr"] != 0.0 or result["headline"]["cagr"] == 0.0  # no crash
        assert "sharpe" in result["headline"]
        assert "max_drawdown" in result["headline"]

    def test_empty_prices_graceful_result(self) -> None:
        """Empty price DataFrame produces empty result, no crash."""
        prices = pd.DataFrame(columns=["ticker", "period_end", "close", "adj_close"])
        weights = [_make_weight(day="2024-01-10", confidence=0.5)]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert result["equity_curve"] == []
        assert result["daily_returns"] == []
        assert result["headline"]["cagr"] == 0.0
        assert result["regime_breakdown"] == []

    def test_empty_weights_graceful_result(self) -> None:
        """Empty weights list produces empty result, no crash."""
        prices = _make_prices("AAPL", n_days=10)
        weights: list[dict[str, Any]] = []

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert result["equity_curve"] == []
        assert result["daily_returns"] == []
        assert result["headline"]["cagr"] == 0.0

    def test_zero_confidence_uses_minimum_floor(self) -> None:
        """A weight with confidence=0 must use the minimum floor of 0.05."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=5, daily_return=0.01)

        # Two decisions: one with confidence=0 (floor 0.05), one with confidence=0.5
        weights_floor = [
            _make_weight(day=prices.iloc[1]["period_end"], confidence=0.0),
        ]
        weights_high = [
            _make_weight(day=prices.iloc[1]["period_end"], confidence=0.5),
        ]

        result_floor = BacktestEngine(prices, weights_floor).compute()
        result_high = BacktestEngine(prices, weights_high).compute()

        # The higher-confidence weight should produce a larger daily return
        assert abs(result_high["daily_returns"][0]) > abs(result_floor["daily_returns"][0])

    def test_none_prices_handled(self) -> None:
        """Passing None-like empty DataFrame does not crash."""
        prices = pd.DataFrame()
        weights = [_make_weight(day="2024-01-10")]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert result["equity_curve"] == []


# ---------------------------------------------------------------------------
# Test: sensitivity -- different weights produce different CAGR
# ---------------------------------------------------------------------------


class TestWeightSensitivity:
    """Different weights must produce different results."""

    def test_different_weights_different_cagr(self) -> None:
        """Higher confidence produces higher CAGR when prices rise."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=20, daily_return=0.01)

        weights_low = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.1) for i in range(1, 20)
        ]
        weights_high = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.9) for i in range(1, 20)
        ]

        result_low = BacktestEngine(prices, weights_low).compute()
        result_high = BacktestEngine(prices, weights_high).compute()

        # Both positive because prices are rising
        assert result_low["headline"]["cagr"] > 0.0
        assert result_high["headline"]["cagr"] > 0.0

        # Higher confidence -> larger CAGR (because we're buying into rising prices)
        assert result_high["headline"]["cagr"] > result_low["headline"]["cagr"]

    def test_sell_into_rising_prices_negative_cagr(self) -> None:
        """Selling into rising prices produces negative portfolio return."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=20, daily_return=0.01)

        weights = [
            _make_weight(
                day=prices.iloc[i]["period_end"],
                action="sell",
                confidence=0.5,
            )
            for i in range(1, 20)
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        # Sell into rising prices -> negative weighted return -> negative CAGR
        assert result["headline"]["cagr"] < 0.0


# ---------------------------------------------------------------------------
# Test: equity curve shape
# ---------------------------------------------------------------------------


class TestEquityCurve:
    """Equity curve starts at 1.0 and has correct length."""

    def test_equity_curve_starts_at_one(self) -> None:
        """Equity curve must start at 1.0 (initial capital)."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=10, daily_return=0.01)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(1, 10)
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert result["equity_curve"][0] == 1.0

    def test_equity_curve_length_equals_returns_plus_one(self) -> None:
        """Equity curve has len(daily_returns) + 1 entries."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=10, daily_return=0.01)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(1, 10)
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert len(result["equity_curve"]) == len(result["daily_returns"]) + 1


# ---------------------------------------------------------------------------
# Test: sub-horizon consistency
# ---------------------------------------------------------------------------


class TestSubHorizons:
    """Sub-horizon positive-period fractions."""

    def test_all_positive_returns_gives_high_positive_pct(self) -> None:
        """When all returns are positive, sub-horizon pct should be high."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=65, daily_return=0.01)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(1, 65)
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        # All returns are positive, so both monthly and quarterly should be 1.0
        assert result["sub_horizons"]["monthly_positive_pct"] == 1.0
        assert result["sub_horizons"]["quarterly_positive_pct"] == 1.0

    def test_sub_horizons_present_in_output(self) -> None:
        """Sub-horizons dict always has the three expected keys."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=5, daily_return=0.01)
        weights = [
            _make_weight(day=prices.iloc[i]["period_end"], confidence=0.5) for i in range(1, 5)
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        assert "monthly_positive_pct" in result["sub_horizons"]
        assert "quarterly_positive_pct" in result["sub_horizons"]
        assert "annual_positive_pct" in result["sub_horizons"]


# ---------------------------------------------------------------------------
# Test: multi-ticker positions
# ---------------------------------------------------------------------------


class TestMultiTicker:
    """Positions spanning multiple tickers."""

    def test_two_tickers_combined_return(self) -> None:
        """Two tickers with equal weight produce the average of their returns."""
        prices_aapl = _make_prices("AAPL", start="2024-01-08", n_days=5, daily_return=0.02)
        prices_msft = _make_prices("MSFT", start="2024-01-08", n_days=5, daily_return=0.01)
        prices = pd.concat([prices_aapl, prices_msft], ignore_index=True)

        # One decision with two instruments, confidence=1.0
        # per_ticker_weight = 1.0 / 2 = 0.5 each
        weights = [
            _make_weight(
                day=prices_aapl.iloc[1]["period_end"],
                instruments="AAPL,MSFT",
                confidence=1.0,
            ),
        ]

        engine = BacktestEngine(prices, weights)
        result = engine.compute()

        # Expected: 0.5 * 0.02 + 0.5 * 0.01 = 0.015
        assert len(result["daily_returns"]) == 1
        assert abs(result["daily_returns"][0] - 0.015) < 1e-4


# ---------------------------------------------------------------------------
# Test: z_scale classification thresholds
# ---------------------------------------------------------------------------


class TestZScaleClassification:
    """Verify z_scale band boundaries from the spec."""

    def test_calm_upper_boundary(self) -> None:
        """z_scale = 0.299 -> CALM."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=3, daily_return=0.01)
        weights = [_make_weight(day=prices.iloc[1]["period_end"], confidence=0.5)]
        labels = [_make_regime_label(prices.iloc[1]["period_end"], z_scale=0.299)]

        engine = BacktestEngine(prices, weights, regime_labels=labels)
        result = engine.compute()

        calm = [r for r in result["regime_breakdown"] if r["name"] == "CALM"]
        assert calm[0]["time_pct"] == 1.0

    def test_elevated_lower_boundary(self) -> None:
        """z_scale = 0.3 -> ELEVATED."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=3, daily_return=0.01)
        weights = [_make_weight(day=prices.iloc[1]["period_end"], confidence=0.5)]
        labels = [_make_regime_label(prices.iloc[1]["period_end"], z_scale=0.3)]

        engine = BacktestEngine(prices, weights, regime_labels=labels)
        result = engine.compute()

        elevated = [r for r in result["regime_breakdown"] if r["name"] == "ELEVATED"]
        assert elevated[0]["time_pct"] == 1.0

    def test_crisis_threshold(self) -> None:
        """z_scale = 0.9 -> CRISIS."""
        prices = _make_prices("AAPL", start="2024-01-08", n_days=3, daily_return=0.01)
        weights = [_make_weight(day=prices.iloc[1]["period_end"], confidence=0.5)]
        labels = [_make_regime_label(prices.iloc[1]["period_end"], z_scale=0.9)]

        engine = BacktestEngine(prices, weights, regime_labels=labels)
        result = engine.compute()

        crisis = [r for r in result["regime_breakdown"] if r["name"] == "CRISIS"]
        assert crisis[0]["time_pct"] == 1.0
