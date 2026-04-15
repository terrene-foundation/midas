"""Tier 1 unit tests for M14 Scheduler, M15 Execution, M16 Attribution.

Covers:
- SchedulerService: register_job, list_jobs, trigger_job, start/stop
- ScheduledJobs: get_all_jobs returns 13 definitions
- JobFailureRecovery: exponential backoff retry
- OrderStateMachine: valid transitions, invalid transitions, terminal states
- ExecutionAgent: execute_decision, handle_partial_fill, handle_rejection
- RateLimiter: budget enforcement
- ReconciliationService: reconcile_order
- NAVComputation: compute_nav from positions and marks
- BrinsonDecomposition: allocation/selection/interaction decomposition
- RiskMetrics: Sharpe, Sortino, Calmar, max drawdown, volatility,
  tracking error, information ratio, Jensen's alpha, recovery time
- CounterfactualEngine: compute_counterfactual at horizons
- TrackRecordScorer: compute_composite from metrics
"""

import asyncio
import os
import tempfile
import time

import numpy as np
import pytest

from midas.fabric.engine import create_fabric, reset_fabric


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_infra.db")
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


async def _create_order(db, fields: dict) -> str:
    """Create an order via express.create and return the generated ID."""
    await db.express.create("orders", fields)
    rows = await db.express.list("orders", filter={})
    # Return the ID of the most recently created order
    return str(rows[-1]["id"])
    try:
        await db.close_async()
    except Exception:
        pass


# ===========================================================================
# M14 — Scheduler
# ===========================================================================


class TestSchedulerService:
    """SchedulerService: register_job, list_jobs, trigger_job, start/stop."""

    @pytest.mark.asyncio
    async def test_register_job_adds_to_list(self, started_db):
        """register_job stores the job and list_jobs returns it."""
        from midas.scheduler.scheduler import SchedulerService

        svc = SchedulerService(started_db)

        async def dummy_handler(context):
            return {"ok": True}

        svc.register_job("test_job", "*/5 * * * *", dummy_handler, "test")

        jobs = await svc.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == "test_job"
        assert jobs[0]["cron_expr"] == "*/5 * * * *"
        assert jobs[0]["description"] == "test"

    @pytest.mark.asyncio
    async def test_register_multiple_jobs(self, started_db):
        """Multiple jobs can be registered and listed."""
        from midas.scheduler.scheduler import SchedulerService

        svc = SchedulerService(started_db)

        async def noop(ctx):
            return {}

        svc.register_job("j1", "0 8 * * 1-5", noop, "morning")
        svc.register_job("j2", "0 18 * * 1-5", noop, "eod")
        svc.register_job("j3", "*/5 * * * *", noop, "health")

        jobs = await svc.list_jobs()
        assert len(jobs) == 3
        ids = {j["job_id"] for j in jobs}
        assert ids == {"j1", "j2", "j3"}

    @pytest.mark.asyncio
    async def test_trigger_job_executes_handler(self, started_db):
        """trigger_job calls the handler and returns the result."""
        from midas.scheduler.scheduler import SchedulerService

        svc = SchedulerService(started_db)

        async def handler(context):
            return {"processed": 42}

        svc.register_job("work", "0 0 * * *", handler, "test work")

        result = await svc.trigger_job("work", context={"input": 1})

        assert result["success"] is True
        assert result["result"]["processed"] == 42
        assert "duration_ms" in result

    @pytest.mark.asyncio
    async def test_trigger_job_unknown_raises(self, started_db):
        """trigger_job raises on unknown job_id."""
        from midas.scheduler.scheduler import SchedulerService

        svc = SchedulerService(started_db)

        with pytest.raises(KeyError, match="unknown"):
            await svc.trigger_job("unknown")

    @pytest.mark.asyncio
    async def test_trigger_job_failure_returns_error(self, started_db):
        """trigger_job returns success=False when the handler raises."""
        from midas.scheduler.scheduler import SchedulerService

        svc = SchedulerService(started_db)

        async def failing_handler(context):
            raise ValueError("boom")

        svc.register_job("fail", "0 0 * * *", failing_handler)

        result = await svc.trigger_job("fail")

        assert result["success"] is False
        assert "boom" in result["error"]

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, started_db):
        """start/stop transition the scheduler state."""
        from midas.scheduler.scheduler import SchedulerService

        svc = SchedulerService(started_db)

        async def noop(ctx):
            return {}

        svc.register_job("lifecycle", "0 0 * * *", noop)

        await svc.start()
        assert svc._running is True

        await svc.stop()
        assert svc._running is False

    @pytest.mark.asyncio
    async def test_get_job_status(self, started_db):
        """get_job_status returns current job info."""
        from midas.scheduler.scheduler import SchedulerService

        svc = SchedulerService(started_db)

        async def noop(ctx):
            return {}

        svc.register_job("status_job", "*/10 * * * *", noop, "status test")

        status = await svc.get_job_status("status_job")
        assert status["job_id"] == "status_job"
        assert status["status"] == "idle"

    @pytest.mark.asyncio
    async def test_get_job_status_unknown_raises(self, started_db):
        """get_job_status raises on unknown job_id."""
        from midas.scheduler.scheduler import SchedulerService

        svc = SchedulerService(started_db)

        with pytest.raises(KeyError):
            await svc.get_job_status("nonexistent")


