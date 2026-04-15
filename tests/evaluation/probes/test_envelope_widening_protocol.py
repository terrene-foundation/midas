"""
Tests for T-00-07: Envelope-Widening Cooldown And Drawdown Lockout.

Tier 2: injects drawdown-locked scenario and asserts widening is blocked;
second test confirms widening succeeds after cooldown and no recent drawdown.

Ref: specs/08-autonomy-and-trust.md §1, §7
Ref: specs/11-compliance-and-risk.md §3.1
Ref: specs/10-moments-of-truth.md §7
Ref: T-00-07
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from midas.evaluation.probes.envelope_widening_protocol import (
    EnvelopeWideningProtocol,
    EnvelopeWideningResult,
    EnvelopeWideningCheck,
    DrawdownEvent,
    EnvelopeChangeRecord,
)


def make_event(
    hours_ago: float,
    drawdown_fraction: float = 0.60,
    event_id: str | None = None,
) -> DrawdownEvent:
    now = datetime.now(timezone.utc)
    return DrawdownEvent(
        event_id=event_id or str(hours_ago),
        event_time=now - timedelta(hours=hours_ago),
        drawdown_fraction=drawdown_fraction,
    )


def make_widening(
    hours_ago: float,
    change_id: str | None = None,
) -> EnvelopeChangeRecord:
    now = datetime.now(timezone.utc)
    return EnvelopeChangeRecord(
        change_id=change_id or str(hours_ago),
        change_time=now - timedelta(hours=hours_ago),
        change_type="widening",
        parameter="max_drawdown_ceiling",
        old_value=0.20,
        new_value=0.25,
    )


class TestEnvelopeWideningProtocol:
    """Tier 2 tests for envelope widening protocol."""

    def test_widening_blocked_during_drawdown_lockout(self):
        """Drawdown at 80% of ceiling → widening blocked regardless of cooldown."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )
        # No history — only drawdown lockout should fire
        result = protocol.evaluate(
            current_drawdown_fraction=0.80,  # 80% of ceiling → above 70% lockout
            debate_invoked=True,
        )

        assert (
            result.check == EnvelopeWideningCheck.FAIL_DRAWDOWN_LOCKOUT
        ), f"Expected FAIL_DRAWDOWN_LOCKOUT, got {result.check}: {result.message}"
        assert result.drawdown_fraction_of_ceiling == 0.80

    def test_widening_blocked_during_cooldown(self):
        """Widening 12 hours ago → cooldown not elapsed → blocked."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )
        now = datetime.now(timezone.utc)
        protocol.load_widening_history([make_widening(hours_ago=12)])

        result = protocol.evaluate(
            current_drawdown_fraction=0.50,  # below lockout
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.FAIL_COOLDOWN
        assert result.cooldown_hours_remaining > 0
        assert "Cooldown active" in result.message

    def test_widening_blocked_within_72h_of_drawdown_event(self):
        """Drawdown event 24 hours ago → 72h window not elapsed → blocked."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
            drawdown_event_threshold=0.50,
        )
        protocol.load_drawdown_events([make_event(hours_ago=24, drawdown_fraction=0.60)])

        result = protocol.evaluate(
            current_drawdown_fraction=0.50,  # below lockout
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.FAIL_DRAWDOWN_EVENT_WINDOW
        assert result.hours_since_drawdown_event is not None
        assert result.hours_since_drawdown_event < 72.0

    def test_widening_blocked_without_debate(self):
        """Debate not invoked → widening blocked even when all other gates pass."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )
        # No history, no drawdown, debate not invoked
        result = protocol.evaluate(
            current_drawdown_fraction=0.40,
            debate_invoked=False,
        )

        assert result.check == EnvelopeWideningCheck.FAIL_NO_DEBATE_INVOKED
        assert "Debate agent must be invoked" in result.message

    def test_widening_passes_after_full_cooldown_no_drawdown_event(self):
        """All gates pass: below lockout, cooldown elapsed, no recent event, debate invoked."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )
        # Last widening 25 hours ago (>24h cooldown)
        protocol.load_widening_history([make_widening(hours_ago=25)])
        # No drawdown events
        protocol.load_drawdown_events([])

        result = protocol.evaluate(
            current_drawdown_fraction=0.40,  # below 70% lockout
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.PASS
        assert result.cooldown_hours_remaining == 0.0
        assert result.debate_invoked is True

    def test_widening_passes_with_old_drawdown_event(self):
        """Drawdown event 96 hours ago (beyond 72h window) → passes."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )
        protocol.load_widening_history([make_widening(hours_ago=25)])
        protocol.load_drawdown_events([make_event(hours_ago=96, drawdown_fraction=0.60)])

        result = protocol.evaluate(
            current_drawdown_fraction=0.40,
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.PASS

    def test_small_drawdown_event_below_threshold_ignored(self):
        """Drawdown event at 40% of ceiling (below 50% threshold) → ignored."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
            drawdown_event_threshold=0.50,
        )
        protocol.load_widening_history([make_widening(hours_ago=25)])
        # Event below threshold should not block
        protocol.load_drawdown_events([make_event(hours_ago=1, drawdown_fraction=0.40)])

        result = protocol.evaluate(
            current_drawdown_fraction=0.40,
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.PASS

    def test_multiple_widening_history_uses_most_recent(self):
        """Multiple widenings in history → cooldown computed from most recent."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )
        now = datetime.now(timezone.utc)
        # Widening 30 hours ago AND 5 hours ago → most recent is 5h ago
        protocol.load_widening_history(
            [
                make_widening(hours_ago=30),
                make_widening(hours_ago=5),
            ]
        )

        result = protocol.evaluate(
            current_drawdown_fraction=0.40,
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.FAIL_COOLDOWN
        assert result.cooldown_hours_remaining > 0

    def test_no_widening_history_cooldown_pass(self):
        """No prior widening history → cooldown passes immediately."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )
        protocol.load_widening_history([])

        result = protocol.evaluate(
            current_drawdown_fraction=0.40,
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.PASS
        assert result.hours_since_last_widening == float("inf")

    def test_drawdown_at_exactly_lockout_threshold_fails(self):
        """Drawdown exactly at threshold (0.70) → fails (must be below)."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )

        result = protocol.evaluate(
            current_drawdown_fraction=0.70,  # exactly at threshold
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.FAIL_DRAWDOWN_LOCKOUT

    def test_drawdown_one_below_lockout_threshold_passes(self):
        """Drawdown just below threshold → passes if all other gates pass."""
        protocol = EnvelopeWideningProtocol(
            cooldown_hours=24.0,
            drawdown_lockout_fraction=0.70,
            drawdown_event_window_hours=72.0,
        )

        result = protocol.evaluate(
            current_drawdown_fraction=0.699,  # just below
            debate_invoked=True,
        )

        assert result.check == EnvelopeWideningCheck.PASS
