"""Regression: BacktestEngine metrics match RiskMetrics formulas.

Ensures BacktestEngine delegates to RiskMetrics for Sharpe, max_drawdown,
calmar, and volatility — no inline reimplementations that can silently drift.

Ref: R3 — regression test for formula consistency.
"""

import numpy as np
import pytest

from midas.attribution.metrics import RiskMetrics
from midas.backtest.engine import BacktestEngine


def _make_simple_scenario():
    """5-day scenario with known returns."""
    import pandas as pd

    prices = pd.DataFrame(
        [
            {"ticker": "X", "period_end": "2024-01-02", "close": 100.0},
            {"ticker": "X", "period_end": "2024-01-03", "close": 102.0},
            {"ticker": "X", "period_end": "2024-01-04", "close": 101.0},
            {"ticker": "X", "period_end": "2024-01-05", "close": 103.0},
            {"ticker": "X", "period_end": "2024-01-08", "close": 105.0},
        ]
    )
    decisions = [
        {
            "decision_id": "d1",
            "instruments": "X",
            "confidence": 0.8,
            "action": "buy",
            "created_at_day": "2024-01-02",
        },
        {
            "decision_id": "d2",
            "instruments": "X",
            "confidence": 0.8,
            "action": "buy",
            "created_at_day": "2024-01-03",
        },
        {
            "decision_id": "d3",
            "instruments": "X",
            "confidence": 0.8,
            "action": "buy",
            "created_at_day": "2024-01-04",
        },
        {
            "decision_id": "d4",
            "instruments": "X",
            "confidence": 0.8,
            "action": "buy",
            "created_at_day": "2024-01-05",
        },
        {
            "decision_id": "d5",
            "instruments": "X",
            "confidence": 0.8,
            "action": "buy",
            "created_at_day": "2024-01-08",
        },
    ]
    return prices, decisions


@pytest.mark.regression
def test_sharpe_matches_risk_metrics():
    """Engine Sharpe equals RiskMetrics.sharpe_ratio for the same returns."""
    prices, decisions = _make_simple_scenario()
    engine = BacktestEngine(prices=prices, weights=decisions)
    result = engine.compute()

    rets = np.array(result["daily_returns"])
    expected_sharpe = RiskMetrics.sharpe_ratio(rets, risk_free_rate=0.0, annualize=True)

    assert abs(result["headline"]["sharpe"] - float(expected_sharpe)) < 1e-10


@pytest.mark.regression
def test_max_drawdown_matches_risk_metrics():
    """Engine max_drawdown equals RiskMetrics.max_drawdown."""
    prices, decisions = _make_simple_scenario()
    engine = BacktestEngine(prices=prices, weights=decisions)
    result = engine.compute()

    rets = np.array(result["daily_returns"])
    equity = np.cumprod(1 + rets)
    expected_dd = RiskMetrics.max_drawdown(equity)

    assert abs(result["headline"]["max_drawdown"] - float(expected_dd)) < 1e-10


@pytest.mark.regression
def test_volatility_matches_risk_metrics():
    """Engine volatility equals RiskMetrics.volatility."""
    prices, decisions = _make_simple_scenario()
    engine = BacktestEngine(prices=prices, weights=decisions)
    result = engine.compute()

    rets = np.array(result["daily_returns"])
    expected_vol = RiskMetrics.volatility(rets, annualize=True)

    assert abs(result["headline"]["volatility"] - float(expected_vol)) < 1e-10


@pytest.mark.regression
def test_calmar_matches_risk_metrics():
    """Engine calmar equals RiskMetrics.calmar_ratio."""
    prices, decisions = _make_simple_scenario()
    engine = BacktestEngine(prices=prices, weights=decisions)
    result = engine.compute()

    rets = np.array(result["daily_returns"])
    expected_calmar = RiskMetrics.calmar_ratio(rets, annualize=True)

    assert abs(result["headline"]["calmar"] - float(expected_calmar)) < 1e-10
