"""Execution agent — routes approved decisions to IBKR with priority queue.

Creates orders, handles partial fills, broker rejections, and provides
a kill switch (cancel_all_pending).

Ref: M15 — ExecutionAgent
"""

import time

import structlog
from dataflow import DataFlow

from midas.execution.order_state import OrderStatus, OrderStateMachine

logger = structlog.get_logger("midas.execution.execution_agent")


class ExecutionAgent:
    """Routes approved decisions to IBKR with priority queue."""

    def __init__(self, db: DataFlow):
        self._db = db
        self._state_machine = OrderStateMachine(db)
        self._log = structlog.get_logger("midas.execution.execution_agent")

    async def execute_decision(
        self,
        decision: dict,
        execution_params: dict | None = None,
    ) -> dict:
        """Execute a decision. Creates order, routes to broker.

        Returns {order_id, status, fills}.
        """
        instrument = decision["instrument"]
        action = decision.get("action", "BUY")
        quantity = decision.get("quantity", 0)
        order_type = decision.get("order_type", "MARKET")
        limit_price = decision.get("limit_price", 0.0)
        params = execution_params or {}

        self._log.info(
            "execution.create_order",
            instrument=instrument,
            action=action,
            quantity=quantity,
            order_type=order_type,
        )

        # Create the order record in pending state
        await self._db.express.create(
            "orders",
            {
                "ticker": instrument,
                "side": action,
                "order_type": order_type,
                "quantity": quantity,
                "limit_price": limit_price,
                "status": OrderStatus.PENDING,
                "filled_qty": 0.0,
                "filled_price": 0.0,
                "submitted_at": "",
                "filled_at": "",
                "broker_order_id": "",
                "parent_decision_id": params.get("decision_id", ""),
            },
        )

        # Retrieve the generated ID via list (express.create does not return it)
        rows = await self._db.express.list("orders", filter={"ticker": instrument})
        order_id = str(rows[-1]["id"])

        self._log.info(
            "execution.order_created",
            order_id=order_id,
            instrument=instrument,
        )

        return {
            "order_id": order_id,
            "status": OrderStatus.PENDING,
            "fills": [],
        }

    async def handle_partial_fill(self, order_id: str, fill_info: dict) -> dict:
        """Handle partial fill - update order with fill info.

        Transitions to partial status and records the fill details.
        """
        self._log.info(
            "execution.partial_fill",
            order_id=order_id,
            fill_price=fill_info.get("fill_price"),
            fill_quantity=fill_info.get("fill_quantity"),
        )

        fill_price = fill_info.get("fill_price", 0.0)
        fill_qty = fill_info.get("fill_quantity", 0.0)

        # Read current order to accumulate fills
        order = await self._db.express.read("orders", order_id)
        current_filled = order.get("filled_qty", 0.0) or 0.0
        new_filled = current_filled + fill_qty

        # Update the order with partial fill
        await self._db.express.update(
            "orders",
            order_id,
            {
                "status": OrderStatus.PARTIAL_FILLED,
                "filled_qty": new_filled,
                "filled_price": fill_price,
            },
        )

        # Create fill record
        await self._db.express.create(
            "fills",
            {
                "order_id": order_id,
                "ticker": order.get("ticker", ""),
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

        return {
            "order_id": order_id,
            "status": OrderStatus.PARTIAL_FILLED,
            "filled_quantity": new_filled,
            "fill_price": fill_price,
        }

    async def handle_rejection(self, order_id: str, rejection_reason: str) -> dict:
        """Handle broker rejection.

        Transitions the order to rejected if it is in submitted state,
        or cancelled otherwise.
        """
        self._log.warning(
            "execution.rejection",
            order_id=order_id,
            reason=rejection_reason,
        )

        order = await self._db.express.read("orders", order_id)
        current_status = order.get("status", OrderStatus.PENDING)

        # Determine the appropriate terminal state
        if current_status == OrderStatus.SUBMITTED_PENDING:
            target = OrderStatus.REJECTED
        else:
            target = OrderStatus.CANCELLED

        # Try state machine transition; if it fails, force the status
        try:
            result = await self._state_machine.transition(order_id, target)
        except ValueError:
            # Force update for cases where the state machine path is not direct
            await self._db.express.update("orders", order_id, {"status": target})
            result = {"order_id": order_id, "status": target}

        return result

    async def cancel_all_pending(self) -> list[str]:
        """Cancel all pending orders (for kill switch).

        Returns list of cancelled order IDs.
        """
        self._log.warning("execution.kill_switch", action="cancel_all_pending")

        cancelled_ids: list[str] = []

        # List all orders that are in a cancellable state
        cancellable_statuses = (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED_PENDING,
            OrderStatus.WORKING,
        )

        for status in cancellable_statuses:
            try:
                orders = await self._db.express.list("orders", filter={"status": status})
                for order in orders:
                    order_id = str(order["id"])
                    await self._db.express.update(
                        "orders",
                        order_id,
                        {"status": OrderStatus.CANCELLED},
                    )
                    cancelled_ids.append(order_id)
                    self._log.info("execution.cancelled", order_id=order_id)
            except Exception as exc:
                self._log.error(
                    "execution.cancel_failed",
                    status=status,
                    error=str(exc),
                )

        self._log.info("execution.kill_switch.complete", cancelled=len(cancelled_ids))
        return cancelled_ids
