"""Tier 1 unit tests for M08 Regime Rendering.

Tests cover: AttentionBand enum, RegimeState dataclass, RegimeRenderer
attention-score computation, band classification, disclosure levels,
recommended actions, edge cases (empty posterior, single observation,
NaN inputs, out-of-range inputs).
"""

import math
from datetime import datetime, timezone

import pytest

from midas.regime import AttentionBand, RegimeRenderer, RegimeState


# ---------------------------------------------------------------------------
# AttentionBand
# ---------------------------------------------------------------------------


class TestAttentionBand:
    """AttentionBand enum has four members with correct values."""

    def test_has_four_members(self):
        assert len(AttentionBand) == 4

    def test_member_values(self):
        assert AttentionBand.CALM.value == "calm"
        assert AttentionBand.ELEVATED.value == "elevated"
        assert AttentionBand.URGENT.value == "urgent"
        assert AttentionBand.CRISIS.value == "crisis"

    def test_lookup_by_value(self):
        assert AttentionBand("calm") is AttentionBand.CALM
        assert AttentionBand("crisis") is AttentionBand.CRISIS

    def test_lookup_invalid_raises(self):
        with pytest.raises(ValueError):
            AttentionBand("nonexistent")


# ---------------------------------------------------------------------------
# RegimeState
# ---------------------------------------------------------------------------


class TestRegimeState:
    """RegimeState frozen dataclass stores all regime components."""

    def test_create_with_all_fields(self):
        state = RegimeState(
            a_t=0.72,
            band=AttentionBand.URGENT,
            z_t_posterior=[0.1, -0.3, 0.5],
            volatility_percentile=0.6,
            ood_score=0.4,
            transition_pressure=0.8,
            model_disagreement=0.3,
            drawdown_velocity=0.1,
            timestamp="2025-04-16T12:00:00+00:00",
        )
        assert state.a_t == 0.72
        assert state.band is AttentionBand.URGENT
        assert state.z_t_posterior == [0.1, -0.3, 0.5]
        assert state.volatility_percentile == 0.6
        assert state.ood_score == 0.4
        assert state.transition_pressure == 0.8
        assert state.timestamp == "2025-04-16T12:00:00+00:00"

    def test_frozen_raises_on_mutation(self):
        state = RegimeState(
            a_t=0.1,
            band=AttentionBand.CALM,
            z_t_posterior=[],
            volatility_percentile=0.1,
            ood_score=0.0,
            transition_pressure=0.0,
            model_disagreement=0.0,
            drawdown_velocity=0.0,
            timestamp="",
        )
        with pytest.raises(AttributeError):
            state.a_t = 0.9

    def test_equality(self):
        kwargs = dict(
            a_t=0.5,
            band=AttentionBand.ELEVATED,
            z_t_posterior=[0.1, 0.2],
            volatility_percentile=0.5,
            ood_score=0.3,
            transition_pressure=0.2,
            model_disagreement=0.0,
            drawdown_velocity=0.0,
            timestamp="2025-01-01T00:00:00+00:00",
        )
        s1 = RegimeState(**kwargs)
        s2 = RegimeState(**kwargs)
        assert s1 == s2

    def test_inequality_different_a_t(self):
        base = dict(
            band=AttentionBand.CALM,
            z_t_posterior=[],
            volatility_percentile=0.0,
            ood_score=0.0,
            transition_pressure=0.0,
            model_disagreement=0.0,
            drawdown_velocity=0.0,
            timestamp="",
        )
        s1 = RegimeState(a_t=0.1, **base)
        s2 = RegimeState(a_t=0.2, **base)
        assert s1 != s2


# ---------------------------------------------------------------------------
# RegimeRenderer.get_band
# ---------------------------------------------------------------------------


