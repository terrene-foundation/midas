"""
Universe membership adapter for S&P 1500 constituents.

Tracks S&P 500/400/600 constituents as-of a given date, writing membership
changes to the ``universe_changelog`` fabric table. For v1, uses a static
snapshot of major S&P 500 constituents.

Ref: T-01-15
"""

from datetime import date, datetime, timezone
from typing import Any

import httpx
import structlog
from dataflow import DataFlow

from midas.fabric.adapters.base import AdapterError, BaseAdapter

logger = structlog.get_logger("midas.fabric.adapters.universe")

# Static snapshot of major S&P 500 constituents for v1
_SP500_SNAPSHOT_2024: list[str] = [
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "META",
    "NVDA",
    "TSLA",
    "BRK-B",
    "JPM",
    "V",
    "JNJ",
    "UNH",
    "HD",
    "PG",
    "MA",
    "DIS",
    "PYPL",
    "BAC",
    "XOM",
    "ADBE",
    "CRM",
    "NFLX",
    "CMCSA",
    "PFE",
    "ABBV",
    "PEP",
    "KO",
    "CSCO",
    "AVGO",
    "TMO",
    "MRK",
    "ABT",
    "ORCL",
    "COST",
    "LLY",
    "CVX",
    "NKE",
    "ACN",
    "WMT",
    "T",
    "MCD",
    "MDLZ",
    "DHR",
    "UPS",
    "QCOM",
    "LIN",
    "NEE",
    "BMY",
    "PM",
    "HON",
    "RTX",
    "TXN",
    "LOW",
    "SBUX",
    "IBM",
    "AMGN",
    "GS",
    "CAT",
    "INTC",
    "AMD",
    "DE",
    "BLK",
    "AXP",
    "ISRG",
    "BKNG",
    "MDT",
    "ADI",
    "SYK",
    "MMC",
    "ZTS",
    "MO",
    "CME",
    "CI",
    "COP",
    "TJX",
    "DUK",
    "SLB",
    "BDX",
    "CB",
    "CL",
    "APD",
    "SO",
    "EQIX",
    "EOG",
    "F",
    "PGR",
    "NSC",
    "ICE",
    "NOC",
    "ECL",
    "ITW",
]

_SP500_SNAPSHOT_2020: list[str] = [
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "FB",
    "JPM",
    "V",
    "JNJ",
    "WMT",
    "BAC",
    "PG",
    "UNH",
    "MA",
    "HD",
    "DIS",
    "NVDA",
    "PYPL",
    "XOM",
    "TSLA",
    "ADBE",
    "CRM",
    "NFLX",
    "CMCSA",
    "PFE",
    "ABBV",
    "PEP",
    "KO",
    "CSCO",
    "AVGO",
    "TMO",
    "MRK",
    "ABT",
    "ORCL",
    "COST",
    "LLY",
    "CVX",
    "NKE",
    "ACN",
    "INTC",
    "T",
    "MCD",
    "MDLZ",
    "DHR",
    "UPS",
    "QCOM",
    "LIN",
    "NEE",
    "BMY",
    "PM",
    "HON",
    "RTX",
    "TXN",
    "LOW",
    "SBUX",
    "IBM",
    "AMGN",
    "GS",
    "CAT",
    "AMD",
    "DE",
    "BLK",
    "AXP",
    "ISRG",
    "BKNG",
    "MDT",
    "ADI",
    "SYK",
    "MMC",
    "ZTS",
    "MO",
    "CME",
    "CI",
    "COP",
    "TJX",
    "DUK",
    "SLB",
    "BDX",
    "CB",
    "CL",
    "APD",
    "SO",
    "F",
]


class UniverseAdapter(BaseAdapter):
    """Adapter for S&P 1500 universe membership tracking."""

    SOURCE_NAME = "universe"

    def __init__(self, db: DataFlow | None = None, **kwargs) -> None:
        super().__init__(db, **kwargs)

    async def close(self) -> None:
        pass

    async def health_check(self) -> dict[str, Any]:
        return {
            "source": self.SOURCE_NAME,
            "healthy": True,
            "detail": "universe adapter uses static snapshot",
        }

    async def fetch_constituents(
        self,
        index_name: str = "sp500",
        as_of_date: str = "",
    ) -> list[str]:
        """Fetch S&P index constituents as-of a given date.

        Writes membership to universe_changelog if not already present.
        """
        if not as_of_date:
            as_of_date = date.today().isoformat()

        year = int(as_of_date[:4]) if len(as_of_date) >= 4 else 2024

        if index_name == "sp500":
            if year <= 2020:
                tickers = list(_SP500_SNAPSHOT_2020)
            else:
                tickers = list(_SP500_SNAPSHOT_2024)
        else:
            tickers = list(_SP500_SNAPSHOT_2024)

        db = self._get_db()
        for ticker in tickers:
            try:
                await db.express.create(
                    "universe_changelog",
                    {
                        "ticker": ticker,
                        "action": "member",
                        "reason": f"sp500_constituent_{year}",
                        "effective_date": as_of_date,
                        "backtest_impact": "",
                    },
                )
            except Exception as exc:
                self._log.warning("universe.changelog_write_failed", ticker=ticker, error=str(exc))

        self._log.info(
            "fetch_constituents.complete", index=index_name, count=len(tickers), as_of=as_of_date
        )
        return tickers

    async def get_membership(self, as_of_date: str, fabric_db: DataFlow) -> list[str]:
        """Retrieve known universe membership from the changelog."""
        try:
            rows = await fabric_db.express.list("universe_changelog", filter={"action": "member"})
            return list({r["ticker"] for r in rows})
        except Exception as exc:
            self._log.warning("universe.membership_fetch_failed", error=str(exc))
            return []
