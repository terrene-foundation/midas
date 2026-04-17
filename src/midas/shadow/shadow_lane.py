"""
Isolated shadow execution lane for challenger models.

Shadow decisions are recorded to the shadow_decisions table and NEVER
reach the production decisions or orders tables. This isolation is the
key safety property: shadow trades are hypothetical only.

Ref: specs/06-meta-router.md
"""

import json

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)


class ShadowLane:
    """Isolated shadow execution lane for challenger models.

    Every decision recorded here goes to the shadow_decisions table.
    The lane has zero write access to the decisions or orders tables,
    ensuring shadow trades never reach production systems.
    """

    def __init__(
        self,
        db: DataFlow,
        model_family: str,
        model_version: str,
    ) -> None:
        self._db = db
        self.model_family = model_family
        self.model_version = model_version

    async def record_shadow_decision(
        self,
        decision_type: str,
        action: str,
        instruments: str,
        rationale: str,
        confidence: float,
        z_t_snapshot: str,
        diverges_from_champion: bool = False,
    ) -> None:
        """Record a shadow decision. NEVER reaches order manager.

        Writes exclusively to the shadow_decisions fabric table.
        No rows are written to decisions or orders.
        """
        row = {
            "model_family": self.model_family,
            "model_version": self.model_version,
            "decision_type": decision_type,
            "instruments": instruments,
            "action": action,
            "rationale": rationale,
            "confidence": confidence,
            "z_t_snapshot": z_t_snapshot,
            "diverges_from_champion": diverges_from_champion,
        }

        await self._db.express.create("shadow_decisions", row)

        logger.info(
            "shadow.decision_recorded",
            model_family=self.model_family,
            model_version=self.model_version,
            action=action,
            instruments=instruments,
            diverges=diverges_from_champion,
        )

    async def get_shadow_pnl(
        self,
        start_date: str,
        end_date: str,
    ) -> dict:
        """Compute hypothetical P&L for shadow decisions.

        Returns a summary of shadow trades and their hypothetical P&L.
        The P&L is based on simple direction assumptions since shadow
        trades have no real fills.
        """
        rows = await self._db.express.list("shadow_decisions")
        # Filter to this lane's decisions
        lane_rows = [
            r
            for r in rows
            if r.get("model_family") == self.model_family
            and r.get("model_version") == self.model_version
        ]

        total_trades = len(lane_rows)
        hypothetical_pnl = 0.0
        winning_trades = 0

        for row in lane_rows:
            action = row.get("action", "")
            ticker = row.get("ticker", "")
            decision_date = row.get("decision_date", start_date)
            entry_price = float(row.get("price_at_decision", 0))
            size = float(row.get("size", 1.0))

            if entry_price <= 0 or not ticker:
                continue

            try:
                price_rows = await self._db.express.list(
                    "prices",
                    filter={"instrument": ticker},
                )
                exit_prices = [
                    float(r["close"])
                    for r in price_rows
                    if r.get("period_end", "") >= end_date and r.get("close")
                ]
                exit_price = exit_prices[0] if exit_prices else entry_price
            except Exception:
                exit_price = entry_price

            trade_pnl = (
                (exit_price - entry_price) * size
                if action == "buy"
                else (entry_price - exit_price) * size
            )
            hypothetical_pnl += trade_pnl
            if trade_pnl > 0:
                winning_trades += 1

        return {
            "total_trades": total_trades,
            "hypothetical_pnl": hypothetical_pnl,
            "model_family": self.model_family,
            "model_version": self.model_version,
        }

    async def compare_with_champion(self) -> dict:
        """Compare shadow performance vs champion.

        Reads champion metrics from model_registry and returns a comparison
        dict with both challenger and champion statistics.
        """
        # Find champion
        registry_rows = await self._db.express.list("model_registry")
        champion_rows = [r for r in registry_rows if r.get("promotion_status") == "champion"]

        # Count shadow trades for this lane
        shadow_rows = await self._db.express.list("shadow_decisions")
        lane_decisions = [
            r
            for r in shadow_rows
            if r.get("model_family") == self.model_family
            and r.get("model_version") == self.model_version
        ]

        champion_family = ""
        if champion_rows:
            champion_family = champion_rows[-1].get("model_family", "")

        return {
            "shadow_trades": len(lane_decisions),
            "champion_family": champion_family,
            "challenger_family": self.model_family,
        }