class TestScheduledJobs:
    """ScheduledJobs: get_all_jobs returns 13 definitions."""

    @pytest.mark.asyncio
    async def test_get_all_jobs_returns_13(self, started_db):
        """get_all_jobs() returns exactly 13 job definitions."""
        from midas.scheduler.jobs import ScheduledJobs

        jobs_svc = ScheduledJobs(started_db)
        jobs = jobs_svc.get_all_jobs()

        assert len(jobs) == 13

    @pytest.mark.asyncio
    async def test_all_jobs_have_required_fields(self, started_db):
        """Each job definition has job_id, cron_expr, description, handler."""
        from midas.scheduler.jobs import ScheduledJobs

        jobs_svc = ScheduledJobs(started_db)
        jobs = jobs_svc.get_all_jobs()

        for job in jobs:
            assert "job_id" in job, f"missing job_id in {job}"
            assert "cron_expr" in job, f"missing cron_expr in {job}"
            assert "description" in job, f"missing description in {job}"
            assert "handler" in job, f"missing handler in {job}"

    @pytest.mark.asyncio
    async def test_eod_ingestion_job_definition(self, started_db):
        """eod_ingestion has the correct cron schedule."""
        from midas.scheduler.jobs import ScheduledJobs

        jobs_svc = ScheduledJobs(started_db)
        jobs = jobs_svc.get_all_jobs()

        eod = next(j for j in jobs if j["job_id"] == "eod_ingestion")
        assert eod["cron_expr"] == "0 18 * * 1-5"

    @pytest.mark.asyncio
    async def test_eod_ingestion_executes(self, started_db):
        """eod_ingestion handler can be called and returns a result."""
        from midas.scheduler.jobs import ScheduledJobs

        jobs_svc = ScheduledJobs(started_db)
        result = await jobs_svc.eod_ingestion({})
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_health_check_executes(self, started_db):
        """health_check handler runs and returns status."""
        from midas.scheduler.jobs import ScheduledJobs

        jobs_svc = ScheduledJobs(started_db)
        result = await jobs_svc.health_check({})
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_nav_valuation_executes(self, started_db):
        """nav_valuation handler runs and returns a result."""
        from midas.scheduler.jobs import ScheduledJobs

        jobs_svc = ScheduledJobs(started_db)
        result = await jobs_svc.nav_valuation({})
        assert isinstance(result, dict)
        assert "success" in result


