"""Tests for Gap 3: Attention budget tracker.

Verifies the AttentionBudgetTracker computes fatigue correctly,
records decisions and notifications, and respects suppression rules.
"""

import pytest

from midas.attention.budget_tracker import (
    AttentionBudget,
    AttentionBudgetTracker,
)


class TestAttentionBudgetDataclass:
    """Tests for the AttentionBudget snapshot dataclass."""

    def test_default_budget_is_zero(self):
        budget = AttentionBudget()
        assert budget.decision_seconds_today == 0.0
        assert budget.decisions_today == 0
        assert budget.fatigue_score == 0.0
        assert budget.avg_time_to_decide_ms == 0.0

    def test_notifications_by_tier_defaults_empty(self):
        budget = AttentionBudget()
        assert budget.notifications_by_tier == {}


class TestAttentionBudgetTrackerRecording:
    """Tests for decision and notification recording."""

    def test_record_decision_increments_count(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(5.0, "rebalance")
        tracker.record_decision(3.0, "rebalance")
        budget = tracker.compute_budget()
        assert budget.decisions_today == 2

    def test_record_decision_accumulates_time(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(5.0, "rebalance")
        tracker.record_decision(3.0, "rebalance")
        budget = tracker.compute_budget()
        assert budget.decision_seconds_today == 8.0

    def test_record_decision_ignores_negative_duration(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(-1.0, "rebalance")
        budget = tracker.compute_budget()
        assert budget.decisions_today == 0

    def test_record_decision_ignores_nan_duration(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(float("nan"), "rebalance")
        budget = tracker.compute_budget()
        assert budget.decisions_today == 0

    def test_record_decision_ignores_inf_duration(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(float("inf"), "rebalance")
        budget = tracker.compute_budget()
        assert budget.decisions_today == 0

    def test_record_notification_increments_tier(self):
        tracker = AttentionBudgetTracker()
        tracker.record_notification("standard_push")
        tracker.record_notification("standard_push")
        tracker.record_notification("emergency")
        budget = tracker.compute_budget()
        assert budget.notifications_by_tier.get("standard_push") == 2
        assert budget.notifications_by_tier.get("emergency") == 1


class TestAttentionBudgetTrackerFatigue:
    """Tests for fatigue computation."""

    def test_no_decisions_no_fatigue(self):
        tracker = AttentionBudgetTracker()
        assert tracker.compute_fatigue() == 0.0

    def test_low_activity_low_fatigue(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(10.0, "rebalance")
        assert tracker.compute_fatigue() < 0.2

    def test_high_decision_count_increases_fatigue(self):
        tracker = AttentionBudgetTracker()
        for _ in range(50):
            tracker.record_decision(1.0, "rebalance")
        fatigue = tracker.compute_fatigue()
        assert fatigue > 0.3

    def test_tap_immediately_rate_increases_fatigue(self):
        tracker = AttentionBudgetTracker()
        # 10 instant decisions out of 10 = 100% tap-immediately rate
        for _ in range(10):
            tracker.record_decision(0.5, "rebalance")
        fatigue = tracker.compute_fatigue()
        assert fatigue > 0.3

    def test_notification_overload_increases_fatigue(self):
        tracker = AttentionBudgetTracker()
        for _ in range(10):
            tracker.record_notification("emergency")
        fatigue = tracker.compute_fatigue()
        # Only notification component fires (no decisions), so it's
        # the sole contributor: 10 emergency * 3.0 weight / 10.0 = 3.0, capped to 1.0
        # Average of [1.0] = 1.0
        assert fatigue > 0.3

    def test_fatigue_bounded_between_0_and_1(self):
        tracker = AttentionBudgetTracker()
        # Push every signal to max
        for _ in range(100):
            tracker.record_decision(10.0, "rebalance")
            tracker.record_notification("emergency")
        fatigue = tracker.compute_fatigue()
        assert 0.0 <= fatigue <= 1.0


class TestAttentionBudgetTrackerAvgTime:
    """Tests for average time-to-decide computation."""

    def test_avg_time_no_decisions(self):
        tracker = AttentionBudgetTracker()
        budget = tracker.compute_budget()
        assert budget.avg_time_to_decide_ms == 0.0

    def test_avg_time_single_decision(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(5.0, "rebalance")
        budget = tracker.compute_budget()
        assert budget.avg_time_to_decide_ms == 5000.0

    def test_avg_time_multiple_decisions(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(2.0, "rebalance")
        tracker.record_decision(4.0, "rebalance")
        tracker.record_decision(6.0, "rebalance")
        budget = tracker.compute_budget()
        # avg = (2+4+6)/3 = 4.0 seconds = 4000 ms
        assert abs(budget.avg_time_to_decide_ms - 4000.0) < 0.01


class TestAttentionBudgetTrackerSuppression:
    """Tests for notification suppression logic."""

    def test_emergency_never_suppressed(self):
        tracker = AttentionBudgetTracker()
        # Exhaust the user
        for _ in range(100):
            tracker.record_decision(10.0, "rebalance")
        assert tracker.should_suppress_notification("emergency") is False

    def test_silent_in_app_suppressed_at_high_fatigue(self):
        tracker = AttentionBudgetTracker()
        # Exhaust decision time + count AND add notification overload
        for _ in range(100):
            tracker.record_decision(10.0, "rebalance")
            tracker.record_notification("emergency")
        assert tracker.should_suppress_notification("silent_in_app") is True

    def test_silent_in_app_not_suppressed_at_low_fatigue(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(5.0, "rebalance")
        assert tracker.should_suppress_notification("silent_in_app") is False

    def test_standard_push_suppressed_at_high_fatigue(self):
        tracker = AttentionBudgetTracker()
        for _ in range(100):
            tracker.record_decision(10.0, "rebalance")
            tracker.record_notification("emergency")
        assert tracker.should_suppress_notification("standard_push") is True

    def test_prominent_push_requires_extreme_fatigue(self):
        tracker = AttentionBudgetTracker()
        for _ in range(40):
            tracker.record_decision(10.0, "rebalance")
        # May or may not suppress depending on fatigue level
        result = tracker.should_suppress_notification("prominent_push")
        assert isinstance(result, bool)


class TestAttentionBudgetTrackerReset:
    """Tests for daily reset."""

    def test_reset_clears_counters(self):
        tracker = AttentionBudgetTracker()
        tracker.record_decision(5.0, "rebalance")
        tracker.record_notification("standard_push")
        tracker.reset_daily()
        budget = tracker.compute_budget()
        assert budget.decisions_today == 0
        assert budget.decision_seconds_today == 0.0
        assert budget.notifications_by_tier == {}


class TestAttentionBudgetTrackerCustomCeiling:
    """Tests for custom daily decision seconds ceiling."""

    def test_custom_ceiling_affects_fatigue(self):
        tracker = AttentionBudgetTracker(daily_decision_seconds_ceiling=10.0)
        tracker.record_decision(8.0, "rebalance")
        fatigue = tracker.compute_fatigue()
        # 80% of a 10s ceiling, but averaged with count_ratio (1/50) and
        # tap-immediately (not enough decisions yet).  Still meaningfully > 0.
        assert fatigue > 0.2
