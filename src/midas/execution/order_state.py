"""Order state machine for IBKR execution lifecycle.

Maps full IBKR order-state enumeration to Midas states per spec 14 S6.
Every transition is audited to the audit_log fabric table.

Ref: specs/14-ibkr-integration.md S6 (Order State Machine)
"""

import time

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.execution.order_state")


class OrderStatus:
    """Order status constants aligned with IBKR states per spec 14 S6."""

    PENDING = "pending"
    SUBMITTED_PENDING = "submitted_pending"  # IBKR PendingSubmit
    SUBMITTED_WAITING = "submitted_waiting"  # IBKR PreSubmitted (broker-held)
    WORKING = "working"  # IBKR Submitted
    PARTIAL_FILLED = "partial_filled"  # IBKR Filled (partial)
    FILLED = "filled"  # IBKR Filled (complete)
    RECONCILED = "reconciled"
    ATTRIBUTED = "attributed"
    CANCEL_PENDING = "cancel_pending"  # IBKR PendingCancel
    CANCELLED = "cancelled"  # IBKR Cancelled
    CANCELLED_API = "cancelled_api"  # IBKR ApiCancelled
    INACTIVE_FLAGGED = "inactive_flagged"  # IBKR Inactive (trap state)
    REJECTED = "rejected"

    ALL = (
        PENDING,
        SUBMITTED_PENDING,
        SUBMITTED_WAITING,
        WORKING,
        PARTIAL_FILLED,
        FILLED,
        RECONCILED,
        ATTRIBUTED,
        CANCEL_PENDING,
        CANCELLED,
        CANCELLED_API,
        INACTIVE_FLAGGED,
        REJECTED,
    )


# Transition table: from_status -> set of allowed target statuses.
TRANSITIONS = {
    OrderStatus.PENDING: {
        OrderStatus.SUBMITTED_PENDING,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCELLED,
    },
    OrderStatus.SUBMITTED_PENDING: {
        OrderStatus.SUBMITTED_WAITING,
        OrderStatus.WORKING,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.REJECTED,
    },
    OrderStatus.SUBMITTED_WAITING: {
        OrderStatus.WORKING,
        OrderStatus.PARTIAL_FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.REJECTED,
        OrderStatus.INACTIVE_FLAGGED,
    },
    OrderStatus.WORKING: {
        OrderStatus.PARTIAL_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.REJECTED,
        OrderStatus.INACTIVE_FLAGGED,
    },
    OrderStatus.PARTIAL_FILLED: {
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
    },
    OrderStatus.FILLED: {OrderStatus.RECONCILED},
    OrderStatus.RECONCILED: {OrderStatus.ATTRIBUTED},
    OrderStatus.ATTRIBUTED: set(),
    OrderStatus.CANCEL_PENDING: {
        OrderStatus.CANCELLED,
        OrderStatus.CANCELLED_API,
        OrderStatus.FILLED,
    },
    OrderStatus.CANCELLED: set(),
    OrderStatus.CANCELLED_API: set(),
    OrderStatus.INACTIVE_FLAGGED: {
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    },
    OrderStatus.REJECTED: set(),
}

TERMINAL_STATES = {
    OrderStatus.ATTRIBUTED,
    OrderStatus.CANCELLED,
    OrderStatus.CANCELLED_API,
    OrderStatus.REJECTED,
}


class OrderStateMachine:
    """Order state machine with full IBKR state mapping per spec 14 S6.

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

    def handle_inactive_flagged(self, order_id: str, ibkr_message: str) -> dict:
        """Handle IBKR Inactive state — trap state per spec 14 S6.

        IBKR returns Inactive when an order is technically open but will
        not execute (bad limit, risk reject). Midas treats this as a
        rejection and surfaces it to the user.
        """
        self._log.warning(
            "order_state.inactive_flagged",
            order_id=order_id,
            ibkr_message=ibkr_message,
        )
        return {
            "order_id": order_id,
            "action": "flag_inactive",
            "resolution_required": True,
            "message": ibkr_message,
        }
