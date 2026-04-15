"""
Universe constraint enforcement.

Feeds the PACT compliance env.universe rule — any proposed trade
outside the current universe is blocked.

Ref: specs/03-universe-and-data.md §1.3
Ref: T-02-07
"""

from typing import Any

import structlog

from midas.fabric.adapters.universe import UniverseAdapter

logger = structlog.get_logger(__name__)


class UniverseConstraint:
    """Checks whether a ticker is in the current investable universe."""

    def __init__(self, universe_adapter: UniverseAdapter) -> None:
        self._adapter = universe_adapter
        self._current_universe: set[str] = set()

    async def refresh(self, as_of_date: str) -> None:
        """Refresh the current universe from the fabric."""
        tickers = await self._adapter.fetch_constituents("sp500", as_of_date)
        tickers += await self._adapter.fetch_constituents("sp400", as_of_date)
        tickers += await self._adapter.fetch_constituents("sp600", as_of_date)
        self._current_universe = set(tickers)
        logger.info("universe_constraint.refreshed", count=len(self._current_universe))

    def is_allowed(self, ticker: str) -> bool:
        """Return True if ticker is in the current universe."""
        return ticker.upper() in self._current_universe

    def filter_allowed(self, tickers: list[str]) -> list[str]:
        """Return only the tickers that are in the current universe."""
        return [t for t in tickers if self.is_allowed(t)]

    def check_trade(self, ticker: str, side: str) -> tuple[bool, str]:
        """Check if a trade is allowed. Returns (allowed, reason)."""
        if not self.is_allowed(ticker):
            reason = f"ticker {ticker!r} not in current universe (as of today)"
            logger.warning("universe.trade_blocked", ticker=ticker, side=side, reason=reason)
            return False, reason
        return True, ""

    async def get_universe_snapshot(self, as_of_date: str) -> dict[str, Any]:
        """Return a snapshot of the universe for compliance reporting."""
        if not self._current_universe:
            await self.refresh(as_of_date)
        return {
            "as_of_date": as_of_date,
            "universe_size": len(self._current_universe),
            "tickers": sorted(self._current_universe),
        }
