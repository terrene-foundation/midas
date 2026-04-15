"""
Universe review scheduler.

Monthly ETF review, quarterly full re-evaluation, quarterly S&P 1500
rebalance window scan.

Ref: specs/03-universe-and-data.md §1.3
Ref: T-02-06
"""

from dataclasses import dataclass
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ReviewSchedule:
    next_etf_review: str  # ISO date
    next_full_reeval: str  # ISO date
    next_sp1500_scan: str  # ISO date


def compute_next_review_dates() -> ReviewSchedule:
    """Compute next review dates based on current date.

    - ETF monthly review: first Monday of each month
    - Quarterly full re-eval: first Monday of Jan/Apr/Jul/Oct
    - S&P 1500 quarterly scan: aligned with index rebalance windows (Mar/Jun/Sep/Dec)
    """
    now = datetime.now()

    # Monthly ETF review — first Monday of next month
    year = now.year
    month = now.month + 1
    if month > 12:
        month = 1
        year += 1
    next_etf_review = _first_monday(year, month)

    # Quarterly full re-eval — first Monday of Q1 start month
    quarter_start_month = ((now.month - 1) // 3 + 1) * 3 + 1
    if quarter_start_month > 12:
        quarter_start_month = 1
        year += 1
    next_full_reeval = _first_monday(year, quarter_start_month)

    # S&P 1500 quarterly — index rebalance windows (third Friday of Mar/Jun/Sep/Dec)
    sp1500_month = ((now.month - 1) // 3 + 1) * 3
    if sp1500_month > 12:
        sp1500_month = 3
        year += 1
    next_sp1500_scan = _third_friday(year, sp1500_month)

    logger.info(
        "scheduler.computed",
        next_etf_review=next_etf_review,
        next_full_reeval=next_full_reeval,
        next_sp1500_scan=next_sp1500_scan,
    )
    return ReviewSchedule(
        next_etf_review=next_etf_review,
        next_full_reeval=next_full_reeval,
        next_sp1500_scan=next_sp1500_scan,
    )


def _first_monday(year: int, month: int) -> str:
    """Return ISO date string of first Monday in the given month."""
    from calendar import monthrange

    # Day 1 of month
    first_day_weekday = monthrange(year, month)[0]  # 0=Monday, 6=Sunday
    days_until_monday = (0 - first_day_weekday) % 7
    day = 1 + days_until_monday
    if day < 1:
        day = 1 + ((0 - first_day_weekday + 7) % 7)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _third_friday(year: int, month: int) -> str:
    """Return ISO date string of third Friday in the given month."""
    from calendar import monthrange

    # Find first day of month
    first_day_weekday = monthrange(year, month)[0]  # 0=Monday
    # First Friday is day 1 + days until Friday (4 - weekday) % 7
    days_until_friday = (4 - first_day_weekday) % 7
    first_friday = 1 + days_until_friday
    third_friday = first_friday + 14
    return f"{year:04d}-{month:02d}-{third_friday:02d}"
