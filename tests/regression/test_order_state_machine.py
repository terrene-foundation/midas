"""Regression tests for IBKR order state machine lifecycle.

Covers: all non-terminal states reachable from SUBMITTED_PENDING, terminal
states block transitions, inactive_flagged trap, all 8+ rejection codes
classified, unknown IBKR code falls to UNKNOWN, risk rejection never
auto-retries, halted kills outstanding, partial fill updates quantity not state.

Ref: specs/14-ibkr-integration.md S6-S7
"""

import os
import tempfile

import pytest

from midas.execution.order_state import (
    IllegalTransitionError,
    OrderStateMachine,
    TerminalStateError,
    TRANSITIONS,
)
from midas.execution.order_manager import OrderManager
from midas.execution.rejection_codes import RejectionCategory, classify_rejection
from midas.fabric.engine import create_fabric, reset_fabric
from midas.fabric.models import OrderState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_order_sm.db")
    db_url = f"sqlite:///{db_path}"
    database = create_fabric(database_url=db_url, auto_migrate=True)
    yield database
    try:
        database.close()
    except Exception:
        pass
    reset_fabric()
    for suffix in ("-wal", "-shm"):
        try:
            os.unlink(db_path + suffix)
        except OSError:
            pass
    try:
        os.unlink(db_path)
    except OSError:
        pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


@pytest.fixture
async def started_db(db):
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


async def _create_order(started_db, **overrides):
    defaults = {
        "ticker": "AAPL",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 100.0,
        "limit_price": 185.0,
        "status": OrderState.PENDING.value,
        "filled_qty": 0.0,
        "filled_price": 0.0,
        "submitted_at": "",
        "filled_at": "",
        "broker_order_id": "IB-12345",
        "parent_decision_id": "",
    }
    defaults.update(overrides)
    await started_db.express.create("orders", defaults)
    rows = await started_db.express.list("orders")
    return str(rows[-1]["id"])


# ---------------------------------------------------------------------------
# R8.1 — All non-terminal states reachable from SUBMITTED_PENDING
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestStateReachability:
    """All IBKR-mapped states must be reachable from SUBMITTED_PENDING."""

    @pytest.mark.asyncio
    async def test_all_ibkr_states_reachable(self):
        reachable: set[OrderState] = set()
        frontier = {OrderState.SUBMITTED_PENDING}
        visited: set[OrderState] = set()

        while frontier:
            current = frontier.pop()
            visited.add(current)
            for target in TRANSITIONS.get(current, set()):
                reachable.add(target)
                if target not in visited:
                    frontier.add(target)

        ibkr_states = {
            OrderState.SUBMITTED_WAITING,
            OrderState.WORKING,
            OrderState.PARTIAL_FILLED,
            OrderState.FILLED,
            OrderState.CANCEL_PENDING,
            OrderState.CANCELLED,
            OrderState.CANCELLED_API,
            OrderState.INACTIVE_FLAGGED,
        }
        for state in ibkr_states:
            assert state in reachable, f"{state.value} not reachable from SUBMITTED_PENDING"


# ---------------------------------------------------------------------------
# R8.2 — Terminal states block transitions
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestTerminalBlock:
    @pytest.mark.asyncio
    async def test_cancelled_blocks_all_transitions(self, started_db):
        oid = await _create_order(started_db, status=OrderState.CANCELLED.value)
        sm = OrderStateMachine(started_db)
        for state in OrderState:
            if state == OrderState.CANCELLED:
                continue
            assert not sm.can_transition(OrderState.CANCELLED, state)

    @pytest.mark.asyncio
    async def test_cancelled_api_blocks_all_transitions(self):
        for state in OrderState:
            if state == OrderState.CANCELLED_API:
                continue
            assert not OrderStateMachine.can_transition(OrderState.CANCELLED_API, state)

    @pytest.mark.asyncio
    async def test_attributed_blocks_all_transitions(self):
        for state in OrderState:
            if state == OrderState.ATTRIBUTED:
                continue
            assert not OrderStateMachine.can_transition(OrderState.ATTRIBUTED, state)

    @pytest.mark.asyncio
    async def test_rejected_blocks_all_transitions(self):
        for state in OrderState:
            if state == OrderState.REJECTED:
                continue
            assert not OrderStateMachine.can_transition(OrderState.REJECTED, state)