class TestGetBand:
    """get_band maps a_t thresholds to AttentionBand correctly."""

    @pytest.mark.parametrize(
        "a_t, expected",
        [
            (0.0, AttentionBand.CALM),
            (0.1, AttentionBand.CALM),
            (0.29, AttentionBand.CALM),
            (0.3, AttentionBand.ELEVATED),
            (0.45, AttentionBand.ELEVATED),
            (0.59, AttentionBand.ELEVATED),
            (0.6, AttentionBand.URGENT),
            (0.75, AttentionBand.URGENT),
            (0.84, AttentionBand.URGENT),
            (0.85, AttentionBand.CRISIS),
            (0.95, AttentionBand.CRISIS),
            (1.0, AttentionBand.CRISIS),
        ],
    )
    def test_threshold_boundaries(self, a_t, expected):
        assert RegimeRenderer.get_band(a_t) is expected

    def test_negative_maps_to_calm(self):
        """Negative a_t is not expected but get_band does not clamp."""
        # get_band does not clamp; it only compares thresholds.
        # A negative value falls below 0.3, so CALM.
        assert RegimeRenderer.get_band(-0.1) is AttentionBand.CALM

    def test_above_one_maps_to_crisis(self):
        assert RegimeRenderer.get_band(1.5) is AttentionBand.CRISIS


# ---------------------------------------------------------------------------
# RegimeRenderer.get_disclosure_level
# ---------------------------------------------------------------------------


class TestGetDisclosureLevel:
    """get_disclosure_level returns human-readable string per band."""

    @pytest.mark.parametrize(
        "band, expected",
        [
            (AttentionBand.CALM, "minimal"),
            (AttentionBand.ELEVATED, "standard"),
            (AttentionBand.URGENT, "detailed"),
            (AttentionBand.CRISIS, "full"),
        ],
    )
    def test_all_bands(self, band, expected):
        assert RegimeRenderer.get_disclosure_level(band) == expected


# ---------------------------------------------------------------------------
# RegimeRenderer.get_recommended_actions
# ---------------------------------------------------------------------------


class TestGetRecommendedActions:
    """get_recommended_actions returns non-empty action lists per band."""

    @pytest.mark.parametrize(
        "band, expected_count",
        [
            (AttentionBand.CALM, 2),
            (AttentionBand.ELEVATED, 2),
            (AttentionBand.URGENT, 2),
            (AttentionBand.CRISIS, 3),
        ],
    )
    def test_action_list_length(self, band, expected_count):
        state = RegimeState(
            a_t=0.5,
            band=band,
            z_t_posterior=[],
            volatility_percentile=0.5,
            ood_score=0.5,
            transition_pressure=0.5,
            model_disagreement=0.0,
            drawdown_velocity=0.0,
            timestamp="",
        )
        actions = RegimeRenderer.get_recommended_actions(state)
        assert isinstance(actions, list)
        assert len(actions) == expected_count

    def test_crisis_actions_include_kill_switch(self):
        state = RegimeState(
            a_t=0.9,
            band=AttentionBand.CRISIS,
            z_t_posterior=[],
            volatility_percentile=0.9,
            ood_score=0.9,
            transition_pressure=0.9,
            model_disagreement=0.0,
            drawdown_velocity=0.0,
            timestamp="",
        )
        actions = RegimeRenderer.get_recommended_actions(state)
        assert "kill_switch_prominent" in actions

    def test_calm_actions_include_auto_rebalance(self):
        state = RegimeState(
            a_t=0.1,
            band=AttentionBand.CALM,
            z_t_posterior=[],
            volatility_percentile=0.1,
            ood_score=0.0,
            transition_pressure=0.0,
            model_disagreement=0.0,
            drawdown_velocity=0.0,
            timestamp="",
        )
        actions = RegimeRenderer.get_recommended_actions(state)
        assert "auto_rebalance" in actions

    def test_actions_are_strings(self):
        for band in AttentionBand:
            state = RegimeState(
                a_t=0.5,
                band=band,
                z_t_posterior=[],
                volatility_percentile=0.5,
                ood_score=0.5,
                transition_pressure=0.5,
                model_disagreement=0.0,
                drawdown_velocity=0.0,
                timestamp="",
            )
            actions = RegimeRenderer.get_recommended_actions(state)
            for action in actions:
                assert isinstance(action, str)


# ---------------------------------------------------------------------------
# RegimeRenderer.render — attention score computation
# ---------------------------------------------------------------------------


