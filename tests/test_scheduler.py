"""Tier 1 unit tests for the Midas scheduler module.

Tests cover:
- SchedulerService: register_job, trigger_job, list_jobs, get_job_status, start/stop
- JobFailureRecovery: exponential backoff retry logic
- ScheduledJobs: all 13 job definitions smoke tests
- Edge cases: concurrent triggers, failed job recovery, job not found
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midas.scheduler.jobs import JOB_DEFINITIONS, ScheduledJobs
from midas.scheduler.scheduler import JobFailureRecovery, SchedulerService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """DataFlow mock that does not require a real database."""
    db = MagicMock(name="DataFlow")
    db.express = MagicMock()
    db.express.list = AsyncMock(return_value=[])
    return db


@pytest.fixture
def scheduler(mock_db):
    """SchedulerService backed by a mock database."""
    return SchedulerService(mock_db)


@pytest.fixture
def recovery():
    """JobFailureRecovery with short delays so tests run fast."""
    return JobFailureRecovery(max_retries=3, base_delay=0.01)


@pytest.fixture
def scheduled_jobs(mock_db):
    """ScheduledJobs backed by a mock database."""
    return ScheduledJobs(mock_db)


def _make_handler(return_value=None, side_effect=None):
    """Create an async handler for test jobs."""
    handler = AsyncMock()
    if return_value is not None:
        handler.return_value = return_value
    if side_effect is not None:
        handler.side_effect = side_effect
    return handler


# ---------------------------------------------------------------------------
# SchedulerService — register_job
# ---------------------------------------------------------------------------


class TestSchedulerServiceRegisterJob:
    def test_register_job_stores_correct_fields(self, scheduler):
        """register_job stores the job with all expected fields."""
        handler = _make_handler(return_value={"ok": True})
        scheduler.register_job(
            job_id="test_job",
            cron_expr="0 * * * *",
            handler=handler,
            description="A test job",
            max_retries=5,
        )
        assert "test_job" in scheduler._jobs
        job = scheduler._jobs["test_job"]
        assert job["job_id"] == "test_job"
        assert job["cron_expr"] == "0 * * * *"
        assert job["handler"] is handler
        assert job["description"] == "A test job"
        assert job["max_retries"] == 5
        assert job["status"] == "idle"
        assert job["last_run"] is None
        assert job["last_result"] is None

    def test_register_job_default_max_retries(self, scheduler):
        """register_job defaults max_retries to 3."""
        handler = _make_handler()
        scheduler.register_job("j1", "0 * * * *", handler)
        assert scheduler._jobs["j1"]["max_retries"] == 3

    def test_register_job_overwrites_duplicate(self, scheduler):
        """Registering the same job_id overwrites the previous entry."""
        handler_v1 = _make_handler(return_value={"v": 1})
        handler_v2 = _make_handler(return_value={"v": 2})
        scheduler.register_job("dup", "0 * * * *", handler_v1)
        scheduler.register_job("dup", "*/5 * * * *", handler_v2, description="updated")
        assert scheduler._jobs["dup"]["cron_expr"] == "*/5 * * * *"
        assert scheduler._jobs["dup"]["description"] == "updated"
        assert scheduler._jobs["dup"]["handler"] is handler_v2

    def test_register_multiple_jobs(self, scheduler):
        """Multiple distinct job_ids can be registered."""
        for i in range(5):
            scheduler.register_job(f"job_{i}", "0 * * * *", _make_handler())
        assert len(scheduler._jobs) == 5


# ---------------------------------------------------------------------------
# SchedulerService — trigger_job
# ---------------------------------------------------------------------------


class TestSchedulerServiceTriggerJob:
    @pytest.mark.asyncio
    async def test_trigger_job_success(self, scheduler):
        """trigger_job returns success dict with result and duration."""
        handler = _make_handler(return_value={"rows": 42})
        scheduler.register_job("ok_job", "0 * * * *", handler)

        result = await scheduler.trigger_job("ok_job")

        assert result["success"] is True
        assert result["result"] == {"rows": 42}
        assert isinstance(result["duration_ms"], float)
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_trigger_job_passes_context(self, scheduler):
        """trigger_job passes context dict to the handler."""
        captured = {}

        async def capture_handler(ctx):
            captured.update(ctx)
            return {"ok": True}

        scheduler.register_job("ctx_job", "0 * * * *", capture_handler)
        await scheduler.trigger_job("ctx_job", context={"key": "value", "num": 7})

        assert captured == {"key": "value", "num": 7}

    @pytest.mark.asyncio
    async def test_trigger_job_default_empty_context(self, scheduler):
        """trigger_job uses empty dict when no context provided."""
        captured = {}

        async def capture_handler(ctx):
            captured.update(ctx)
            return {}

        scheduler.register_job("def_ctx", "0 * * * *", capture_handler)
        await scheduler.trigger_job("def_ctx")

        assert captured == {}

    @pytest.mark.asyncio
    async def test_trigger_job_not_found_raises_key_error(self, scheduler):
        """trigger_job raises KeyError for an unregistered job_id."""
        with pytest.raises(KeyError, match="not_a_job"):
            await scheduler.trigger_job("not_a_job")

    @pytest.mark.asyncio
    async def test_trigger_job_handler_error_returns_failure(self, scheduler):
        """trigger_job catches handler exception and returns failure dict."""
        handler = _make_handler(side_effect=RuntimeError("db connection lost"))
        scheduler.register_job("fail_job", "0 * * * *", handler)

        result = await scheduler.trigger_job("fail_job")

        assert result["success"] is False
        assert "db connection lost" in result["error"]
        assert isinstance(result["duration_ms"], float)

    @pytest.mark.asyncio
    async def test_trigger_job_updates_last_run(self, scheduler):
        """trigger_job sets last_run and last_result after execution."""
        handler = _make_handler(return_value={"processed": 10})
        scheduler.register_job("lr_job", "0 * * * *", handler)

        assert scheduler._jobs["lr_job"]["last_run"] is None
        await scheduler.trigger_job("lr_job")

        assert scheduler._jobs["lr_job"]["last_run"] is not None
        assert scheduler._jobs["lr_job"]["last_result"] == {"processed": 10}

    @pytest.mark.asyncio
    async def test_trigger_job_status_transitions(self, scheduler):
        """Job status transitions to 'running' during execution and back to 'idle'."""
        statuses_seen = []

        async def slow_handler(ctx):
            statuses_seen.append(scheduler._jobs["slow"]["status"])
            await asyncio.sleep(0.01)
            return {"ok": True}

        scheduler.register_job("slow", "0 * * * *", slow_handler)

        assert scheduler._jobs["slow"]["status"] == "idle"
        await scheduler.trigger_job("slow")
        assert scheduler._jobs["slow"]["status"] == "idle"
        assert "running" in statuses_seen

    @pytest.mark.asyncio
    async def test_trigger_job_status_idle_after_failure(self, scheduler):
        """Job status returns to idle even when handler raises."""
        handler = _make_handler(side_effect=ValueError("boom"))
        scheduler.register_job("fail_idle", "0 * * * *", handler)

        await scheduler.trigger_job("fail_idle")
        assert scheduler._jobs["fail_idle"]["status"] == "idle"


# ---------------------------------------------------------------------------
# SchedulerService — get_job_status
# ---------------------------------------------------------------------------


class TestSchedulerServiceGetJobStatus:
    @pytest.mark.asyncio
    async def test_get_job_status_returns_all_fields(self, scheduler):
        """get_job_status returns a complete status dict."""
        handler = _make_handler(return_value={"ok": True})
        scheduler.register_job("stat_job", "*/10 * * * *", handler, description="status test")

        status = await scheduler.get_job_status("stat_job")

        assert status["job_id"] == "stat_job"
        assert status["cron_expr"] == "*/10 * * * *"
        assert status["description"] == "status test"
        assert status["status"] == "idle"
        assert status["last_run"] is None
        assert status["last_result"] is None

    @pytest.mark.asyncio
    async def test_get_job_status_after_trigger(self, scheduler):
        """get_job_status reflects results after a trigger."""
        handler = _make_handler(return_value={"done": True})
        scheduler.register_job("ran_job", "0 * * * *", handler)
        await scheduler.trigger_job("ran_job")

        status = await scheduler.get_job_status("ran_job")

        assert status["last_run"] is not None
        assert status["last_result"] == {"done": True}

    @pytest.mark.asyncio
    async def test_get_job_status_not_found_raises(self, scheduler):
        """get_job_status raises KeyError for unregistered job."""
        with pytest.raises(KeyError, match="missing_job"):
            await scheduler.get_job_status("missing_job")


# ---------------------------------------------------------------------------
# SchedulerService — list_jobs
# ---------------------------------------------------------------------------


class TestSchedulerServiceListJobs:
    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, scheduler):
        """list_jobs returns empty list when no jobs registered."""
        jobs = await scheduler.list_jobs()
        assert jobs == []

    @pytest.mark.asyncio
    async def test_list_jobs_returns_all(self, scheduler):
        """list_jobs returns entries for every registered job."""
        for i in range(4):
            scheduler.register_job(f"lj_{i}", f"{i} * * * *", _make_handler())

        jobs = await scheduler.list_jobs()

        assert len(jobs) == 4
        job_ids = {j["job_id"] for j in jobs}
        assert job_ids == {"lj_0", "lj_1", "lj_2", "lj_3"}

    @pytest.mark.asyncio
    async def test_list_jobs_schema(self, scheduler):
        """Each list_jobs entry has the required keys."""
        scheduler.register_job("schema_job", "0 * * * *", _make_handler(), description="test")
        jobs = await scheduler.list_jobs()
        entry = jobs[0]

        assert "job_id" in entry
        assert "cron_expr" in entry
        assert "description" in entry
        assert "status" in entry
        assert "last_run" in entry


# ---------------------------------------------------------------------------
# SchedulerService — start / stop
# ---------------------------------------------------------------------------


class TestSchedulerServiceStartStop:
    @pytest.mark.asyncio
    async def test_start_sets_running(self, scheduler):
        """start() sets _running to True."""
        assert scheduler._running is False
        await scheduler.start()
        assert scheduler._running is True

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, scheduler):
        """stop() sets _running to False."""
        scheduler._running = True
        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_start_stop_cycle(self, scheduler):
        """Full start-stop cycle works."""
        await scheduler.start()
        assert scheduler._running is True
        await scheduler.stop()
        assert scheduler._running is False


# ---------------------------------------------------------------------------
# JobFailureRecovery — exponential backoff
# ---------------------------------------------------------------------------


class TestJobFailureRecovery:
    @pytest.mark.asyncio
    async def test_succeeds_first_attempt(self, recovery):
        """Handler succeeds on first try — no retries needed."""
        handler = _make_handler(return_value={"ok": True})

        result = await recovery.execute_with_retry("fast_job", handler)

        assert result["success"] is True
        assert result["result"] == {"ok": True}
        assert result["attempts"] == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        """Handler fails twice, succeeds on third attempt."""
        handler = AsyncMock(
            side_effect=[
                RuntimeError("fail 1"),
                RuntimeError("fail 2"),
                {"success": True},
            ]
        )
        recovery = JobFailureRecovery(max_retries=3, base_delay=0.01)

        result = await recovery.execute_with_retry("retry_job", handler)

        assert result["success"] is True
        assert result["result"] == {"success": True}
        assert result["attempts"] == 3
        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries(self, recovery):
        """All retries exhausted returns failure with error message."""
        handler = _make_handler(side_effect=ConnectionError("timeout"))

        result = await recovery.execute_with_retry("dead_job", handler)

        assert result["success"] is False
        assert "timeout" in result["error"]
        assert result["attempts"] == 3

    @pytest.mark.asyncio
    async def test_respects_max_retries_setting(self):
        """Custom max_retries limits the number of attempts."""
        handler = _make_handler(side_effect=RuntimeError("nope"))
        recovery = JobFailureRecovery(max_retries=5, base_delay=0.01)

        result = await recovery.execute_with_retry("five_job", handler)

        assert result["success"] is False
        assert result["attempts"] == 5
        assert handler.call_count == 5

    @pytest.mark.asyncio
    async def test_delay_caps_at_300_seconds(self):
        """Backoff delay is capped at 300s to prevent excessive waits."""
        handler = _make_handler(side_effect=RuntimeError("fail"))
        recovery = JobFailureRecovery(max_retries=6, base_delay=200.0)

        # We measure wall-clock time. With base_delay=200 and cap=300,
        # the delays should be: 200, 300 (capped), 300 (capped), ...
        # We only wait 0.01s per sleep in practice, but we patch asyncio.sleep
        # to verify the delay values.
        delays_seen = []

        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            delays_seen.append(delay)
            await original_sleep(0)  # yield control but don't actually wait

        with patch("asyncio.sleep", side_effect=mock_sleep):
            result = await recovery.execute_with_retry("capped_job", handler)

        assert result["success"] is False
        assert len(delays_seen) == 5  # 6 retries => 5 sleeps (not after last)
        # First delay is base_delay (200), subsequent ones are capped at 300
        assert delays_seen[0] == 200.0
        for d in delays_seen[1:]:
            assert d == 300.0

    @pytest.mark.asyncio
    async def test_custom_base_delay(self):
        """base_delay controls the initial retry interval."""
        handler = AsyncMock(side_effect=[RuntimeError("first fail"), {"ok": True}])
        recovery = JobFailureRecovery(max_retries=3, base_delay=0.05)

        delays_seen = []

        original_sleep = asyncio.sleep

        async def capture_sleep(delay):
            delays_seen.append(delay)
            await original_sleep(0)

        with patch("asyncio.sleep", side_effect=capture_sleep):
            result = await recovery.execute_with_retry("bd_job", handler)

        assert result["success"] is True
        assert len(delays_seen) == 1
        assert delays_seen[0] == pytest.approx(0.05, abs=0.01)

    @pytest.mark.asyncio
    async def test_passes_context_to_handler(self, recovery):
        """Context dict is forwarded to the handler on each attempt."""
        captured_contexts = []

        async def recording_handler(ctx):
            captured_contexts.append(dict(ctx))
            return {"ok": True}

        await recovery.execute_with_retry("ctx_job", recording_handler, context={"tenant": "acme"})

        assert len(captured_contexts) == 1
        assert captured_contexts[0] == {"tenant": "acme"}

    @pytest.mark.asyncio
    async def test_default_context_is_empty_dict(self, recovery):
        """When no context is given, handler receives an empty dict."""
        captured = {}

        async def grab_handler(ctx):
            captured.update(ctx)
            return {}

        await recovery.execute_with_retry("no_ctx", grab_handler)
        assert captured == {}


# ---------------------------------------------------------------------------
# ScheduledJobs — job definitions
# ---------------------------------------------------------------------------


class TestJobDefinitions:
    def test_job_definitions_count(self):
        """There are exactly 14 canonical job definitions."""
        assert len(JOB_DEFINITIONS) == 14

    def test_each_definition_has_required_fields(self):
        """Every job definition has job_id, cron_expr, and description."""
        for defn in JOB_DEFINITIONS:
            assert "job_id" in defn, f"Missing job_id in {defn}"
            assert "cron_expr" in defn, f"Missing cron_expr for {defn.get('job_id')}"
            assert "description" in defn, f"Missing description for {defn.get('job_id')}"

    def test_all_job_ids_unique(self):
        """All 14 job_ids are distinct."""
        ids = [d["job_id"] for d in JOB_DEFINITIONS]
        assert len(ids) == len(set(ids))

    def test_expected_job_ids(self):
        """The 14 expected job IDs are present."""
        expected = {
            "eod_ingestion",
            "fundamentals_refresh",
            "news_pipeline",
            "macro_ingestion",
            "representation_inference",
            "state_inference_update",
            "router_calibration",
            "rebalance_check",
            "counterfactual_computation",
            "pbt_challenger",
            "kill_switch_auto_trip",
            "health_check",
            "nav_valuation",
            "paper_trading_report",
        }
        actual = {d["job_id"] for d in JOB_DEFINITIONS}
        assert actual == expected


class TestScheduledJobs:
    def test_get_all_jobs_returns_14(self, scheduled_jobs):
        """get_all_jobs returns exactly 14 job entries."""
        jobs = scheduled_jobs.get_all_jobs()
        assert len(jobs) == 14

    def test_each_job_has_handler(self, scheduled_jobs):
        """Every returned job has a callable handler."""
        jobs = scheduled_jobs.get_all_jobs()
        for job in jobs:
            assert callable(job["handler"]), f"Handler not callable for {job['job_id']}"

    def test_each_job_has_required_keys(self, scheduled_jobs):
        """Every job entry has job_id, cron_expr, description, handler."""
        jobs = scheduled_jobs.get_all_jobs()
        for job in jobs:
            assert "job_id" in job
            assert "cron_expr" in job
            assert "description" in job
            assert "handler" in job


# ---------------------------------------------------------------------------
# ScheduledJobs — individual job handler smoke tests
# ---------------------------------------------------------------------------


class TestScheduledJobsSmokeTests:
    """Each of the 14 jobs should execute and return a result dict."""

    @pytest.mark.asyncio
    async def test_eod_ingestion(self, scheduled_jobs):
        """eod_ingestion returns success with rows_ingested."""
        result = await scheduled_jobs.eod_ingestion({})
        assert result["success"] is True
        assert result["job"] == "eod_ingestion"
        assert "rows_ingested" in result

    @pytest.mark.asyncio
    async def test_fundamentals_refresh(self, scheduled_jobs):
        result = await scheduled_jobs._fundamentals_refresh({})
        assert result["success"] is True
        assert result["job"] == "fundamentals_refresh"

    @pytest.mark.asyncio
    async def test_news_pipeline(self, scheduled_jobs):
        result = await scheduled_jobs._news_pipeline({})
        assert result["success"] is True
        assert result["job"] == "news_pipeline"

    @pytest.mark.asyncio
    async def test_macro_ingestion(self, scheduled_jobs):
        result = await scheduled_jobs._macro_ingestion({})
        assert result["success"] is True
        assert result["job"] == "macro_ingestion"

    @pytest.mark.asyncio
    async def test_representation_inference(self, scheduled_jobs):
        result = await scheduled_jobs._representation_inference({})
        assert result["success"] is True
        assert result["job"] == "representation_inference"

    @pytest.mark.asyncio
    async def test_state_inference_update(self, scheduled_jobs):
        result = await scheduled_jobs._state_inference_update({})
        assert result["success"] is True
        assert result["job"] == "state_inference_update"

    @pytest.mark.asyncio
    async def test_router_calibration(self, scheduled_jobs):
        result = await scheduled_jobs._router_calibration({})
        assert result["success"] is True
        assert result["job"] == "router_calibration"

    @pytest.mark.asyncio
    async def test_rebalance_check(self, scheduled_jobs):
        result = await scheduled_jobs._rebalance_check({})
        assert result["success"] is True
        assert result["job"] == "rebalance_check"

    @pytest.mark.asyncio
    async def test_counterfactual_computation(self, scheduled_jobs):
        result = await scheduled_jobs._counterfactual_computation({})
        assert result["success"] is True
        assert result["job"] == "counterfactual_computation"

    @pytest.mark.asyncio
    async def test_pbt_challenger(self, scheduled_jobs):
        result = await scheduled_jobs._pbt_challenger({})
        assert result["success"] is True
        assert result["job"] == "pbt_challenger"

    @pytest.mark.asyncio
    async def test_kill_switch_auto_trip(self, scheduled_jobs):
        result = await scheduled_jobs._kill_switch_auto_trip({})
        assert result["success"] is True
        assert result["job"] == "kill_switch_auto_trip"

    @pytest.mark.asyncio
    async def test_health_check_returns_adapters_checked(self, scheduled_jobs):
        """health_check returns success with adapters_checked count (0 when no adapters)."""
        result = await scheduled_jobs.health_check({})
        assert result["success"] is True
        assert result["job"] == "health_check"
        assert "adapters_checked" in result
        assert isinstance(result["adapters_checked"], int)

    @pytest.mark.asyncio
    async def test_nav_valuation_returns_nav(self, scheduled_jobs):
        """nav_valuation returns success with nav value."""
        result = await scheduled_jobs.nav_valuation({})
        assert result["success"] is True
        assert result["job"] == "nav_valuation"
        assert "nav" in result
        assert isinstance(result["nav"], (int, float))

    @pytest.mark.asyncio
    async def test_paper_trading_report(self, scheduled_jobs):
        result = await scheduled_jobs._paper_trading_report({})
        assert result["success"] is True
        assert result["job"] == "paper_trading_report"

    @pytest.mark.asyncio
    async def test_all_14_handlers_via_get_all_jobs(self, scheduled_jobs):
        """Every handler from get_all_jobs executes and returns success."""
        jobs = scheduled_jobs.get_all_jobs()
        assert len(jobs) == 14

        for job in jobs:
            result = await job["handler"]({})
            assert result["success"] is True, f"Job {job['job_id']} did not return success"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_concurrent_triggers_same_job(self, scheduler):
        """Concurrent triggers on the same job_id both complete."""
        call_order = []

        async def slow_handler(ctx):
            call_order.append("start")
            await asyncio.sleep(0.02)
            call_order.append("end")
            return {"ok": True}

        scheduler.register_job("concurrent", "0 * * * *", slow_handler)

        # Fire two triggers concurrently
        results = await asyncio.gather(
            scheduler.trigger_job("concurrent"),
            scheduler.trigger_job("concurrent"),
        )

        assert results[0]["success"] is True
        assert results[1]["success"] is True
        assert call_order == ["start", "start", "end", "end"]

    @pytest.mark.asyncio
    async def test_trigger_updates_last_run_on_success_and_failure(self, scheduler):
        """last_run is updated after both successful and failed executions."""
        good_handler = _make_handler(return_value={"ok": True})
        bad_handler = _make_handler(side_effect=RuntimeError("fail"))

        scheduler.register_job("good", "0 * * * *", good_handler)
        scheduler.register_job("bad", "0 * * * *", bad_handler)

        await scheduler.trigger_job("good")
        good_last_run = scheduler._jobs["good"]["last_run"]
        assert good_last_run is not None

        await scheduler.trigger_job("bad")
        bad_last_run = scheduler._jobs["bad"]["last_run"]
        assert bad_last_run is not None

    @pytest.mark.asyncio
    async def test_recovery_handler_succeeds_after_transient_failure(self):
        """Recovery succeeds when the handler starts failing then recovers."""
        fail_count = 0

        async def flaky_handler(ctx):
            nonlocal fail_count
            fail_count += 1
            if fail_count <= 2:
                raise ConnectionError(f"attempt {fail_count} failed")
            return {"recovered": True}

        recovery = JobFailureRecovery(max_retries=5, base_delay=0.01)
        result = await recovery.execute_with_retry("flaky", flaky_handler)

        assert result["success"] is True
        assert result["result"] == {"recovered": True}
        assert result["attempts"] == 3

    @pytest.mark.asyncio
    async def test_trigger_job_not_found_error_message(self, scheduler):
        """KeyError message includes the missing job_id."""
        with pytest.raises(KeyError) as exc_info:
            await scheduler.trigger_job("does_not_exist")

        error_msg = str(exc_info.value)
        assert "does_not_exist" in error_msg

    @pytest.mark.asyncio
    async def test_get_job_status_not_found_error_message(self, scheduler):
        """KeyError from get_job_status includes the missing job_id."""
        with pytest.raises(KeyError) as exc_info:
            await scheduler.get_job_status("also_missing")

        error_msg = str(exc_info.value)
        assert "also_missing" in error_msg

    @pytest.mark.asyncio
    async def test_trigger_job_duration_is_positive(self, scheduler):
        """Duration is positive even for very fast handlers."""
        handler = _make_handler(return_value={"fast": True})
        scheduler.register_job("fast_job", "0 * * * *", handler)

        result = await scheduler.trigger_job("fast_job")

        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_trigger_job_with_slow_handler_measures_duration(self, scheduler):
        """Duration for a deliberately slow handler is at least 30ms."""

        async def slow_handler(ctx):
            await asyncio.sleep(0.05)
            return {"slow": True}

        scheduler.register_job("measured", "0 * * * *", slow_handler)
        result = await scheduler.trigger_job("measured")

        assert result["success"] is True
        assert result["duration_ms"] >= 40  # 50ms sleep, allow some margin

    @pytest.mark.asyncio
    async def test_register_and_trigger_many_jobs(self, scheduler):
        """Register and trigger many jobs in sequence to verify no cross-contamination."""
        for i in range(20):
            handler = _make_handler(return_value={"index": i})
            scheduler.register_job(f"many_{i}", "0 * * * *", handler)

        for i in range(20):
            result = await scheduler.trigger_job(f"many_{i}")
            assert result["success"] is True
            assert result["result"]["index"] == i
