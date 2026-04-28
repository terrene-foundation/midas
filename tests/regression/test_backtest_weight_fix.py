"""
Regression test: backtest position weight must reflect decision confidence.

Bug: _compute_returns_from_decisions uses hardcoded +0.1 / -0.1 for position
weights, ignoring the decision's confidence field (0.0-1.0).  A high-confidence
buy (confidence=0.9) gets the same weight as a low-confidence buy (confidence=0.2),
producing incorrect backtest returns.

Expected: the weight should come from d.get("confidence", 0.1) with a minimum
of 0.05 when confidence is 0.

Ref: src/midas/api/routes_extended.py lines 723-726

NOTE ON PRICE INDEXING: The method indexes into the price array using the
positional loop index i over sorted_days. When i=0, idx=0, so prev_p equals
curr_p and ret=0, making the first day's return always zero regardless of
weight. Tests use a "padding" decision on an earlier day to push i>=1 for
the days under comparison, ensuring both days produce non-zero returns that
reveal the confidence-weighting bug.
"""

from __future__ import annotations

from typing import Any

import pytest

from midas.api.routes_extended import BacktestDetailRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The bug uses hardcoded 0.1 for all weights.  After the fix, weights will
# vary with confidence.  The ratio between weights for confidence=0.9 and
# confidence=0.2 should be 0.9/0.2 = 4.5x.  With the bug it is 1.0x.
# We use a generous threshold (1.5x) to accommodate compounding effects
# while still clearly rejecting the 1.0x ratio from the hardcoded bug.
_CONFIDENCE_RATIO_THRESHOLD = 1.5


def _make_decision(
    *,
    day: str,
    action: str,
    instruments: str,
    confidence: float,
) -> dict[str, Any]:
    """Build a minimal shadow_decision dict understood by _compute_returns_from_decisions."""
    return {
        "created_at_day": day,
        "action": action,
        "instruments": instruments,
        "confidence": confidence,
    }


def _make_price(
    *,
    ticker: str,
    period_end: str,
    close: float,
) -> dict[str, Any]:
    """Build a minimal price record for the mock DB."""
    return {
        "ticker": ticker,
        "period_end": period_end,
        "close": close,
    }


class _FakeExpress:
    """Minimal fake of db.express with an async list() method."""

    def __init__(self, prices: list[dict[str, Any]]) -> None:
        self._prices = prices

    async def list(self, model: str) -> list[dict[str, Any]]:
        if model == "prices":
            return self._prices
        return []