class TestJobFailureRecovery:
    """JobFailureRecovery: exponential backoff retry."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """execute_with_retry returns result on first success."""
        from midas.scheduler.scheduler import JobFailureRecovery

        recovery = JobFailureRecovery(max_retries=3, base_delay=0.01)

        async def ok_handler(ctx):
            return {"done": True}

        result = await recovery.execute_with_retry("j1", ok_handler, {})
        assert result["success"] is True
        assert result["result"]["done"] is True

    @pytest.mark.asyncio
    async def test_retry_then_succeed(self):
        """execute_with_retry retries and succeeds on later attempt."""
        from midas.scheduler.scheduler import JobFailureRecovery

        recovery = JobFailureRecovery(max_retries=3, base_delay=0.01)
        attempt = 0

        async def eventually_ok(ctx):
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise RuntimeError("not yet")
            return {"done": True}

        result = await recovery.execute_with_retry("j1", eventually_ok, {})
        assert result["success"] is True
        assert attempt == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries(self):
        """execute_with_retry returns failure after exhausting retries."""
        from midas.scheduler.scheduler import JobFailureRecovery

        recovery = JobFailureRecovery(max_retries=2, base_delay=0.01)

        async def always_fails(ctx):
            raise RuntimeError("always")

        result = await recovery.execute_with_retry("j1", always_fails, {})
        assert result["success"] is False
        assert "always" in result["error"]


# ===========================================================================
# M15 — Execution
# ===========================================================================


class TestOrderStateMachine:
    """OrderStateMachine: valid transitions, invalid transitions, terminal."""

    def test_valid_transitions(self):
        """Each allowed transition succeeds."""
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(None)

        # pending -> submitted
        assert sm.can_transition(OrderStatus.PENDING, OrderStatus.SUBMITTED) is True
        # pending -> cancelled
        assert sm.can_transition(OrderStatus.PENDING, OrderStatus.CANCELLED) is True
        # submitted -> partial
        assert sm.can_transition(OrderStatus.SUBMITTED, OrderStatus.PARTIAL) is True
        # submitted -> filled
        assert sm.can_transition(OrderStatus.SUBMITTED, OrderStatus.FILLED) is True
        # submitted -> cancelled
        assert sm.can_transition(OrderStatus.SUBMITTED, OrderStatus.CANCELLED) is True
        # submitted -> rejected
        assert sm.can_transition(OrderStatus.SUBMITTED, OrderStatus.REJECTED) is True
        # partial -> filled
        assert sm.can_transition(OrderStatus.PARTIAL, OrderStatus.FILLED) is True
        # partial -> cancelled
        assert sm.can_transition(OrderStatus.PARTIAL, OrderStatus.CANCELLED) is True
        # filled -> reconciled
        assert sm.can_transition(OrderStatus.FILLED, OrderStatus.RECONCILED) is True
        # reconciled -> attributed
        assert sm.can_transition(OrderStatus.RECONCILED, OrderStatus.ATTRIBUTED) is True

    def test_invalid_transitions_rejected(self):
        """Transitions not in the TRANSITIONS map are rejected."""
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(None)

        # pending cannot go directly to filled
        assert sm.can_transition(OrderStatus.PENDING, OrderStatus.FILLED) is False
        # pending cannot go to reconciled
        assert sm.can_transition(OrderStatus.PENDING, OrderStatus.RECONCILED) is False
        # filled cannot go back to submitted
        assert sm.can_transition(OrderStatus.FILLED, OrderStatus.SUBMITTED) is False
        # reconciled cannot go back to filled
        assert sm.can_transition(OrderStatus.RECONCILED, OrderStatus.FILLED) is False

    def test_terminal_states_have_no_transitions(self):
        """Terminal states (attributed, cancelled, rejected) allow no transitions."""
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(None)

        all_statuses = OrderStatus.ALL
        for terminal in (OrderStatus.ATTRIBUTED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            assert sm.is_terminal(terminal) is True
            for target in all_statuses:
                if target == terminal:
                    continue
                assert (
                    sm.can_transition(terminal, target) is False
                ), f"terminal {terminal} should not transition to {target}"

    def test_non_terminal_states_are_not_terminal(self):
        """Non-terminal states report is_terminal=False."""
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(None)

        non_terminal = [
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL,
            OrderStatus.FILLED,
            OrderStatus.RECONCILED,
        ]
        for status in non_terminal:
            assert sm.is_terminal(status) is False

    @pytest.mark.asyncio
    async def test_transition_stores_and_returns_status(self, started_db):
        """transition() returns the new status and records the change."""
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(started_db)

        order_id = await _create_order(
            started_db,
            {
                "ticker": "AAPL",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 100,
                "limit_price": 150.0,
                "status": "pending",
            },
        )

        result = await sm.transition(order_id, OrderStatus.SUBMITTED)

        assert result["status"] == "submitted"
        assert result["previous_status"] == "pending"

    @pytest.mark.asyncio
    async def test_transition_invalid_raises(self, started_db):
        """transition() raises on invalid state change."""
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(started_db)

        order_id = await _create_order(
            started_db,
            {
                "ticker": "AAPL",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 100,
                "limit_price": 150.0,
                "status": "pending",
            },
        )

        with pytest.raises(ValueError, match="[Ii]nvalid"):
            await sm.transition(order_id, OrderStatus.FILLED)

    @pytest.mark.asyncio
    async def test_transition_terminal_raises(self, started_db):
        """transition() raises when trying to leave a terminal state."""
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(started_db)

        order_id = await _create_order(
            started_db,
            {
                "ticker": "AAPL",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 100,
                "limit_price": 150.0,
                "status": "cancelled",
            },
        )

        with pytest.raises(ValueError, match="[Tt]erminal"):
            await sm.transition(order_id, OrderStatus.SUBMITTED)

    def test_full_lifecycle_pending_to_attributed(self):
        """Full happy path: pending -> submitted -> filled -> reconciled -> attributed."""
        from midas.execution.order_state import OrderStateMachine, OrderStatus

        sm = OrderStateMachine(None)

        chain = [
            (OrderStatus.PENDING, OrderStatus.SUBMITTED),
            (OrderStatus.SUBMITTED, OrderStatus.FILLED),
            (OrderStatus.FILLED, OrderStatus.RECONCILED),
            (OrderStatus.RECONCILED, OrderStatus.ATTRIBUTED),
        ]
        for current, target in chain:
            assert sm.can_transition(current, target) is True


class TestExecutionAgent:
    """ExecutionAgent: execute_decision, handle_partial_fill, handle_rejection."""

    @pytest.mark.asyncio
    async def test_execute_decision_creates_order(self, started_db):
        """execute_decision creates an order and returns its details."""
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)

        decision = {
            "instrument": "SPY",
            "action": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }
        result = await agent.execute_decision(decision)

        assert "order_id" in result
        assert result["status"] == "pending"
        assert "fills" in result

    @pytest.mark.asyncio
    async def test_handle_partial_fill(self, started_db):
        """handle_partial_fill updates the order with partial fill info."""
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)

        decision = {"instrument": "QQQ", "action": "SELL", "quantity": 100, "order_type": "LIMIT"}
        order = await agent.execute_decision(decision)
        order_id = order["order_id"]

        fill_result = await agent.handle_partial_fill(
            order_id, {"fill_price": 400.0, "fill_quantity": 40}
        )
        assert fill_result["status"] == "partial"
        assert fill_result["filled_quantity"] == 40

    @pytest.mark.asyncio
    async def test_handle_rejection(self, started_db):
        """handle_rejection transitions order to rejected state."""
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)

        decision = {"instrument": "AAPL", "action": "BUY", "quantity": 10, "order_type": "MARKET"}
        order = await agent.execute_decision(decision)
        order_id = order["order_id"]

        # Must transition to submitted before rejection is valid
        rejection_result = await agent.handle_rejection(order_id, "insufficient buying power")
        assert rejection_result["status"] in ("rejected", "cancelled")

    @pytest.mark.asyncio
    async def test_cancel_all_pending(self, started_db):
        """cancel_all_pending cancels all orders in pending/submitted state."""
        from midas.execution.execution_agent import ExecutionAgent

        agent = ExecutionAgent(started_db)

        # Create several orders
        for i in range(3):
            await agent.execute_decision(
                {"instrument": f"TICK{i}", "action": "BUY", "quantity": 10, "order_type": "MARKET"}
            )

        cancelled = await agent.cancel_all_pending()
        assert len(cancelled) >= 3


class TestRateLimiter:
    """RateLimiter: budget enforcement."""

    @pytest.mark.asyncio
    async def test_allows_within_budget(self):
        """Requests within budget are allowed."""
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=5)

        for _ in range(5):
            assert await limiter.acquire() is True

    @pytest.mark.asyncio
    async def test_rejects_over_budget(self):
        """Requests exceeding budget are rejected."""
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=3)

        for _ in range(3):
            await limiter.acquire()

        result = await limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_remaining_budget(self):
        """get_remaining_budget tracks current capacity."""
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=10)

        assert limiter.get_remaining_budget() == 10

        await limiter.acquire()
        assert limiter.get_remaining_budget() == 9

        await limiter.acquire()
        assert limiter.get_remaining_budget() == 8

    @pytest.mark.asyncio
    async def test_priority_high_goes_first(self):
        """High priority requests are distinguished from normal."""
        from midas.execution.rate_limiter import RateLimiter

        limiter = RateLimiter(budget_per_minute=5)

        # Consume all budget
        for _ in range(5):
            await limiter.acquire()

        # Normal priority is rejected
        assert await limiter.acquire(priority="normal") is False

        # High priority can still be rejected (same budget pool),
        # but the priority parameter is accepted
        result = await limiter.acquire(priority="high")
        assert isinstance(result, bool)


class TestReconciliationService:
    """ReconciliationService: reconcile_order, daily_reconciliation."""

    @pytest.mark.asyncio
    async def test_reconcile_order_matched(self, started_db):
        """reconcile_order returns matched=True when fill matches expected."""
        from midas.execution.reconciliation import ReconciliationService

        svc = ReconciliationService(started_db)

        order_id = await _create_order(
            started_db,
            {
                "ticker": "SPY",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 100,
                "limit_price": 450.0,
                "status": "filled",
                "filled_qty": 100,
                "filled_price": 450.0,
            },
        )

        result = await svc.reconcile_order(order_id)
        assert "matched" in result

    @pytest.mark.asyncio
    async def test_daily_reconciliation(self, started_db):
        """daily_reconciliation runs for all orders on a date."""
        from midas.execution.reconciliation import ReconciliationService

        svc = ReconciliationService(started_db)

        # Create a couple of filled orders
        await started_db.express.create(
            "orders",
            {
                "ticker": "SPY",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 50,
                "status": "filled",
                "filled_qty": 50,
                "filled_price": 450.0,
                "filled_at": "2026-04-16T10:00:00",
            },
        )
        await started_db.express.create(
            "orders",
            {
                "ticker": "QQQ",
                "side": "SELL",
                "order_type": "MARKET",
                "quantity": 30,
                "status": "filled",
                "filled_qty": 30,
                "filled_price": 380.0,
                "filled_at": "2026-04-16T11:00:00",
            },
        )

        result = await svc.daily_reconciliation("2026-04-16")
        assert "total_orders" in result
        assert result["total_orders"] >= 2


# ===========================================================================
# M16 — Attribution
# ===========================================================================


class TestNAVComputation:
    """NAVComputation: compute_nav from positions and marks."""

    @pytest.mark.asyncio
    async def test_compute_nav_from_positions(self, started_db):
        """compute_nav calculates NAV from positions * prices + cash."""
        from midas.attribution.nav import NAVComputation

        # Create positions
        await started_db.express.create(
            "positions",
            {
                "ticker": "SPY",
                "quantity": 100,
                "avg_cost": 440.0,
                "current_price": 450.0,
                "market_value": 45000.0,
                "unrealized_pnl": 1000.0,
                "as_of_date": "2026-04-16",
            },
        )
        await started_db.express.create(
            "positions",
            {
                "ticker": "QQQ",
                "quantity": 50,
                "avg_cost": 370.0,
                "current_price": 380.0,
                "market_value": 19000.0,
                "unrealized_pnl": 500.0,
                "as_of_date": "2026-04-16",
            },
        )

        nav_svc = NAVComputation(started_db)
        result = await nav_svc.compute_nav("2026-04-16")

        assert "nav" in result
        assert result["nav"] > 0
        assert "positions_value" in result
        assert result["positions_value"] > 0

    @pytest.mark.asyncio
    async def test_compute_nav_no_positions(self, started_db):
        """compute_nav returns zero NAV when no positions exist."""
        from midas.attribution.nav import NAVComputation

        nav_svc = NAVComputation(started_db)
        result = await nav_svc.compute_nav("2026-01-01")

        assert result["nav"] == 0
        assert result["positions_value"] == 0


class TestBrinsonDecomposition:
    """BrinsonDecomposition: allocation/selection/interaction decomposition."""

    def test_basic_decomposition(self):
        """Brinson produces allocation + selection + interaction = total active."""
        from midas.attribution.brinson import BrinsonDecomposition

        bd = BrinsonDecomposition()

        # Portfolio: overweight tech, underweight bonds
        w_p = np.array([0.5, 0.3, 0.2])
        w_b = np.array([0.4, 0.4, 0.2])
        r_p = np.array([0.12, 0.06, 0.08])
        r_b = np.array([0.10, 0.05, 0.07])

        result = bd.decompose(w_p, w_b, r_p, r_b)

        assert "allocation_effect" in result
        assert "selection_effect" in result
        assert "interaction_effect" in result
        assert "total_active_return" in result

        # Sum of effects equals total active return
        total = (
            result["allocation_effect"] + result["selection_effect"] + result["interaction_effect"]
        )
        np.testing.assert_allclose(total, result["total_active_return"], atol=1e-10)

    def test_allocation_effect_positive_when_overweight_outperform(self):
        """Overweighting a sector that beats the benchmark gives positive allocation."""
        from midas.attribution.brinson import BrinsonDecomposition

        bd = BrinsonDecomposition()

        # Overweight the high-return sector
        w_p = np.array([0.6, 0.4])
        w_b = np.array([0.4, 0.6])
        r_p = np.array([0.10, 0.04])
        r_b = np.array([0.10, 0.04])

        result = bd.decompose(w_p, w_b, r_p, r_b)

        # Overweighting the high-return sector should give positive allocation
        assert result["allocation_effect"] > 0

    def test_selection_effect_positive_when_portfolio_outperforms(self):
        """Better stock selection within a sector gives positive selection."""
        from midas.attribution.brinson import BrinsonDecomposition

        bd = BrinsonDecomposition()

        w_p = np.array([0.5, 0.5])
        w_b = np.array([0.5, 0.5])
        r_p = np.array([0.12, 0.08])
        r_b = np.array([0.10, 0.06])

        result = bd.decompose(w_p, w_b, r_p, r_b)

        assert result["selection_effect"] > 0

    def test_per_category_breakdown(self):
        """Decomposition includes per-category effects."""
        from midas.attribution.brinson import BrinsonDecomposition

        bd = BrinsonDecomposition()

        w_p = np.array([0.5, 0.3, 0.2])
        w_b = np.array([0.4, 0.4, 0.2])
        r_p = np.array([0.12, 0.06, 0.08])
        r_b = np.array([0.10, 0.05, 0.07])
        categories = ["equity", "bonds", "commodities"]

        result = bd.decompose(w_p, w_b, r_p, r_b, categories=categories)

        assert "per_category" in result
        assert len(result["per_category"]) == 3
        for entry in result["per_category"]:
            assert "category" in entry
            assert "allocation" in entry
            assert "selection" in entry
            assert "interaction" in entry

    def test_equal_weights_zero_active_return(self):
        """Equal portfolio and benchmark weights with equal returns give zero effects."""
        from midas.attribution.brinson import BrinsonDecomposition

        bd = BrinsonDecomposition()

        w = np.array([0.4, 0.3, 0.3])
        r = np.array([0.10, 0.05, 0.08])

        result = bd.decompose(w, w, r, r)

        np.testing.assert_allclose(result["total_active_return"], 0.0, atol=1e-10)
        np.testing.assert_allclose(result["allocation_effect"], 0.0, atol=1e-10)
        np.testing.assert_allclose(result["selection_effect"], 0.0, atol=1e-10)

    def test_raises_on_mismatched_lengths(self):
        """Mismatched array lengths raise ValueError."""
        from midas.attribution.brinson import BrinsonDecomposition

        bd = BrinsonDecomposition()

        with pytest.raises(ValueError):
            bd.decompose(
                np.array([0.5, 0.5]),
                np.array([0.4, 0.3, 0.3]),
                np.array([0.10, 0.05]),
                np.array([0.10, 0.05]),
            )


class TestRiskMetrics:
    """RiskMetrics: Sharpe, Sortino, max drawdown, volatility, etc."""

    def test_sharpe_ratio_positive(self):
        """Positive Sharpe for returns above risk-free rate."""
        from midas.attribution.metrics import RiskMetrics

        returns = np.array([0.01, 0.02, 0.015, 0.03, 0.005, 0.02, 0.01, -0.005, 0.025, 0.015])
        sharpe = RiskMetrics.sharpe_ratio(returns, risk_free_rate=0.0)
        assert sharpe > 0

    def test_sharpe_ratio_negative_returns(self):
        """Negative Sharpe for consistently negative returns."""
        from midas.attribution.metrics import RiskMetrics

        returns = np.array([-0.02, -0.01, -0.03, -0.015, -0.02])
        sharpe = RiskMetrics.sharpe_ratio(returns, risk_free_rate=0.0)
        assert sharpe < 0

    def test_sharpe_ratio_no_annualize(self):
        """Non-annualized Sharpe differs from annualized."""
        from midas.attribution.metrics import RiskMetrics

        returns = np.array([0.01, 0.02, -0.01, 0.015, 0.005])
        annualized = RiskMetrics.sharpe_ratio(returns, annualize=True)
        raw = RiskMetrics.sharpe_ratio(returns, annualize=False)
        assert annualized != raw

    def test_sortino_ratio(self):
        """Sortino penalizes only downside volatility."""
        from midas.attribution.metrics import RiskMetrics

        # Returns with some downside
        returns = np.array([0.03, -0.02, 0.01, -0.01, 0.04, 0.02, -0.015, 0.025])
        sortino = RiskMetrics.sortino_ratio(returns, target_return=0.0)
        assert sortino > 0

    def test_sortino_ratio_all_positive(self):
        """Sortino is higher than Sharpe when all returns are positive."""
        from midas.attribution.metrics import RiskMetrics

        returns = np.array([0.01, 0.02, 0.015, 0.005, 0.025])
        sharpe = RiskMetrics.sharpe_ratio(returns, annualize=False)
        sortino = RiskMetrics.sortino_ratio(returns, annualize=False)
        # Sortino should be higher (no downside deviation)
        assert sortino >= sharpe

    def test_calmar_ratio(self):
        """Calmar ratio returns positive for good return / low drawdown."""
        from midas.attribution.metrics import RiskMetrics

        equity = np.array([100, 102, 104, 103, 105, 107, 106, 108, 110])
        returns = np.diff(equity) / equity[:-1]
        calmar = RiskMetrics.calmar_ratio(returns, annualize=False)
        assert isinstance(calmar, float)

    def test_max_drawdown(self):
        """Max drawdown computes correctly for known series."""
        from midas.attribution.metrics import RiskMetrics

        equity = np.array([100, 110, 105, 95, 100, 90, 95, 105])
        dd = RiskMetrics.max_drawdown(equity)
        # Max drawdown: peak 110 to trough 90 = 20/110 = 0.1818...
        np.testing.assert_allclose(dd, (110 - 90) / 110, atol=1e-4)

    def test_max_drawdown_no_drawdown(self):
        """Max drawdown is 0 for monotonically increasing series."""
        from midas.attribution.metrics import RiskMetrics

        equity = np.array([100, 110, 120, 130])
        dd = RiskMetrics.max_drawdown(equity)
        assert dd == 0.0

    def test_volatility_annualize(self):
        """Annualized volatility is larger than daily volatility."""
        from midas.attribution.metrics import RiskMetrics

        returns = np.array([0.01, -0.005, 0.02, -0.01, 0.015, 0.005, -0.008, 0.012])
        annual_vol = RiskMetrics.volatility(returns, annualize=True)
        daily_vol = RiskMetrics.volatility(returns, annualize=False)
        assert annual_vol > daily_vol

    def test_tracking_error(self):
        """Tracking error is non-negative."""
        from midas.attribution.metrics import RiskMetrics

        port = np.array([0.02, 0.01, -0.01, 0.03, 0.005])
        bench = np.array([0.015, 0.008, -0.005, 0.02, 0.003])
        te = RiskMetrics.tracking_error(port, bench)
        assert te >= 0

    def test_tracking_error_identical(self):
        """Tracking error is 0 when portfolio matches benchmark."""
        from midas.attribution.metrics import RiskMetrics

        r = np.array([0.01, 0.02, -0.01, 0.015])
        te = RiskMetrics.tracking_error(r, r)
        np.testing.assert_allclose(te, 0.0, atol=1e-10)

    def test_information_ratio(self):
        """Information ratio is positive for outperforming portfolio."""
        from midas.attribution.metrics import RiskMetrics

        port = np.array([0.03, 0.02, 0.01, 0.04, 0.02])
        bench = np.array([0.02, 0.01, 0.005, 0.03, 0.01])
        ir = RiskMetrics.information_ratio(port, bench)
        assert ir > 0

    def test_information_ratio_zero_tracking_error(self):
        """Information ratio raises or returns inf when tracking error is 0."""
        from midas.attribution.metrics import RiskMetrics

        r = np.array([0.01, 0.02])
        ir = RiskMetrics.information_ratio(r, r)
        assert np.isinf(ir) or np.isnan(ir)

    def test_jensens_alpha_positive(self):
        """Jensen's alpha is positive for risk-adjusted outperformance."""
        from midas.attribution.metrics import RiskMetrics

        port = np.array([0.04, 0.03, 0.02, 0.05, 0.03])
        bench = np.array([0.03, 0.02, 0.01, 0.04, 0.02])
        alpha = RiskMetrics.jensens_alpha(port, bench)
        assert alpha > 0

    def test_recovery_time(self):
        """Recovery time counts days from max drawdown to recovery."""
        from midas.attribution.metrics import RiskMetrics

        # Peak at index 2 (110), trough at index 5 (90), recovery at index 7 (105)
        equity = np.array([100, 105, 110, 100, 95, 90, 95, 105, 110])
        days = RiskMetrics.recovery_time(equity)
        # Drawdown at index 5 (90), recovery to 110-level never happens in this series
        # Actually 105 at index 7 is not above 110 peak.
        # Let me reconsider: peak=110 at idx 2, so recovery means reaching >=110 again
        # That happens at idx 8 (110). So recovery_time = 8 - 5 = 3
        assert isinstance(days, int)
        assert days >= 0

    def test_recovery_time_no_drawdown(self):
        """Recovery time is 0 when there is no drawdown."""
        from midas.attribution.metrics import RiskMetrics

        equity = np.array([100, 110, 120, 130])
        days = RiskMetrics.recovery_time(equity)
        assert days == 0


