"""Post-execution reconciliation.

Compares filled quantities and prices against the pre-trade brief to
detect discrepancies. Runs per-order and daily reconciliation.

Ref: M15 — Reconciliation
"""

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.execution.reconciliation")


class ReconciliationService:
    """Post-execution reconciliation."""

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = structlog.get_logger("midas.execution.reconciliation")

    async def reconcile_order(self, order_id: str) -> dict:
        """Compare filled quantities * prices to pre-trade brief.

        Returns {matched, discrepancies, order_id}.
        """
        self._log.info("reconciliation.order", order_id=order_id)

        order = await self._db.express.read("orders", order_id)

        expected_qty = order.get("quantity", 0.0) or 0.0
        expected_price = order.get("limit_price", 0.0) or 0.0
        filled_qty = order.get("filled_qty", 0.0) or 0.0
        filled_price = order.get("filled_price", 0.0) or 0.0
        status = order.get("status", "")

        discrepancies = []

        # Check quantity match
        if abs(filled_qty - expected_qty) > 1e-6:
            discrepancies.append(
                {
                    "field": "quantity",
                    "expected": expected_qty,
                    "actual": filled_qty,
                }
            )

        # Check price match (only for limit orders with a set price)
        if expected_price > 0 and abs(filled_price - expected_price) > 0.01:
            discrepancies.append(
                {
                    "field": "price",
                    "expected": expected_price,
                    "actual": filled_price,
                }
            )

        matched = len(discrepancies) == 0

        self._log.info(
            "reconciliation.order.result",
            order_id=order_id,
            matched=matched,
            discrepancies=len(discrepancies),
        )

        return {
            "order_id": order_id,
            "matched": matched,
            "discrepancies": discrepancies,
            "status": status,
        }

    async def daily_reconciliation(self, as_of_date: str) -> dict:
        """Run daily reconciliation for all orders.

        Returns {total_orders, matched, discrepancies, details}.
        """
        self._log.info("reconciliation.daily", as_of_date=as_of_date)

        # Fetch orders that were filled on this date
        try:
            orders = await self._db.express.list("orders", filter={})
        except Exception:
            orders = []

        # Filter to filled orders from the given date
        filled_orders = []
        for order in orders:
            filled_at = order.get("filled_at", "") or ""
            status = order.get("status", "")
            if as_of_date in filled_at or status == "filled":
                filled_orders.append(order)

        total = len(filled_orders)
        matched_count = 0
        all_discrepancies = []

        for order in filled_orders:
            order_id = str(order["id"])
            result = await self.reconcile_order(order_id)
            if result["matched"]:
                matched_count += 1
            all_discrepancies.extend(result.get("discrepancies", []))

        self._log.info(
            "reconciliation.daily.result",
            as_of_date=as_of_date,
            total=total,
            matched=matched_count,
        )

        return {
            "as_of_date": as_of_date,
            "total_orders": total,
            "matched": matched_count,
            "discrepancies": all_discrepancies,
        }
