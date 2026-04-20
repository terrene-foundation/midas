"""
ETF selection engine for the Midas universe.

Selects ETFs based on liquidity, AUM, expense, tracking error, and overlap criteria.
For v1, uses a curated list of core ETFs with scoring.

Ref: specs/03-universe-and-data.md §1.2
Ref: T-02-01
"""

from dataclasses import dataclass

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)

# Factor map: maps factor names to ETF tickers.
# Used by detect_missing_exposures and imported by agents/tools.py.
FACTOR_MAP: dict[str, list[str]] = {
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

# Ireland-domiciled UCITS alternatives per spec 03 §1.2 item 8.
# For Singapore residents: US-source dividends have 30% WHT,
# Ireland-domiciled UCITS equivalents benefit from 15% WHT via treaty.
# Key: US ticker → UCITS equivalent with dividend yield and domicile info.
UCITS_ALTERNATIVES: dict[str, dict[str, str | float]] = {
    "SPY": {
        "ucits_ticker": "SPYL",
        "name": "SPDR S&P 500 UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 1.3,
    },
    "IVV": {
        "ucits_ticker": "CSPX",
        "name": "iShares Core S&P 500 UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 1.3,
    },
    "VOO": {
        "ucits_ticker": "VUAA",
        "name": "Vanguard S&P 500 UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 1.3,
    },
    "VEA": {
        "ucits_ticker": "VEUD",
        "name": "Vanguard FTSE Developed World UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 2.5,
    },
    "VWO": {
        "ucits_ticker": "VWCE",
        "name": "Vanguard FTSE All-World UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 2.0,
    },
    "AGG": {
        "ucits_ticker": "AGGU",
        "name": "iShares Core Global Aggregate Bond UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 3.0,
    },
    "QQQ": {
        "ucits_ticker": "QQQI",
        "name": "Invesco EQQQ Nasdaq-100 UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 0.6,
    },
    "IWM": {
        "ucits_ticker": "IUSN",
        "name": "iShares MSCI USA Small Cap UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 1.5,
    },
    "TLT": {
        "ucits_ticker": "TLTL",
        "name": "SPDR Bloomberg Long Duration Treasury UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 3.5,
    },
    "GLD": {
        "ucits_ticker": "GLDN",
        "name": "Invesco Physical Gold A UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 0.0,
    },
    "VNQ": {
        "ucits_ticker": "VNQI",
        "name": "Vanguard Global ex-US Real Estate UCITS ETF",
        "domicile": "Ireland",
        "div_yield_pct": 3.0,
    },
}

# Dividend withholding rates for Singapore residents
US_WHT_RATE = 0.30  # 30% on US-source dividends
IRELAND_WHT_RATE = 0.15  # 15% for Ireland-domiciled UCITS via treaty


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
    missing = []
    for factor in target_factors:
        etfs = FACTOR_MAP.get(factor, [])
        if not any(e in current_holdings for e in etfs):
            missing.append(factor)
    return missing


def evaluate_ucits_alternative(
    us_ticker: str,
    us_div_yield_pct: float,
    us_expense_ratio: float,
) -> dict | None:
    """Evaluate Ireland-domiciled UCITS alternative per spec 03 §1.2 item 8.

    Compares the US ETF against its UCITS equivalent on
    dividend-withholding-adjusted net return for Singapore residents.

    Parameters
    ----------
    us_ticker:
        The US-domiciled ETF ticker.
    us_div_yield_pct:
        The dividend yield of the US ETF (e.g. 1.3 for 1.3%).
    us_expense_ratio:
        The expense ratio of the US ETF (e.g. 0.0009 for 0.09%).

    Returns
    -------
    dict or None
        Comparison result with recommendation, or None if no UCITS alternative exists.
    """
    ucits = UCITS_ALTERNATIVES.get(us_ticker)
    if ucits is None:
        return None

    us_yield = us_div_yield_pct / 100
    ucits_yield = float(ucits["div_yield_pct"]) / 100

    # After withholding tax, Singapore resident nets:
    us_after_wht = us_yield * (1 - US_WHT_RATE)
    ucits_after_wht = ucits_yield * (1 - IRELAND_WHT_RATE)

    # Net dividend advantage per year
    wht_savings = ucits_after_wht - us_after_wht

    recommendation = "ucits_preferred" if wht_savings > 0.001 else "us_preferred"

    return {
        "us_ticker": us_ticker,
        "ucits_ticker": ucits["ucits_ticker"],
        "ucits_name": ucits["name"],
        "us_div_yield_after_wht": round(us_after_wht, 4),
        "ucits_div_yield_after_wht": round(ucits_after_wht, 4),
        "annual_wht_savings_pct": round(wht_savings * 100, 4),
        "recommendation": recommendation,
    }


async def select_etfs_with_ucits(as_of_date: str, fabric_db: DataFlow) -> list[dict]:
    """Select ETFs with UCITS evaluation for all candidates.

    Returns the scored ETF list augmented with UCITS comparison data.
    """
    selected = await select_etfs(as_of_date, fabric_db)

    results = []
    for etf in selected:
        entry = {
            "ticker": etf.ticker,
            "name": etf.name,
            "category": etf.category,
            "score": etf.score,
        }
        ucits_eval = evaluate_ucits_alternative(
            etf.ticker,
            # Estimate dividend yield from category (simplified for v1)
            {
                "us_large_cap": 1.3,
                "us_total": 1.4,
                "intl_developed": 2.5,
                "intl_emerging": 2.0,
                "us_bond": 3.0,
                "us_long_bond": 3.5,
                "commodities": 0.0,
                "real_estate": 3.0,
                "us_tech": 0.6,
                "us_small_cap": 1.5,
            }.get(etf.category, 1.5),
            etf.expense_ratio,
        )
        if ucits_eval is not None:
            entry["ucits_evaluation"] = ucits_eval
        results.append(entry)

    logger.info("etf_selection.ucits_evaluated", count=len(results))
    return results