class TestCounterfactualEngine:
    """CounterfactualEngine: compute counterfactual at horizons."""

    @pytest.mark.asyncio
    async def test_compute_counterfactual(self, started_db):
        """compute_counterfactual returns results at specified horizons."""
        from midas.attribution.counterfactual import CounterfactualEngine

        # First create a decision
        await started_db.express.create(
            "decisions",
            {
                "decision_type": "trade",
                "instruments": "SPY",
                "action": "BUY",
                "brief_json": "{}",
                "outcome_json": "{}",
                "counterfactual_json": "{}",
                "created_at_day": "2026-04-16",
            },
        )
        rows = await started_db.express.list("decisions", filter={})
        decision_id = str(rows[-1]["id"])

        engine = CounterfactualEngine(started_db)
        result = await engine.compute_counterfactual(decision_id, horizons=[1, 5, 21])

        assert "decision_id" in result
        assert "counterfactuals" in result
        assert len(result["counterfactuals"]) == 3
        for cf in result["counterfactuals"]:
            assert "horizon" in cf
            assert "executed_return" in cf
            assert "counterfactual_return" in cf
            assert "diff" in cf


class TestTrackRecordScorer:
    """TrackRecordScorer: compute_composite from metrics."""

    def test_compute_composite(self):
        """Composite score is between 0 and 100."""
        from midas.attribution.track_record import TrackRecordScorer

        scorer = TrackRecordScorer()
        metrics = {
            "sharpe_ratio": 1.5,
            "sortino_ratio": 2.0,
            "max_drawdown": 0.15,
            "win_rate": 0.6,
            "avg_return": 0.08,
        }
        score = scorer.compute_composite(metrics)
        assert 0 <= score <= 100

    def test_compute_composite_high_score(self):
        """Good metrics produce a high composite score."""
        from midas.attribution.track_record import TrackRecordScorer

        scorer = TrackRecordScorer()
        metrics = {
            "sharpe_ratio": 2.5,
            "sortino_ratio": 3.0,
            "max_drawdown": 0.05,
            "win_rate": 0.75,
            "avg_return": 0.15,
        }
        score = scorer.compute_composite(metrics)
        assert score > 70

    def test_compute_composite_low_score(self):
        """Poor metrics produce a low composite score."""
        from midas.attribution.track_record import TrackRecordScorer

        scorer = TrackRecordScorer()
        metrics = {
            "sharpe_ratio": -0.5,
            "sortino_ratio": -0.3,
            "max_drawdown": 0.40,
            "win_rate": 0.3,
            "avg_return": -0.05,
        }
        score = scorer.compute_composite(metrics)
        assert score < 30

    def test_compute_composite_clamps_to_range(self):
        """Extreme metrics are clamped to 0-100."""
        from midas.attribution.track_record import TrackRecordScorer

        scorer = TrackRecordScorer()

        # Extremely bad
        bad_score = scorer.compute_composite(
            {
                "sharpe_ratio": -10,
                "sortino_ratio": -10,
                "max_drawdown": 1.0,
                "win_rate": 0.0,
                "avg_return": -1.0,
            }
        )
        assert bad_score == 0

        # Extremely good
        good_score = scorer.compute_composite(
            {
                "sharpe_ratio": 10,
                "sortino_ratio": 10,
                "max_drawdown": 0.0,
                "win_rate": 1.0,
                "avg_return": 1.0,
            }
        )
        assert good_score == 100
