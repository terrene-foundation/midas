"""
Tier 1 tests for the contextual bandit router (M06 middle loop).

Tests LinUCB, Thompson Sampling, and the ContextualBanditRouter integration.
Uses temp-file SQLite DataFlow with all fabric models registered, matching
the existing test_router_shadow.py fixture pattern.
"""

import json
import math
import os
import tempfile

import numpy as np
import pytest

from midas.fabric.engine import create_fabric, reset_fabric
from midas.router import (
    ContextualBanditRouter,
    ContextualRouter,
    LinUCBContextualBandit,
    ThompsonSamplingBandit,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow with all fabric models registered."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_bandit.db")
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
def linucb():
    """Fresh LinUCB bandit."""
    return LinUCBContextualBandit(alpha=1.0)


@pytest.fixture
def thompson():
    """Fresh Thompson Sampling bandit."""
    return ThompsonSamplingBandit(prior_mu=0.0, prior_sigma=1.0)


@pytest.fixture
def bandit_router(db):
    """ContextualBanditRouter with LinUCB strategy."""
    return ContextualBanditRouter(db, n_experts=5, strategy="linucb")


@pytest.fixture
def thompson_router(db):
    """ContextualBanditRouter with Thompson Sampling strategy."""
    return ContextualBanditRouter(db, n_experts=5, strategy="thompson")


# ===========================================================================
# LinUCB Contextual Bandit
# ===========================================================================


class TestLinUCBContextualBandit:
    """Tests for the LinUCB bandit core algorithm."""

    def test_select_arm_returns_valid_distribution(self, linucb):
        """select_arm returns a chosen index and probabilities summing to 1."""
        context = [0.1, -0.2, 0.3]
        chosen, probs = linucb.select_arm(context, n_arms=5)

        assert 0 <= chosen < 5
        assert len(probs) == 5
        assert abs(sum(probs) - 1.0) < 1e-9
        assert all(p >= 0 for p in probs)

    def test_select_arm_with_exploration(self):
        """Higher alpha leads to more exploration (more uniform probs)."""
        context = [1.0, 0.5, -0.3, 0.2]
        n_arms = 4

        # Low alpha: exploitation-heavy
        bandit_exploit = LinUCBContextualBandit(alpha=0.01)
        _, probs_exploit = bandit_exploit.select_arm(context, n_arms)

        # High alpha: exploration-heavy
        bandit_explore = LinUCBContextualBandit(alpha=100.0)
        _, probs_explore = bandit_explore.select_arm(context, n_arms)

        # With high alpha, the exploration term dominates and distributions
        # should be more uniform. Measure via entropy.
        def entropy(p):
            return -sum(pi * math.log(pi + 1e-15) for pi in p)

        # High-alpha entropy should be >= low-alpha entropy for fresh bandits
        assert entropy(probs_explore) >= entropy(probs_exploit) - 0.1

    def test_alpha_must_be_positive(self):
        """Negative or zero alpha raises ValueError."""
        with pytest.raises(ValueError, match="alpha must be positive"):
            LinUCBContextualBandit(alpha=0.0)
        with pytest.raises(ValueError, match="alpha must be positive"):
            LinUCBContextualBandit(alpha=-1.0)

    def test_update_increments_confidence(self, linucb):
        """After updating an arm, its confidence proxy decreases."""
        context = [0.5, -0.5, 1.0]
        arm = 2

        conf_before = linucb.get_confidence(arm)
        linucb.update(arm, context, reward=1.0)
        conf_after = linucb.get_confidence(arm)

        # Confidence proxy: 1/(1+n). After 1 update, should drop.
        assert conf_after < conf_before
        assert conf_after == pytest.approx(0.5)

    def test_multiple_updates_accumulate(self, linucb):
        """Multiple updates to the same arm accumulate correctly."""
        context = [1.0, 0.0, 0.0]
        arm = 0

        for i in range(10):
            linucb.update(arm, context, reward=1.0)

        # After 10 updates: confidence = 1/(1+10) = 1/11
        assert linucb.get_confidence(arm) == pytest.approx(1.0 / 11.0)

    def test_get_confidence_for_unseen_arm(self, linucb):
        """An arm with no updates returns 1.0 (maximum uncertainty)."""
        assert linucb.get_confidence(99) == 1.0


