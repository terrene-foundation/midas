"""
Tier 1 tests for M06 Meta-Router and M07 Shadow Infrastructure.

Uses temp-file SQLite DataFlow with all fabric models registered.
Every test verifies write-then-read round-trips through the real DataFlow
express API against the model_registry, shadow_decisions, decisions, and
audit_log fabric tables.
"""

import json
import os
import tempfile

import pytest

from midas.fabric.engine import create_fabric, reset_fabric
from midas.router import (
    CalibrationService,
    ContextualRouter,
    DemotionEvaluator,
    PBTHarness,
    PromotionEvaluator,
)
from midas.shadow import ShadowLane, ShadowMonitor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow with all fabric models registered."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_router_shadow.db")
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
def calibration(db):
    return CalibrationService(db)


@pytest.fixture
def router(db):
    return ContextualRouter(db, n_experts=5)


@pytest.fixture
def pbt(db):
    return PBTHarness(db, population_size=8)


@pytest.fixture
def promotion(db):
    return PromotionEvaluator(db)


@pytest.fixture
def demotion(db):
    return DemotionEvaluator(db)


@pytest.fixture
def shadow_lane(db):
    return ShadowLane(db, model_family="challenger_v1", model_version="v0.9.0")


@pytest.fixture
def monitor(db):
    return ShadowMonitor(db)


# ---------------------------------------------------------------------------
# Helper: register a model in model_registry
# ---------------------------------------------------------------------------


async def _register_model(db, family, version, status="shadow"):
    """Insert a model_registry row via express.create."""
    row = {
        "model_family": family,
        "model_version": version,
        "model_type": "test_learner",
        "training_window_start": "2024-01-01",
        "training_window_end": "2024-12-31",
        "calibration_json": "",
        "promotion_status": status,
        "sample_count": 1000,
        "parameter_count": 50000,
        "trained_at": "2025-01-15T10:00:00",
        "config_hash": "abc123",
        "parent_version": "",
        "pool_layer": "test_pool",
        "metrics_json": json.dumps({"sharpe": 1.2}),
    }
    return await db.express.create("model_registry", row)


# ===========================================================================
# M06 — CalibrationService
# ===========================================================================


class TestCalibrationService:
    """Tests for the inner-loop calibration tracking service."""

    @pytest.mark.asyncio
    async def test_record_prediction_stores_row(self, calibration, db):
        """record_prediction writes to the audit_log and is retrievable."""
        prediction = {"direction": "bullish", "magnitude": 0.03}
        actual_outcome = {"direction": "bullish", "magnitude": 0.028}

        await calibration.record_prediction(
            head_name="ssl_transformer_v1",
            z_t_hash="abc123",
            horizon=5,
            prediction=prediction,
            actual_outcome=actual_outcome,
        )

        # Verify the prediction was recorded by reading from audit_log
        rows = await db.express.list("audit_log")
        assert len(rows) >= 1
        last = rows[-1]
        assert "ssl_transformer_v1" in last.get("details", "")
        assert last["action"] == "calibration_record"

    @pytest.mark.asyncio
    async def test_record_prediction_without_outcome(self, calibration, db):
        """record_prediction works when actual_outcome is None."""
        prediction = {"direction": "bearish", "magnitude": -0.02}

        await calibration.record_prediction(
            head_name="contrastive_v1",
            z_t_hash="def456",
            horizon=10,
            prediction=prediction,
        )

        rows = await db.express.list("audit_log")
        assert len(rows) >= 1
        last = rows[-1]
        assert "contrastive_v1" in last.get("details", "")

    @pytest.mark.asyncio
    async def test_compute_calibration_curve_returns_bins(self, calibration, db):
        """compute_calibration_curve returns n_bins calibration entries."""
        # Record several predictions with outcomes
        for i in range(20):
            await calibration.record_prediction(
                head_name="mae_v1",
                z_t_hash="hash_a",
                horizon=5,
                prediction={"direction": "up", "probability": 0.6 + i * 0.01},
                actual_outcome={"direction": "up" if i % 3 != 0 else "down"},
            )

        curve = await calibration.compute_calibration_curve("mae_v1", horizon=5, n_bins=5)
        assert isinstance(curve, list)
        assert len(curve) == 5
        for entry in curve:
            assert "predicted_mean" in entry
            assert "actual_frequency" in entry
            assert "count" in entry

    @pytest.mark.asyncio
    async def test_get_reliability_returns_score(self, calibration, db):
        """get_reliability returns a float between 0 and 1."""
        # Seed some data
        for i in range(10):
            await calibration.record_prediction(
                head_name="vae_v1",
                z_t_hash="region_x",
                horizon=5,
                prediction={"direction": "up"},
                actual_outcome={"direction": "up"},
            )

        score = await calibration.get_reliability("vae_v1", "region_x", horizon=5)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ===========================================================================
