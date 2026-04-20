"""Rejection code taxonomy mapping IBKR codes to Midas classifications.

Maps Interactive Brokers API error codes to a structured classification
so the decision brief can explain rejections in domain terms rather
than raw broker codes.

Covers all 8 spec-required categories per specs/14 S7.

Ref: specs/14-ibkr-integration.md S7 (Rejection Taxonomy)
"""

from dataclasses import dataclass
from enum import Enum


class RejectionCategory(Enum):
    """Structured rejection classification per spec 14 S7."""

    INSUFFICIENT_MARGIN = "rejected.margin"
    ORDER_LIMIT_EXCEEDED = "rejected.risk"
    MARKET_DATA_MISSING = "rejected.no_data"
    INSTRUMENT_HALTED = "rejected.halted"
    INVALID_ORDER = "rejected.invalid"
    PRICE_BAND = "rejected.price_band"
    UNKNOWN_CONTRACT = "rejected.contract"
    DUPLICATE_ORDER = "rejected.duplicate"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RejectionCode:
    """A classified rejection with original IBKR code and description."""

    ibkr_code: int
    category: RejectionCategory
    description: str


# IBKR error code to category mapping per spec 14 S7.
_IBKR_CODE_MAP: dict[int, RejectionCategory] = {
    201: RejectionCategory.INSUFFICIENT_MARGIN,
    202: RejectionCategory.ORDER_LIMIT_EXCEEDED,
    399: RejectionCategory.INVALID_ORDER,
    404: RejectionCategory.UNKNOWN_CONTRACT,
    421: RejectionCategory.PRICE_BAND,
    502: RejectionCategory.MARKET_DATA_MISSING,
    504: RejectionCategory.MARKET_DATA_MISSING,
    1100: RejectionCategory.DUPLICATE_ORDER,
}

# Substring patterns in the message text that indicate specific categories.
_MESSAGE_PATTERNS: list[tuple[str, RejectionCategory]] = [
    ("halted", RejectionCategory.INSTRUMENT_HALTED),
    ("halt", RejectionCategory.INSTRUMENT_HALTED),
    ("auction", RejectionCategory.INSTRUMENT_HALTED),
    ("insufficient margin", RejectionCategory.INSUFFICIENT_MARGIN),
    ("buying power", RejectionCategory.INSUFFICIENT_MARGIN),
    ("no market data", RejectionCategory.MARKET_DATA_MISSING),
    ("market data permission", RejectionCategory.MARKET_DATA_MISSING),
    ("price outside", RejectionCategory.PRICE_BAND),
    ("outside range", RejectionCategory.PRICE_BAND),
    ("unknown contract", RejectionCategory.UNKNOWN_CONTRACT),
    ("invalid contract", RejectionCategory.UNKNOWN_CONTRACT),
    ("security not found", RejectionCategory.UNKNOWN_CONTRACT),
    ("duplicate order", RejectionCategory.DUPLICATE_ORDER),
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