# ===========================================================================
# Thompson Sampling Bandit
# ===========================================================================


class TestThompsonSamplingBandit:
    """Tests for the Thompson Sampling bandit."""

    def test_select_arm_returns_valid_distribution(self, thompson):
        """select_arm returns a valid probability distribution."""
        context = [0.1, 0.2]
        chosen, probs = thompson.select_arm(context, n_arms=3)

        assert 0 <= chosen < 3
        assert len(probs) == 3
        assert abs(sum(probs) - 1.0) < 1e-9
        assert all(p >= 0 for p in probs)

    def test_update_reduces_sigma(self, thompson):
        """After updating an arm, its posterior sigma shrinks."""
        context = [1.0]
        arm = 1

        sigma_before = thompson.get_confidence(arm)
        thompson.update(arm, context, reward=0.5)
        sigma_after = thompson.get_confidence(arm)

        assert sigma_after < sigma_before

    def test_update_shifts_posterior_mean(self, thompson):
        """After updates with high rewards, posterior mean increases."""
        context = [1.0]
        arm = 0

        # Feed high rewards
        for _ in range(20):
            thompson.update(arm, context, reward=5.0)

        # Posterior mean should be close to 5.0
        assert thompson._mu[arm] == pytest.approx(5.0, abs=0.01)

    def test_many_arms_independent(self, thompson):
        """Updates to one arm do not affect another arm's posterior."""
        context = [1.0]

        # Update arm 0 with high reward
        for _ in range(10):
            thompson.update(0, context, reward=10.0)

        # Update arm 1 with low reward
        for _ in range(10):
            thompson.update(1, context, reward=-10.0)

        # Arm 0 should have much higher posterior mean
        assert thompson._mu[0] > thompson._mu[1]


# ===========================================================================
# Reward updates improve arm selection (both strategies)
# ===========================================================================


class TestLearningFromRewards:
    """Both bandit strategies should learn to prefer higher-reward arms."""

    def test_linucb_learns_best_arm(self):
        """LinUCB converges toward the arm with highest reward."""
        bandit = LinUCBContextualBandit(alpha=0.1)  # low exploration
        context = [1.0, 0.5, -0.2]
        best_arm = 2

        # Train: best arm gets high reward, others get low
        for _ in range(50):
            for arm in range(5):
                reward = 1.0 if arm == best_arm else 0.0
                bandit.update(arm, context, reward)

        # Selection should now strongly prefer the best arm
        chosen, probs = bandit.select_arm(context, n_arms=5)
        assert chosen == best_arm
        # Best arm should have the highest probability (softer than a fixed
        # threshold because softmax over UCB scores spreads weight across 5 arms)
        assert probs[best_arm] == max(probs)

    def test_thompson_learns_best_arm(self):
        """Thompson Sampling converges toward the arm with highest reward."""
        bandit = ThompsonSamplingBandit()
        context = [1.0, 0.5]
        best_arm = 3

        # Train: best arm gets high reward, others get low
        for _ in range(50):
            for arm in range(5):
                reward = 1.0 if arm == best_arm else 0.0
                bandit.update(arm, context, reward)

        # Count how often the best arm is chosen across many trials
        best_count = 0
        n_trials = 100
        for _ in range(n_trials):
            chosen, _ = bandit.select_arm(context, n_arms=5)
            if chosen == best_arm:
                best_count += 1

        # Should pick the best arm most of the time (>60%)
        assert best_count > n_trials * 0.6


# ===========================================================================
# ContextualBanditRouter integration
# ===========================================================================