# M06 — ContextualRouter
# ===========================================================================


class TestContextualRouter:
    """Tests for the middle-loop contextual bandit router."""

    @pytest.mark.asyncio
    async def test_select_experts_returns_weights(self, router):
        """select_experts returns selected_heads, weights, and routing_scores."""
        z_t = [0.1, -0.2, 0.3, 0.05, -0.1]
        context = {"regime": "expansion", "volatility": "low"}

        result = await router.select_experts(z_t, context)

        assert "selected_heads" in result
        assert "weights" in result
        assert "routing_scores" in result
        assert len(result["selected_heads"]) > 0
        assert len(result["weights"]) == len(result["selected_heads"])
        # Weights should sum to approximately 1.0
        assert abs(sum(result["weights"]) - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_blend_outputs_combines_by_weights(self, router):
        """blend_outputs produces a weighted combination of head outputs."""
        outputs = [
            {"allocation": {"AAPL": 0.5, "MSFT": 0.5}},
            {"allocation": {"AAPL": 0.3, "MSFT": 0.7}},
        ]
        weights = [0.6, 0.4]

        blended = await router.blend_outputs(outputs, weights)

        assert "allocation" in blended
        # Weighted average: AAPL = 0.5*0.6 + 0.3*0.4 = 0.42
        #                  MSFT = 0.5*0.6 + 0.7*0.4 = 0.58
        assert abs(blended["allocation"]["AAPL"] - 0.42) < 0.001
        assert abs(blended["allocation"]["MSFT"] - 0.58) < 0.001

    @pytest.mark.asyncio
    async def test_record_routing_decision_writes_audit(self, router, db):
        """record_routing_decision writes to the audit_log table."""
        await router.record_routing_decision(
            decision_id="dec_001",
            z_t=[0.1, -0.2, 0.3],
            heads=["ssl_transformer_v1", "contrastive_v1"],
            weights=[0.7, 0.3],
        )

        rows = await db.express.list("audit_log")
        assert len(rows) >= 1
        routing_rows = [r for r in rows if r["action"] == "routing_decision"]
        assert len(routing_rows) >= 1
        assert routing_rows[-1]["decision_id"] == "dec_001"


# ===========================================================================
# M06 — PBTHarness
# ===========================================================================


class TestPBTHarness:
    """Tests for the outer-loop population-based training harness."""

    @pytest.mark.asyncio
    async def test_run_generation_returns_fitness_pairs(self, pbt):
        """run_generation evaluates configs and returns (config, fitness) pairs."""

        configs = [
            {"lr": 0.001, "hidden_dim": 64},
            {"lr": 0.01, "hidden_dim": 128},
            {"lr": 0.0001, "hidden_dim": 32},
        ]

        # Simple fitness function: negative distance from ideal lr=0.01
        def fitness_fn(config):
            return -abs(config["lr"] - 0.01)

        results = await pbt.run_generation(configs, fitness_fn)

        assert len(results) == 3
        for result in results:
            assert "config" in result
            assert "fitness" in result
        # The second config (lr=0.01, dist=0) should have highest fitness
        best = max(results, key=lambda r: r["fitness"])
        assert best["config"]["lr"] == 0.01

    @pytest.mark.asyncio
    async def test_select_and_mutate_produces_population(self, pbt):
        """select_and_mutate fills the population from winners."""

        population = [
            {"config": {"lr": 0.001}, "fitness": 0.8},
            {"config": {"lr": 0.01}, "fitness": 0.95},
            {"config": {"lr": 0.0001}, "fitness": 0.3},
        ]

        next_gen = await pbt.select_and_mutate(population, n_winners=2)

        # Population size should be maintained
        assert len(next_gen) >= 2
        # Winners should be included
        winners_lrs = [r["config"]["lr"] for r in next_gen[:2]]
        assert 0.01 in winners_lrs
        assert 0.001 in winners_lrs


# ===========================================================================
# M06 — PromotionEvaluator
# ===========================================================================


class TestPromotionEvaluator:
    """Tests for the champion/challenger promotion contract evaluator."""

    @pytest.mark.asyncio
    async def test_evaluate_promotion_returns_statistics(self, promotion, db):
        """evaluate_promotion computes p_value, CI, and metric_diff."""
        # Register champion and challenger
        await _register_model(db, "champion_v1", "v1.0.0", status="champion")
        await _register_model(db, "challenger_v1", "v0.9.0", status="shadow")

        # Record some decisions for both
        for i in range(30):
            await db.express.create(
                "decisions",
                {
                    "decision_type": "allocation",
                    "instruments": "AAPL",
                    "action": "buy",
                    "rationale": f"test decision {i}",
                    "model_version": "challenger_v1/v0.9.0" if i < 15 else "champion_v1/v1.0.0",
                    "confidence": 0.8,
                    "z_t_snapshot": "[0.1, -0.2]",
                    "outcome_json": json.dumps({"sharpe": 1.5 if i < 15 else 1.0}),
                    "created_at_day": "2024-06-15",
                },
            )

        result = await promotion.evaluate_promotion(
            challenger_family="challenger_v1",
            challenger_version="v0.9.0",
            champion_family="champion_v1",
            metric="sharpe",
            min_observations=10,
            confidence_level=0.95,
        )

        assert "should_promote" in result
        assert "p_value" in result
        assert "ci_lower" in result
        assert "ci_upper" in result
        assert "metric_diff" in result
        assert isinstance(result["should_promote"], bool)
        assert isinstance(result["p_value"], float)

    @pytest.mark.asyncio
    async def test_evaluate_demotion_detects_degradation(self, promotion, db):
        """evaluate_demotion checks if champion has degraded."""
        await _register_model(db, "champ_family", "v2.0.0", status="champion")

        result = await promotion.evaluate_demotion(
            champion_family="champ_family",
            metric="sharpe",
            degradation_threshold=-0.5,
        )

        assert "should_demote" in result
        assert "current_metric" in result
        assert "threshold_breached" in result
        assert isinstance(result["should_demote"], bool)


# ===========================================================================
# M06 — DemotionEvaluator
# ===========================================================================


class TestDemotionEvaluator:
    """Tests for continuous champion health checking."""

    @pytest.mark.asyncio
    async def test_check_champion_health_returns_status(self, demotion, db):
        """check_champion_health returns healthy flag and metrics."""
        await _register_model(db, "healthy_champ", "v1.0.0", status="champion")

        result = await demotion.check_champion_health("healthy_champ")

        assert "healthy" in result
        assert "metrics" in result
        assert "violations" in result
        assert isinstance(result["healthy"], bool)
        assert isinstance(result["violations"], list)


# ===========================================================================
# M07 — ShadowLane
# ===========================================================================


class TestShadowLane:
    """Tests for isolated shadow execution lanes."""

    @pytest.mark.asyncio
    async def test_record_shadow_decision_writes_to_shadow_table(self, shadow_lane, db):
        """record_shadow_decision writes to shadow_decisions, NOT decisions or orders."""
        await shadow_lane.record_shadow_decision(
            decision_type="allocation",
            action="buy",
            instruments="AAPL,MSFT",
            rationale="Shadow test rationale",
            confidence=0.85,
            z_t_snapshot="[0.1, -0.2, 0.3]",
            diverges_from_champion=True,
        )

        # Verify shadow_decisions has the row
        shadow_rows = await db.express.list("shadow_decisions")
        assert len(shadow_rows) >= 1
        last_shadow = shadow_rows[-1]
        assert last_shadow["model_family"] == "challenger_v1"
        assert last_shadow["model_version"] == "v0.9.0"
        assert last_shadow["action"] == "buy"
        assert (
            last_shadow["diverges_from_champion"] == True
        )  # noqa: E712 — SQLite stores bools as int

        # Verify decisions table was NOT touched by shadow
        decision_rows = await db.express.list("decisions")
        shadow_in_decisions = [
            r for r in decision_rows if "shadow" in r.get("model_version", "").lower()
        ]
        assert len(shadow_in_decisions) == 0

        # Verify orders table was NOT touched
        order_rows = await db.express.list("orders")
        assert len(order_rows) == 0

    @pytest.mark.asyncio
    async def test_get_shadow_pnl_computes_hypothetical(self, shadow_lane, db):
        """get_shadow_pnl returns hypothetical P&L for shadow decisions."""
        # Record a few shadow decisions with simulated outcomes
        for i in range(5):
            await shadow_lane.record_shadow_decision(
                decision_type="allocation",
                action="buy" if i % 2 == 0 else "sell",
                instruments="AAPL",
                rationale=f"shadow trade {i}",
                confidence=0.7 + i * 0.05,
                z_t_snapshot=f"[{0.1 * i}]",
            )

        result = await shadow_lane.get_shadow_pnl(
            start_date="2024-01-01",
            end_date="2025-12-31",
        )

        assert "total_trades" in result
        assert "hypothetical_pnl" in result
        assert result["total_trades"] == 5

    @pytest.mark.asyncio
    async def test_compare_with_champion_returns_comparison(self, shadow_lane, db):
        """compare_with_champion returns performance comparison dict."""
        # Register champion
        await _register_model(db, "champion_v1", "v1.0.0", status="champion")

        # Record shadow decisions
        await shadow_lane.record_shadow_decision(
            decision_type="allocation",
            action="buy",
            instruments="AAPL",
            rationale="comparison test",
            confidence=0.8,
            z_t_snapshot="[0.1]",
        )

        result = await shadow_lane.compare_with_champion()

        assert "shadow_trades" in result
        assert "champion_family" in result
        assert "challenger_family" in result


# ===========================================================================
# M07 — ShadowMonitor
# ===========================================================================


class TestShadowMonitor:
    """Tests for shadow lane monitoring and isolation verification."""

    @pytest.mark.asyncio
    async def test_list_active_lanes_returns_registered_shadows(self, monitor, db):
        """list_active_lanes returns shadow models from model_registry."""
        await _register_model(db, "challenger_a", "v0.1.0", status="shadow")
        await _register_model(db, "challenger_b", "v0.2.0", status="shadow")
        await _register_model(db, "champion_x", "v1.0.0", status="champion")

        lanes = await monitor.list_active_lanes()

        assert isinstance(lanes, list)
        assert len(lanes) >= 2
        families = {lane["model_family"] for lane in lanes}
        assert "challenger_a" in families
        assert "challenger_b" in families
        # Champion should not be listed as a shadow lane
        assert "champion_x" not in families

    @pytest.mark.asyncio
    async def test_get_lane_status_returns_detail(self, monitor, db):
        """get_lane_status returns detailed status for a shadow lane."""
        await _register_model(db, "challenger_c", "v0.3.0", status="shadow")

        # Record some shadow decisions for this lane
        lane = ShadowLane(db, model_family="challenger_c", model_version="v0.3.0")
        await lane.record_shadow_decision(
            decision_type="allocation",
            action="buy",
            instruments="MSFT",
            rationale="status test",
            confidence=0.75,
            z_t_snapshot="[0.2]",
        )

        status = await monitor.get_lane_status("challenger_c")

        assert "model_family" in status
        assert "model_version" in status
        assert "decision_count" in status
        assert status["model_family"] == "challenger_c"
        assert status["decision_count"] >= 1

    @pytest.mark.asyncio
    async def test_check_isolation_passes_for_clean_lane(self, monitor, db):
        """check_isolation returns True when no production call sites exist."""
        await _register_model(db, "isolated_challenger", "v0.1.0", status="shadow")

        is_isolated = await monitor.check_isolation("isolated_challenger")
        assert is_isolated is True

    @pytest.mark.asyncio
    async def test_check_isolation_fails_for_leaked_shadow(self, monitor, db):
        """check_isolation returns False when shadow decisions appear in production tables."""
        await _register_model(db, "leaky_challenger", "v0.1.0", status="shadow")

        # Simulate a leak: write a production decision with the shadow model family
        await db.express.create(
            "decisions",
            {
                "decision_type": "allocation",
                "instruments": "AAPL",
                "action": "buy",
                "rationale": "leaked shadow decision",
                "model_version": "leaky_challenger/v0.1.0",
                "confidence": 0.8,
                "z_t_snapshot": "[0.1]",
            },
        )

        is_isolated = await monitor.check_isolation("leaky_challenger")
        assert is_isolated is False
