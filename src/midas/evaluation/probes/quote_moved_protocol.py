"""
Quote-Moved-Since-Brief Protocol.

T-00-18: At biometric confirmation, a fresh quote is pulled. If the mid price has
moved by more than the regime-adaptive threshold since the brief was composed, the
approval does NOT auto-execute. The UI surfaces a modal asking the user to proceed,
set a limit, or cancel.

Ref: specs/10-moments-of-truth.md §6.4
Ref: specs/14-ibkr-integration.md §8.2
Ref: T-00-18
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Regime and threshold
# ---------------------------------------------------------------------------


class RegimeBand(Enum):
    CALM = auto()
    ELEVATED = auto()
    URGENT = auto()


# Regime-adaptive thresholds (fraction of mid price)
QUOTE_MOVE_THRESHOLDS = {
    RegimeBand.CALM: 0.005,  # 0.5%
    RegimeBand.ELEVATED: 0.003,  # 0.3%
    RegimeBand.URGENT: 0.002,  # 0.2%
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class QuoteMovedCheckResult:
    """Result of checking whether the quote has moved beyond the threshold."""

    instrument: str
    regime_band: RegimeBand
    threshold: float  # the applicable threshold fraction
    brief_mid_price: float
    current_mid_price: float
    price_move_fraction: float  # absolute fraction moved
    threshold_exceeded: bool
    auto_execute_permitted: bool  # False when threshold exceeded
    message: str


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class QuoteMovedProtocol:
    """Evaluates whether a fresh quote has moved beyond the regime-adaptive threshold.

    Every approval screen carries the quote snapshot from brief-composition time.
    At biometric confirmation:
      1. A fresh quote is pulled (exec.freshness_at_execution rule).
      2. The mid price is compared to the brief snapshot.
      3. If the absolute move exceeds the regime-adaptive threshold, the approval
         does NOT auto-execute — the UI surfaces a modal.
      4. The user must explicitly confirm: proceed at current price, set a limit,
         or cancel.

    Thresholds:
      - CALM:     0.5% (most tolerant — routine decisions)
      - ELEVATED: 0.3% (moderate — elevated regime)
      - URGENT:   0.2% (least tolerant — time-sensitive decisions)
    """

    def __init__(self, thresholds: dict[RegimeBand, float] | None = None) -> None:
        self.thresholds = thresholds or QUOTE_MOVE_THRESHOLDS

    def threshold_for(self, regime: RegimeBand) -> float:
        return self.thresholds.get(regime, QUOTE_MOVE_THRESHOLDS[regime])

    def check(
        self,
        instrument: str,
        regime_band: RegimeBand,
        brief_mid_price: float,
        current_mid_price: float,
    ) -> QuoteMovedCheckResult:
        """Check whether the price move exceeds the regime-adaptive threshold.

        Args:
            instrument: Ticker symbol.
            regime_band: Current regime band (CALM / ELEVATED / URGENT).
            brief_mid_price: Mid price at brief-composition time.
            current_mid_price: Mid price at biometric-confirmation time.

        Returns QuoteMovedCheckResult with pass/fail for auto-execute gate.
        """
        if brief_mid_price <= 0 or current_mid_price <= 0:
            raise ValueError("Prices must be positive")

        threshold = self.threshold_for(regime_band)
        price_move_fraction = abs((current_mid_price - brief_mid_price) / brief_mid_price)
        exceeded = price_move_fraction > threshold
        # Auto-execute is ONLY permitted when move is within threshold
        auto_execute_permitted = not exceeded

        if exceeded:
            pct = price_move_fraction * 100
            thr_pct = threshold * 100
            message = (
                f"Price moved {pct:.2f}% (threshold: {thr_pct:.1f}% for {regime_band.name}). "
                f"Approval requires explicit user re-confirm."
            )
        else:
            message = (
                f"Price move {price_move_fraction*100:.3f}% within "
                f"{threshold*100:.1f}% threshold for {regime_band.name}. "
                f"Auto-execute permitted."
            )

        return QuoteMovedCheckResult(
            instrument=instrument,
            regime_band=regime_band,
            threshold=threshold,
            brief_mid_price=brief_mid_price,
            current_mid_price=current_mid_price,
            price_move_fraction=price_move_fraction,
            threshold_exceeded=exceeded,
            auto_execute_permitted=auto_execute_permitted,
            message=message,
        )

    def check_and_raise(
        self,
        instrument: str,
        regime_band: RegimeBand,
        brief_mid_price: float,
        current_mid_price: float,
    ) -> QuoteMovedCheckResult:
        """Check and raise if auto-execute is not permitted."""
        result = self.check(instrument, regime_band, brief_mid_price, current_mid_price)
        if not result.auto_execute_permitted:
            raise QuoteMovedError(result.message, result)
        return result


class QuoteMovedError(Exception):
    """Raised when the price move exceeds the threshold and auto-execute is blocked."""

    def __init__(self, message: str, result: QuoteMovedCheckResult) -> None:
        super().__init__(message)
        self.result = result