class TestContextualBanditRouterIntegration:
    """Integration tests for the full bandit router."""

    @pytest.mark.asyncio
    async def test_cold_start_returns_uniform_weights(self, bandit_router):
        """Before any outcomes, the router returns uniform weights."""
        z_t = [0.1, -0.2, 0.3, 0.05, -0.1]
        context = {"regime": "expansion"}

        result = await bandit_router.select_experts(z_t, context)

        assert "selected_heads" in result
        assert "weights" in result
        assert "bandit_metadata" in result
        assert result["bandit_metadata"]["cold_start"] is True
        assert result["bandit_metadata"]["chosen_arm"] is None

        # Uniform: all weights equal 1/n
        n = len(result["weights"])
        expected = 1.0 / n
        for w in result["weights"]:
            assert w == pytest.approx(expected, abs=1e-9)

    @pytest.mark.asyncio
    async def test_weights_sum_to_one(self, bandit_router):
        """Weights always sum to 1.0, cold start or not."""
        z_t = [0.1, -0.2, 0.3, 0.05, -0.1]
        context = {"regime": "bull"}

        result = await bandit_router.select_experts(z_t, context)
        assert abs(sum(result["weights"]) - 1.0) < 1e-9

    @pytest.mark.asyncio
    async def test_after_outcome_uses_bandit(self, bandit_router):
        """After recording an outcome, the router switches to bandit mode."""
        z_t = [0.1, -0.2, 0.3, 0.05, -0.1]
        context = {"regime": "expansion"}

        # Record some outcomes
        for i in range(5):
            bandit_router.record_outcome(
                decision_id=f"dec_{i}",
                expert_idx=2,
                reward=1.0,
                context=z_t,
            )

        result = await bandit_router.select_experts(z_t, context)

        assert result["bandit_metadata"]["cold_start"] is False
        assert isinstance(result["bandit_metadata"]["chosen_arm"], int)
        assert isinstance(result["bandit_metadata"]["confidence"], float)
        # Weights should still sum to 1
        assert abs(sum(result["weights"]) - 1.0) < 1e-9

    @pytest.mark.asyncio
    async def test_select_experts_returns_all_heads(self, bandit_router):
        """select_experts returns all expert heads (weighted blend)."""
        z_t = [0.5, -0.3, 0.1]
        context = {"regime": "contraction"}

        result = await bandit_router.select_experts(z_t, context)

        assert len(result["selected_heads"]) == 5
        assert len(result["weights"]) == 5
        assert len(result["routing_scores"]) == 5

    @pytest.mark.asyncio
    async def test_blend_outputs_same_as_contextual_router(self, db):
        """blend_outputs produces identical results to ContextualRouter."""
        fallback = ContextualRouter(db, n_experts=5)
        bandit = ContextualBanditRouter(db, n_experts=5)

        outputs = [
            {"allocation": {"AAPL": 0.5, "MSFT": 0.5}},
            {"allocation": {"AAPL": 0.3, "MSFT": 0.7}},
        ]
        weights = [0.6, 0.4]

        blended_fallback = await fallback.blend_outputs(outputs, weights)
        blended_bandit = await bandit.blend_outputs(outputs, weights)

        assert blended_fallback == blended_bandit
        # Verify expected weighted average
        assert abs(blended_bandit["allocation"]["AAPL"] - 0.42) < 0.001
        assert abs(blended_bandit["allocation"]["MSFT"] - 0.58) < 0.001

    @pytest.mark.asyncio
    async def test_blend_outputs_handles_scalar_values(self, bandit_router):
        """blend_outputs handles flat scalar dicts correctly."""
        outputs = [
            {"score": 0.8, "confidence": 0.9},
            {"score": 0.6, "confidence": 0.7},
        ]
        weights = [0.75, 0.25]

        blended = await bandit_router.blend_outputs(outputs, weights)

        # 0.8*0.75 + 0.6*0.25 = 0.75
        assert abs(blended["score"] - 0.75) < 0.001
        # 0.9*0.75 + 0.7*0.25 = 0.85
        assert abs(blended["confidence"] - 0.85) < 0.001

    @pytest.mark.asyncio
    async def test_blend_outputs_empty_returns_empty(self, bandit_router):
        """blend_outputs with empty inputs returns empty dict."""
        blended = await bandit_router.blend_outputs([], [])
        assert blended == {}

    @pytest.mark.asyncio
    async def test_blend_outputs_mismatched_lengths_raises(self, bandit_router):
        """blend_outputs raises ValueError if lengths mismatch."""
        with pytest.raises(ValueError, match="must match"):
            await bandit_router.blend_outputs([{"a": 1}], [0.5, 0.5])

    @pytest.mark.asyncio
    async def test_thompson_strategy_router(self, thompson_router):
        """Thompson strategy router works end-to-end."""
        z_t = [0.2, -0.1, 0.4, 0.3, -0.5]
        context = {"regime": "neutral"}

        # Cold start
        result = await thompson_router.select_experts(z_t, context)
        assert result["bandit_metadata"]["strategy"] == "thompson"
        assert result["bandit_metadata"]["cold_start"] is True

        # After outcome
        thompson_router.record_outcome("dec_ts_1", 0, 1.0, context=z_t)
        result = await thompson_router.select_experts(z_t, context)
        assert result["bandit_metadata"]["cold_start"] is False

    @pytest.mark.asyncio
    async def test_invalid_strategy_raises(self, db):
        """Invalid bandit strategy raises ValueError."""
        with pytest.raises(ValueError, match="Unknown bandit strategy"):
            ContextualBanditRouter(db, strategy="greedy")

    @pytest.mark.asyncio
    async def test_record_outcome_without_context(self, bandit_router):
        """record_outcome with no context uses default zero vector."""
        bandit_router.record_outcome("dec_0", 1, 0.5, context=None)

        # Should now be in non-cold-start mode
        assert bandit_router._has_outcomes is True

        z_t = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = await bandit_router.select_experts(z_t, {"regime": "test"})
        assert result["bandit_metadata"]["cold_start"] is False