class TestRegimeRendererRender:
    """render() computes a_t from z_t posterior components."""

    def setup_method(self):
        self.renderer = RegimeRenderer()

    # -- Basic output structure --

    def test_returns_regime_state(self):
        state = self.renderer.render(
            z_t_posterior=[0.1, 0.2, 0.3],
            volatility=0.2,
            ood_score=0.1,
            change_point_prob=0.05,
            timestamp="2025-01-01T00:00:00+00:00",
        )
        assert isinstance(state, RegimeState)

    def test_timestamp_preserved(self):
        ts = "2025-06-15T14:30:00+00:00"
        state = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.1,
            ood_score=0.1,
            change_point_prob=0.1,
            timestamp=ts,
        )
        assert state.timestamp == ts

    def test_timestamp_generated_when_empty(self):
        state = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.1,
            ood_score=0.1,
            change_point_prob=0.1,
            timestamp="",
        )
        assert state.timestamp != ""
        # Must be a valid ISO 8601 string
        parsed = datetime.fromisoformat(state.timestamp)
        assert parsed.tzinfo is not None

    def test_posterior_echoed_in_state(self):
        posterior = [0.1, -0.3, 0.8]
        state = self.renderer.render(
            z_t_posterior=posterior,
            volatility=0.2,
            ood_score=0.1,
            change_point_prob=0.05,
        )
        assert state.z_t_posterior == posterior

    # -- a_t is bounded [0, 1] --

    def test_a_t_bounded_zero_to_one_all_zeros(self):
        state = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        assert 0.0 <= state.a_t <= 1.0

    def test_a_t_bounded_zero_to_one_all_ones(self):
        state = self.renderer.render(
            z_t_posterior=[1.0, 1.0],
            volatility=1.0,
            ood_score=1.0,
            change_point_prob=1.0,
        )
        assert 0.0 <= state.a_t <= 1.0

    # -- Input clamping --

    def test_volatility_clamped_below_zero(self):
        state_neg = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=-0.5,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        state_zero = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        assert state_neg.volatility_percentile == 0.0
        assert state_neg.a_t == state_zero.a_t

    def test_volatility_clamped_above_one(self):
        state_high = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=2.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        state_one = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=1.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        assert state_high.volatility_percentile == 1.0
        assert state_high.a_t == state_one.a_t

    def test_ood_score_clamped_below_zero(self):
        state = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=0.0,
            ood_score=-1.0,
            change_point_prob=0.0,
        )
        assert state.ood_score == 0.0

    def test_ood_score_clamped_above_one(self):
        state = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=0.0,
            ood_score=5.0,
            change_point_prob=0.0,
        )
        assert state.ood_score == 1.0

    def test_change_point_prob_clamped_below_zero(self):
        state = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=-0.3,
        )
        assert state.transition_pressure == 0.0

    def test_change_point_prob_clamped_above_one(self):
        state = self.renderer.render(
            z_t_posterior=[0.0],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=1.5,
        )
        assert state.transition_pressure == 1.0

    # -- Weights sum to 1.0, so max a_t with zero posterior variance is bounded --

    def test_weights_sum_to_one(self):
        """Verify internal weight constants sum to 1.0."""
        assert RegimeRenderer._W_VOL == pytest.approx(0.30)
        assert RegimeRenderer._W_OOD == pytest.approx(0.25)
        assert RegimeRenderer._W_TRANSITION == pytest.approx(0.15)
        assert RegimeRenderer._W_VARIANCE == pytest.approx(0.15)
        assert RegimeRenderer._W_DISAGREEMENT == pytest.approx(0.10)
        assert RegimeRenderer._W_DRAWDOWN_VELOCITY == pytest.approx(0.05)
        total = (
            RegimeRenderer._W_VOL
            + RegimeRenderer._W_OOD
            + RegimeRenderer._W_TRANSITION
            + RegimeRenderer._W_VARIANCE
            + RegimeRenderer._W_DISAGREEMENT
            + RegimeRenderer._W_DRAWDOWN_VELOCITY
        )
        assert total == pytest.approx(1.0)

    # -- a_t computation correctness --

    def test_all_zero_inputs_zero_posterior_variance(self):
        """With zero posterior (mean=0, var=0), all signals zero, a_t ~ 0."""
        state = self.renderer.render(
            z_t_posterior=[0.0, 0.0],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        assert state.a_t == pytest.approx(0.0)

    def test_all_max_inputs_zero_posterior_variance(self):
        """With vol=1, ood=1, trans=1, posterior=[x,x] (var=0),
        a_t = 0.30*1 + 0.25*1 + 0.15*1 + 0.15*0 + 0.10*0 + 0.05*0 = 0.70."""
        state = self.renderer.render(
            z_t_posterior=[0.5, 0.5],
            volatility=1.0,
            ood_score=1.0,
            change_point_prob=1.0,
        )
        expected = 0.30 * 1.0 + 0.25 * 1.0 + 0.15 * 1.0 + 0.15 * 0.0 + 0.10 * 0.0 + 0.05 * 0.0
        assert state.a_t == pytest.approx(expected)

    def test_known_a_t_computation(self):
        """Manual a_t check: vol=0.5, ood=0.3, trans=0.4, posterior=[0.0, 1.0].
        Mean = 0.5, variance = ((0-0.5)^2 + (1-0.5)^2) / 2 = 0.25.
        var_signal = min(0.25 / 2.0, 1.0) = 0.125.
        a_t = 0.30*0.5 + 0.25*0.3 + 0.15*0.4 + 0.15*0.125 + 0.10*0 + 0.05*0
            = 0.15 + 0.075 + 0.06 + 0.01875
            = 0.30375."""
        state = self.renderer.render(
            z_t_posterior=[0.0, 1.0],
            volatility=0.5,
            ood_score=0.3,
            change_point_prob=0.4,
        )
        expected = 0.30 * 0.5 + 0.25 * 0.3 + 0.15 * 0.4 + 0.15 * 0.125 + 0.10 * 0.0 + 0.05 * 0.0
        assert state.a_t == pytest.approx(expected)

    def test_higher_volatility_increases_a_t(self):
        state_low = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.1,
            ood_score=0.2,
            change_point_prob=0.1,
        )
        state_high = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.9,
            ood_score=0.2,
            change_point_prob=0.1,
        )
        assert state_high.a_t > state_low.a_t

    def test_higher_ood_increases_a_t(self):
        state_low = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.3,
            ood_score=0.1,
            change_point_prob=0.2,
        )
        state_high = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.3,
            ood_score=0.9,
            change_point_prob=0.2,
        )
        assert state_high.a_t > state_low.a_t

    def test_higher_transition_increases_a_t(self):
        state_low = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.3,
            ood_score=0.2,
            change_point_prob=0.05,
        )
        state_high = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.3,
            ood_score=0.2,
            change_point_prob=0.95,
        )
        assert state_high.a_t > state_low.a_t

    def test_higher_posterior_variance_increases_a_t(self):
        """A wider spread posterior increases the variance signal and a_t."""
        state_tight = self.renderer.render(
            z_t_posterior=[0.49, 0.50, 0.51],
            volatility=0.3,
            ood_score=0.2,
            change_point_prob=0.1,
        )
        state_wide = self.renderer.render(
            z_t_posterior=[-2.0, 0.0, 2.0],
            volatility=0.3,
            ood_score=0.2,
            change_point_prob=0.1,
        )
        assert state_wide.a_t > state_tight.a_t

    # -- State fields echo clamped inputs --

    def test_state_echoes_clamped_inputs(self):
        state = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=-1.0,
            ood_score=2.0,
            change_point_prob=-0.5,
        )
        assert state.volatility_percentile == 0.0
        assert state.ood_score == 1.0
        assert state.transition_pressure == 0.0


