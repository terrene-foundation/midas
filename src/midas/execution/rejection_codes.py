"""Rejection code taxonomy mapping IBKR codes to Midas classifications.

Maps Interactive Brokers API error codes to a structured classification
so the decision brief can explain rejections in domain terms rather
than raw broker codes.

Ref: specs/14-ibkr-integration.md S7 (Rejection Taxonomy)
"""

from dataclasses import dataclass
from enum import Enum


class RejectionCategory(Enum):
    """Structured rejection classification."""

    INSUFFICIENT_MARGIN = "insufficient_margin"
    ORDER_LIMIT_EXCEEDED = "order_limit_exceeded"
    MARKET_DATA_MISSING = "market_data_missing"
    INSTRUMENT_HALTED = "instrument_halted"
    INVALID_ORDER = "invalid_order"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RejectionCode:
    """A classified rejection with original IBKR code and description."""

    ibkr_code: int
    category: RejectionCategory
    description: str


# IBKR error code to category mapping.
_IBKR_CODE_MAP: dict[int, RejectionCategory] = {
    201: RejectionCategory.INSUFFICIENT_MARGIN,
    202: RejectionCategory.ORDER_LIMIT_EXCEEDED,
    399: RejectionCategory.INVALID_ORDER,
}

# Substring patterns in the message text that indicate specific categories.
_MESSAGE_PATTERNS: list[tuple[str, RejectionCategory]] = [
    ("halted", RejectionCategory.INSTRUMENT_HALTED),
    ("halt", RejectionCategory.INSTRUMENT_HALTED),
    ("auction", RejectionCategory.INSTRUMENT_HALTED),
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
