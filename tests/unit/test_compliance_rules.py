"""Tier 1 tests for the four new compliance rules added during red team audit.

Ref: specs/13-execution-cost-and-microstructure.md §9
Ref: src/midas/compliance/blocking_rules.py
Ref: src/midas/compliance/warning_rules.py
"""

import pytest

from midas.compliance.blocking_rules import create_blocking_rules
from midas.compliance.warning_rules import create_warning_rules


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_rule(rules, rule_id):
    return next(r for r in rules if r.rule_id == rule_id)


# ---------------------------------------------------------------------------
# Task 1: data.stale_cost_inputs (blocking rule #9)
# ---------------------------------------------------------------------------


class TestStaleCostInputs:
    @pytest.fixture
    def rule(self):
        return _find_rule(create_blocking_rules(), "data.stale_cost_inputs")

    def test_rule_exists(self, rule):
        assert rule is not None
        assert rule.category == "data"
        assert rule.severity.value == "block"

    def test_fresh_inputs_pass(self, rule):
        # cost_input_age_seconds = 0 (fresh) should NOT violate
        ctx = {"cost_input_age_seconds": 0}
        assert rule.predicate(ctx) is False

    def test_stale_inputs_violate(self, rule):
        # cost_input_age_seconds = 86401 (just over 1 day) should violate
        ctx = {"cost_input_age_seconds": 86401}
        assert rule.predicate(ctx) is True

    def test_exactly_one_day_is_stale(self, rule):
        # exactly 1 day = 86400 seconds is still within threshold
        ctx = {"cost_input_age_seconds": 86400}
        assert rule.predicate(ctx) is False

    def test_missing_age_defaults_to_fresh(self, rule):
        # missing key defaults to 0 which is fresh
        ctx = {}
        assert rule.predicate(ctx) is False


# ---------------------------------------------------------------------------
# Task 2: exec.participation_cap (blocking rule #21)
# ---------------------------------------------------------------------------


class TestParticipationCapBlocking:
    @pytest.fixture
    def rule(self):
        return _find_rule(create_blocking_rules(), "exec.participation_cap")

    def test_rule_exists(self, rule):
        assert rule is not None
        assert rule.category == "exec"
        assert rule.severity.value == "block"

    def test_small_order_within_cap_passes(self, rule):
        # 1% participation should pass with default 5% cap
        ctx = {"order_size": 10_000, "avg_daily_volume": 1_000_000}
        assert rule.predicate(ctx) is False

    def test_order_exceeding_cap_violates(self, rule):
        # 10% participation with default 5% cap should violate
        ctx = {"order_size": 100_000, "avg_daily_volume": 1_000_000}
        assert rule.predicate(ctx) is True

    def test_order_at_cap_boundary_passes(self, rule):
        # exactly at cap should pass (not exceeded)
        ctx = {"order_size": 50_000, "avg_daily_volume": 1_000_000}
        assert rule.predicate(ctx) is False

    def test_zero_adv_blocks(self, rule):
        # zero ADV means no data — should block
        ctx = {"order_size": 100, "avg_daily_volume": 0}
        assert rule.predicate(ctx) is True

    def test_custom_cap_applied(self, rule):
        # 3% participation with 2% custom cap should violate
        ctx = {"order_size": 30_000, "avg_daily_volume": 1_000_000, "participation_cap": 0.02}
        assert rule.predicate(ctx) is True

    def test_negative_order_size_uses_absolute(self, rule):
        # negative order size should use absolute value
        ctx = {"order_size": -100_000, "avg_daily_volume": 1_000_000}
        assert rule.predicate(ctx) is True

    def test_missing_order_size_defaults_to_zero(self, rule):
        # no order_size key → defaults to 0 → 0/ADV = 0 → within cap
        ctx = {"avg_daily_volume": 1_000_000}
        assert rule.predicate(ctx) is False


# ---------------------------------------------------------------------------
# Task 3: warn.wide_spread (warning rule #8)
# ---------------------------------------------------------------------------


class TestWideSpread:
    @pytest.fixture
    def rule(self):
        return _find_rule(create_warning_rules(), "warn.wide_spread")

    def test_rule_exists(self, rule):
        assert rule is not None
        assert rule.category == "warn"
        assert rule.severity.value == "warn"

    def test_spread_within_bands_passes(self, rule):
        # current = 10, mean = 10, stdev = 2, multiplier = 2
        # threshold = 10 + 2*2 = 14; 10 < 14 → pass
        ctx = {
            "current_spread": 10,
            "spread_rolling_mean": 10,
            "spread_stdev": 2,
            "spread_stdev_multiplier": 2,
        }
        assert rule.predicate(ctx) is False

    def test_spread_exceeds_threshold_violates(self, rule):
        # current = 15, mean = 10, stdev = 2, multiplier = 2
        # threshold = 10 + 2*2 = 14; 15 > 14 → violate
        ctx = {
            "current_spread": 15,
            "spread_rolling_mean": 10,
            "spread_stdev": 2,
            "spread_stdev_multiplier": 2,
        }
        assert rule.predicate(ctx) is True

    def test_spread_at_threshold_passes(self, rule):
        # exactly at threshold should pass
        ctx = {
            "current_spread": 14,
            "spread_rolling_mean": 10,
            "spread_stdev": 2,
            "spread_stdev_multiplier": 2,
        }
        assert rule.predicate(ctx) is False

    def test_default_multiplier_is_two(self, rule):
        # multiplier missing → defaults to 2
        ctx = {"current_spread": 15, "spread_rolling_mean": 10, "spread_stdev": 2}
        assert rule.predicate(ctx) is True

    def test_zero_stdev_uses_only_mean(self, rule):
        # zero stdev means only mean matters
        ctx = {
            "current_spread": 11,
            "spread_rolling_mean": 10,
            "spread_stdev": 0,
            "spread_stdev_multiplier": 2,
        }
        assert rule.predicate(ctx) is True

    def test_all_zeros_passes(self, rule):
        # all zeros → threshold = 0 → 0 > 0 is False
        ctx = {"current_spread": 0, "spread_rolling_mean": 0, "spread_stdev": 0}
        assert rule.predicate(ctx) is False


# ---------------------------------------------------------------------------
# Task 4: warn.event_adjacent (warning rule #9)
# ---------------------------------------------------------------------------


class TestEventAdjacent:
    @pytest.fixture
    def rule(self):
        return _find_rule(create_warning_rules(), "warn.event_adjacent")

    def test_rule_exists(self, rule):
        assert rule is not None
        assert rule.category == "warn"
        assert rule.severity.value == "warn"

    def test_no_event_nearby_passes(self, rule):
        # event_window_days = 0 means no event nearby
        ctx = {"event_window_days": 0}
        assert rule.predicate(ctx) is False

    def test_event_within_window_violates(self, rule):
        # event within 5 days should trigger warning
        ctx = {"event_window_days": 5}
        assert rule.predicate(ctx) is True

    def test_event_exactly_zero_passes(self, rule):
        # exactly 0 means no pending event
        ctx = {"event_window_days": 0}
        assert rule.predicate(ctx) is False

    def test_missing_key_defaults_to_zero_passes(self, rule):
        # missing event_window_days → defaults to 0 → no warning
        ctx = {}
        assert rule.predicate(ctx) is False
