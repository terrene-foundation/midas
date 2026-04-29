"""Execution agent — routes approved decisions to IBKR with priority queue.

Delegates order lifecycle management to OrderManager for state machine
enforcement and rejection classification. Creates orders, handles partial
fills, broker rejections, and provides a kill switch (cancel_all_pending).

Ref: M15 — ExecutionAgent
"""

import structlog
from dataflow import DataFlow

from midas.execution.order_manager import OrderManager
from midas.fabric.models import OrderState

logger = structlog.get_logger("midas.execution.execution_agent")


class ExecutionAgent:
    """Routes approved decisions to IBKR with priority queue."""

    def __init__(self, db: DataFlow):
        self._db = db
        self._order_manager = OrderManager(db)
        self._log = structlog.get_logger("midas.execution.execution_agent")

    async def execute_decision(
        self,
        decision: dict,
        execution_params: dict | None = None,
    ) -> dict:
        """Execute a decision. Creates order, routes to broker.

        Returns {order_id, status, fills}.
        """
        params = execution_params or {}
        instrument = decision["instrument"]

        self._log.info(
            "execution.create_order",
            instrument=instrument,
            action=decision.get("action", "BUY"),
            quantity=decision.get("quantity", 0),
            order_type=decision.get("order_type", "MARKET"),
        )

        result = await self._order_manager.submit_order(
            {
                "ticker": instrument,
                "side": decision.get("action", "BUY"),
                "order_type": decision.get("order_type", "MARKET"),
                "quantity": decision.get("quantity", 0),
                "limit_price": decision.get("limit_price", 0.0),
                "parent_decision_id": params.get("decision_id", ""),
            }
        )

        self._log.info(
            "execution.order_created",
            order_id=result["order_id"],
            instrument=instrument,
        )

        return {
            "order_id": result["order_id"],
            "status": result["status"],
            "fills": [],
        }

    async def handle_partial_fill(self, order_id: str, fill_info: dict) -> dict:
        """Handle partial fill - update order with fill info.

        Delegates to OrderManager for state machine enforcement.
        """
        self._log.info(
            "execution.partial_fill",
            order_id=order_id,
            fill_price=fill_info.get("fill_price"),
            fill_quantity=fill_info.get("fill_quantity"),
        )

        fill_price = fill_info.get("fill_price", 0.0)
        fill_qty = fill_info.get("fill_quantity", 0.0)

        # Delegate state transition to OrderManager
        result = await self._order_manager.process_ibkr_status_update(
            order_id,
            "PartiallyFilled",
            fill_quantity=fill_qty,
            fill_price=fill_price,
        )

        # Create fill record
        order = await self._db.express.read("orders", order_id)
        await self._db.express.create(
            "fills",
            {
                "order_id": order_id,
                "ticker": (order or {}).get("ticker", ""),
                "fill_price": fill_price,
                "fill_qty": fill_qty,
                "commission": fill_info.get("commission", 0.0),
                "exchange_fee": fill_info.get("exchange_fee", 0.0),
                "regulatory_fee": fill_info.get("regulatory_fee", 0.0),
                "venue": fill_info.get("venue", ""),
                "fill_timestamp": "",
                "broker_fill_id": fill_info.get("broker_fill_id", ""),
                "period_end": "",
                "filed_at": "",
                "restated_at": "",
                "source_vintage": "",
            },
        )

        order_data = await self._db.express.read("orders", order_id)
        filled_qty = (order_data or {}).get("filled_qty", 0.0) or 0.0

        return {
            "order_id": order_id,
            "status": OrderState.PARTIAL_FILLED.value,
            "filled_quantity": filled_qty,
            "fill_price": fill_price,
        }

    async def handle_rejection(self, order_id: str, rejection_reason: str) -> dict:
        """Handle broker rejection via OrderManager.

        Delegates to process_ibkr_status_update with REJECTED state and
        classifies the rejection code.
        """
        self._log.warning(
            "execution.rejection",
            order_id=order_id,
            reason=rejection_reason,
        )

        result = await self._order_manager.process_ibkr_status_update(
            order_id,
            "Rejected",
            ibkr_message=rejection_reason,
        )
        return result

    async def cancel_all_pending(self) -> list[str]:
        """Cancel all pending orders (for kill switch).

        Returns list of cancelled order IDs.
        """
        self._log.warning("execution.kill_switch", action="cancel_all_pending")

        cancelled_ids: list[str] = []
        cancellable_states = [
            OrderState.PENDING,
            OrderState.SUBMITTED_PENDING,
            OrderState.WORKING,
        ]

        for state in cancellable_states:
            try:
                orders = await self._db.express.list("orders", filter={"status": state.value})
                for order in orders:
                    order_id = str(order["id"])
                    result = await self._order_manager.cancel_order(order_id)
                    if "error" not in result:
                        cancelled_ids.append(order_id)
                        self._log.info("execution.cancelled", order_id=order_id)
            except Exception as exc:
                self._log.error(
                    "execution.cancel_failed",
                    status=state.value,
                    error=str(exc),
                )

        self._log.info("execution.kill_switch.complete", cancelled=len(cancelled_ids))
        return cancelled_ids