# ---------------------------------------------------------------------------
# RegimeRenderer.render — edge cases
# ---------------------------------------------------------------------------


class TestRegimeRendererEdgeCases:
    """Edge-case inputs: empty posterior, single element, NaN."""

    def setup_method(self):
        self.renderer = RegimeRenderer()

    def test_empty_posterior_uses_default_variance_signal(self):
        """Empty z_t_posterior defaults var_signal to 0.5."""
        state = self.renderer.render(
            z_t_posterior=[],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        # a_t = 0.30*0 + 0.25*0 + 0.15*0 + 0.15*0.5 + 0.10*0 + 0.05*0 = 0.075
        assert state.a_t == pytest.approx(0.075)
        assert state.z_t_posterior == []

    def test_single_element_posterior_zero_variance(self):
        """Single-element posterior has zero variance."""
        state = self.renderer.render(
            z_t_posterior=[0.7],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        # mean = 0.7, variance = 0.0, var_signal = 0.0
        assert state.a_t == pytest.approx(0.0)

    def test_single_element_posterior_large_value(self):
        """Single-element posterior still has zero variance regardless of magnitude."""
        state = self.renderer.render(
            z_t_posterior=[100.0],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        # variance = 0.0 for single element, var_signal = 0.0
        assert state.a_t == pytest.approx(0.0)

    def test_uniform_posterior_zero_variance(self):
        """All identical values produce zero variance signal."""
        state = self.renderer.render(
            z_t_posterior=[0.3, 0.3, 0.3, 0.3],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        assert state.a_t == pytest.approx(0.0)

    def test_large_posterior_variance_capped_at_one(self):
        """Variance signal is capped at 1.0 (variance / 2.0 > 1.0 for var > 2.0)."""
        # posterior with variance > 2.0: e.g., [-10, 10]
        # mean = 0, var = (100 + 100) / 2 = 100
        # var_signal = min(100/2, 1.0) = 1.0
        state = self.renderer.render(
            z_t_posterior=[-10.0, 10.0],
            volatility=1.0,
            ood_score=1.0,
            change_point_prob=1.0,
        )
        # a_t = 0.30 + 0.25 + 0.15 + 0.15*1.0 + 0.10*0 + 0.05*0 = 0.85
        assert state.a_t == pytest.approx(0.85)

    def test_nan_in_posterior_propagates_to_a_t(self):
        """NaN in z_t_posterior produces NaN in a_t (no silent masking).
        This is a documenting test: NaN input should not silently return
        a valid-looking score."""
        state = self.renderer.render(
            z_t_posterior=[0.1, float("nan"), 0.3],
            volatility=0.2,
            ood_score=0.1,
            change_point_prob=0.1,
        )
        assert math.isnan(state.a_t)

    def test_nan_volatility_produces_nan_a_t(self):
        state = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=float("nan"),
            ood_score=0.1,
            change_point_prob=0.1,
        )
        # min(max(NaN, 0.0), 1.0) = NaN in Python
        assert math.isnan(state.a_t) or math.isnan(state.volatility_percentile)

    def test_inf_in_posterior_produces_nan_variance(self):
        """Inf in posterior produces NaN in mean, NaN in variance, NaN in a_t."""
        state = self.renderer.render(
            z_t_posterior=[0.1, float("inf")],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        # (inf - inf) ** 2 = NaN
        assert math.isnan(state.a_t)

    def test_negative_inf_in_posterior(self):
        """-Inf produces NaN variance."""
        state = self.renderer.render(
            z_t_posterior=[float("-inf"), 0.5],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        assert math.isnan(state.a_t)

    def test_render_is_deterministic(self):
        """Same inputs always produce same a_t (no randomness)."""
        kwargs = dict(
            z_t_posterior=[0.1, -0.3, 0.5],
            volatility=0.4,
            ood_score=0.25,
            change_point_prob=0.15,
            timestamp="2025-01-01T00:00:00Z",
        )
        s1 = self.renderer.render(**kwargs)
        s2 = self.renderer.render(**kwargs)
        assert s1.a_t == s2.a_t
        assert s1 == s2

    def test_multiple_renders_independent(self):
        """Calling render multiple times does not accumulate state."""
        kwargs = dict(
            z_t_posterior=[0.1, 0.2],
            volatility=0.3,
            ood_score=0.1,
            change_point_prob=0.2,
            timestamp="2025-01-01T00:00:00Z",
        )
        s1 = self.renderer.render(**kwargs)
        s2 = self.renderer.render(**kwargs)
        assert s1.a_t == s2.a_t

    def test_band_matches_a_t(self):
        """The band in the returned RegimeState matches get_band(a_t)."""
        state = self.renderer.render(
            z_t_posterior=[0.1, -0.3, 0.5, 0.8],
            volatility=0.6,
            ood_score=0.7,
            change_point_prob=0.5,
        )
        assert state.band is RegimeRenderer.get_band(state.a_t)

    def test_calmer_inputs_produce_lower_band(self):
        """Low signals produce CALM, high signals produce CRISIS."""
        calm = self.renderer.render(
            z_t_posterior=[0.5, 0.5],
            volatility=0.05,
            ood_score=0.02,
            change_point_prob=0.01,
        )
        crisis = self.renderer.render(
            z_t_posterior=[-10.0, 10.0],
            volatility=1.0,
            ood_score=1.0,
            change_point_prob=1.0,
        )
        assert calm.band is AttentionBand.CALM
        assert crisis.band is AttentionBand.CRISIS
        assert calm.a_t < crisis.a_t

    def test_state_is_frozen(self):
        """Returned RegimeState cannot be mutated."""
        state = self.renderer.render(
            z_t_posterior=[0.5],
            volatility=0.2,
            ood_score=0.1,
            change_point_prob=0.05,
        )
        with pytest.raises(AttributeError):
            state.a_t = 0.99


# ---------------------------------------------------------------------------
# RegimeRenderer — posterior variance computation details
# ---------------------------------------------------------------------------


class TestPosteriorVarianceSignal:
    """Variance signal extraction from z_t_posterior."""

    def setup_method(self):
        self.renderer = RegimeRenderer()

    def test_zero_variance_produces_zero_signal(self):
        """Identical values produce zero variance, zero signal."""
        # a_t = 0.15 * var_signal + 0 = 0.15 * 0 = 0
        state = self.renderer.render(
            z_t_posterior=[1.0, 1.0, 1.0],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        assert state.a_t == pytest.approx(0.0)

    def test_variance_exactly_2_produces_signal_1(self):
        """When variance = 2.0, var_signal = min(2.0/2.0, 1.0) = 1.0.
        Posterior [0, 2]: mean=1, var = ((0-1)^2 + (2-1)^2)/2 = 1.0
        Posterior [-1, 1]: mean=0, var = (1+1)/2 = 1.0
        Need var=2: posterior [0, 2, 0, 2]: mean=1, var=1.0 -- not 2.
        Posterior [-sqrt(2), sqrt(2)]: mean=0, var=2.0/1=2.0 -- single pair.
        Actually for 2 elements: [a,b] mean=(a+b)/2, var = ((a-m)^2 + (b-m)^2)/2.
        If a=-t, b=t: mean=0, var = (t^2+t^2)/2 = t^2. So t=sqrt(2): var=2.0.
        """
        import math as m

        t = m.sqrt(2)
        state = self.renderer.render(
            z_t_posterior=[-t, t],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        # var_signal = min(2.0/2.0, 1.0) = 1.0
        # a_t = 0.15 * 1.0 = 0.15 (only variance component, all others zero)
        assert state.a_t == pytest.approx(0.15)

    def test_variance_quarter_produces_signal_eighth(self):
        """Posterior [-0.5, 0.5]: mean=0, var = (0.25+0.25)/2 = 0.25.
        var_signal = min(0.25/2.0, 1.0) = 0.125.
        a_t = 0.15 * 0.125 = 0.01875.
        """
        state = self.renderer.render(
            z_t_posterior=[-0.5, 0.5],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        assert state.a_t == pytest.approx(0.01875)

    def test_many_element_posterior(self):
        """Posterior with many elements computes correct population variance."""
        # posterior = list(range(10)) = [0,1,2,...,9]
        # mean = 4.5, var = sum((x-4.5)^2)/10 = 8.25
        # var_signal = min(8.25/2.0, 1.0) = 1.0
        posterior = list(range(10))
        state = self.renderer.render(
            z_t_posterior=[float(x) for x in posterior],
            volatility=0.0,
            ood_score=0.0,
            change_point_prob=0.0,
        )
        # var_signal capped at 1.0
        assert state.a_t == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# RegimeRenderer — disclosure level integration
# ---------------------------------------------------------------------------


class TestDisclosureIntegration:
    """Disclosure level matches band from rendered state."""

    def setup_method(self):
        self.renderer = RegimeRenderer()

    def test_calm_state_gets_minimal_disclosure(self):
        state = self.renderer.render(
            z_t_posterior=[0.5, 0.5],
            volatility=0.05,
            ood_score=0.02,
            change_point_prob=0.01,
        )
        assert RegimeRenderer.get_disclosure_level(state.band) == "minimal"

    def test_crisis_state_gets_full_disclosure(self):
        state = self.renderer.render(
            z_t_posterior=[-10.0, 10.0],
            volatility=1.0,
            ood_score=1.0,
            change_point_prob=1.0,
        )
        assert RegimeRenderer.get_disclosure_level(state.band) == "full"
