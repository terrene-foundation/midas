"""
Tests for T-00-09: Kill-Switch Process-Lock.

Tier 2: asserts the clear flow cannot be bypassed — brief must be shown,
acknowledged, and 60-second dwell enforced on first post-clear decision.

Ref: specs/08-autonomy-and-trust.md §5.4
Ref: specs/10-moments-of-truth.md §5
Ref: T-00-09
"""

from __future__ import annotations

import pytest

from midas.evaluation.probes.kill_switch_process_lock import (
    KillSwitchProcessLock,
    KillSwitchState,
    ClearFlowStep,
    KillSwitchClearFlowResult,
    KillSwitchStateOfWorld,
    make_brief,
)


class TestKillSwitchProcessLock:
    """Tier 2 tests for kill-switch process-lock protocol."""

    def test_initial_state_is_active(self):
        """Kill switch starts in ACTIVE state, not clearable."""
        protocol = KillSwitchProcessLock()
        result = protocol.evaluate_clear_flow()

        assert result.kill_switch_state == KillSwitchState.ACTIVE
        assert result.can_clear is False
        assert result.autonomy_reverted_to_l1 is False

    def test_cannot_acknowledge_without_beginning_flow(self):
        """Attempting to acknowledge brief without beginning clear flow → raises."""
        protocol = KillSwitchProcessLock()
        brief = make_brief()

        with pytest.raises(ValueError, match="Clear flow not initiated"):
            protocol.acknowledge_brief(brief)

    def test_cannot_complete_clear_without_acknowledging_brief(self):
        """Attempting to clear without brief acknowledgment → raises."""
        protocol = KillSwitchProcessLock()
        protocol.begin_clear_flow()

        with pytest.raises(ValueError, match="Brief must be acknowledged"):
            protocol.complete_clear()

    def test_full_clear_flow_succeeds(self):
        """Complete flow: begin → brief read → acknowledge → complete → cleared."""
        protocol = KillSwitchProcessLock()
        brief = make_brief()

        protocol.begin_clear_flow()
        result1 = protocol.evaluate_clear_flow()
        assert result1.kill_switch_state == KillSwitchState.CLEARING_PROCESS
        assert result1.can_clear is False

        protocol.acknowledge_brief(brief)
        result2 = protocol.evaluate_clear_flow()
        assert result2.brief_acknowledged is True
        assert result2.can_clear is True

        protocol.complete_clear()
        result3 = protocol.evaluate_clear_flow()
        assert result3.kill_switch_state == KillSwitchState.CLEARED
        assert result3.autonomy_reverted_to_l1 is True
        assert result3.can_clear is True

    def test_empty_brief_rejected(self):
        """Brief with no substantive content → acknowledged_brief raises."""
        protocol = KillSwitchProcessLock()
        protocol.begin_clear_flow()

        empty_brief = KillSwitchStateOfWorld(
            z_t_posterior="",
            drawdown_state="",
            pool_disagreement=-1.0,
            compliance_events=[],
            generated_at=protocol._brief_read_at or None,
        )

        with pytest.raises(ValueError, match="brief has no content"):
            protocol.acknowledge_brief(empty_brief)

    def test_post_clear_dwell_tracks(self):
        """After clear, dwell_seconds_remaining starts at 60."""
        protocol = KillSwitchProcessLock()
        protocol.begin_clear_flow()
        protocol.acknowledge_brief(make_brief())
        protocol.complete_clear()

        result = protocol.evaluate_clear_flow()
        assert result.dwell_seconds_remaining == 60.0
        assert result.first_post_clear_requires_approval is True

    def test_post_clear_dwell_decrements(self):
        """advance_dwell decrements the dwell counter correctly."""
        protocol = KillSwitchProcessLock()
        protocol.begin_clear_flow()
        protocol.acknowledge_brief(make_brief())
        protocol.complete_clear()

        protocol.advance_dwell(15.0)
        assert protocol.post_clear_dwell_remaining == 45.0

        protocol.advance_dwell(15.0)
        assert protocol.post_clear_dwell_remaining == 30.0

        protocol.advance_dwell(30.0)
        assert protocol.first_post_clear_dwell_complete() is True

    def test_dwell_incomplete_blocks_complete(self):
        """After clear but before dwell elapses, first post-clear dwell is not complete."""
        protocol = KillSwitchProcessLock()
        protocol.begin_clear_flow()
        protocol.acknowledge_brief(make_brief())
        protocol.complete_clear()
        protocol.advance_dwell(30.0)  # only 30s elapsed, not 60

        result = protocol.evaluate_clear_flow()
        assert result.dwell_seconds_remaining == 30.0
        assert result.failures == ["post_clear_dwell_incomplete"]

    def test_cannot_begin_flow_when_not_active(self):
        """Once CLEARED, begin_clear_flow is a no-op."""
        protocol = KillSwitchProcessLock()
        protocol.begin_clear_flow()
        protocol.acknowledge_brief(make_brief())
        protocol.complete_clear()

        # Trying to begin again should be a no-op (already cleared)
        protocol.begin_clear_flow()
        result = protocol.evaluate_clear_flow()
        assert result.kill_switch_state == KillSwitchState.CLEARED

    def test_current_step_tracks_progress(self):
        """current_step reflects where in the flow we are."""
        protocol = KillSwitchProcessLock()

        assert protocol.current_step == ClearFlowStep.NOT_STARTED

        protocol.begin_clear_flow()
        assert protocol.current_step == ClearFlowStep.BRIEF_READ

        protocol.acknowledge_brief(make_brief())
        assert protocol.current_step == ClearFlowStep.BRIEF_ACKNOWLEDGED

        protocol.complete_clear()
        assert protocol.current_step == ClearFlowStep.COMPLETE

    def test_brief_read_at_set_on_begin(self):
        """brief_read_at is set when flow begins."""
        protocol = KillSwitchProcessLock()
        assert protocol._brief_read_at is None

        protocol.begin_clear_flow()
        assert protocol._brief_read_at is not None

    def test_no_bypass_flow_enforced(self):
        """evaluate_no_bypass returns True (structural enforcement prevents bypass)."""
        protocol = KillSwitchProcessLock()
        assert protocol.evaluate_no_bypass() is True

    def test_cannot_skip_from_active_to_cleared(self):
        """Cannot go from ACTIVE directly to CLEARED — flow steps are mandatory."""
        protocol = KillSwitchProcessLock()

        # Directly calling complete_clear should raise
        with pytest.raises(ValueError, match="Clear flow not initiated"):
            protocol.complete_clear()

        # Directly acknowledging should raise
        with pytest.raises(ValueError, match="Clear flow not initiated"):
            protocol.acknowledge_brief(make_brief())

    def test_15_minute_timer_not_used(self):
        """The protocol has no 15-minute timer — cooldown is process-based."""
        protocol = KillSwitchProcessLock()

        # Verify no time-based attribute exists that could act as 15-minute bypass
        assert not hasattr(protocol, "_clear_cooldown_seconds")
        assert not hasattr(protocol, "_time_lock_minutes")