# ---------------------------------------------------------------------------
# R8.3 — inactive_flagged is a trap state
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestInactiveFlagged:
    @pytest.mark.asyncio
    async def test_inactive_flagged_only_allows_cancel_or_reject(self):
        allowed = TRANSITIONS[OrderState.INACTIVE_FLAGGED]
        assert allowed == {OrderState.CANCELLED, OrderState.REJECTED}
        assert OrderState.WORKING not in allowed
        assert OrderState.SUBMITTED_PENDING not in allowed

    @pytest.mark.asyncio
    async def test_inactive_flagged_surfaces_user_notification(self, started_db):
        oid = await _create_order(started_db, status=OrderState.WORKING.value)
        om = OrderManager(started_db)
        result = await om.process_ibkr_status_update(
            oid, "Inactive", ibkr_message="Order is inactive — bad limit price"
        )
        assert result["status"] == OrderState.INACTIVE_FLAGGED.value
        assert result["inactive"]["resolution_required"] is True


# ---------------------------------------------------------------------------
# R8.4 — All rejection codes classified
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRejectionClassification:
    def test_risk_code_201(self):
        r = classify_rejection(201, "Order rejected by risk management")
        assert r.category == RejectionCategory.RISK
        assert r.category.severity == "critical"
        assert not r.category.should_auto_retry

    def test_cancelled_risk_code_202(self):
        r = classify_rejection(202, "Order cancelled by risk")
        assert r.category == RejectionCategory.CANCELLED_RISK
        assert r.category.severity == "medium"

    def test_info_code_399(self):
        r = classify_rejection(399, "Forwarded to destination")
        assert r.category == RejectionCategory.INFO
        assert r.category.severity == "low"
        assert r.category.should_auto_retry

    def test_margin_message(self):
        r = classify_rejection(999, "Insufficient margin for this order")
        assert r.category == RejectionCategory.MARGIN
        assert r.category.severity == "critical"
        assert not r.category.should_auto_retry

    def test_halted_message(self):
        r = classify_rejection(999, "Instrument is halted")
        assert r.category == RejectionCategory.HALTED
        assert r.category.kills_outstanding
        assert r.category.severity == "high"

    def test_no_data_message(self):
        r = classify_rejection(999, "No market data permission")
        assert r.category == RejectionCategory.NO_DATA

    def test_price_band_message(self):
        r = classify_rejection(999, "Price outside range")
        assert r.category == RejectionCategory.PRICE_BAND
        assert r.category.should_auto_retry

    def test_contract_message(self):
        r = classify_rejection(999, "Unknown contract specified")
        assert r.category == RejectionCategory.CONTRACT


# ---------------------------------------------------------------------------
# R8.5 — Unknown IBKR code falls to UNKNOWN
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestUnknownFallback:
    def test_unknown_code_classified(self):
        r = classify_rejection(99999, "Something unprecedented happened")
        assert r.category == RejectionCategory.UNKNOWN
        assert r.ibkr_code == 99999

    def test_empty_message_unknown_code(self):
        r = classify_rejection(7777, "")
        assert r.category == RejectionCategory.UNKNOWN


# ---------------------------------------------------------------------------
# R8.6 — Risk rejection never auto-retries
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRiskNoAutoRetry:
    def test_risk_no_retry(self):
        r = classify_rejection(201, "Risk reject")
        assert not r.category.should_auto_retry

    def test_margin_no_retry(self):
        r = classify_rejection(999, "Insufficient margin")
        assert not r.category.should_auto_retry

    @pytest.mark.asyncio
    async def test_risk_rejection_surfaces_alert(self, started_db):
        oid = await _create_order(started_db, status=OrderState.SUBMITTED_PENDING.value)
        om = OrderManager(started_db)
        result = await om.process_ibkr_status_update(
            oid, "Rejected", ibkr_code=201, ibkr_message="Risk management rejection"
        )
        assert result["rejection"] is not None
        assert result["rejection"]["category"] == "rejected.risk"
        assert not result["rejection"]["auto_retry"]


