"""Tier 1 tests for the paper trading module (M19).

Covers PaperTradingManager (state transitions, minimum operating days,
audit logging) and PaperTradingReport (7 subsystem pass/fail checks,
overall pass/fail logic, edge cases).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midas.paper_trading.paper_manager import (
    MIN_OPERATING_DAYS,
    PaperTradingManager,
)
from midas.paper_trading.report import PaperTradingReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(mock_list_return=None):
    """Build a fake DataFlow with an express.list AsyncMock.

    Parameters
    ----------
    mock_list_return : list | None
        The rows returned by ``db.express.list(...)``.  Defaults to ``[]``
        (no prior state), which simulates a fresh paper trading start.
    """
    db = MagicMock()
    db.express = MagicMock()
    db.express.list = AsyncMock(return_value=mock_list_return or [])
    return db


def _run(coro):
    """Run an async coroutine synchronously in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _iso(days_ago: int) -> str:
    """Return an ISO-8601 timestamp for *days_ago* days before now."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ===================================================================
# PaperTradingManager
# ===================================================================


class TestPaperTradingManagerInit:
    """PaperTradingManager: initialisation in paper mode."""

    def test_get_state_no_history_returns_paper_mode(self):
        """When no audit rows exist, state defaults to paper mode."""
        db = _make_db()
        manager = PaperTradingManager(db)

        state = _run(manager.get_state())

        assert state["mode"] == "paper"
        assert state["started_at"] == ""
        assert state["days_elapsed"] == 0
        assert state["operating_days_elapsed"] == 0
        assert state["eligible_for_live"] is False
        assert state["anomalies"] == []

    def test_start_paper_trading_returns_paper_mode(self):
        """start_paper_trading returns mode=paper and current timestamp."""
        db = _make_db()
        manager = PaperTradingManager(db)

        result = _run(manager.start_paper_trading())

        assert result["mode"] == "paper"
        assert result["min_operating_days"] == MIN_OPERATING_DAYS
        assert result["started_at"]
        # Verify the timestamp is parseable and recent (within last 5s)
        started = datetime.fromisoformat(result["started_at"])
        age = datetime.now(timezone.utc) - started
        assert age.total_seconds() < 5


class TestPaperTradingManagerMinimumDays:
    """PaperTradingManager: two-week operating-day minimum enforcement."""

    def test_go_live_rejected_when_under_minimum_days(self):
        """request_go_live is rejected when operating days < 14."""
        started_5_days_ago = _iso(5)
        rows = [
            {"action": "paper", "details": started_5_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.request_go_live(user_approved=True))

        assert result["status"] == "rejected"
        assert "Minimum 14 operating days required" in result["reason"]
        assert result["remaining_days"] == MIN_OPERATING_DAYS - 5

    def test_go_live_rejected_with_zero_days_elapsed(self):
        """request_go_live is rejected immediately after start (0 days)."""
        started_now = _iso(0)
        rows = [{"action": "paper", "details": started_now, "rule_name": "paper_trading_state"}]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.request_go_live(user_approved=True))

        assert result["status"] == "rejected"
        assert result["remaining_days"] == MIN_OPERATING_DAYS

    def test_go_live_approved_at_exactly_14_days(self):
        """request_go_live is approved when exactly 14 operating days have elapsed."""
        started_14_days_ago = _iso(14)
        rows = [
            {"action": "paper", "details": started_14_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.request_go_live(user_approved=True))

        assert result["status"] == "approved"
        assert result["mode"] == "live"
        assert result["transitioned_at"]
        assert result["first_seven_days_l1"] is True

    def test_go_live_approved_after_20_days(self):
        """request_go_live is approved well past the minimum."""
        started_20_days_ago = _iso(20)
        rows = [
            {"action": "paper", "details": started_20_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.request_go_live(user_approved=True))

        assert result["status"] == "approved"
        assert result["mode"] == "live"

    def test_check_eligibility_under_minimum(self):
        """check_eligibility reports not eligible when under 14 days."""
        started_7_days_ago = _iso(7)
        rows = [
            {"action": "paper", "details": started_7_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.check_eligibility())

        assert result["eligible"] is False
        assert result["days_remaining"] == MIN_OPERATING_DAYS - 7
        assert result["operating_days_elapsed"] == 7

    def test_check_eligibility_at_minimum(self):
        """check_eligibility reports eligible at exactly 14 days."""
        started_14_days_ago = _iso(14)
        rows = [
            {"action": "paper", "details": started_14_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.check_eligibility())

        assert result["eligible"] is True
        assert result["days_remaining"] == 0


class TestPaperTradingManagerStateTransitions:
    """PaperTradingManager: state transitions and gating conditions."""

    def test_go_live_rejected_when_not_in_paper_mode(self):
        """request_go_live is rejected if the system is already live."""
        started_20_days_ago = _iso(20)
        rows = [
            {"action": "live", "details": started_20_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.request_go_live(user_approved=True))

        assert result["status"] == "rejected"
        assert "Not in paper mode" in result["reason"]

    def test_go_live_rejected_without_user_approval(self):
        """request_go_live is rejected when user_approved is False."""
        started_20_days_ago = _iso(20)
        rows = [
            {"action": "paper", "details": started_20_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.request_go_live(user_approved=False))

        assert result["status"] == "rejected"
        assert "User approval required" in result["reason"]

    def test_go_live_approved_includes_l1_autonomy_conditions(self):
        """Approved transition includes first-seven-days L1 autonomy conditions."""
        started_14_days_ago = _iso(14)
        rows = [
            {"action": "paper", "details": started_14_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        result = _run(manager.request_go_live(user_approved=True))

        assert result["status"] == "approved"
        assert "First seven days at L1 autonomy" in result["conditions"]
        assert "Enhanced monitoring active" in result["conditions"]
        assert "Kill switch armed" in result["conditions"]
        assert result["first_seven_days_l1"] is True

    def test_go_live_rejected_when_anomalies_present(self):
        """request_go_live is rejected when unresolved anomalies exist."""
        started_20_days_ago = _iso(20)
        # get_state uses rows[-1], so the anomaly row must be the last one.
        # The get_state method reads 'anomalies' from the state dict, but
        # currently the real implementation hard-codes anomalies=[].
        # We test the guard path by patching get_state to return anomalies.
        db = _make_db()
        manager = PaperTradingManager(db)

        async def _fake_state():
            return {
                "mode": "paper",
                "started_at": started_20_days_ago,
                "days_elapsed": 20,
                "operating_days_elapsed": 20,
                "eligible_for_live": True,
                "anomalies": ["latency_spike_on_data_ingestion", "missing_feature_vector"],
            }

        with patch.object(manager, "get_state", new=_fake_state):
            result = _run(manager.request_go_live(user_approved=True))

        assert result["status"] == "rejected"
        assert "Unresolved anomalies block Go Live" in result["reason"]
        assert len(result["anomalies"]) == 2


class TestPaperTradingManagerAuditLogging:
    """PaperTradingManager: audit log integration via DataFlow."""

    def test_get_state_reads_from_audit_log(self):
        """get_state queries audit_log with the correct filter."""
        db = _make_db()
        manager = PaperTradingManager(db)

        _run(manager.get_state())

        db.express.list.assert_awaited_once_with(
            "audit_log",
            filter={"rule_name": "paper_trading_state"},
        )

    def test_get_state_uses_last_row(self):
        """get_state uses the last audit row (most recent state)."""
        now_iso = _iso(10)
        rows = [
            {"action": "paper", "details": _iso(0), "rule_name": "paper_trading_state"},
            {"action": "paper", "details": now_iso, "rule_name": "paper_trading_state"},
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        state = _run(manager.get_state())

        # Should use the last row's started_at
        assert state["days_elapsed"] == 10
        assert state["started_at"] == now_iso

    def test_get_state_handles_invalid_iso_timestamp(self):
        """get_state returns days_elapsed=0 for unparseable timestamps."""
        rows = [{"action": "paper", "details": "not-a-date", "rule_name": "paper_trading_state"}]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        state = _run(manager.get_state())

        assert state["days_elapsed"] == 0
        assert state["operating_days_elapsed"] == 0
        assert state["eligible_for_live"] is False

    def test_get_state_handles_empty_details(self):
        """get_state returns days_elapsed=0 when details is empty string."""
        rows = [{"action": "paper", "details": "", "rule_name": "paper_trading_state"}]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        state = _run(manager.get_state())

        assert state["days_elapsed"] == 0

    def test_get_state_handles_missing_details_key(self):
        """get_state returns days_elapsed=0 when details key is absent."""
        rows = [{"action": "paper", "rule_name": "paper_trading_state"}]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        state = _run(manager.get_state())

        assert state["days_elapsed"] == 0


class TestPaperTradingManagerDaysElapsedCap:
    """PaperTradingManager: operating_days_elapsed caps at 365."""

    def test_operating_days_capped_at_365(self):
        """operating_days_elapsed is capped at 365 even if more days have passed."""
        started_400_days_ago = _iso(400)
        rows = [
            {"action": "paper", "details": started_400_days_ago, "rule_name": "paper_trading_state"}
        ]
        db = _make_db(mock_list_return=rows)
        manager = PaperTradingManager(db)

        state = _run(manager.get_state())

        assert state["days_elapsed"] == 400
        assert state["operating_days_elapsed"] == 365
        # Still eligible because capped value (365) > MIN_OPERATING_DAYS
        assert state["eligible_for_live"] is True


# ===================================================================
# PaperTradingReport
# ===================================================================


class TestPaperTradingReportSubsystemChecks:
    """PaperTradingReport: individual subsystem pass/fail checks."""

    def test_report_contains_all_seven_subsystems(self):
        """generate_report covers all 7 subsystems."""
        db = _make_db()
        report = PaperTradingReport(db)

        result = _run(report.generate_report())

        subsystem_names = [s["subsystem"] for s in result["subsystems"]]
        assert subsystem_names == list(PaperTradingReport.SUBSYSTEMS)

    def test_each_subsystem_has_required_fields(self):
        """Every subsystem result contains subsystem, status, checks, evaluated_at."""
        db = _make_db()
        report = PaperTradingReport(db)

        result = _run(report.generate_report())

        for subsystem in result["subsystems"]:
            assert "subsystem" in subsystem
            assert "status" in subsystem
            assert "checks" in subsystem
            assert "evaluated_at" in subsystem
            assert "errors_during_period" in subsystem
            assert isinstance(subsystem["checks"], list)
            assert len(subsystem["checks"]) > 0

    def test_each_check_has_required_fields(self):
        """Every check within a subsystem has check, result, detail."""
        db = _make_db()
        report = PaperTradingReport(db)

        result = _run(report.generate_report())

        for subsystem in result["subsystems"]:
            for check in subsystem["checks"]:
                assert "check" in check
                assert "result" in check
                assert "detail" in check

    def test_subsystem_names_are_correct(self):
        """All 7 subsystem names match the spec (specs/08 section 6.2)."""
        expected = [
            "data_ingestion",
            "feature_engineering",
            "representation_learner",
            "state_inference",
            "model_heads",
            "execution_simulator",
            "compliance_engine",
        ]
        assert list(PaperTradingReport.SUBSYSTEMS) == expected


class TestPaperTradingReportOverallPassFail:
    """PaperTradingReport: overall pass/fail/warning logic."""

    def test_all_subsystems_pass_yields_overall_pass(self):
        """When every subsystem passes, overall_status is 'pass'."""
        db = _make_db()
        report = PaperTradingReport(db)

        result = _run(report.generate_report())

        assert result["overall_status"] == "pass"
        assert result["all_pass"] is True
        assert result["go_live_eligible"] is True
        assert result["summary"]["passing"] == 7
        assert result["summary"]["warnings"] == 0
        assert result["summary"]["failing"] == 0

    def test_all_subsystems_fail_yields_overall_fail(self):
        """When every subsystem fails, overall_status is 'fail'."""
        db = _make_db()
        report = PaperTradingReport(db)

        # Override _evaluate_subsystem to return failures
        async def _failing_subsystem(name, as_of_date):
            return {
                "subsystem": name,
                "status": "fail",
                "checks": [{"check": "operational", "result": "fail", "detail": "Errors detected"}],
                "errors_during_period": 5,
                "evaluated_at": as_of_date,
            }

        with patch.object(report, "_evaluate_subsystem", side_effect=_failing_subsystem):
            result = _run(report.generate_report())

        assert result["overall_status"] == "fail"
        assert result["all_pass"] is False
        assert result["go_live_eligible"] is False
        assert result["summary"]["failing"] == 7
        assert result["summary"]["passing"] == 0

    def test_warning_subsystems_yields_overall_warning(self):
        """When some subsystems have warnings, overall_status is 'warning'."""
        db = _make_db()
        report = PaperTradingReport(db)

        call_count = 0

        async def _mixed_subsystem(name, as_of_date):
            nonlocal call_count
            call_count += 1
            status = "warning" if call_count <= 2 else "pass"
            return {
                "subsystem": name,
                "status": status,
                "checks": [{"check": "operational", "result": status, "detail": "ok"}],
                "errors_during_period": 0,
                "evaluated_at": as_of_date,
            }

        with patch.object(report, "_evaluate_subsystem", side_effect=_mixed_subsystem):
            result = _run(report.generate_report())

        assert result["overall_status"] == "warning"
        assert result["all_pass"] is False
        assert result["go_live_eligible"] is False
        assert result["summary"]["warnings"] == 2
        assert result["summary"]["passing"] == 5

    def test_mix_of_pass_and_fail_yields_overall_fail(self):
        """When there are both passes and failures (no warnings), overall is 'fail'."""
        db = _make_db()
        report = PaperTradingReport(db)

        call_count = 0

        async def _mixed_subsystem(name, as_of_date):
            nonlocal call_count
            call_count += 1
            status = "fail" if call_count == 1 else "pass"
            return {
                "subsystem": name,
                "status": status,
                "checks": [{"check": "operational", "result": status, "detail": "ok"}],
                "errors_during_period": 1 if status == "fail" else 0,
                "evaluated_at": as_of_date,
            }

        with patch.object(report, "_evaluate_subsystem", side_effect=_mixed_subsystem):
            result = _run(report.generate_report())

        assert result["overall_status"] == "fail"
        assert result["summary"]["failing"] == 1
        assert result["summary"]["passing"] == 6

    def test_go_live_eligible_only_when_all_pass(self):
        """go_live_eligible is True only when all subsystems pass."""
        db = _make_db()
        report = PaperTradingReport(db)

        # Default implementation has all passing
        result_pass = _run(report.generate_report())
        assert result_pass["go_live_eligible"] is True

        # With a single warning, not eligible
        async def _one_warning(name, as_of_date):
            return {
                "subsystem": name,
                "status": "warning" if name == "data_ingestion" else "pass",
                "checks": [],
                "errors_during_period": 0,
                "evaluated_at": as_of_date,
            }

        with patch.object(report, "_evaluate_subsystem", side_effect=_one_warning):
            result_warn = _run(report.generate_report())

        assert result_warn["go_live_eligible"] is False


class TestPaperTradingReportSummary:
    """PaperTradingReport: summary counts and report_date."""

    def test_summary_totals_match_subsystem_count(self):
        """passing + warnings + failing equals total_subsystems."""
        db = _make_db()
        report = PaperTradingReport(db)

        result = _run(report.generate_report())

        summary = result["summary"]
        assert summary["total_subsystems"] == 7
        assert (
            summary["passing"] + summary["warnings"] + summary["failing"]
            == summary["total_subsystems"]
        )

    def test_report_date_defaults_to_now(self):
        """When no as_of_date is given, report_date is set to a current timestamp."""
        db = _make_db()
        report = PaperTradingReport(db)

        result = _run(report.generate_report())

        assert result["report_date"]
        report_dt = datetime.fromisoformat(result["report_date"])
        age = datetime.now(timezone.utc) - report_dt
        assert age.total_seconds() < 5

    def test_report_date_uses_provided_value(self):
        """When as_of_date is provided, report_date uses that value."""
        db = _make_db()
        report = PaperTradingReport(db)
        fixed_date = "2026-01-15T12:00:00+00:00"

        result = _run(report.generate_report(as_of_date=fixed_date))

        assert result["report_date"] == fixed_date

    def test_each_subsystem_evaluated_at_matches_report_date(self):
        """All subsystems share the same evaluated_at as the report_date."""
        db = _make_db()
        report = PaperTradingReport(db)
        fixed_date = "2026-03-01T09:30:00+00:00"

        result = _run(report.generate_report(as_of_date=fixed_date))

        for subsystem in result["subsystems"]:
            assert subsystem["evaluated_at"] == fixed_date


class TestPaperTradingReportEdgeCases:
    """PaperTradingReport: edge cases."""

    def test_report_structure_when_no_subsystems(self):
        """If SUBSYSTEMS were empty, report would still have valid structure."""
        db = _make_db()
        report = PaperTradingReport(db)

        # Temporarily empty the subsystems list
        original = PaperTradingReport.SUBSYSTEMS
        PaperTradingReport.SUBSYSTEMS = []
        try:
            result = _run(report.generate_report())
        finally:
            PaperTradingReport.SUBSYSTEMS = original

        assert result["overall_status"] == "pass"  # vacuously true
        assert result["all_pass"] is True
        assert result["summary"]["total_subsystems"] == 0
        assert result["summary"]["passing"] == 0

    def test_single_subsystem_failure_blocks_go_live(self):
        """A single subsystem failure is enough to block go_live_eligible."""
        db = _make_db()
        report = PaperTradingReport(db)

        async def _one_failure(name, as_of_date):
            return {
                "subsystem": name,
                "status": "fail" if name == "compliance_engine" else "pass",
                "checks": [{"check": "operational", "result": "pass", "detail": "ok"}],
                "errors_during_period": 0,
                "evaluated_at": as_of_date,
            }

        with patch.object(report, "_evaluate_subsystem", side_effect=_one_failure):
            result = _run(report.generate_report())

        assert result["go_live_eligible"] is False
        assert result["summary"]["failing"] == 1
        assert result["summary"]["passing"] == 6
