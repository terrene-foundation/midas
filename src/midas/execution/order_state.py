"""Order state machine for IBKR execution lifecycle.

Manages transitions: pending -> submitted -> partial -> filled -> reconciled -> attributed.
Terminal states: attributed, cancelled, rejected.

Every transition is audited to the audit_log fabric table.

Ref: M15 — Order state machine
"""

import time

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.execution.order_state")


class OrderStatus:
    """Order status constants."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    RECONCILED = "reconciled"
    ATTRIBUTED = "attributed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    ALL = (PENDING, SUBMITTED, PARTIAL, FILLED, RECONCILED, ATTRIBUTED, CANCELLED, REJECTED)


# Transition table: from_status -> set of allowed target statuses.
TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.SUBMITTED, OrderStatus.CANCELLED},
    OrderStatus.SUBMITTED: {
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    },
    OrderStatus.PARTIAL: {OrderStatus.FILLED, OrderStatus.CANCELLED},
    OrderStatus.FILLED: {OrderStatus.RECONCILED},
    OrderStatus.RECONCILED: {OrderStatus.ATTRIBUTED},
    OrderStatus.ATTRIBUTED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
}

TERMINAL_STATES = {OrderStatus.ATTRIBUTED, OrderStatus.CANCELLED, OrderStatus.REJECTED}


class OrderStateMachine:
    """Order state machine: pending -> submitted -> partial -> filled -> reconciled -> attributed.

    Transition table is defined by the TRANSITIONS constant above.
    Every transition is audited.
    """

    def __init__(self, db: DataFlow | None = None):
        self._db = db
        self._log = structlog.get_logger("midas.execution.order_state")

    def can_transition(self, current: str, target: str) -> bool:
        """Check if transitioning from current to target status is allowed."""
        allowed = TRANSITIONS.get(current, set())
        return target in allowed

    def is_terminal(self, status: str) -> bool:
        """Check if the status is terminal (no further transitions possible)."""
        return status in TERMINAL_STATES

    async def transition(
        self,
        order_id: str,
        new_status: str,
        details: dict | None = None,
    ) -> dict:
        """Transition order status. Audits every transition.

        Raises ValueError if the transition is invalid or the current state
        is terminal.
        """
        if self._db is None:
            raise RuntimeError("OrderStateMachine requires a DataFlow instance for transitions")

        # Read current order
        order = await self._db.express.read("orders", order_id)
        current_status = order["status"]

        if self.is_terminal(current_status):
            raise ValueError(
                f"Order '{order_id}' is in terminal state '{current_status}' — "
                f"no further transitions allowed"
            )

        if not self.can_transition(current_status, new_status):
            raise ValueError(
                f"Invalid transition for order '{order_id}': "
                f"'{current_status}' -> '{new_status}' is not allowed"
            )

        # Update the order status
        await self._db.express.update(
            "orders",
            order_id,
            {"status": new_status},
        )

        self._log.info(
            "order_state.transition",
            order_id=order_id,
            previous_status=current_status,
            new_status=new_status,
        )

        # Audit the transition
        if details is None:
            details = {}
        details["previous_status"] = current_status
        details["new_status"] = new_status

        try:
            import json

            await self._db.express.create(
                "audit_log",
                {
                    "audit_id": f"order_transition:{order_id}:{new_status}",
                    "rule_name": "order_state_transition",
                    "action": new_status,
                    "details": json.dumps(details),
                    "agent": "order_state_machine",
                    "period_end": "",
                    "filed_at": "",
                    "z_t_snapshot": "",
                },
            )
        except Exception as exc:
            self._log.error("order_state.audit_failed", error=str(exc))

        return {
            "order_id": order_id,
            "status": new_status,
            "previous_status": current_status,
        }
