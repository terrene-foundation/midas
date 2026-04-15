"""Tier 1 tests for M11 Autonomy Ladder and M12 Compliance Agent.

Uses temp-file SQLite via DataFlow to match project patterns.
All async tests use @pytest.mark.asyncio with auto mode.

Ref: specs/08-autonomy-and-trust.md
Ref: specs/11-compliance-and-risk.md
"""

import os
import tempfile

import pytest

from midas.fabric.engine import create_fabric, reset_fabric


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for autonomy/compliance tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_autonomy_compliance.db")
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
# M11: Investment Envelope
# ---------------------------------------------------------------------------


class TestInvestmentEnvelope:
    """Tests for the InvestmentEnvelope data class."""

    def test_default_envelope_is_valid(self):
        """Default envelope parameters should pass validation."""
        from midas.autonomy.envelope import InvestmentEnvelope

        env = InvestmentEnvelope()
        violations = env.validate()
        assert violations == [], f"Default envelope has violations: {violations}"

    def test_negative_drawdown_ceiling_fails(self):
        """Negative drawdown ceiling is a violation."""
        from midas.autonomy.envelope import InvestmentEnvelope

        env = InvestmentEnvelope(drawdown_ceiling=-0.1)
        violations = env.validate()
        assert len(violations) > 0
        assert any("drawdown_ceiling" in v for v in violations)

    def test_vol_band_inverted_fails(self):
        """vol_target_low > vol_target_high is a violation."""
        from midas.autonomy.envelope import InvestmentEnvelope

        env = InvestmentEnvelope(vol_target_low=0.20, vol_target_high=0.08)
        violations = env.validate()
        assert len(violations) > 0
        assert any("vol_target" in v for v in violations)

    def test_concentration_exceeds_one_fails(self):
        """Position concentration exceeding 1.0 is a violation."""
        from midas.autonomy.envelope import InvestmentEnvelope

        env = InvestmentEnvelope(concentration_position_max=1.5)
        violations = env.validate()
        assert len(violations) > 0
        assert any("concentration_position_max" in v for v in violations)

    def test_to_dict_round_trip(self):
        """Envelope serializes and deserializes correctly."""
        from midas.autonomy.envelope import InvestmentEnvelope

        env = InvestmentEnvelope(
            drawdown_ceiling=0.10,
            vol_target_low=0.05,
            vol_target_high=0.15,
        )
        data = env.to_dict()
        assert data["drawdown_ceiling"] == 0.10
        assert data["vol_target_low"] == 0.05
        assert data["vol_target_high"] == 0.15


class TestEnvelopeStore:
    """Tests for EnvelopeStore persistence."""

    @pytest.mark.asyncio
    async def test_get_default_envelope(self, started_db):
        """Getting envelope when none stored returns defaults."""
        from midas.autonomy.envelope import EnvelopeStore

        store = EnvelopeStore(started_db)
        env = await store.get_envelope()
        assert env.drawdown_ceiling == 0.15
        assert env.vol_target_low == 0.08

    @pytest.mark.asyncio
    async def test_update_envelope_persists(self, started_db):
        """Updating envelope writes to fabric and can be read back."""
        from midas.autonomy.envelope import EnvelopeStore, InvestmentEnvelope

        store = EnvelopeStore(started_db)
        new_env = InvestmentEnvelope(drawdown_ceiling=0.10)
        result = await store.update_envelope(
            new_env, approved_by="user@test.com", reason=" tighten risk"
        )
        assert result["success"] is True

        # Read back
        env = await store.get_envelope()
        assert env.drawdown_ceiling == 0.10

    @pytest.mark.asyncio
    async def test_update_envelope_creates_audit_record(self, started_db):
        """Envelope update must create an audit_log entry."""
        from midas.autonomy.envelope import EnvelopeStore, InvestmentEnvelope

        store = EnvelopeStore(started_db)
        new_env = InvestmentEnvelope(drawdown_ceiling=0.12)
        await store.update_envelope(new_env, approved_by="user@test.com", reason="risk reduction")

        rows = await started_db.express.list("audit_log")
        assert len(rows) >= 1
        assert any(
            r.get("rule_name") == "envelope_update" or r.get("action") == "envelope_update"
            for r in rows
        )