class _FakeDB:
    """Minimal fake database object with .express attribute."""

    def __init__(self, prices: list[dict[str, Any]]) -> None:
        self.express = _FakeExpress(prices)


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestBacktestWeightUsesConfidence:
    """Position weight in backtest must vary with decision confidence.

    The current code hardcodes +0.1 for every buy regardless of confidence.
    These tests will FAIL until the fix lands.
    """

    async def test_high_confidence_buy_produces_larger_return_than_low(
        self,
    ) -> None:
        """A high-confidence buy (0.9) must produce a meaningfully larger
        daily return than a low-confidence buy (0.2).

        With the bug (hardcoded 0.1), both days produce approximately the
        same return (~0.01).  With the fix, the high-confidence day should
        produce a return at least 1.5x larger.

        A padding decision on an earlier day ensures the price-indexing
        logic (which uses the loop index i) lands on non-zero returns for
        both days under comparison.
        """
        router = BacktestDetailRouter()

        # Three decision days. Day 0 is padding so price indexing
        # gives non-zero returns for days 1 and 2.
        decisions = [
            _make_decision(
                day="2024-01-09",
                action="buy",
                instruments="AAPL",
                confidence=0.5,
            ),
            _make_decision(
                day="2024-01-10",
                action="buy",
                instruments="AAPL",
                confidence=0.2,
            ),
            _make_decision(
                day="2024-01-11",
                action="buy",
                instruments="AAPL",
                confidence=0.9,
            ),
        ]

        # Price history: consistent +10% move each period.
        # i=0 -> prices[0], ret=0 (padding, prev_p == curr_p at idx 0)
        # i=1 -> prices[1]=110, prev=100, ret=+10%
        # i=2 -> prices[2]=121, prev=110, ret=+10%
        prices = [
            _make_price(ticker="AAPL", period_end="2024-01-08", close=100.0),
            _make_price(ticker="AAPL", period_end="2024-01-09", close=110.0),
            _make_price(ticker="AAPL", period_end="2024-01-10", close=121.0),
            _make_price(ticker="AAPL", period_end="2024-01-11", close=133.1),
        ]

        db = _FakeDB(prices)
        returns = await router._compute_returns_from_decisions(db, decisions)

        assert len(returns) == 3, f"Expected 3 daily returns, got {len(returns)}"
        assert returns[1] > 0.0, f"Day 1 return should be positive, got {returns[1]}"
        assert returns[2] > 0.0, f"Day 2 return should be positive, got {returns[2]}"

        # With the bug: returns[2] / returns[1] ~= 1.0 (both use weight 0.1).
        # With the fix: returns[2] / returns[1] >= 0.9/0.2 = 4.5.
        # We check for >= 1.5 to tolerate compounding noise.
        ratio = returns[2] / returns[1]
        assert ratio >= _CONFIDENCE_RATIO_THRESHOLD, (
            f"High-confidence buy (0.9) should produce at least "
            f"{_CONFIDENCE_RATIO_THRESHOLD}x the return of low-confidence "
            f"buy (0.2), but ratio was {ratio:.3f} "
            f"(returns={returns}). This indicates position weight ignores "
            f"confidence and uses hardcoded 0.1."
        )

    async def test_zero_confidence_buy_uses_minimum_weight(self) -> None:
        """A buy with confidence=0 must still produce a non-zero position
        weight (minimum 0.05), ensuring the decision is not entirely ignored.

        Tests the minimum-weight floor: max(confidence, 0.05).
        The bug gives confidence=0 the same weight (0.1) as confidence=0.5,
        so the returns will be approximately equal.  With the fix,
        confidence=0.5 should produce a return at least 1.5x larger than
        the confidence=0 floor.
        """
        router = BacktestDetailRouter()

        decisions = [
            _make_decision(
                day="2024-01-09",
                action="buy",
                instruments="MSFT",
                confidence=0.5,
            ),
            _make_decision(
                day="2024-01-10",
                action="buy",
                instruments="MSFT",
                confidence=0.0,
            ),
            _make_decision(
                day="2024-01-11",
                action="buy",
                instruments="MSFT",
                confidence=0.5,
            ),
        ]

        prices = [
            _make_price(ticker="MSFT", period_end="2024-01-08", close=200.0),
            _make_price(ticker="MSFT", period_end="2024-01-09", close=220.0),
            _make_price(ticker="MSFT", period_end="2024-01-10", close=242.0),
            _make_price(ticker="MSFT", period_end="2024-01-11", close=266.2),
        ]

        db = _FakeDB(prices)
        returns = await router._compute_returns_from_decisions(db, decisions)

        assert len(returns) == 3, f"Expected 3 daily returns, got {len(returns)}"

        # Zero-confidence buy must produce a non-zero return (minimum floor).
        assert returns[1] > 0.0, (
            f"Zero-confidence buy should use minimum weight 0.05, producing "
            f"a non-zero return, but got returns[1]={returns[1]}"
        )

        # Confidence=0.5 should produce a meaningfully larger return than
        # the confidence=0 minimum floor.  With the bug they are equal.
        # With the fix: 0.5 / 0.05 = 10x ratio.  Check >= 1.5x.
        assert returns[2] > 0.0, f"Day 2 return should be positive, got {returns[2]}"
        ratio = returns[2] / returns[1]
        assert ratio >= _CONFIDENCE_RATIO_THRESHOLD, (
            f"Confidence=0.5 buy should produce at least "
            f"{_CONFIDENCE_RATIO_THRESHOLD}x the return of confidence=0 "
            f"buy (floor 0.05), but ratio was {ratio:.3f} "
            f"(returns={returns}). Position weight likely ignores "
            f"confidence and uses hardcoded 0.1."
        )

    async def test_sell_weight_also_uses_confidence(self) -> None:
        """A high-confidence sell (0.8) must produce a larger short-position
        impact (more negative return contribution) than a low-confidence
        sell (0.1) when prices are rising.

        With the bug, both sells get weight -0.1, producing approximately
        equal negative returns.  With the fix, the high-confidence sell
        should produce a meaningfully larger magnitude.
        """
        router = BacktestDetailRouter()

        decisions = [
            _make_decision(
                day="2024-01-09",
                action="sell",
                instruments="GOOG",
                confidence=0.5,
            ),
            _make_decision(
                day="2024-01-10",
                action="sell",
                instruments="GOOG",
                confidence=0.1,
            ),
            _make_decision(
                day="2024-01-11",
                action="sell",
                instruments="GOOG",
                confidence=0.8,
            ),
        ]

        prices = [
            _make_price(ticker="GOOG", period_end="2024-01-08", close=100.0),
            _make_price(ticker="GOOG", period_end="2024-01-09", close=110.0),
            _make_price(ticker="GOOG", period_end="2024-01-10", close=121.0),
            _make_price(ticker="GOOG", period_end="2024-01-11", close=133.1),
        ]

        db = _FakeDB(prices)
        returns = await router._compute_returns_from_decisions(db, decisions)

        assert len(returns) == 3, f"Expected 3 daily returns, got {len(returns)}"
        # Both returns should be negative (negative weight * rising prices).
        assert returns[1] < 0.0, (
            f"Low-confidence sell into rising prices should be negative, " f"got {returns[1]}"
        )
        assert returns[2] < 0.0, (
            f"High-confidence sell into rising prices should be negative, " f"got {returns[2]}"
        )

        # Compare absolute magnitudes.  With the bug, both are ~equal.
        # With the fix, |returns[2]| / |returns[1]| >= 0.8/0.1 = 8x.
        # Check >= 1.5x to tolerate compounding.
        ratio = abs(returns[2]) / abs(returns[1])
        assert ratio >= _CONFIDENCE_RATIO_THRESHOLD, (
            f"High-confidence sell (0.8) should produce at least "
            f"{_CONFIDENCE_RATIO_THRESHOLD}x the magnitude of "
            f"low-confidence sell (0.1), but ratio was {ratio:.3f} "
            f"(returns={returns}). Position weight likely ignores "
            f"confidence and uses hardcoded 0.1."
        )

    async def test_different_confidences_produce_different_returns(self) -> None:
        """Two buys with very different confidence (0.15 vs 0.75) must NOT
        produce approximately equal returns.

        With the bug, both get weight=0.1 and returns are approximately
        equal (within floating-point noise).  With the fix, the ratio
        should be approximately 0.75/0.15 = 5x.
        """
        router = BacktestDetailRouter()

        decisions = [
            _make_decision(
                day="2024-01-31",
                action="buy",
                instruments="TSLA",
                confidence=0.5,
            ),
            _make_decision(
                day="2024-02-01",
                action="buy",
                instruments="TSLA",
                confidence=0.15,
            ),
            _make_decision(
                day="2024-02-02",
                action="buy",
                instruments="TSLA",
                confidence=0.75,
            ),
        ]

        prices = [
            _make_price(ticker="TSLA", period_end="2024-01-30", close=100.0),
            _make_price(ticker="TSLA", period_end="2024-01-31", close=110.0),
            _make_price(ticker="TSLA", period_end="2024-02-01", close=121.0),
            _make_price(ticker="TSLA", period_end="2024-02-02", close=133.1),
        ]

        db = _FakeDB(prices)
        returns = await router._compute_returns_from_decisions(db, decisions)

        assert len(returns) == 3
        assert (
            returns[1] > 0.0 and returns[2] > 0.0
        ), f"Both comparison days should have positive returns, got {returns}"

        ratio = returns[2] / returns[1]
        assert ratio >= _CONFIDENCE_RATIO_THRESHOLD, (
            f"Confidence 0.75 should produce at least "
            f"{_CONFIDENCE_RATIO_THRESHOLD}x the return of confidence 0.15, "
            f"but ratio was {ratio:.3f} (returns={returns}). "
            f"Position weight is hardcoded at 0.1 ignoring confidence."
        )
