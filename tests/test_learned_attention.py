"""Tests for learned attention model and regime integration."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import torch

from midas.regime import (
    AttentionBand,
    AttentionWeightLearner,
    LearnedAttentionModel,
    RegimeRenderer,
    RegimeState,
)
from midas.regime.learned_attention import (
    DEFAULT_PRIOR_WEIGHTS,
    FEATURE_NAMES,
    NUM_FEATURES,
)


# ---------------------------------------------------------------------------
# LearnedAttentionModel unit tests
# ---------------------------------------------------------------------------


class TestLearnedAttentionModel:
    def test_output_shape_and_sum(self):
        model = LearnedAttentionModel()
        x = torch.randn(1, NUM_FEATURES)
        out = model(x)
        assert out.shape == (1, NUM_FEATURES)
        assert abs(out.sum().item() - 1.0) < 1e-5

    def test_predict_weights_returns_list(self):
        model = LearnedAttentionModel()
        features = torch.randn(NUM_FEATURES)
        weights = model.predict_weights(features)
        assert len(weights) == NUM_FEATURES
        assert abs(sum(weights) - 1.0) < 1e-5

    def test_get_weights_returns_list(self):
        model = LearnedAttentionModel()
        weights = model.get_weights()
        assert len(weights) == NUM_FEATURES
        assert abs(sum(weights) - 1.0) < 1e-5

    def test_all_weights_nonnegative(self):
        model = LearnedAttentionModel()
        weights = model.get_weights()
        assert all(w >= 0 for w in weights)

    def test_train_step_reduces_loss(self):
        model = LearnedAttentionModel()
        features = torch.tensor([0.5, 0.3, 0.2, 0.4, 0.1, 0.6])
        target = torch.tensor([0.8])
        losses = []
        for _ in range(50):
            loss = model.train_step(features, target, lr=0.01)
            losses.append(loss)
        # Loss should trend downward
        assert losses[-1] < losses[0]

    def test_train_step_records_history(self):
        model = LearnedAttentionModel()
        features = torch.randn(NUM_FEATURES)
        target = torch.tensor([0.5])
        model.train_step(features, target)
        assert model.training_steps == 1
        assert len(model.training_history) == 1
        assert model.training_history[0]["step"] == 1

    def test_1d_input_handled(self):
        model = LearnedAttentionModel()
        features = torch.randn(NUM_FEATURES)
        weights = model.predict_weights(features)
        assert len(weights) == NUM_FEATURES


# ---------------------------------------------------------------------------
# AttentionWeightLearner tests
# ---------------------------------------------------------------------------


class TestAttentionWeightLearner:
    def test_not_trained_initially(self):
        learner = AttentionWeightLearner()
        assert not learner.is_trained
        assert learner.get_weights() is None

    def test_add_observation(self):
        learner = AttentionWeightLearner()
        learner.add_observation([0.5, 0.3, 0.2, 0.4, 0.1, 0.6], 0.8)
        assert learner.observation_count == 1

    def test_add_observation_tensor(self):
        learner = AttentionWeightLearner()
        features = torch.tensor([0.5, 0.3, 0.2, 0.4, 0.1, 0.6])
        learner.add_observation(features, 0.8)
        assert learner.observation_count == 1

    def test_add_observation_wrong_size_raises(self):
        learner = AttentionWeightLearner()
        with pytest.raises(ValueError, match="Expected 6 features"):
            learner.add_observation([0.1, 0.2], 0.5)

    def test_train_batch_insufficient_data(self):
        learner = AttentionWeightLearner(batch_size=32)
        for i in range(10):
            learner.add_observation([0.1] * 6, 0.5)
        result = learner.train_batch()
        assert result is None
        assert not learner.is_trained

    def test_train_batch_sufficient_data(self):
        learner = AttentionWeightLearner(batch_size=8)
        for i in range(10):
            learner.add_observation(
                [0.5, 0.3, 0.2, 0.4, 0.1, 0.6],
                0.8,
            )
        result = learner.train_batch()
        assert result is not None
        assert learner.is_trained
        assert learner.get_weights() is not None

    def test_train_all(self):
        learner = AttentionWeightLearner()
        for i in range(20):
            learner.add_observation(
                [0.5, 0.3, 0.2, 0.4, 0.1, 0.6],
                0.8,
            )
        losses = learner.train_all(epochs=3)
        assert len(losses) == 3
        assert learner.is_trained

    def test_train_all_empty(self):
        learner = AttentionWeightLearner()
        losses = learner.train_all()
        assert losses == []

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learner = AttentionWeightLearner(save_base_dir=tmpdir)
            for i in range(20):
                learner.add_observation(
                    [0.5, 0.3, 0.2, 0.4, 0.1, 0.6],
                    0.8,
                )
            learner.train_all(epochs=5)
            original_weights = learner.get_weights()

            path = Path(tmpdir) / "model.json"
            learner.save(path)
            assert path.exists()

            learner2 = AttentionWeightLearner(save_base_dir=tmpdir)
            learner2.load(path)
            assert learner2.is_trained
            loaded_weights = learner2.get_weights()
            assert loaded_weights is not None
            for orig, loaded in zip(original_weights, loaded_weights):
                assert abs(orig - loaded) < 1e-5


# ---------------------------------------------------------------------------
# RegimeRenderer integration with learned weights
# ---------------------------------------------------------------------------


class TestRegimeRendererLearnedWeights:
    def test_default_weights_without_learner(self):
        renderer = RegimeRenderer()
        state = renderer.render(
            z_t_posterior=[0.1, 0.2, 0.3],
            volatility=0.5,
            ood_score=0.3,
            change_point_prob=0.2,
            model_disagreement=0.1,
            drawdown_velocity=0.05,
        )
        assert isinstance(state, RegimeState)
        assert 0.0 <= state.a_t <= 1.0

    def test_default_weights_match_prior(self):
        renderer = RegimeRenderer()
        # Compute a_t manually with default weights
        posterior = [0.1, 0.2, 0.3]
        vol, ood, trans, disagreement, dd_vel = 0.5, 0.3, 0.2, 0.1, 0.05
        # Replicate RegimeRenderer's variance computation
        mean_p = sum(posterior) / len(posterior)
        variance = sum((x - mean_p) ** 2 for x in posterior) / len(posterior)
        var_signal = min(variance / 2.0, 1.0)
        expected = sum(
            w * s
            for w, s in zip(
                DEFAULT_PRIOR_WEIGHTS,
                [vol, ood, trans, var_signal, disagreement, dd_vel],
            )
        )
        state = renderer.render(
            z_t_posterior=posterior,
            volatility=vol,
            ood_score=ood,
            change_point_prob=trans,
            model_disagreement=disagreement,
            drawdown_velocity=dd_vel,
        )
        assert abs(state.a_t - expected) < 1e-6

    def test_learned_weights_override_defaults(self):
        learner = AttentionWeightLearner()
        # Train with data that emphasizes volatility
        for _ in range(50):
            learner.add_observation([1.0, 0.0, 0.0, 0.0, 0.0, 0.0], 1.0)
            learner.add_observation([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.0)
        learner.train_all(epochs=10)

        renderer_learned = RegimeRenderer(weight_learner=learner)
        renderer_default = RegimeRenderer()

        state_learned = renderer_learned.render(
            z_t_posterior=[0.1, 0.2, 0.3],
            volatility=1.0,
            ood_score=0.0,
            change_point_prob=0.0,
            model_disagreement=0.0,
            drawdown_velocity=0.0,
        )
        state_default = renderer_default.render(
            z_t_posterior=[0.1, 0.2, 0.3],
            volatility=1.0,
            ood_score=0.0,
            change_point_prob=0.0,
            model_disagreement=0.0,
            drawdown_velocity=0.0,
        )
        # Learned model should produce different a_t than default
        assert state_learned.a_t != state_default.a_t

    def test_untrained_learner_falls_back_to_defaults(self):
        learner = AttentionWeightLearner()
        renderer = RegimeRenderer(weight_learner=learner)
        state = renderer.render(
            z_t_posterior=[0.1, 0.2, 0.3],
            volatility=0.5,
            ood_score=0.3,
            change_point_prob=0.2,
            model_disagreement=0.1,
            drawdown_velocity=0.05,
        )
        # Should use default weights since learner is untrained
        assert isinstance(state, RegimeState)
        assert state.band in [
            AttentionBand.CALM,
            AttentionBand.ELEVATED,
            AttentionBand.URGENT,
            AttentionBand.CRISIS,
        ]

    def test_learned_weights_always_valid(self):
        learner = AttentionWeightLearner()
        for _ in range(50):
            learner.add_observation([0.5, 0.3, 0.2, 0.4, 0.1, 0.6], 0.8)
        learner.train_all(epochs=5)

        weights = learner.get_weights()
        assert weights is not None
        assert len(weights) == NUM_FEATURES
        assert abs(sum(weights) - 1.0) < 1e-4
        assert all(w >= -0.01 for w in weights)

        renderer = RegimeRenderer(weight_learner=learner)
        state = renderer.render(
            z_t_posterior=[0.1, 0.2, 0.3],
            volatility=0.9,
            ood_score=0.8,
            change_point_prob=0.7,
            model_disagreement=0.6,
            drawdown_velocity=0.5,
        )
        assert 0.0 <= state.a_t <= 1.0
