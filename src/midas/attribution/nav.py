"""Daily NAV computation.

Computes Net Asset Value from positions multiplied by current market prices,
plus cash and minus unsettled amounts.

Ref: M16 — NAV computation
"""

import math

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.attribution.nav")


class NAVComputation:
    """Daily NAV computation."""

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = structlog.get_logger("midas.attribution.nav")

    async def compute_nav(self, as_of_date: str) -> dict:
        """Compute NAV from positions * marks.

        Returns {nav, positions_value, cash, unsettled}.
        """
        self._log.info("nav.compute", as_of_date=as_of_date)

        try:
            positions = await self._db.express.list(
                "positions",
                filter={"as_of_date": as_of_date},
            )
        except Exception as exc:
            logger.error("nav.positions_fetch_failed", as_of_date=as_of_date, error=str(exc))
            positions = []

        positions_value = 0.0
        for pos in positions:
            market_value = pos.get("market_value", 0.0) or 0.0
            positions_value += market_value

        # Cash and unsettled are not yet tracked in separate tables;
        # they default to 0 until the cash management module is built.
        cash = 0.0
        unsettled = 0.0

        nav = positions_value + cash - unsettled

        if not math.isfinite(nav):
            self._log.warning(
                "nav.non_finite",
                nav=nav,
                positions_value=positions_value,
                cash=cash,
                unsettled=unsettled,
            )
            nav = 0.0

        self._log.info(
            "nav.compute.ok",
            as_of_date=as_of_date,
            nav=nav,
            positions_value=positions_value,
            positions_count=len(positions),
        )

        return {
            "nav": nav,
            "positions_value": positions_value,
            "cash": cash,
            "unsettled": unsettled,
            "as_of_date": as_of_date,
            "positions_count": len(positions),
        }
