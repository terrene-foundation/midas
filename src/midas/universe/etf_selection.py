"""
ETF selection engine for the Midas universe.

Selects ETFs based on liquidity, AUM, expense, tracking error, and overlap criteria.
For v1, uses a curated list of core ETFs with scoring.

Ref: specs/03-universe-and-data.md §1.2
Ref: T-02-01
"""

from dataclasses import dataclass
from typing import Any

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)


@dataclass
class ETFCandidate:
    ticker: str
    name: str
    aum: float
    expense_ratio: float
    avg_daily_volume: float
    tracking_error: float
    fund_age_years: float
    category: str
    score: float = 0.0


# Minimum thresholds from spec 03 §1.2
MIN_AUM = 500_000_000
MIN_AVG_VOLUME = 5_000_000
MAX_EXPENSE = 0.0040  # 0.40%
MAX_TRACKING_ERROR = 0.0015  # 0.15%
MIN_FUND_AGE = 2.0


def score_etf(etf: ETFCandidate) -> float:
    """Score an ETF against selection criteria. Higher is better."""
    score = 0.0
    if etf.aum >= MIN_AUM:
        score += min(etf.aum / 1e9, 10.0)
    if etf.avg_daily_volume >= MIN_AVG_VOLUME:
        score += min(etf.avg_daily_volume / 1e7, 5.0)
    if etf.expense_ratio <= MAX_EXPENSE:
        score += (MAX_EXPENSE - etf.expense_ratio) * 1000
    if etf.tracking_error <= MAX_TRACKING_ERROR:
        score += (MAX_TRACKING_ERROR - etf.tracking_error) * 1000
    if etf.fund_age_years >= MIN_FUND_AGE:
        score += 2.0
    return score


async def select_etfs(as_of_date: str, fabric_db: DataFlow) -> list[ETFCandidate]:
    """Select ETFs for the Midas universe based on scoring criteria."""
    # Core ETF universe for Singapore-domiciled investor (FP-6: no US tax)
    candidates = [
        ETFCandidate("SPY", "SPDR S&P 500 ETF", 400e9, 0.0009, 30e9, 0.0002, 30, "us_large_cap"),
        ETFCandidate(
            "IVV", "iShares Core S&P 500 ETF", 450e9, 0.0003, 10e9, 0.0002, 22, "us_large_cap"
        ),
        ETFCandidate(
            "VTI", "Vanguard Total Stock Market ETF", 350e9, 0.0003, 5e9, 0.0003, 22, "us_total"
        ),
        ETFCandidate(
            "VEA",
            "Vanguard FTSE Developed Markets ETF",
            120e9,
            0.0005,
            2e9,
            0.0005,
            18,
            "intl_developed",
        ),
        ETFCandidate(
            "VWO",
            "Vanguard FTSE Emerging Markets ETF",
            80e9,
            0.0008,
            2e9,
            0.0008,
            18,
            "intl_emerging",
        ),
        ETFCandidate(
            "AGG", "iShares Core US Aggregate Bond ETF", 100e9, 0.0003, 2e9, 0.0003, 20, "us_bond"
        ),
        ETFCandidate(
            "BND", "Vanguard Total Bond Market ETF", 90e9, 0.0003, 1e9, 0.0003, 18, "us_bond"
        ),
        ETFCandidate(
            "TLT",
            "iShares 20+ Year Treasury Bond ETF",
            50e9,
            0.0015,
            2e9,
            0.0010,
            22,
            "us_long_bond",
        ),
        ETFCandidate("GLD", "SPDR Gold Shares", 60e9, 0.0040, 2e9, 0.0005, 20, "commodities"),
        ETFCandidate(
            "VNQ", "Vanguard Real Estate ETF", 40e9, 0.0012, 1e9, 0.0008, 18, "real_estate"
        ),
        ETFCandidate("QQQ", "Invesco QQQ Trust", 200e9, 0.0020, 15e9, 0.0003, 25, "us_tech"),
        ETFCandidate(
            "IWM", "iShares Russell 2000 ETF", 50e9, 0.0019, 3e9, 0.0008, 24, "us_small_cap"
        ),
    ]

    for etf in candidates:
        etf.score = score_etf(etf)

    selected = sorted(candidates, key=lambda e: e.score, reverse=True)
    logger.info("etf_selection.complete", count=len(selected), as_of=as_of_date)
    return selected


async def detect_missing_exposures(
    current_holdings: list[str],
    target_factors: list[str],
) -> list[str]:
    """Detect missing factor exposures in current holdings."""
    factor_map = {
        "us_large_cap": ["SPY", "IVV", "VOO"],
        "us_small_cap": ["IWM", "VB"],
        "intl_developed": ["VEA", "EFA"],
        "intl_emerging": ["VWO", "EEM"],
        "us_bond": ["AGG", "BND"],
        "us_long_bond": ["TLT"],
        "commodities": ["GLD", "IAU"],
        "real_estate": ["VNQ", "IYR"],
        "us_tech": ["QQQ", "XLK"],
    }

    missing = []
    for factor in target_factors:
        etfs = factor_map.get(factor, [])
        if not any(e in current_holdings for e in etfs):
            missing.append(factor)
    return missing