# ---------------------------------------------------------------------------
# R8.7 — Halted kills outstanding
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestHaltedKillsOutstanding:
    @pytest.mark.asyncio
    async def test_halted_cancels_sibling_orders(self, started_db):
        # Create two orders for the same instrument
        oid1 = await _create_order(
            started_db, ticker="TSLA", status=OrderState.WORKING.value, broker_order_id="IB-001"
        )
        oid2 = await _create_order(
            started_db,
            ticker="TSLA",
            status=OrderState.SUBMITTED_PENDING.value,
            broker_order_id="IB-002",
        )
        om = OrderManager(started_db)

        # Halt rejection on oid1 should cancel oid2
        result = await om.process_ibkr_status_update(
            oid1, "Rejected", ibkr_code=999, ibkr_message="Instrument is halted"
        )
        assert result["rejection"]["category"] == "rejected.halted"

        # oid2 should have been transitioned toward a terminal/cancelling state
        order2 = await started_db.express.read("orders", oid2)
        status2 = order2.get("status", "") if order2 else ""
        assert status2 in (
            OrderState.CANCEL_PENDING.value,
            OrderState.CANCELLED.value,
            OrderState.REJECTED.value,
        ), f"oid2 status '{status2}' should be cancelled or rejected after halt kill"


# ---------------------------------------------------------------------------
# R8.8 — Partial fill updates quantity not state
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestPartialFill:
    @pytest.mark.asyncio
    async def test_partial_fill_updates_quantity(self, started_db):
        oid = await _create_order(
            started_db, status=OrderState.WORKING.value, quantity=100.0, filled_qty=0.0
        )
        om = OrderManager(started_db)

        result = await om.process_ibkr_status_update(
            oid, "PartiallyFilled", fill_quantity=40.0, fill_price=185.50
        )
        assert result["status"] == OrderState.PARTIAL_FILLED.value

        order = await started_db.express.read("orders", oid)
        assert order["filled_qty"] == 40.0
        assert order["filled_price"] == 185.50

    @pytest.mark.asyncio
    async def test_partial_fill_accumulates(self, started_db):
        oid = await _create_order(
            started_db, status=OrderState.PARTIAL_FILLED.value, quantity=100.0, filled_qty=40.0
        )
        om = OrderManager(started_db)

        await om.process_ibkr_status_update(
            oid, "PartiallyFilled", fill_quantity=35.0, fill_price=186.0
        )

        order = await started_db.express.read("orders", oid)
        assert order["filled_qty"] == 75.0


# ---------------------------------------------------------------------------
# R8.9 — OrderManager full lifecycle end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestOrderManagerLifecycle:
    @pytest.mark.asyncio
    async def test_full_happy_path(self, started_db):
        om = OrderManager(started_db)

        # Submit
        submit_result = await om.submit_order(
            {
                "ticker": "SPY",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 50.0,
                "limit_price": 500.0,
            }
        )
        oid = submit_result["order_id"]
        assert submit_result["status"] == OrderState.PENDING.value

        # IBKR acknowledges
        r = await om.process_ibkr_status_update(oid, "PendingSubmit")
        assert r["status"] == OrderState.SUBMITTED_PENDING.value

        # Goes working
        r = await om.process_ibkr_status_update(oid, "Submitted")
        assert r["status"] == OrderState.WORKING.value

        # Partial fill
        r = await om.process_ibkr_status_update(
            oid, "PartiallyFilled", fill_quantity=25.0, fill_price=500.10
        )
        assert r["status"] == OrderState.PARTIAL_FILLED.value

        # Full fill
        r = await om.process_ibkr_status_update(
            oid, "Filled", fill_quantity=25.0, fill_price=500.15
        )
        assert r["status"] == OrderState.FILLED.value

        # FILLED is not terminal — it still needs reconciliation
        state = await om.get_order_state(oid)
        assert state["is_terminal"] is False

        # Reconcile and attribute to reach terminal state
        sm = OrderStateMachine(started_db)
        await sm.transition(oid, OrderState.RECONCILED)
        await sm.transition(oid, OrderState.ATTRIBUTED)

        state = await om.get_order_state(oid)
        assert state["is_terminal"] is True
        assert state["status"] == OrderState.ATTRIBUTED.value

    @pytest.mark.asyncio
    async def test_cancel_path(self, started_db):
        om = OrderManager(started_db)
        submit_result = await om.submit_order(
            {"ticker": "QQQ", "side": "SELL", "order_type": "MARKET", "quantity": 10.0}
        )
        oid = submit_result["order_id"]

        await om.process_ibkr_status_update(oid, "PendingSubmit")
        await om.process_ibkr_status_update(oid, "Submitted")

        # User cancels
        cancel_result = await om.cancel_order(oid)
        assert cancel_result["status"] == OrderState.CANCEL_PENDING.value

        # IBKR confirms cancellation
        r = await om.process_ibkr_status_update(oid, "Cancelled")
        assert r["status"] == OrderState.CANCELLED.value
