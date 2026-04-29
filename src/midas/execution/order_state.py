"""Order state machine for IBKR execution lifecycle.

Uses the canonical OrderState enum from fabric/models.py as the single source
of truth for all order states. Enforces legal transitions per spec 14 S6 and
audits every transition to the audit_log fabric table.

Ref: specs/14-ibkr-integration.md S6 (Order State Machine)
"""

import json
import time

import structlog
from dataflow import DataFlow

from midas.fabric.models import OrderState

logger = structlog.get_logger("midas.execution.order_state")


class IllegalTransitionError(Exception):
    """Raised when an order state transition is not allowed."""

    def __init__(self, order_id: str, from_state: OrderState, to_state: OrderState):
        self.order_id = order_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Order '{order_id}': illegal transition " f"'{from_state.value}' -> '{to_state.value}'"
        )


class TerminalStateError(Exception):
    """Raised when attempting to transition from a terminal state."""

    def __init__(self, order_id: str, state: OrderState):
        self.order_id = order_id
        self.state = state
        super().__init__(
            f"Order '{order_id}' is in terminal state '{state.value}' — "
            f"no further transitions allowed"
        )


# Transition table: OrderState -> set of allowed target OrderStates.
# Covers both IBKR-driven transitions and Midas-internal lifecycle (PENDING,
# RECONCILED, ATTRIBUTED).
TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.PENDING: {
        OrderState.SUBMITTED_PENDING,
        OrderState.CANCEL_PENDING,
        OrderState.CANCELLED,
        OrderState.REJECTED,
    },
    OrderState.SUBMITTED_PENDING: {
        OrderState.SUBMITTED_WAITING,
        OrderState.WORKING,
        OrderState.CANCEL_PENDING,
        OrderState.REJECTED,
    },
    OrderState.SUBMITTED_WAITING: {
        OrderState.WORKING,
        OrderState.PARTIAL_FILLED,
        OrderState.CANCEL_PENDING,
        OrderState.REJECTED,
        OrderState.INACTIVE_FLAGGED,
    },
    OrderState.WORKING: {
        OrderState.PARTIAL_FILLED,
        OrderState.FILLED,
        OrderState.CANCEL_PENDING,
        OrderState.REJECTED,
        OrderState.INACTIVE_FLAGGED,
    },
    OrderState.PARTIAL_FILLED: {
        OrderState.FILLED,
        OrderState.CANCEL_PENDING,
    },
    OrderState.FILLED: {
        OrderState.RECONCILED,
    },
    OrderState.RECONCILED: {
        OrderState.ATTRIBUTED,
    },
    OrderState.ATTRIBUTED: set(),
    OrderState.CANCEL_PENDING: {
        OrderState.CANCELLED,
        OrderState.CANCELLED_API,
        OrderState.FILLED,
    },
    OrderState.CANCELLED: set(),
    OrderState.CANCELLED_API: set(),
    OrderState.INACTIVE_FLAGGED: {
        OrderState.CANCELLED,
        OrderState.REJECTED,
    },
    OrderState.REJECTED: set(),
}

TERMINAL_STATES: set[OrderState] = OrderState.terminal_states()


class OrderStateMachine:
    """Order state machine with full IBKR state mapping per spec 14 S6.

    Transition table is defined by the TRANSITIONS constant above.
    Every transition is audited. Uses OrderState enum from fabric/models.py
    as the canonical type.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = structlog.get_logger("midas.execution.order_state")

    @staticmethod
    def can_transition(current: OrderState, target: OrderState) -> bool:
        """Check if transitioning from current to target status is allowed."""
        allowed = TRANSITIONS.get(current, set())
        return target in allowed

    @staticmethod
    def is_terminal(status: OrderState) -> bool:
        """Check if the status is terminal (no further transitions possible)."""
        return status in TERMINAL_STATES

    async def transition(
        self,
        order_id: str,
        new_status: OrderState,
        *,
        reason: str = "",
        ibkr_message: str | None = None,
    ) -> dict:
        """Transition order status. Audits every transition.

        Raises IllegalTransitionError if the transition is not allowed.
        Raises TerminalStateError if the current state is terminal.
        """
        order = await self._db.express.read("orders", order_id)
        raw_status = order.get("status") if order else None
        if not raw_status:
            raise ValueError(f"Order '{order_id}' not found or has no status")
        current_status = OrderState(raw_status)

        if self.is_terminal(current_status):
            raise TerminalStateError(order_id, current_status)

        if not self.can_transition(current_status, new_status):
            raise IllegalTransitionError(order_id, current_status, new_status)

        await self._db.express.update(
            "orders",
            order_id,
            {"status": new_status.value},
        )

        self._log.info(
            "order_state.transition",
            order_id=order_id,
            previous_status=current_status.value,
            new_status=new_status.value,
            reason=reason,
        )

        # Audit the transition
        details = {
            "previous_status": current_status.value,
            "new_status": new_status.value,
            "reason": reason,
        }
        if ibkr_message:
            details["ibkr_message"] = ibkr_message

        try:
            await self._db.express.create(
                "audit_log",
                {
                    "audit_id": f"order_transition:{order_id}:{new_status.value}:{int(time.time() * 1000)}",
                    "rule_name": "order_state_transition",
                    "action": new_status.value,
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
            "status": new_status.value,
            "previous_status": current_status.value,
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
