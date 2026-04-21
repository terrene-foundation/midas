"""Tier 1 unit tests for M15 Execution module.

Tests cover:
- ExecutionAgent: order creation, partial fills, rejection, kill switch
- OrderState: state machine transitions, terminal states, invalid transitions
- RateLimiter: sliding window budget enforcement
- Reconciliation: order-level and daily discrepancy detection
- CostAwareRLChampion: forward pass shape checks, output bounds
- LinearImpactBaseline: impact estimation monotonicity

All async tests use @pytest.mark.asyncio with auto mode.
Database fixtures follow the project pattern (temp-file SQLite via DataFlow).
"""

import os
import tempfile

import numpy as np
import pytest
import torch

from midas.fabric.engine import create_fabric, reset_fabric


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for execution tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_execution.db")
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
    """Start the database for async tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rand_batch(dim1, dim2=None, dim3=None):
    """Return a random float32 tensor of the requested shape."""
    if dim3 is not None:
        return torch.randn(dim1, dim2, dim3)
    if dim2 is not None:
        return torch.randn(dim1, dim2)
    return torch.randn(dim1)


async def _create_test_order(started_db, **overrides):
    """Create a test order and return its id. Defaults to a BUY MARKET order."""
    defaults = {
        "ticker": "SPY",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 100.0,
        "limit_price": 0.0,
        "status": "pending",
        "filled_qty": 0.0,
        "filled_price": 0.0,
        "submitted_at": "",
        "filled_at": "",
        "broker_order_id": "",
        "parent_decision_id": "",
    }
    defaults.update(overrides)
    await started_db.express.create("orders", defaults)
    rows = await started_db.express.list(
        "orders", filter={"ticker": overrides.get("ticker", "SPY")}
    )
    return str(rows[-1]["id"])


# ===================================================================
# OrderStatus constants
# ===================================================================


class TestOrderStatusConstants:
    """Verify OrderStatus exposes all expected status strings."""

    def test_all_statuses_defined(self):
        from midas.execution.order_state import OrderStatus

        expected = {
            "pending",
            "submitted_pending",
            "submitted_waiting",
            "working",
            "partial_filled",
            "filled",
            "reconciled",
            "attributed",
            "cancel_pending",
            "cancelled",
            "cancelled_api",
            "inactive_flagged",
            "rejected",
        }
        for status in expected:
            attr = status.upper()
            assert getattr(OrderStatus, attr) == status

    def test_all_tuple_contains_every_status(self):
        from midas.execution.order_state import OrderStatus

        assert len(OrderStatus.ALL) == 13
        assert OrderStatus.PENDING in OrderStatus.ALL
        assert OrderStatus.SUBMITTED_PENDING in OrderStatus.ALL
        assert OrderStatus.WORKING in OrderStatus.ALL
        assert OrderStatus.PARTIAL_FILLED in OrderStatus.ALL
        assert OrderStatus.FILLED in OrderStatus.ALL
        assert OrderStatus.RECONCILED in OrderStatus.ALL
        assert OrderStatus.ATTRIBUTED in OrderStatus.ALL
        assert OrderStatus.CANCELLED in OrderStatus.ALL
        assert OrderStatus.REJECTED in OrderStatus.ALL


# ===================================================================
# OrderStateMachine — transition logic
# ===================================================================


class TestOrderStateMachineTransitions:
    """Tests for valid and invalid state machine transitions."""

    def test_can_transition_pending_to_submitted_pending(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.PENDING, OrderStatus.SUBMITTED_PENDING) is True

    def test_can_transition_pending_to_cancelled(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.PENDING, OrderStatus.CANCELLED) is True

    def test_cannot_transition_pending_to_filled(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.PENDING, OrderStatus.FILLED) is False

    def test_can_transition_submitted_pending_to_working(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.SUBMITTED_PENDING, OrderStatus.WORKING) is True

    def test_can_transition_working_to_filled(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.WORKING, OrderStatus.FILLED) is True

    def test_can_transition_submitted_pending_to_cancel_pending(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.SUBMITTED_PENDING, OrderStatus.CANCEL_PENDING) is True

    def test_can_transition_submitted_pending_to_rejected(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.SUBMITTED_PENDING, OrderStatus.REJECTED) is True

    def test_can_transition_partial_filled_to_filled(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.PARTIAL_FILLED, OrderStatus.FILLED) is True

    def test_can_transition_partial_filled_to_cancel_pending(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.PARTIAL_FILLED, OrderStatus.CANCEL_PENDING) is True

    def test_can_transition_filled_to_reconciled(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.FILLED, OrderStatus.RECONCILED) is True

    def test_can_transition_reconciled_to_attributed(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.RECONCILED, OrderStatus.ATTRIBUTED) is True

    def test_cannot_transition_working_to_pending(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.WORKING, OrderStatus.PENDING) is False

    def test_cannot_transition_filled_to_working(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition(OrderStatus.FILLED, OrderStatus.WORKING) is False


class TestOrderStateMachineTerminalStates:
    """Tests for terminal state detection."""

    def test_attributed_is_terminal(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.is_terminal(OrderStatus.ATTRIBUTED) is True

    def test_cancelled_is_terminal(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.is_terminal(OrderStatus.CANCELLED) is True

    def test_rejected_is_terminal(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.is_terminal(OrderStatus.REJECTED) is True

    def test_pending_is_not_terminal(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.is_terminal(OrderStatus.PENDING) is False

    def test_working_is_not_terminal(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.is_terminal(OrderStatus.WORKING) is False

    def test_filled_is_not_terminal(self):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        sm = OrderStateMachine()
        assert sm.is_terminal(OrderStatus.FILLED) is False


class TestOrderStateMachineTransition:
    """Tests for the async transition method with database persistence."""

    @pytest.mark.asyncio
    async def test_valid_transition_updates_order_status(self, started_db):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        order_id = await _create_test_order(started_db)
        sm = OrderStateMachine(started_db)
        result = await sm.transition(order_id, OrderStatus.SUBMITTED_PENDING)

        assert result["order_id"] == order_id
        assert result["status"] == OrderStatus.SUBMITTED_PENDING
        assert result["previous_status"] == OrderStatus.PENDING

        # Verify the order was actually updated in the database
        order = await started_db.express.read("orders", order_id)
        assert order["status"] == OrderStatus.SUBMITTED_PENDING

    @pytest.mark.asyncio
    async def test_valid_transition_creates_audit_record(self, started_db):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        order_id = await _create_test_order(started_db)
        sm = OrderStateMachine(started_db)
        await sm.transition(order_id, OrderStatus.SUBMITTED_PENDING)

        rows = await started_db.express.list("audit_log")
        assert len(rows) >= 1
        assert any("order_state_transition" in r.get("rule_name", "") for r in rows)

    @pytest.mark.asyncio
    async def test_invalid_transition_raises_value_error(self, started_db):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        order_id = await _create_test_order(started_db)
        sm = OrderStateMachine(started_db)

        with pytest.raises(ValueError, match="Invalid transition"):
            await sm.transition(order_id, OrderStatus.FILLED)

    @pytest.mark.asyncio
    async def test_transition_from_terminal_state_raises_value_error(self, started_db):
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        order_id = await _create_test_order(started_db, status="cancelled")
        sm = OrderStateMachine(started_db)

        with pytest.raises(ValueError, match="terminal state"):
            await sm.transition(order_id, OrderStatus.SUBMITTED_PENDING)

    @pytest.mark.asyncio
    async def test_transition_without_db_raises_runtime_error(self):
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(db=None)
        with pytest.raises(RuntimeError, match="DataFlow instance"):
            await sm.transition("any-id", OrderStatus.SUBMITTED_PENDING)

    @pytest.mark.asyncio
    async def test_full_lifecycle_pending_to_attributed(self, started_db):
        """Walk the full happy-path lifecycle: pending -> submitted_pending -> working -> partial_filled -> filled -> reconciled -> attributed."""
        from midas.execution.order_state import OrderStatus, OrderStateMachine

        order_id = await _create_test_order(started_db)
        sm = OrderStateMachine(started_db)

        for target in [
            OrderStatus.SUBMITTED_PENDING,
            OrderStatus.WORKING,
            OrderStatus.PARTIAL_FILLED,
            OrderStatus.FILLED,
            OrderStatus.RECONCILED,
            OrderStatus.ATTRIBUTED,
        ]:
            result = await sm.transition(order_id, target)
            assert result["status"] == target

        # Now in terminal state, no further transitions
        with pytest.raises(ValueError, match="terminal state"):
            await sm.transition(order_id, OrderStatus.PENDING)


# ===================================================================
# ExecutionAgent
# ===================================================================


class TestExecutionAgent:
    """Tests for the ExecutionAgent order routing."""

    @pytest.mark.asyncio
    async def test_execute_decision_creates_order(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        decision = {
            "instrument": "QQQ",
            "action": "BUY",
            "quantity": 50.0,
            "order_type": "LIMIT",
            "limit_price": 380.50,
        }
        result = await agent.execute_decision(decision)

        assert "order_id" in result
        assert result["status"] == "pending"
        assert result["fills"] == []

        # Verify the order was persisted
        order = await started_db.express.read("orders", result["order_id"])
        assert order["ticker"] == "QQQ"
        assert order["side"] == "BUY"
        assert order["quantity"] == 50.0
        assert order["order_type"] == "LIMIT"
        assert order["limit_price"] == 380.50

    @pytest.mark.asyncio
    async def test_execute_decision_defaults_to_market_buy(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        decision = {"instrument": "SPY"}
        result = await agent.execute_decision(decision)

        order = await started_db.express.read("orders", result["order_id"])
        assert order["side"] == "BUY"
        assert order["order_type"] == "MARKET"
        assert order["quantity"] == 0

    @pytest.mark.asyncio
    async def test_execute_decision_with_execution_params(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        decision = {"instrument": "IWM", "action": "SELL", "quantity": 200.0}
        result = await agent.execute_decision(decision, {"decision_id": "dec-42"})

        order = await started_db.express.read("orders", result["order_id"])
        assert order["parent_decision_id"] == "dec-42"

    @pytest.mark.asyncio
    async def test_handle_partial_fill_accumulates_quantity(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)

        # Create order in submitted state
        order_id = await _create_test_order(started_db, quantity=100.0, status="submitted")

        fill_1 = await agent.handle_partial_fill(
            order_id,
            {
                "fill_price": 450.00,
                "fill_quantity": 30.0,
            },
        )
        assert fill_1["filled_quantity"] == 30.0
        assert fill_1["status"] == "partial"

        fill_2 = await agent.handle_partial_fill(
            order_id,
            {
                "fill_price": 451.00,
                "fill_quantity": 40.0,
            },
        )
        assert fill_2["filled_quantity"] == 70.0
        assert fill_2["fill_price"] == 451.00

        # Verify the order status was updated
        order = await started_db.express.read("orders", order_id)
        assert order["filled_qty"] == 70.0

    @pytest.mark.asyncio
    async def test_handle_partial_fill_creates_fill_record(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        order_id = await _create_test_order(started_db, quantity=100.0, status="submitted")

        await agent.handle_partial_fill(
            order_id,
            {
                "fill_price": 450.00,
                "fill_quantity": 50.0,
                "commission": 1.00,
                "venue": "ARCA",
            },
        )

        fills = await started_db.express.list("fills", filter={"order_id": order_id})
        assert len(fills) >= 1
        assert fills[0]["fill_price"] == 450.00
        assert fills[0]["fill_qty"] == 50.0
        assert fills[0]["commission"] == 1.00
        assert fills[0]["venue"] == "ARCA"

    @pytest.mark.asyncio
    async def test_handle_rejection_on_submitted_order(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        order_id = await _create_test_order(started_db, status="submitted")

        result = await agent.handle_rejection(order_id, "insufficient margin")
        assert result["status"] == "rejected"

        order = await started_db.express.read("orders", order_id)
        assert order["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_handle_rejection_on_pending_order_cancels(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        order_id = await _create_test_order(started_db, status="pending")

        result = await agent.handle_rejection(order_id, "market closed")
        assert result["status"] == "cancelled"

        order = await started_db.express.read("orders", order_id)
        assert order["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_all_pending_cancels_pending_and_submitted(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)

        # Create orders in various states
        await _create_test_order(started_db, ticker="SPY", status="pending")
        await _create_test_order(started_db, ticker="QQQ", status="submitted")
        await _create_test_order(started_db, ticker="IWM", status="filled")

        cancelled_ids = await agent.cancel_all_pending()
        assert len(cancelled_ids) == 2

        # Verify the filled order was not cancelled
        iwm_orders = await started_db.express.list("orders", filter={"ticker": "IWM"})
        assert iwm_orders[0]["status"] == "filled"

    @pytest.mark.asyncio
    async def test_cancel_all_pending_empty_returns_empty(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        result = await agent.cancel_all_pending()
        assert result == []

    @pytest.mark.asyncio
    async def test_cancel_all_pending_updates_status(self, started_db):
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        order_id = await _create_test_order(started_db, status="pending")

        await agent.cancel_all_pending()
        order = await started_db.express.read("orders", order_id)
        assert order["status"] == "cancelled"


# ===================================================================
# RateLimiter
# ===================================================================


class TestRateLimiter:
    """Tests for the sliding window rate limiter."""

    def test_acquire_within_budget_succeeds(self):
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=10)
        assert limiter.get_remaining_budget() == 10

    @pytest.mark.asyncio
    async def test_single_acquire_returns_true(self):
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=10)
        result = await limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_decrements_remaining_budget(self):
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=10)
        await limiter.acquire()
        assert limiter.get_remaining_budget() == 9

    @pytest.mark.asyncio
    async def test_acquire_up_to_budget_succeeds(self):
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=5)
        for _ in range(5):
            result = await limiter.acquire()
            assert result is True

        assert limiter.get_remaining_budget() == 0

    @pytest.mark.asyncio
    async def test_acquire_exceeding_budget_returns_false(self):
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=3)
        for _ in range(3):
            await limiter.acquire()

        result = await limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_budget_default_is_50(self):
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter()
        assert limiter.get_remaining_budget() == 50

    @pytest.mark.asyncio
    async def test_remaining_budget_never_negative(self):
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=2)
        for _ in range(5):
            await limiter.acquire()
        assert limiter.get_remaining_budget() == 0

    @pytest.mark.asyncio
    async def test_acquire_with_priority_parameter(self):
        """Priority parameter is accepted but shares the same pool."""
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=5)
        result = await limiter.acquire(priority="high")
        assert result is True
        assert limiter.get_remaining_budget() == 4

    @pytest.mark.asyncio
    async def test_multiple_limiters_are_independent(self):
        """Each RateLimiter instance tracks its own budget."""
        from midas.execution.rate_limiter import RateLimiter

        limiter_a = RateLimiter(budget_per_minute=2)
        limiter_b = RateLimiter(budget_per_minute=5)

        await limiter_a.acquire()
        await limiter_a.acquire()

        assert limiter_a.get_remaining_budget() == 0
        assert limiter_b.get_remaining_budget() == 5

        result = await limiter_a.acquire()
        assert result is False

        result = await limiter_b.acquire()
        assert result is True


# ===================================================================
# Reconciliation
# ===================================================================


class TestReconciliation:
    """Tests for post-execution reconciliation."""

    @pytest.mark.asyncio
    async def test_reconcile_matched_order(self, started_db):
        from midas.execution.reconciliation import ReconciliationService

        order_id = await _create_test_order(
            started_db,
            ticker="SPY",
            quantity=100.0,
            limit_price=450.00,
            filled_qty=100.0,
            filled_price=450.00,
            status="filled",
        )

        svc = ReconciliationService(started_db)
        result = await svc.reconcile_order(order_id)

        assert result["order_id"] == order_id
        assert result["matched"] is True
        assert result["discrepancies"] == []

    @pytest.mark.asyncio
    async def test_reconcile_quantity_mismatch(self, started_db):
        from midas.execution.reconciliation import ReconciliationService

        order_id = await _create_test_order(
            started_db,
            ticker="QQQ",
            quantity=100.0,
            filled_qty=80.0,
            status="partial",
        )

        svc = ReconciliationService(started_db)
        result = await svc.reconcile_order(order_id)

        assert result["matched"] is False
        assert len(result["discrepancies"]) >= 1
        qty_disc = [d for d in result["discrepancies"] if d["field"] == "quantity"]
        assert len(qty_disc) == 1
        assert qty_disc[0]["expected"] == 100.0
        assert qty_disc[0]["actual"] == 80.0

    @pytest.mark.asyncio
    async def test_reconcile_price_mismatch(self, started_db):
        from midas.execution.reconciliation import ReconciliationService

        order_id = await _create_test_order(
            started_db,
            ticker="IWM",
            quantity=100.0,
            limit_price=200.00,
            filled_qty=100.0,
            filled_price=205.00,
            status="filled",
        )

        svc = ReconciliationService(started_db)
        result = await svc.reconcile_order(order_id)

        assert result["matched"] is False
        price_disc = [d for d in result["discrepancies"] if d["field"] == "price"]
        assert len(price_disc) == 1
        assert price_disc[0]["expected"] == 200.00
        assert price_disc[0]["actual"] == 205.00

    @pytest.mark.asyncio
    async def test_reconcile_market_order_skips_price_check(self, started_db):
        """Market orders (limit_price=0) should not trigger price discrepancy."""
        from midas.execution.reconciliation import ReconciliationService

        order_id = await _create_test_order(
            started_db,
            ticker="SPY",
            quantity=100.0,
            limit_price=0.0,
            filled_qty=100.0,
            filled_price=455.00,
            status="filled",
        )

        svc = ReconciliationService(started_db)
        result = await svc.reconcile_order(order_id)

        assert result["matched"] is True
        assert result["discrepancies"] == []

    @pytest.mark.asyncio
    async def test_reconcile_price_within_tolerance(self, started_db):
        """Price within 0.01 tolerance is considered matched."""
        from midas.execution.reconciliation import ReconciliationService

        order_id = await _create_test_order(
            started_db,
            ticker="SPY",
            quantity=100.0,
            limit_price=450.00,
            filled_qty=100.0,
            filled_price=450.005,
            status="filled",
        )

        svc = ReconciliationService(started_db)
        result = await svc.reconcile_order(order_id)

        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_reconcile_both_mismatches(self, started_db):
        """Both quantity and price mismatch at the same time."""
        from midas.execution.reconciliation import ReconciliationService

        order_id = await _create_test_order(
            started_db,
            ticker="SPY",
            quantity=100.0,
            limit_price=450.00,
            filled_qty=80.0,
            filled_price=460.00,
            status="partial",
        )

        svc = ReconciliationService(started_db)
        result = await svc.reconcile_order(order_id)

        assert result["matched"] is False
        assert len(result["discrepancies"]) == 2

    @pytest.mark.asyncio
    async def test_daily_reconciliation_returns_summary(self, started_db):
        from midas.execution.reconciliation import ReconciliationService

        # Create two filled orders: one matched, one mismatched
        await _create_test_order(
            started_db,
            ticker="SPY",
            quantity=100.0,
            filled_qty=100.0,
            filled_price=450.00,
            status="filled",
            filled_at="2026-04-16",
        )
        await _create_test_order(
            started_db,
            ticker="QQQ",
            quantity=200.0,
            filled_qty=150.0,
            filled_price=380.00,
            status="filled",
            filled_at="2026-04-16",
        )

        svc = ReconciliationService(started_db)
        result = await svc.daily_reconciliation("2026-04-16")

        assert "total_orders" in result
        assert "matched" in result
        assert "discrepancies" in result
        assert result["as_of_date"] == "2026-04-16"

    @pytest.mark.asyncio
    async def test_daily_reconciliation_empty(self, started_db):
        from midas.execution.reconciliation import ReconciliationService

        svc = ReconciliationService(started_db)
        result = await svc.daily_reconciliation("2026-01-01")

        assert result["total_orders"] == 0
        assert result["matched"] == 0


# ===================================================================
# CostAwareRLChampion — execution head
# ===================================================================


class TestCostAwareRLChampionHead:
    """Tests for the CostAwareRLChampion execution head."""

    def test_output_is_size_and_timing(self):
        from midas.heads.execution import CostAwareRLChampion

        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        order_params = _rand_batch(4, 3)
        venue_features = _rand_batch(4, 5)
        size_frac, timing_score = model(z_t, order_params, venue_features)
        assert size_frac.shape == (4,)
        assert timing_score.shape == (4,)

    def test_size_fraction_is_bounded_0_to_1(self):
        from midas.heads.execution import CostAwareRLChampion

        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(8, 16)
        order_params = _rand_batch(8, 3)
        venue_features = _rand_batch(8, 5)
        size_frac, _ = model(z_t, order_params, venue_features)
        assert (size_frac >= 0).all() and (size_frac <= 1).all()

    def test_timing_score_is_bounded_0_to_1(self):
        from midas.heads.execution import CostAwareRLChampion

        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(8, 16)
        order_params = _rand_batch(8, 3)
        venue_features = _rand_batch(8, 5)
        _, timing_score = model(z_t, order_params, venue_features)
        assert (timing_score >= 0).all() and (timing_score <= 1).all()

    def test_forward_without_venue_features(self):
        """Forward pass works when venue_features is None."""
        from midas.heads.execution import CostAwareRLChampion

        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        order_params = _rand_batch(4, 3)
        size_frac, timing_score = model(z_t, order_params, venue_features=None)
        assert size_frac.shape == (4,)
        assert timing_score.shape == (4,)

    def test_output_is_finite(self):
        from midas.heads.execution import CostAwareRLChampion

        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        order_params = _rand_batch(4, 3)
        venue_features = _rand_batch(4, 5)
        size_frac, timing_score = model(z_t, order_params, venue_features)
        assert torch.isfinite(size_frac).all()
        assert torch.isfinite(timing_score).all()

    def test_single_batch_dimension(self):
        from midas.heads.execution import CostAwareRLChampion

        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(1, 16)
        order_params = _rand_batch(1, 3)
        venue_features = _rand_batch(1, 5)
        size_frac, timing_score = model(z_t, order_params, venue_features)
        assert size_frac.shape == (1,)
        assert timing_score.shape == (1,)

    def test_different_z_dims(self):
        from midas.heads.execution import CostAwareRLChampion

        for z_dim in [8, 32, 64]:
            model = CostAwareRLChampion(z_dim=z_dim, hidden_dim=32)
            z_t = _rand_batch(2, z_dim)
            order_params = _rand_batch(2, 3)
            size_frac, timing_score = model(z_t, order_params)
            assert size_frac.shape == (2,)
            assert timing_score.shape == (2,)

    def test_gradient_flows(self):
        """Verify gradients propagate through both output heads."""
        from midas.heads.execution import CostAwareRLChampion

        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        order_params = _rand_batch(4, 3)
        venue_features = _rand_batch(4, 5)

        z_t.requires_grad_(True)
        size_frac, timing_score = model(z_t, order_params, venue_features)
        loss = size_frac.sum() + timing_score.sum()
        loss.backward()

        assert z_t.grad is not None
        assert torch.isfinite(z_t.grad).all()


# ===================================================================
# LinearImpactBaseline — classical execution model
# ===================================================================


class TestLinearImpactBaseline:
    """Tests for the Almgren-Chriss impact model."""

    def test_output_is_scalar(self):
        from midas.heads.execution import LinearImpactBaseline

        model = LinearImpactBaseline()
        impact = model.estimate_impact(order_size=1000.0, avg_volume=100000.0, volatility=0.2)
        assert isinstance(impact, float)

    def test_impact_is_non_negative(self):
        from midas.heads.execution import LinearImpactBaseline

        model = LinearImpactBaseline()
        impact = model.estimate_impact(order_size=1000.0, avg_volume=100000.0, volatility=0.2)
        assert impact >= 0.0

    def test_larger_order_more_impact(self):
        from midas.heads.execution import LinearImpactBaseline

        model = LinearImpactBaseline()
        small = model.estimate_impact(order_size=100.0, avg_volume=100000.0, volatility=0.2)
        large = model.estimate_impact(order_size=10000.0, avg_volume=100000.0, volatility=0.2)
        assert large > small

    def test_higher_vol_more_impact(self):
        from midas.heads.execution import LinearImpactBaseline

        model = LinearImpactBaseline()
        low = model.estimate_impact(order_size=1000.0, avg_volume=100000.0, volatility=0.1)
        high = model.estimate_impact(order_size=1000.0, avg_volume=100000.0, volatility=0.4)
        assert high > low

    def test_larger_volume_less_impact(self):
        from midas.heads.execution import LinearImpactBaseline

        model = LinearImpactBaseline()
        thin = model.estimate_impact(order_size=1000.0, avg_volume=50000.0, volatility=0.2)
        thick = model.estimate_impact(order_size=1000.0, avg_volume=200000.0, volatility=0.2)
        assert thin > thick

    def test_zero_volume_returns_infinity(self):
        from midas.heads.execution import LinearImpactBaseline

        model = LinearImpactBaseline()
        impact = model.estimate_impact(order_size=1000.0, avg_volume=0.0, volatility=0.2)
        assert impact == float("inf")

    def test_zero_size_returns_zero_impact(self):
        from midas.heads.execution import LinearImpactBaseline

        model = LinearImpactBaseline()
        impact = model.estimate_impact(order_size=0.0, avg_volume=100000.0, volatility=0.2)
        assert impact == 0.0


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge case tests across the execution module."""

    @pytest.mark.asyncio
    async def test_order_state_cannot_transition_from_unknown_status(self):
        """An unrecognized status has no allowed transitions."""
        from midas.execution.order_state import OrderStateMachine

        sm = OrderStateMachine()
        assert sm.can_transition("unknown_status", "pending") is False

    @pytest.mark.asyncio
    async def test_terminal_states_have_no_allowed_transitions(self):
        """All three terminal states have empty transition sets."""
        from midas.execution.order_state import TRANSITIONS, OrderStatus

        for status in [OrderStatus.ATTRIBUTED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            assert len(TRANSITIONS[status]) == 0

    @pytest.mark.asyncio
    async def test_transition_preserves_details_in_audit(self, started_db):
        """Details dict is passed through to the audit record."""
        from midas.execution.order_state import OrderStatus, OrderStateMachine
        import json

        order_id = await _create_test_order(started_db)
        sm = OrderStateMachine(started_db)
        await sm.transition(order_id, OrderStatus.SUBMITTED_PENDING, details={"source": "test"})

        rows = await started_db.express.list("audit_log")
        assert len(rows) >= 1
        latest = rows[-1]
        details = json.loads(latest.get("details", "{}"))
        assert details["source"] == "test"
        assert details["previous_status"] == "pending"
        assert details["new_status"] == "submitted"

    @pytest.mark.asyncio
    async def test_partial_fill_with_zero_quantity(self, started_db):
        """Partial fill with zero quantity does not crash."""
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)
        order_id = await _create_test_order(started_db, quantity=100.0, status="submitted")

        result = await agent.handle_partial_fill(
            order_id,
            {
                "fill_price": 450.00,
                "fill_quantity": 0.0,
            },
        )
        assert result["filled_quantity"] == 0.0

    @pytest.mark.asyncio
    async def test_rate_limiter_repeated_rejection(self):
        """Once budget is exhausted, all subsequent acquires fail."""
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=1)
        await limiter.acquire()

        for _ in range(10):
            assert await limiter.acquire() is False

    @pytest.mark.asyncio
    async def test_reconcile_order_with_null_filled_values(self, started_db):
        """Reconciliation handles orders where filled fields are None/0."""
        from midas.execution.reconciliation import ReconciliationService

        order_id = await _create_test_order(
            started_db,
            ticker="SPY",
            quantity=100.0,
            limit_price=450.00,
            filled_qty=0.0,
            filled_price=0.0,
            status="pending",
        )

        svc = ReconciliationService(started_db)
        result = await svc.reconcile_order(order_id)

        assert result["matched"] is False
        qty_disc = [d for d in result["discrepancies"] if d["field"] == "quantity"]
        assert len(qty_disc) == 1


