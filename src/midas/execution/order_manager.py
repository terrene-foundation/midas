"""OrderManager — orchestrates order lifecycle from submission through terminal state.

Single entry point for all order state changes. Validates every transition
through the state machine, classifies IBKR rejections, persists transitions
for audit, and surfaces user-actionable states via notification dispatch.

Ref: specs/14-ibkr-integration.md S6-S7, rules/facade-manager-detection.md
"""

import time

import structlog
from dataflow import DataFlow

from midas.execution.order_state import (
    IllegalTransitionError,
    OrderStateMachine,
    TerminalStateError,
)
from midas.execution.rejection_codes import classify_rejection
from midas.fabric.models import OrderState

logger = structlog.get_logger("midas.execution.order_manager")


class NotificationDispatch:
    """Thin notification abstraction for order events.

    Logs at INFO + writes to audit_log so rejection events are never lost.
    Wave 4 wires this to actual delivery channels.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = structlog.get_logger("midas.execution.notification_dispatch")

    async def dispatch(self, event_type: str, payload: dict) -> None:
        self._log.info("notification.dispatch", event_type=event_type, **payload)
        try:
            await self._db.express.create(
                "audit_log",
                {
                    "audit_id": f"notification:{event_type}:{int(time.time() * 1000)}",
                    "rule_name": f"notification_{event_type}",
                    "action": event_type,
                    "details": str(payload),
                    "agent": "notification_dispatch",
                    "period_end": "",
                    "filed_at": "",
                    "z_t_snapshot": "",
                },
            )
        except Exception as exc:
            self._log.error("notification.dispatch_failed", error=str(exc))


class OrderManager:
    """Orchestrates order lifecycle through the state machine.

    Constructor receives DataFlow explicitly (no global lookup).
    Every state change goes through the state machine — no direct OrderState
    mutation. Every transition is persisted to fabric before returning.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._sm = OrderStateMachine(db)
        self._notify = NotificationDispatch(db)
        self._log = structlog.get_logger("midas.execution.order_manager")

    async def submit_order(self, order_params: dict) -> dict:
        """Create an order in PENDING state and return its record.

        Parameters
        ----------
        order_params : dict
            Must include: ticker, side, quantity, order_type.
            May include: limit_price, parent_decision_id.

        Returns
        -------
        dict
            {order_id, status, order}
        """
        instrument = order_params["ticker"]
        side = order_params.get("side", "BUY")
        order_type = order_params.get("order_type", "MARKET")
        quantity = order_params.get("quantity", 0)
        limit_price = order_params.get("limit_price", 0.0)

        self._log.info(
            "order_manager.submit_order",
            instrument=instrument,
            side=side,
            quantity=quantity,
            order_type=order_type,
        )

        row = {
            "ticker": instrument,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "limit_price": limit_price,
            "status": OrderState.PENDING.value,
            "filled_qty": 0.0,
            "filled_price": 0.0,
            "submitted_at": "",
            "filled_at": "",
            "broker_order_id": "",
            "parent_decision_id": order_params.get("parent_decision_id", ""),
        }

        await self._db.express.create("orders", row)

        # Retrieve the generated ID (express.create does not return it)
        rows = await self._db.express.list("orders", filter={"ticker": instrument})
        order = rows[-1] if rows else None
        order_id = str(order["id"]) if order else ""

        self._log.info("order_manager.order_created", order_id=order_id)
        return {
            "order_id": order_id,
            "status": OrderState.PENDING.value,
            "order": order,
        }

    async def cancel_order(self, order_id: str) -> dict:
        """Transition an order to CANCEL_PENDING.

        Only allowed from PENDING, SUBMITTED_PENDING, SUBMITTED_WAITING, WORKING.
        """
        self._log.info("order_manager.cancel_order", order_id=order_id)

        try:
            result = await self._sm.transition(
                order_id, OrderState.CANCEL_PENDING, reason="user_cancel"
            )
        except (IllegalTransitionError, TerminalStateError) as exc:
            self._log.warning(
                "order_manager.cancel_failed",
                order_id=order_id,
                error=str(exc),
            )
            return {"order_id": order_id, "status": "cancel_failed", "error": str(exc)}

        return result

    async def process_ibkr_status_update(
        self,
        order_id: str,
        ibkr_status: str,
        *,
        ibkr_code: int | None = None,
        ibkr_message: str | None = None,
        fill_quantity: float | None = None,
        fill_price: float | None = None,
    ) -> dict:
        """Single entry point for IBKR-driven state transitions.

        Maps the raw IBKR status string to an OrderState, validates the
        transition, classifies rejections, and persists everything.

        Parameters
        ----------
        order_id : str
            The internal order ID.
        ibkr_status : str
            Raw IBKR status string (e.g. "Submitted", "Filled").
        ibkr_code : int, optional
            IBKR error code for rejections.
        ibkr_message : str, optional
            Human-readable message from IBKR.
        fill_quantity : float, optional
            Fill quantity for partial/full fills.
        fill_price : float, optional
            Fill price for partial/full fills.

        Returns
        -------
        dict
            {order_id, status, transition, rejection}
        """
        new_state = OrderState.from_ibkr(ibkr_status)

        self._log.info(
            "order_manager.process_ibkr_status",
            order_id=order_id,
            ibkr_status=ibkr_status,
            mapped_state=new_state.value,
        )

        # Handle inactive_flagged trap state
        if new_state == OrderState.INACTIVE_FLAGGED:
            inactive_result = self._sm.handle_inactive_flagged(
                order_id, ibkr_message or ibkr_status
            )
            await self._notify.dispatch(
                "order_inactive_flagged",
                {"order_id": order_id, "ibkr_message": ibkr_message},
            )
            # Still try the transition (INACTIVE_FLAGGED is allowed from WORKING/SUBMITTED_WAITING)
            try:
                await self._sm.transition(
                    order_id,
                    new_state,
                    reason="ibkr_inactive",
                    ibkr_message=ibkr_message,
                )
            except (IllegalTransitionError, TerminalStateError):
                pass
            return {
                "order_id": order_id,
                "status": new_state.value,
                "inactive": inactive_result,
            }

        # Classify rejections before transitioning
        rejection = None
        if new_state == OrderState.REJECTED and ibkr_code is not None:
            rejection = classify_rejection(ibkr_code, ibkr_message or "")
            self._log.warning(
                "order_manager.rejection_classified",
                order_id=order_id,
                category=rejection.category.value,
                severity=rejection.category.severity,
            )

            # Dispatch notification for user-actionable rejections
            if rejection.category.requires_user_alert:
                await self._notify.dispatch(
                    "order_rejected",
                    {
                        "order_id": order_id,
                        "category": rejection.category.value,
                        "ibkr_code": ibkr_code,
                        "message": ibkr_message,
                    },
                )

            # Kill outstanding orders for halted instruments
            if rejection.category.kills_outstanding:
                await self._kill_outstanding_for_instrument(order_id)

        # Idempotent update: same state (e.g. additional partial fill)
        order = await self._db.express.read("orders", order_id)
        if order and order.get("status") == new_state.value:
            self._log.info(
                "order_manager.idempotent_update",
                order_id=order_id,
                state=new_state.value,
            )
            # Still update fill quantity if provided
            if new_state == OrderState.PARTIAL_FILLED and fill_quantity is not None:
                current_filled = order.get("filled_qty") or 0.0
                new_filled = current_filled + fill_quantity
                update = {"filled_qty": new_filled}
                if fill_price is not None:
                    update["filled_price"] = fill_price
                await self._db.express.update("orders", order_id, update)

            return {
                "order_id": order_id,
                "status": new_state.value,
                "transition": None,
                "rejection": None,
            }

        # Perform the state machine transition
        try:
            transition = await self._sm.transition(
                order_id,
                new_state,
                reason=f"ibkr_status_update:{ibkr_status}",
                ibkr_message=ibkr_message,
            )
        except IllegalTransitionError as exc:
            self._log.warning(
                "order_manager.illegal_ibkr_transition",
                order_id=order_id,
                ibkr_status=ibkr_status,
                mapped_state=new_state.value,
                error=str(exc),
            )
            return {
                "order_id": order_id,
                "status": "transition_rejected",
                "error": str(exc),
            }
        except TerminalStateError as exc:
            self._log.warning(
                "order_manager.terminal_transition_attempt",
                order_id=order_id,
                error=str(exc),
            )
            return {
                "order_id": order_id,
                "status": "already_terminal",
                "error": str(exc),
            }

        # Update fill quantity for partial fills without terminal state change
        if new_state == OrderState.PARTIAL_FILLED and fill_quantity is not None:
            order = await self._db.express.read("orders", order_id)
            current_filled = (order.get("filled_qty") or 0.0) if order else 0.0
            new_filled = current_filled + fill_quantity
            update = {"filled_qty": new_filled}
            if fill_price is not None:
                update["filled_price"] = fill_price
            await self._db.express.update("orders", order_id, update)

        return {
            "order_id": order_id,
            "status": new_state.value,
            "transition": transition,
            "rejection": (
                {
                    "category": rejection.category.value,
                    "ibkr_code": rejection.ibkr_code,
                    "severity": rejection.category.severity,
                    "auto_retry": rejection.category.should_auto_retry,
                }
                if rejection
                else None
            ),
        }

    async def get_order_state(self, order_id: str) -> dict:
        """Read the current state of an order.

        Returns
        -------
        dict
            {order_id, status, is_terminal, is_working}
        """
        order = await self._db.express.read("orders", order_id)
        if not order:
            raise ValueError(f"Order '{order_id}' not found")

        status = OrderState(order["status"])
        return {
            "order_id": order_id,
            "status": status.value,
            "is_terminal": status.is_terminal(),
            "is_working": status.is_working(),
            "order": order,
        }

    async def _kill_outstanding_for_instrument(self, order_id: str) -> int:
        """Cancel all outstanding orders for the same instrument.

        Used when a rejection category triggers kills_outstanding (e.g. halted).
        """
        order = await self._db.express.read("orders", order_id)
        if not order:
            return 0

        instrument = order.get("ticker", "")
        cancellable = [
            OrderState.PENDING.value,
            OrderState.SUBMITTED_PENDING.value,
            OrderState.SUBMITTED_WAITING.value,
            OrderState.WORKING.value,
        ]

        cancelled = 0
        for status in cancellable:
            try:
                orders = await self._db.express.list(
                    "orders", filter={"ticker": instrument, "status": status}
                )
                for o in orders:
                    oid = str(o["id"])
                    if oid == order_id:
                        continue
                    try:
                        await self._sm.transition(
                            oid, OrderState.CANCEL_PENDING, reason="halt_kill"
                        )
                        cancelled += 1
                    except (IllegalTransitionError, TerminalStateError):
                        pass
            except Exception as exc:
                self._log.error(
                    "order_manager.kill_outstanding_failed",
                    instrument=instrument,
                    status=status,
                    error=str(exc),
                )

        if cancelled:
            self._log.warning(
                "order_manager.killed_outstanding",
                instrument=instrument,
                cancelled=cancelled,
            )
        return cancelled