# ---------------------------------------------------------------------------
# M11: Autonomy Ladder
# ---------------------------------------------------------------------------


class TestAutonomyLadder:
    """Tests for the AutonomyLadder state machine."""

    @pytest.mark.asyncio
    async def test_initial_state_is_L0(self, started_db):
        """System starts at L0 (Advisory only)."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        state = await ladder.get_current_state()
        assert state.current_level == AutonomyLevel.L0

    @pytest.mark.asyncio
    async def test_promotion_L0_to_L1_with_user_approval(self, started_db):
        """L0 to L1 promotion succeeds when user approves."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        result = await ladder.request_promotion(
            target_level=AutonomyLevel.L1,
            evidence={"paper_trading_complete": True, "report_reviewed": True},
            user_approved=True,
        )
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L1

    @pytest.mark.asyncio
    async def test_promotion_rejected_without_user_approval(self, started_db):
        """Promotion MUST NOT succeed without user approval."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        result = await ladder.request_promotion(
            target_level=AutonomyLevel.L1,
            evidence={"paper_trading_complete": True},
            user_approved=False,
        )
        assert result["success"] is False
        assert "user approval" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_silent_promotion_blocked(self, started_db):
        """System MUST NOT silently promote without request_promotion."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        state = await ladder.get_current_state()
        # No promotion call made — must still be L0
        assert state.current_level == AutonomyLevel.L0

    @pytest.mark.asyncio
    async def test_cannot_skip_levels(self, started_db):
        """Cannot promote from L0 directly to L2."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        result = await ladder.request_promotion(
            target_level=AutonomyLevel.L2,
            evidence={},
            user_approved=True,
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_demotion_does_not_require_human_approval(self, started_db):
        """Demotion is automatic and does not need user approval."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        # First promote to L1
        await ladder.request_promotion(
            target_level=AutonomyLevel.L1,
            evidence={"paper_trading_complete": True, "report_reviewed": True},
            user_approved=True,
        )
        result = await ladder.demote(reason="drawdown breach", trigger="drawdown_breach")
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L0

    @pytest.mark.asyncio
    async def test_demotion_creates_audit_record(self, started_db):
        """Every demotion writes an audit record."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        await ladder.request_promotion(
            target_level=AutonomyLevel.L1,
            evidence={"paper_trading_complete": True, "report_reviewed": True},
            user_approved=True,
        )
        await ladder.demote(reason="override rate high", trigger="override_rate")

        rows = await started_db.express.list("audit_log")
        assert len(rows) >= 1
        assert any("demot" in r.get("action", "").lower() for r in rows)

    @pytest.mark.asyncio
    async def test_demotion_cannot_go_below_L0(self, started_db):
        """Demotion at L0 stays at L0."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        result = await ladder.demote(reason="already at floor", trigger="test")
        assert result["new_level"] == AutonomyLevel.L0

    @pytest.mark.asyncio
    async def test_promotion_state_tracks_counts(self, started_db):
        """State tracks promotion and demotion counts."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        await ladder.request_promotion(
            target_level=AutonomyLevel.L1,
            evidence={"paper_trading_complete": True},
            user_approved=True,
        )
        state = await ladder.get_current_state()
        assert state.promotion_count == 1

        await ladder.demote(reason="test", trigger="test")
        state = await ladder.get_current_state()
        assert state.demotion_count == 1

    @pytest.mark.asyncio
    async def test_check_upgrade_contract_returns_metrics(self, started_db):
        """Upgrade contract evaluation returns eligibility metrics."""
        from midas.autonomy.ladder import AutonomyLadder, AutonomyLevel

        ladder = AutonomyLadder(started_db)
        result = await ladder.check_upgrade_contract(
            from_level=AutonomyLevel.L0,
            to_level=AutonomyLevel.L1,
        )
        assert "eligible" in result
        assert "requirements_met" in result
        assert "requirements_failed" in result


# ---------------------------------------------------------------------------
# M11: Demotion Triggers
# ---------------------------------------------------------------------------


class TestDemotionTriggers:
    """Tests for automatic demotion triggers."""

    @pytest.mark.asyncio
    async def test_drawdown_breach_fires(self, started_db):
        """Drawdown exceeding ceiling triggers demotion."""
        from midas.autonomy.envelope import InvestmentEnvelope
        from midas.autonomy.triggers import DemotionTriggers

        triggers = DemotionTriggers(started_db)
        envelope = InvestmentEnvelope(drawdown_ceiling=0.10)
        result = await triggers.check_drawdown_breach(envelope, current_drawdown=0.12)
        assert result is not None
        assert "drawdown" in result["trigger"].lower()

    @pytest.mark.asyncio
    async def test_drawdown_within_envelope_no_fire(self, started_db):
        """Drawdown within ceiling does not trigger."""
        from midas.autonomy.envelope import InvestmentEnvelope
        from midas.autonomy.triggers import DemotionTriggers

        triggers = DemotionTriggers(started_db)
        envelope = InvestmentEnvelope(drawdown_ceiling=0.15)
        result = await triggers.check_drawdown_breach(envelope, current_drawdown=0.08)
        assert result is None

    @pytest.mark.asyncio
    async def test_model_health_demotion(self, started_db):
        """Champion model demotion triggers a demotion signal."""
        from midas.autonomy.triggers import DemotionTriggers

        triggers = DemotionTriggers(started_db)
        result = await triggers.check_model_health(
            champion_demoted=True,
        )
        assert result is not None
        assert "model" in result["trigger"].lower()

    @pytest.mark.asyncio
    async def test_override_rate_triggers(self, started_db):
        """High override rate triggers demotion."""
        from midas.autonomy.triggers import DemotionTriggers

        triggers = DemotionTriggers(started_db)
        result = await triggers.check_override_rate(
            window_days=30,
            override_rate=0.6,
            threshold=0.5,
        )
        assert result is not None
        assert "override" in result["trigger"].lower()

    @pytest.mark.asyncio
    async def test_check_all_triggers_aggregates(self, started_db):
        """check_all_triggers returns list of all triggered demotions."""
        from midas.autonomy.envelope import InvestmentEnvelope
        from midas.autonomy.triggers import DemotionTriggers

        triggers = DemotionTriggers(started_db)
        envelope = InvestmentEnvelope(drawdown_ceiling=0.05)
        results = await triggers.check_all_triggers(
            envelope,
            current_drawdown=0.10,
            champion_demoted=True,
            override_rate=0.7,
            override_threshold=0.5,
        )
        assert len(results) >= 2  # drawdown + override at minimum


# ---------------------------------------------------------------------------
# M12: Rules Engine
# ---------------------------------------------------------------------------


class TestRulesEngine:
    """Tests for the data-driven compliance rules engine."""

    @pytest.mark.asyncio
    async def test_register_and_list_rules(self, started_db):
        """Rules can be registered and listed."""
        from midas.compliance.rules_engine import (
            ComplianceRule,
            RuleSeverity,
            RulesEngine,
        )

        engine = RulesEngine(started_db)
        rule = ComplianceRule(
            rule_id="test.rule_1",
            rule_name="Test Rule",
            category="test",
            severity=RuleSeverity.BLOCK,
            description="A test rule",
            predicate=lambda ctx: ctx.get("value", 0) > 10,
        )
        engine.register_rule(rule)
        rules = engine.list_rules()
        assert len(rules) == 1
        assert rules[0]["rule_id"] == "test.rule_1"

    @pytest.mark.asyncio
    async def test_evaluate_all_rules(self, started_db):
        """Evaluating rules runs all registered rules."""
        from midas.compliance.rules_engine import (
            ComplianceRule,
            RuleSeverity,
            RulesEngine,
        )

        engine = RulesEngine(started_db)
        engine.register_rules(
            [
                ComplianceRule(
                    rule_id="test.pass_rule",
                    rule_name="Always Pass",
                    category="test",
                    severity=RuleSeverity.PASS,
                    description="Passes",
                    predicate=lambda ctx: False,
                ),
                ComplianceRule(
                    rule_id="test.block_rule",
                    rule_name="Always Block",
                    category="test",
                    severity=RuleSeverity.BLOCK,
                    description="Blocks when value > 0",
                    predicate=lambda ctx: ctx.get("value", 0) > 0,
                ),
            ]
        )
        results = await engine.evaluate({"value": 5})
        assert len(results) == 2
        blocked = [r for r in results if r.severity == RuleSeverity.BLOCK and not r.passed]
        assert len(blocked) == 1

    @pytest.mark.asyncio
    async def test_evaluate_single_rule(self, started_db):
        """Evaluating a single rule by ID works."""
        from midas.compliance.rules_engine import (
            ComplianceRule,
            RuleSeverity,
            RulesEngine,
        )

        engine = RulesEngine(started_db)
        engine.register_rule(
            ComplianceRule(
                rule_id="test.single",
                rule_name="Single",
                category="test",
                severity=RuleSeverity.BLOCK,
                description="test",
                predicate=lambda ctx: ctx.get("fail", False),
            )
        )
        result = await engine.evaluate_rule("test.single", {"fail": True})
        assert result.passed is False
        assert result.severity == RuleSeverity.BLOCK

    @pytest.mark.asyncio
    async def test_default_deny_on_exception(self, started_db):
        """If rule evaluation throws an exception, default-deny (block)."""
        from midas.compliance.rules_engine import (
            ComplianceRule,
            RuleSeverity,
            RulesEngine,
        )

        engine = RulesEngine(started_db)

        def bad_predicate(ctx):
            raise ValueError("boom")

        engine.register_rule(
            ComplianceRule(
                rule_id="test.crash",
                rule_name="Crash",
                category="test",
                severity=RuleSeverity.BLOCK,
                description="Crashes",
                predicate=bad_predicate,
            )
        )
        result = await engine.evaluate_rule("test.crash", {})
        # Default-deny: evaluation failure = blocked
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_get_blocking_violations(self, started_db):
        """get_blocking_violations returns only blocking failures."""
        from midas.compliance.rules_engine import (
            ComplianceRule,
            RuleSeverity,
            RulesEngine,
        )

        engine = RulesEngine(started_db)
        engine.register_rules(
            [
                ComplianceRule(
                    rule_id="test.block_fail",
                    rule_name="Block Fail",
                    category="test",
                    severity=RuleSeverity.BLOCK,
                    description="",
                    predicate=lambda ctx: True,  # always violated
                ),
                ComplianceRule(
                    rule_id="test.warn_fail",
                    rule_name="Warn Fail",
                    category="test",
                    severity=RuleSeverity.WARN,
                    description="",
                    predicate=lambda ctx: True,
                ),
                ComplianceRule(
                    rule_id="test.block_pass",
                    rule_name="Block Pass",
                    category="test",
                    severity=RuleSeverity.BLOCK,
                    description="",
                    predicate=lambda ctx: False,  # not violated
                ),
            ]
        )
        blocking = await engine.get_blocking_violations({})
        assert len(blocking) == 1
        assert blocking[0].rule_id == "test.block_fail"

    @pytest.mark.asyncio
    async def test_audit_evaluation_writes_to_audit_log(self, started_db):
        """audit_evaluation writes results to the audit_log table."""
        from midas.compliance.rules_engine import (
            ComplianceRule,
            RuleEvaluation,
            RuleSeverity,
            RulesEngine,
        )

        engine = RulesEngine(started_db)
        evaluations = [
            RuleEvaluation(
                rule_id="test.audit",
                rule_name="Audit Test",
                severity=RuleSeverity.BLOCK,
                passed=False,
                message="blocked",
            )
        ]
        await engine.audit_evaluation(evaluations, decision_id="dec-001")

        rows = await started_db.express.list("audit_log")
        assert len(rows) >= 1
        assert any(r.get("rule_name") == "Audit Test" for r in rows)

    @pytest.mark.asyncio
    async def test_audit_evaluation_without_decision_id(self, started_db):
        """audit_evaluation works when decision_id is None."""
        from midas.compliance.rules_engine import (
            RuleEvaluation,
            RuleSeverity,
            RulesEngine,
        )

        engine = RulesEngine(started_db)
        evaluations = [
            RuleEvaluation(
                rule_id="test.no_dec",
                rule_name="No Decision",
                severity=RuleSeverity.WARN,
                passed=True,
                message="ok",
            )
        ]
        await engine.audit_evaluation(evaluations)
        rows = await started_db.express.list("audit_log")
        assert len(rows) >= 1


# ---------------------------------------------------------------------------
# M12: Blocking Rules (16 rules)
# ---------------------------------------------------------------------------


class TestBlockingRules:
    """Tests for the 16 blocking compliance rules."""

    def test_all_16_blocking_rules_created(self):
        """Factory function returns exactly 16 blocking rules."""
        from midas.compliance.blocking_rules import create_blocking_rules

        rules = create_blocking_rules()
        assert len(rules) == 16

    def test_all_blocking_rules_have_unique_ids(self):
        """Every blocking rule has a unique rule_id."""
        from midas.compliance.blocking_rules import create_blocking_rules

        rules = create_blocking_rules()
        ids = [r.rule_id for r in rules]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"

    @pytest.mark.asyncio
    async def test_drawdown_ceiling_blocks(self, started_db):
        """env.drawdown_ceiling blocks when drawdown exceeds ceiling."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "current_drawdown": 0.20,
            "envelope": {"drawdown_ceiling": 0.15},
        }
        result = await engine.evaluate_rule("env.drawdown_ceiling", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_drawdown_ceiling_passes_when_within(self, started_db):
        """env.drawdown_ceiling passes when drawdown is within bounds."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "current_drawdown": 0.10,
            "envelope": {"drawdown_ceiling": 0.15},
        }
        result = await engine.evaluate_rule("env.drawdown_ceiling", context)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_vol_target_blocks_when_outside_band(self, started_db):
        """env.vol_target blocks when vol is outside the target band."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "current_vol": 0.25,
            "envelope": {"vol_target_low": 0.08, "vol_target_high": 0.18},
        }
        result = await engine.evaluate_rule("env.vol_target", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_concentration_position_blocks(self, started_db):
        """env.concentration.position blocks when position exceeds max."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "position_weight": 0.15,
            "envelope": {"concentration_position_max": 0.10},
        }
        result = await engine.evaluate_rule("env.concentration.position", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_concentration_sector_blocks(self, started_db):
        """env.concentration.sector blocks when sector exceeds max."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "sector_weight": 0.40,
            "envelope": {"concentration_sector_max": 0.30},
        }
        result = await engine.evaluate_rule("env.concentration.sector", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_universe_blocks_excluded_instrument(self, started_db):
        """env.universe blocks when instrument not in approved universe."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "instrument": "BTC-USD",
            "approved_universe": ["SPY", "QQQ", "IWM"],
        }
        result = await engine.evaluate_rule("env.universe", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_cost_budget_blocks_when_exceeded(self, started_db):
        """env.cost_budget blocks when annualized costs exceed budget."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "annualized_costs": 0.008,
            "envelope": {"cost_budget_annual": 0.005},
        }
        result = await engine.evaluate_rule("env.cost_budget", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_stale_price_blocks(self, started_db):
        """data.stale_price blocks when price data is stale."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "price_age_seconds": 90000,  # > 1 day
            "frequency": "daily",
        }
        result = await engine.evaluate_rule("data.stale_price", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_stale_fundamental_blocks(self, started_db):
        """data.stale_fundamental blocks when fundamental data is stale."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "fundamental_age_days": 100,  # > 90 days
        }
        result = await engine.evaluate_rule("data.stale_fundamental", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_kill_switch_blocks(self, started_db):
        """state.kill_switch blocks when kill switch is active."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {"kill_switch_active": True}
        result = await engine.evaluate_rule("state.kill_switch", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_paper_trading_blocks_live_orders(self, started_db):
        """state.paper_trading blocks live orders when paper trading."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {"paper_trading": True, "order_type": "live"}
        result = await engine.evaluate_rule("state.paper_trading", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_ood_blocks(self, started_db):
        """state.ood blocks when OOD score exceeds threshold."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {"ood_score": 0.9, "ood_threshold": 0.7, "manually_approved": False}
        result = await engine.evaluate_rule("state.ood", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_autonomy_level_breach_blocks(self, started_db):
        """autonomy.level_breach blocks when action exceeds current level."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "current_autonomy_level": 1,
            "action_required_level": 3,
        }
        result = await engine.evaluate_rule("autonomy.level_breach", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_model_confidence_floor_blocks(self, started_db):
        """model.confidence_floor blocks when confidence is below floor."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {"model_confidence": 0.2, "confidence_floor": 0.3}
        result = await engine.evaluate_rule("model.confidence_floor", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_model_pool_disagreement_blocks(self, started_db):
        """model.pool_disagreement blocks when pool disagreement is high."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "pool_disagreement": 0.8,
            "disagreement_ceiling": 0.5,
            "manually_approved": False,
        }
        result = await engine.evaluate_rule("model.pool_disagreement", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_exec_freshness_blocks(self, started_db):
        """exec.freshness_at_execution blocks when price moved too much."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {
            "price_change_pct": 0.02,
            "freshness_threshold": 0.005,
        }
        result = await engine.evaluate_rule("exec.freshness_at_execution", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_ibkr_health_blocks(self, started_db):
        """api.ibkr_health blocks when IBKR is unhealthy."""
        from midas.compliance.blocking_rules import create_blocking_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_blocking_rules())
        context = {"ibkr_healthy": False}
        result = await engine.evaluate_rule("api.ibkr_health", context)
        assert result.passed is False


# ---------------------------------------------------------------------------
# M12: Escalation Rules (7 rules)
# ---------------------------------------------------------------------------


class TestEscalationRules:
    """Tests for the 7 escalation rules."""

    def test_all_7_escalation_rules_created(self):
        """Factory function returns exactly 7 escalation rules."""
        from midas.compliance.escalation_rules import create_escalation_rules

        rules = create_escalation_rules()
        assert len(rules) == 7

    def test_all_escalation_rules_have_unique_ids(self):
        """Every escalation rule has a unique rule_id."""
        from midas.compliance.escalation_rules import create_escalation_rules

        rules = create_escalation_rules()
        ids = [r.rule_id for r in rules]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"

    @pytest.mark.asyncio
    async def test_urgent_band_escalates(self, started_db):
        """escalate.urgent_band escalates when a_t is in URGENT band."""
        from midas.compliance.escalation_rules import create_escalation_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_escalation_rules())
        context = {"attention_band": "URGENT", "current_autonomy_level": 1}
        result = await engine.evaluate_rule("escalate.urgent_band", context)
        assert result.passed is False  # violated = needs escalation

    @pytest.mark.asyncio
    async def test_crisis_band_escalates(self, started_db):
        """escalate.crisis_band escalates when a_t is in CRISIS band."""
        from midas.compliance.escalation_rules import create_escalation_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_escalation_rules())
        context = {"attention_band": "CRISIS"}
        result = await engine.evaluate_rule("escalate.crisis_band", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_envelope_change_escalates(self, started_db):
        """escalate.envelope_change escalates on envelope modification."""
        from midas.compliance.escalation_rules import create_escalation_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_escalation_rules())
        context = {"action_type": "envelope_change"}
        result = await engine.evaluate_rule("escalate.envelope_change", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_model_promotion_escalates(self, started_db):
        """escalate.model_promotion escalates on model promotion."""
        from midas.compliance.escalation_rules import create_escalation_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_escalation_rules())
        context = {"action_type": "model_promotion"}
        result = await engine.evaluate_rule("escalate.model_promotion", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_autonomy_upgrade_escalates(self, started_db):
        """escalate.autonomy_upgrade escalates on autonomy level upgrade."""
        from midas.compliance.escalation_rules import create_escalation_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_escalation_rules())
        context = {"action_type": "autonomy_upgrade"}
        result = await engine.evaluate_rule("escalate.autonomy_upgrade", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_debate_open_escalates(self, started_db):
        """escalate.debate_open escalates when debate is opened."""
        from midas.compliance.escalation_rules import create_escalation_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_escalation_rules())
        context = {"action_type": "decision_update", "debate_open": True}
        result = await engine.evaluate_rule("escalate.debate_open", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_first_seven_days_escalates(self, started_db):
        """escalate.first_seven_days forces L1 behavior for first 7 days."""
        from midas.compliance.escalation_rules import create_escalation_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_escalation_rules())
        context = {"days_since_live": 3, "current_autonomy_level": 2}
        result = await engine.evaluate_rule("escalate.first_seven_days", context)
        assert result.passed is False


# ---------------------------------------------------------------------------
# M12: Warning Rules (5 rules)
# ---------------------------------------------------------------------------


class TestWarningRules:
    """Tests for the 5 warning rules."""

    def test_all_5_warning_rules_created(self):
        """Factory function returns exactly 5 warning rules."""
        from midas.compliance.warning_rules import create_warning_rules

        rules = create_warning_rules()
        assert len(rules) == 5

    def test_all_warning_rules_have_unique_ids(self):
        """Every warning rule has a unique rule_id."""
        from midas.compliance.warning_rules import create_warning_rules

        rules = create_warning_rules()
        ids = [r.rule_id for r in rules]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"

    @pytest.mark.asyncio
    async def test_high_volatility_warns(self, started_db):
        """warn.high_volatility warns when vol exceeds percentile."""
        from midas.compliance.warning_rules import create_warning_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_warning_rules())
        context = {"current_vol": 0.30, "vol_80th_percentile": 0.20}
        result = await engine.evaluate_rule("warn.high_volatility", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_elevated_attention_warns(self, started_db):
        """warn.elevated_attention warns when a_t enters ELEVATED band."""
        from midas.compliance.warning_rules import create_warning_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_warning_rules())
        context = {"attention_band": "ELEVATED"}
        result = await engine.evaluate_rule("warn.elevated_attention", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_model_calibration_drift_warns(self, started_db):
        """warn.model_calibration_drift warns when calibration drifts."""
        from midas.compliance.warning_rules import create_warning_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_warning_rules())
        context = {"calibration_drift": 0.15, "drift_threshold": 0.10}
        result = await engine.evaluate_rule("warn.model_calibration_drift", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_high_cost_ratio_warns(self, started_db):
        """warn.high_cost_ratio warns when cost ratio exceeds threshold."""
        from midas.compliance.warning_rules import create_warning_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_warning_rules())
        context = {"cost_ratio": 0.6, "cost_ratio_threshold": 0.5}
        result = await engine.evaluate_rule("warn.high_cost_ratio", context)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_approaching_concentration_limit_warns(self, started_db):
        """warn.approaching_concentration_limit warns at 80% of limit."""
        from midas.compliance.warning_rules import create_warning_rules
        from midas.compliance.rules_engine import RulesEngine

        engine = RulesEngine(started_db)
        engine.register_rules(create_warning_rules())
        context = {
            "position_weight": 0.09,
            "concentration_limit": 0.10,
        }
        result = await engine.evaluate_rule("warn.approaching_concentration_limit", context)
        assert result.passed is False  # 90% of limit > 80% threshold


# ---------------------------------------------------------------------------
# M12: Kill Switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    """Tests for the kill switch."""

    @pytest.mark.asyncio
    async def test_activate_kill_switch(self, started_db):
        """Activating kill switch records the reason and state."""
        from midas.compliance.kill_switch import KillSwitch

        ks = KillSwitch(started_db)
        result = await ks.activate(reason="drawdown circuit breaker")
        assert result["active"] is True
        assert result["reason"] == "drawdown circuit breaker"

    @pytest.mark.asyncio
    async def test_is_active_after_activation(self, started_db):
        """Kill switch reports active after activation."""
        from midas.compliance.kill_switch import KillSwitch

        ks = KillSwitch(started_db)
        await ks.activate(reason="test")
        assert await ks.is_active() is True

    @pytest.mark.asyncio
    async def test_is_not_active_by_default(self, started_db):
        """Kill switch is not active by default."""
        from midas.compliance.kill_switch import KillSwitch

        ks = KillSwitch(started_db)
        assert await ks.is_active() is False

    @pytest.mark.asyncio
    async def test_clear_requires_user_approval(self, started_db):
        """Clearing kill switch requires user approval."""
        from midas.compliance.kill_switch import KillSwitch

        ks = KillSwitch(started_db)
        await ks.activate(reason="test")
        result = await ks.clear(
            user_approved=False,
            state_brief={"drawdown": 0.05, "pool_disagreement": 0.1},
        )
        assert result["cleared"] is False

    @pytest.mark.asyncio
    async def test_clear_with_user_approval_succeeds(self, started_db):
        """Clearing kill switch with user approval reverts to L1."""
        from midas.compliance.kill_switch import KillSwitch

        ks = KillSwitch(started_db)
        await ks.activate(reason="test")
        result = await ks.clear(
            user_approved=True,
            state_brief={"drawdown": 0.03, "pool_disagreement": 0.1},
        )
        assert result["cleared"] is True
        assert result["revert_level"] == 1  # Always reverts to L1

    @pytest.mark.asyncio
    async def test_clear_conditions_listed(self, started_db):
        """Cleared kill switch lists the conditions that apply."""
        from midas.compliance.kill_switch import KillSwitch

        ks = KillSwitch(started_db)
        await ks.activate(reason="test")
        result = await ks.clear(
            user_approved=True,
            state_brief={"drawdown": 0.03},
        )
        assert "conditions" in result
        assert isinstance(result["conditions"], list)
        assert len(result["conditions"]) >= 1

    @pytest.mark.asyncio
    async def test_activate_creates_audit_record(self, started_db):
        """Kill switch activation writes an audit record."""
        from midas.compliance.kill_switch import KillSwitch

        ks = KillSwitch(started_db)
        await ks.activate(reason="circuit breaker")
        rows = await started_db.express.list("audit_log")
        assert len(rows) >= 1
        assert any(
            "kill_switch" in r.get("action", "").lower()
            or "kill_switch" in r.get("rule_name", "").lower()
            for r in rows
        )

    @pytest.mark.asyncio
    async def test_clear_creates_audit_record(self, started_db):
        """Kill switch clearing writes an audit record."""
        from midas.compliance.kill_switch import KillSwitch

        ks = KillSwitch(started_db)
        await ks.activate(reason="test")
        await ks.clear(
            user_approved=True,
            state_brief={"drawdown": 0.03},
        )
        rows = await started_db.express.list("audit_log")
        # At least 2: activate + clear
        assert len(rows) >= 2
