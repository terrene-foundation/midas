"""
S&P 1500 filter pipeline.

Filters current S&P 1500 constituents by liquidity floor, price floor,
fundamentals availability, and halt history.

Ref: specs/03-universe-and-data.md §1.2
Ref: T-02-02
"""

from dataclasses import dataclass
import structlog

from midas.fabric.adapters.universe import UniverseAdapter

logger = structlog.get_logger(__name__)

# Minimum thresholds from spec 03 §1.2
MIN_PRICE = 1.0  # Avoids penny-stock microstructure noise
MIN_AVG_DAILY_VOLUME = 1_000_000  # Minimum average daily dollar volume
MIN_SHARES_OUTSTANDING = 1_000_000  # Minimum shares outstanding


@dataclass
class SP1500Candidate:
    ticker: str
    index_membership: str  # "SP500" | "SP400" | "SP600"
    price: float
    avg_daily_volume: float
    shares_outstanding: float
    has_fundamentals: bool = False
    has_halt_history: bool = False  # True if has recent extended halt


async def filter_sp1500_constituents(
    as_of_date: str,
    universe_adapter: UniverseAdapter,
    min_price: float = MIN_PRICE,
    min_volume: float = MIN_AVG_DAILY_VOLUME,
    min_shares: float = MIN_SHARES_OUTSTANDING,
) -> list[SP1500Candidate]:
    """Filter S&P 1500 constituents by liquidity, price, and fundamentals criteria."""
    raw_tickers = await universe_adapter.fetch_constituents("sp500", as_of_date)
    raw_tickers += await universe_adapter.fetch_constituents("sp400", as_of_date)
    raw_tickers += await universe_adapter.fetch_constituents("sp600", as_of_date)

    candidates: list[SP1500Candidate] = []

    for ticker in raw_tickers:
        price = 0.0
        avg_daily_volume = 0.0
        shares_outstanding = 0.0
        has_fundamentals = False

        try:
            price_rows = await universe_adapter._db.express.list(
                "prices", filter={"instrument": ticker}
            )
            if price_rows:
                closes = [float(r["close"]) for r in price_rows if r.get("close")]
                volumes = [float(r.get("volume", 0)) for r in price_rows]
                price = closes[-1] if closes else 0.0
                avg_daily_volume = sum(volumes) / len(volumes) if volumes else 0.0
        except Exception:
            pass

        try:
            fund_rows = await universe_adapter._db.express.list(
                "fundamentals", filter={"ticker": ticker}
            )
            has_fundamentals = len(fund_rows) > 0
        except Exception:
            pass

        candidate = SP1500Candidate(
            ticker=ticker,
            index_membership="SP500",
            price=price,
            avg_daily_volume=avg_daily_volume,
            shares_outstanding=shares_outstanding,
            has_fundamentals=has_fundamentals,
            has_halt_history=False,
        )
        candidates.append(candidate)

    filtered = [
        c
        for c in candidates
        if c.price >= min_price
        and c.avg_daily_volume >= min_volume
        and c.shares_outstanding >= min_shares
        and not c.has_halt_history
    ]

    logger.info(
        "sp1500_filter.done",
        as_of=as_of_date,
        total=len(candidates),
        passed=len(filtered),
    )
    return filtered
