"""Integration tests for BacktestEngine wiring into API routes.

Validates that BacktestRouter.get_results() and BacktestDetailRouter
endpoints delegate to BacktestEngine and return populated metrics.

Ref: F12, T14 — wiring + integration tests.
"""

from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from midas.backtest.engine import BacktestEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prices_df() -> pd.DataFrame:
    """10 days of prices for AAPL and MSFT."""
    dates = pd.date_range("2024-01-02", periods=10, freq="B")
    rows = []
    aapl_prices = [185.0, 186.5, 184.2, 187.0, 188.5, 189.0, 187.5, 190.0, 191.5, 192.0]
    msft_prices = [370.0, 372.5, 369.0, 374.0, 375.5, 377.0, 375.0, 378.5, 380.0, 381.0]
    for i, date in enumerate(dates):
        rows.append(
            {"ticker": "AAPL", "period_end": date.strftime("%Y-%m-%d"), "close": aapl_prices[i]}
        )
        rows.append(
            {"ticker": "MSFT", "period_end": date.strftime("%Y-%m-%d"), "close": msft_prices[i]}
        )
    return pd.DataFrame(rows)


def _make_decisions() -> list[dict]:
    """5 days of buy decisions."""
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    decisions = []
    for d in dates:
        decisions.append(
            {
                "decision_id": f"d-{d}",
                "instruments": "AAPL,MSFT",
                "confidence": 0.6,
                "action": "buy",
                "created_at_day": d,
            }
        )
    return decisions


# ---------------------------------------------------------------------------
# Test: BacktestRouter.get_results wiring
# ---------------------------------------------------------------------------


class TestBacktestRouterWiring:
    """Tests that BacktestRouter.get_results delegates to BacktestEngine."""

    @pytest.mark.asyncio
    async def test_get_results_returns_populated_metrics(self):
        """get_results returns real metrics from BacktestEngine, not empty {}."""
        from midas.api.routes import BacktestRouter

        router = BacktestRouter()

        mock_row = {"id": 1, "rationale": "test backtest"}
        mock_db = AsyncMock()
        mock_db.express.read = AsyncMock(return_value=mock_row)
        mock_db.express.list = AsyncMock(
            side_effect=lambda table, **kw: (
                _make_decisions()
                if table == "shadow_decisions"
                else [{"ticker": "AAPL", "period_end": "2024-01-02", "close": 185.0}]
            )
        )

        with patch("midas.api.routes._get_db", return_value=mock_db):
            result = await router.get_results("1")

        assert result["run_id"] == "1"
        assert result["status"] == "completed"
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        assert "cagr" in metrics
        assert "sharpe" in metrics
        assert "max_drawdown" in metrics
        assert "calmar" in metrics
        assert "volatility" in metrics
        assert "turnover" in metrics
        assert "win_rate" in metrics
        assert isinstance(result["equity_curve"], list)
        assert isinstance(result["daily_returns"], list)
        assert isinstance(result["regime_breakdown"], list)

    @pytest.mark.asyncio
    async def test_get_results_empty_db_returns_pending(self):
        """get_results returns pending when run_id not found."""
        from midas.api.routes import BacktestRouter

        router = BacktestRouter()
        mock_db = AsyncMock()
        mock_db.express.read = AsyncMock(return_value=None)

        with patch("midas.api.routes._get_db", return_value=mock_db):
            result = await router.get_results("999")

        assert result["status"] == "pending"
        assert result["metrics"] == {}


# ---------------------------------------------------------------------------
# Test: BacktestDetailRouter wiring
# ---------------------------------------------------------------------------


class TestBacktestDetailRouterWiring:
    """Tests that BacktestDetailRouter delegates to BacktestEngine."""

    @pytest.mark.asyncio
    async def test_scorecard_returns_headline_metrics(self):
        """get_scorecard returns headline metrics from BacktestEngine."""
        from midas.api.routes_extended import BacktestDetailRouter

        router = BacktestDetailRouter()
        mock_db = AsyncMock()
        mock_db.express.read = AsyncMock(return_value={"id": 1})
        mock_db.express.list = AsyncMock(
            side_effect=lambda table, **kw: (
                _make_decisions() if table == "shadow_decisions" else []
            )
        )

        with patch("midas.api.routes_extended._get_db", return_value=mock_db):
            result = await router.get_scorecard("1")

        assert result["run_id"] == "1"
        assert "cagr" in result
        assert "sharpe" in result

    @pytest.mark.asyncio
    async def test_regime_breakdown_returns_four_regimes(self):
        """get_regime_breakdown returns all four regime bands."""
        from midas.api.routes_extended import BacktestDetailRouter

        router = BacktestDetailRouter()
        mock_db = AsyncMock()
        mock_db.express.read = AsyncMock(return_value={"id": 1})
        mock_db.express.list = AsyncMock(
            side_effect=lambda table, **kw: (
                _make_decisions() if table == "shadow_decisions" else []
            )
        )

        with patch("midas.api.routes_extended._get_db", return_value=mock_db):
            result = await router.get_regime_breakdown("1")

        assert result["run_id"] == "1"
        regimes = result["regimes"]
        assert len(regimes) == 4
        names = {r["name"] for r in regimes}
        assert names == {"calm", "elevated", "urgent", "crisis"}


# ---------------------------------------------------------------------------
# Test: BacktestEngine produces consistent results with API shape
# ---------------------------------------------------------------------------


class TestBacktestEngineAPIConsistency:
    """Tests that BacktestEngine output matches API contract expectations."""

    def test_engine_output_shape_matches_get_results_contract(self):
        """Engine.compute() returns all fields expected by get_results."""
        prices = _make_prices_df()
        decisions = _make_decisions()
        engine = BacktestEngine(prices=prices, weights=decisions)
        result = engine.compute()

        # All required keys present
        assert "equity_curve" in result
        assert "daily_returns" in result
        assert "headline" in result
        assert "regime_breakdown" in result
        assert "sub_horizons" in result

        # Headline has all metric keys
        headline = result["headline"]
        for key in (
            "cagr",
            "sharpe",
            "calmar",
            "max_drawdown",
            "volatility",
            "turnover",
            "win_rate",
        ):
            assert key in headline, f"Missing headline metric: {key}"
            assert isinstance(headline[key], float), f"{key} should be float"

        # Regime breakdown has 4 entries with required fields
        assert len(result["regime_breakdown"]) == 4
        for regime in result["regime_breakdown"]:
            assert "name" in regime
            assert "return_pct" in regime
            assert "sharpe" in regime
            assert "time_pct" in regime

        # Sub-horizons has required keys
        sub = result["sub_horizons"]
        assert "monthly_positive_pct" in sub
        assert "quarterly_positive_pct" in sub
        assert "annual_positive_pct" in sub
