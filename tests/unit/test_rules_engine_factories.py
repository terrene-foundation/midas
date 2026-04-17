"""Tier 1 tests for compliance rule factory functions.

Ref: specs/11-compliance-and-risk.md
Ref: src/midas/compliance/rules_engine.py
"""

from midas.compliance.rules_engine import (
    RuleSeverity,
    make_cost_budget_rule,
    make_participation_cap_rule,
)


class TestParticipationCapRule:
    def test_factory_creates_block_rule(self):
        rule = make_participation_cap_rule()
        assert rule.rule_id == "exec.participation_cap"
        assert rule.severity == RuleSeverity.BLOCK
        assert rule.category == "execution"

    def test_order_within_cap_passes(self):
        rule = make_participation_cap_rule(default_cap=0.05)
        ctx = {"order_size": 1000, "avg_daily_volume": 1_000_000}
        assert rule.predicate(ctx) is False  # not violated

    def test_order_exceeding_cap_violated(self):
        rule = make_participation_cap_rule(default_cap=0.05)
        ctx = {"order_size": 100_000, "avg_daily_volume": 1_000_000}
        assert rule.predicate(ctx) is True  # violated

    def test_zero_adv_blocks(self):
        rule = make_participation_cap_rule()
        ctx = {"order_size": 100, "avg_daily_volume": 0}
        assert rule.predicate(ctx) is True  # blocked: no ADV

    def test_custom_cap_from_context(self):
        rule = make_participation_cap_rule(default_cap=0.10)
        ctx = {"order_size": 100_000, "avg_daily_volume": 1_000_000, "participation_cap": 0.05}
        assert rule.predicate(ctx) is True  # exceeds custom cap

    def test_custom_cap_parameter(self):
        rule = make_participation_cap_rule(default_cap=0.02)
        ctx = {"order_size": 30_000, "avg_daily_volume": 1_000_000}
        assert rule.predicate(ctx) is True  # 3% > 2% custom


class TestCostBudgetRule:
    def test_factory_creates_block_rule(self):
        rule = make_cost_budget_rule()
        assert rule.rule_id == "env.cost_budget"
        assert rule.severity == RuleSeverity.BLOCK
        assert rule.category == "envelope"

    def test_cost_within_budget_passes(self):
        rule = make_cost_budget_rule(annual_budget_bps=50.0)
        ctx = {"expected_cost_bps": 10.0, "remaining_budget_bps": 40.0}
        assert rule.predicate(ctx) is False

    def test_cost_exceeds_budget_violated(self):
        rule = make_cost_budget_rule(annual_budget_bps=50.0)
        ctx = {"expected_cost_bps": 60.0, "remaining_budget_bps": 50.0}
        assert rule.predicate(ctx) is True

    def test_default_budget_from_parameter(self):
        rule = make_cost_budget_rule(annual_budget_bps=25.0)
        # No remaining_budget_bps → defaults to annual_budget_bps
        ctx = {"expected_cost_bps": 30.0}
        assert rule.predicate(ctx) is True

    def test_zero_cost_passes(self):
        rule = make_cost_budget_rule()
        ctx = {"expected_cost_bps": 0.0, "remaining_budget_bps": 50.0}
        assert rule.predicate(ctx) is False
