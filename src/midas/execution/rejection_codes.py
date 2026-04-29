"""Rejection code taxonomy mapping IBKR codes to Midas classifications.

Covers all 8 spec-required categories plus unknown fallback per spec 14 S7.
Each RejectionCategory carries handling strategy, severity, and user-surfacing
requirements.

Ref: specs/14-ibkr-integration.md S7 (Rejection Code Taxonomy)
"""

from dataclasses import dataclass
from enum import Enum


class RejectionCategory(Enum):
    """Structured rejection classification per spec 14 S7.

    Each category defines how Midas responds to the rejection: whether to
    auto-retry, alert the user, or kill outstanding orders for the instrument.
    """

    RISK = "rejected.risk"
    CANCELLED_RISK = "cancelled.risk"
    MARGIN = "rejected.margin"
    HALTED = "rejected.halted"
    NO_DATA = "rejected.no_data"
    PRICE_BAND = "rejected.price_band"
    CONTRACT = "rejected.contract"
    INFO = "info"
    UNKNOWN = "unknown"

    @property
    def should_auto_retry(self) -> bool:
        """Whether the rejection is safe to auto-retry."""
        return self in {RejectionCategory.INFO, RejectionCategory.PRICE_BAND}

    @property
    def requires_user_alert(self) -> bool:
        """Whether the rejection must be surfaced to the user."""
        return self in {
            RejectionCategory.RISK,
            RejectionCategory.CANCELLED_RISK,
            RejectionCategory.MARGIN,
            RejectionCategory.HALTED,
            RejectionCategory.NO_DATA,
            RejectionCategory.CONTRACT,
        }

    @property
    def kills_outstanding(self) -> bool:
        """Whether to cancel all outstanding orders for the instrument."""
        return self == RejectionCategory.HALTED

    @property
    def severity(self) -> str:
        """Severity level for logging and alerting."""
        if self in {RejectionCategory.RISK, RejectionCategory.MARGIN}:
            return "critical"
        if self in {
            RejectionCategory.HALTED,
            RejectionCategory.NO_DATA,
            RejectionCategory.CONTRACT,
        }:
            return "high"
        if self in {
            RejectionCategory.CANCELLED_RISK,
            RejectionCategory.PRICE_BAND,
        }:
            return "medium"
        return "low"


@dataclass(frozen=True)
class RejectionCode:
    """A classified rejection with original IBKR code and description."""

    ibkr_code: int
    category: RejectionCategory
    description: str


# IBKR error code to category mapping per spec 14 S7.
_IBKR_CODE_MAP: dict[int, RejectionCategory] = {
    201: RejectionCategory.RISK,
    202: RejectionCategory.CANCELLED_RISK,
    399: RejectionCategory.INFO,
    404: RejectionCategory.CONTRACT,
    421: RejectionCategory.PRICE_BAND,
    502: RejectionCategory.NO_DATA,
    504: RejectionCategory.NO_DATA,
}

# Substring patterns in the message text that indicate specific categories.
_MESSAGE_PATTERNS: list[tuple[str, RejectionCategory]] = [
    ("halted", RejectionCategory.HALTED),
    ("halt", RejectionCategory.HALTED),
    ("auction", RejectionCategory.HALTED),
    ("insufficient margin", RejectionCategory.MARGIN),
    ("buying power", RejectionCategory.MARGIN),
    ("no market data", RejectionCategory.NO_DATA),
    ("market data permission", RejectionCategory.NO_DATA),
    ("price outside", RejectionCategory.PRICE_BAND),
    ("outside range", RejectionCategory.PRICE_BAND),
    ("unknown contract", RejectionCategory.CONTRACT),
    ("invalid contract", RejectionCategory.CONTRACT),
    ("security not found", RejectionCategory.CONTRACT),
    ("order rejected", RejectionCategory.RISK),
    ("risk", RejectionCategory.RISK),
]


def classify_rejection(ibkr_code: int, message: str) -> RejectionCode:
    """Classify an IBKR rejection into a Midas RejectionCode.

    Parameters
    ----------
    ibkr_code : int
        The numeric error code returned by IBKR.
    message : str
        The human-readable error message from IBKR.

    Returns
    -------
    RejectionCode
        Structured rejection with category and description.
    """
    # 1. Try exact code match first.
    category = _IBKR_CODE_MAP.get(ibkr_code)

    # 2. Fall back to message pattern matching.
    if category is None and message:
        lower = message.lower()
        for pattern, cat in _MESSAGE_PATTERNS:
            if pattern in lower:
                category = cat
                break

    # 3. Default to unknown.
    if category is None:
        category = RejectionCategory.UNKNOWN

    return RejectionCode(
        ibkr_code=ibkr_code,
        category=category,
        description=message,
    )