# ===================================================================
# Rejection Codes
# ===================================================================


class TestRejectionCodes:
    """Tests for IBKR rejection code classification."""

    def test_code_201_classified_as_insufficient_margin(self):
        from midas.execution.rejection_codes import RejectionCategory, classify_rejection

        result = classify_rejection(201, "Insufficient margin")
        assert result.category == RejectionCategory.INSUFFICIENT_MARGIN
        assert result.ibkr_code == 201

    def test_code_202_classified_as_order_limit_exceeded(self):
        from midas.execution.rejection_codes import RejectionCategory, classify_rejection

        result = classify_rejection(202, "Order limit exceeded")
        assert result.category == RejectionCategory.ORDER_LIMIT_EXCEEDED
        assert result.ibkr_code == 202

    def test_code_399_classified_as_invalid_order(self):
        from midas.execution.rejection_codes import RejectionCategory, classify_rejection

        result = classify_rejection(399, "Invalid order parameters")
        assert result.category == RejectionCategory.INVALID_ORDER
        assert result.ibkr_code == 399

    def test_halted_message_classified_as_instrument_halted(self):
        from midas.execution.rejection_codes import RejectionCategory, classify_rejection

        result = classify_rejection(999, "Instrument is halted")
        assert result.category == RejectionCategory.INSTRUMENT_HALTED

    def test_unknown_code_classified_as_unknown(self):
        from midas.execution.rejection_codes import RejectionCategory, classify_rejection

        result = classify_rejection(12345, "Some unknown error")
        assert result.category == RejectionCategory.UNKNOWN

    def test_rejection_code_is_frozen_dataclass(self):
        from midas.execution.rejection_codes import RejectionCode, classify_rejection

        result = classify_rejection(201, "margin")
        assert isinstance(result, RejectionCode)
        assert result.description == "margin"

    def test_rejection_category_enum_values(self):
        from midas.execution.rejection_codes import RejectionCategory

        expected = {
            "INSUFFICIENT_MARGIN",
            "ORDER_LIMIT_EXCEEDED",
            "MARKET_DATA_MISSING",
            "INSTRUMENT_HALTED",
            "INVALID_ORDER",
            "UNKNOWN",
        }
        actual = {cat.name for cat in RejectionCategory}
        assert actual == expected