# ===========================================================================
# Audit logging
# ===========================================================================


class TestBanditAuditLogging:
    """Tests for audit trail persistence."""

    @pytest.mark.asyncio
    async def test_record_routing_decision_writes_audit(self, bandit_router, db):
        """record_routing_decision writes to audit_log table."""
        await bandit_router.record_routing_decision(
            decision_id="bandit_dec_001",
            z_t=[0.1, -0.2, 0.3],
            heads=["ssl_transformer_v1", "contrastive_v1"],
            weights=[0.7, 0.3],
        )

        rows = await db.express.list("audit_log")
        routing_rows = [r for r in rows if r["action"] == "routing_decision"]
        assert len(routing_rows) >= 1

        last = routing_rows[-1]
        assert last["decision_id"] == "bandit_dec_001"
        assert last["rule_name"] == "contextual_bandit_router"

        # Details should contain bandit-specific metadata
        details = json.loads(last["details"])
        assert details["router_type"] == "contextual_bandit"
        assert details["bandit_strategy"] == "linucb"
        assert details["heads"] == ["ssl_transformer_v1", "contrastive_v1"]

    @pytest.mark.asyncio
    async def test_routing_history_tracks_outcomes(self, bandit_router):
        """record_outcome appends to the bounded routing history."""
        assert len(bandit_router._routing_history) == 0

        bandit_router.record_outcome("dec_a", 0, 1.0, context=[0.5])
        bandit_router.record_outcome("dec_b", 2, -0.5, context=[0.3])
        bandit_router.record_outcome("dec_c", 4, 0.8, context=[0.1])

        assert len(bandit_router._routing_history) == 3
        assert bandit_router._routing_history[0]["decision_id"] == "dec_a"
        assert bandit_router._routing_history[1]["reward"] == -0.5
        assert bandit_router._routing_history[2]["expert_idx"] == 4

    @pytest.mark.asyncio
    async def test_routing_history_is_bounded(self, bandit_router):
        """Routing history deque discards old entries at capacity."""
        for i in range(1100):
            bandit_router.record_outcome(f"dec_{i}", i % 5, 0.5, context=[1.0])

        # maxlen=1000, so oldest 100 should be discarded
        assert len(bandit_router._routing_history) == 1000
        assert bandit_router._routing_history[0]["decision_id"] == "dec_100"
