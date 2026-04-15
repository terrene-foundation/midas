"""
Tier 1 tests for M04 State Inference Pool.

Tests cover: posterior service CRUD, Bayesian filter shapes, OOD detection,
changepoint detection, and posterior combination methods.

Ref: M04 State Inference Pool specification
"""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest

from midas.fabric.engine import create_fabric


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fabric_db(tmp_path):
    """Create a temp-file SQLite DataFlow instance with all fabric models."""
    db_path = tmp_path / "test_state_inference.db"
    db = create_fabric(f"sqlite:///{db_path}", auto_migrate=True)
    yield db
    db.close()


# ---------------------------------------------------------------------------
# PosteriorMaintenanceService
# ---------------------------------------------------------------------------


class TestPosteriorService:
    """PosteriorMaintenanceService create/read-back through real DataFlow."""

    @pytest.mark.asyncio
    async def test_update_and_read_back_posterior(self, fabric_db):
        """Write a posterior via update_posterior and read it back."""
        from midas.state_inference.posterior_service import PosteriorMaintenanceService

        svc = PosteriorMaintenanceService(fabric_db)
        z_t = [0.1, -0.3, 0.5, 0.8]
        posterior_var = [0.01, 0.02, 0.015, 0.008]
        as_of = date(2025, 1, 15)

        await svc.update_posterior(
            model_family="ssl_transformer_v1",
            model_version="v1.0",
            z_t_vector=z_t,
            posterior_variance=posterior_var,
            log_likelihood=-12.5,
            as_of_date=as_of,
            is_champion=True,
        )

        result = await svc.get_latest_posterior("ssl_transformer_v1", "v1.0")
        assert result is not None
        assert result["model_family"] == "ssl_transformer_v1"
        assert result["model_version"] == "v1.0"
        assert json.loads(result["z_vector"]) == z_t
        assert json.loads(result["z_covariance"]) == posterior_var
        assert result["learner_role"] == "champion"

    @pytest.mark.asyncio
    async def test_get_latest_returns_most_recent(self, fabric_db):
        """When multiple posteriors exist, get_latest returns the newest."""
        from midas.state_inference.posterior_service import PosteriorMaintenanceService

        svc = PosteriorMaintenanceService(fabric_db)
        z_early = [0.1, 0.2]
        z_late = [0.9, 0.8]

        await svc.update_posterior(
            model_family="ssl_transformer_v1",
            model_version="v1.0",
            z_t_vector=z_early,
            posterior_variance=[0.01, 0.01],
            log_likelihood=-10.0,
            as_of_date=date(2025, 1, 1),
            is_champion=True,
        )
        await svc.update_posterior(
            model_family="ssl_transformer_v1",
            model_version="v1.0",
            z_t_vector=z_late,
            posterior_variance=[0.02, 0.02],
            log_likelihood=-8.0,
            as_of_date=date(2025, 1, 15),
            is_champion=True,
        )

        result = await svc.get_latest_posterior("ssl_transformer_v1", "v1.0")
        assert result is not None
        assert json.loads(result["z_vector"]) == z_late

    @pytest.mark.asyncio
    async def test_get_latest_returns_none_for_unknown(self, fabric_db):
        """get_latest returns None when no posterior exists."""
        from midas.state_inference.posterior_service import PosteriorMaintenanceService

        svc = PosteriorMaintenanceService(fabric_db)
        result = await svc.get_latest_posterior("nonexistent", "v0.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_posterior_history_date_range(self, fabric_db):
        """get_posterior_history returns posteriors within date range."""
        from midas.state_inference.posterior_service import PosteriorMaintenanceService

        svc = PosteriorMaintenanceService(fabric_db)

        for day in [1, 5, 10, 20]:
            await svc.update_posterior(
                model_family="contrastive_v1",
                model_version="v2.0",
                z_t_vector=[float(day)],
                posterior_variance=[0.01],
                log_likelihood=-1.0,
                as_of_date=date(2025, 1, day),
                is_champion=False,
            )

        results = await svc.get_posterior_history(
            "contrastive_v1",
            "v2.0",
            start_date=date(2025, 1, 5),
            end_date=date(2025, 1, 15),
        )
        # Days 5 and 10 are within [Jan 5, Jan 15]; day 1 and 20 are out
        assert len(results) == 2
        days = [json.loads(r["z_vector"])[0] for r in results]
        assert 5.0 in days
        assert 10.0 in days

    @pytest.mark.asyncio
    async def test_list_active_posteriors(self, fabric_db):
        """list_active_posteriors returns all latest posteriors."""
        from midas.state_inference.posterior_service import PosteriorMaintenanceService

        svc = PosteriorMaintenanceService(fabric_db)

        await svc.update_posterior(
            model_family="ssl_transformer_v1",
            model_version="v1.0",
            z_t_vector=[0.5],
            posterior_variance=[0.01],
            log_likelihood=-5.0,
            as_of_date=date(2025, 1, 10),
            is_champion=True,
        )
        await svc.update_posterior(
            model_family="contrastive_v1",
            model_version="v2.0",
            z_t_vector=[0.3],
            posterior_variance=[0.02],
            log_likelihood=-7.0,
            as_of_date=date(2025, 1, 10),
            is_champion=False,
        )

        active = await svc.list_active_posteriors()
        families = {r["model_family"] for r in active}
        assert "ssl_transformer_v1" in families
        assert "contrastive_v1" in families

    @pytest.mark.asyncio
    async def test_update_posterior_uses_pit_discipline(self, fabric_db):
        """Every posterior write carries the as_of_date as its filing date."""
        from midas.state_inference.posterior_service import PosteriorMaintenanceService

        svc = PosteriorMaintenanceService(fabric_db)
        as_of = date(2025, 3, 20)

        await svc.update_posterior(
            model_family="mae_v1",
            model_version="v1.0",
            z_t_vector=[0.1, 0.2],
            posterior_variance=[0.01, 0.01],
            log_likelihood=-3.0,
            as_of_date=as_of,
            is_champion=False,
        )

        result = await svc.get_latest_posterior("mae_v1", "v1.0")
        assert result is not None
        assert result["period_end"] == as_of.isoformat()
        assert result["filed_at"] == datetime.combine(as_of, datetime.min.time()).isoformat()


# ---------------------------------------------------------------------------
# DeepBayesianFilter
# ---------------------------------------------------------------------------


class TestDeepBayesianFilter:
    """DeepBayesianFilter forward pass produces correct output shapes."""

    def test_forward_produces_correct_shapes(self):
        """Forward pass returns (mean, variance, log_likelihood) with correct dims."""
        import torch

        from midas.state_inference.bayesian_filter import DeepBayesianFilter

        input_dim = 20
        latent_dim = 8
        batch_size = 4
        seq_len = 30

        model = DeepBayesianFilter(input_dim=input_dim, latent_dim=latent_dim, num_layers=2)
        obs = torch.randn(batch_size, seq_len, input_dim)

        mean, variance, log_likelihood = model(obs)

        assert mean.shape == (batch_size, latent_dim)
        assert variance.shape == (batch_size, latent_dim)
        assert log_likelihood.shape == (batch_size,)

    def test_variance_is_positive(self):
        """Posterior variance must be positive (exp of log_variance)."""
        import torch

        from midas.state_inference.bayesian_filter import DeepBayesianFilter

        model = DeepBayesianFilter(input_dim=10, latent_dim=4, num_layers=1)
        obs = torch.randn(2, 15, 10)

        _, variance, _ = model(obs)
        assert (variance > 0).all()

    def test_sample_posterior_produces_correct_count(self):
        """sample_posterior returns n_samples from the learned posterior."""
        import torch

        from midas.state_inference.bayesian_filter import DeepBayesianFilter

        model = DeepBayesianFilter(input_dim=10, latent_dim=4, num_layers=1)
        obs = torch.randn(1, 15, 10)
        model(obs)  # set internal state

        samples = model.sample_posterior(n_samples=100)
        assert samples.shape[0] == 100
        assert samples.shape[1] == 4

    def test_single_observation_forward(self):
        """Forward pass handles batch_size=1 correctly."""
        import torch

        from midas.state_inference.bayesian_filter import DeepBayesianFilter

        model = DeepBayesianFilter(input_dim=10, latent_dim=4, num_layers=1)
        obs = torch.randn(1, 10, 10)

        mean, variance, log_likelihood = model(obs)
        assert mean.shape == (1, 4)
        assert variance.shape == (1, 4)
        assert log_likelihood.shape == (1,)


class TestNormalizingFlowChallenger:
    """NormalizingFlowChallenger produces same interface as DeepBayesianFilter."""

    def test_forward_produces_correct_shapes(self):
        """Forward pass returns same tuple structure."""
        import torch

        from midas.state_inference.bayesian_filter import NormalizingFlowChallenger

        model = NormalizingFlowChallenger(input_dim=10, latent_dim=4, num_layers=2)
        obs = torch.randn(3, 20, 10)

        mean, variance, log_likelihood = model(obs)
        assert mean.shape == (3, 4)
        assert variance.shape == (3, 4)
        assert log_likelihood.shape == (3,)

    def test_sample_posterior(self):
        """Can sample from the flow posterior."""
        import torch

        from midas.state_inference.bayesian_filter import NormalizingFlowChallenger

        model = NormalizingFlowChallenger(input_dim=10, latent_dim=4, num_layers=1)
        obs = torch.randn(1, 10, 10)
        model(obs)

        samples = model.sample_posterior(n_samples=50)
        assert samples.shape[0] == 50


class TestNeuralKalmanChallenger:
    """NeuralKalmanChallenger produces same interface."""

    def test_forward_produces_correct_shapes(self):
        """Forward pass returns same tuple structure."""
        import torch

        from midas.state_inference.bayesian_filter import NeuralKalmanChallenger

        model = NeuralKalmanChallenger(input_dim=10, latent_dim=4)
        obs = torch.randn(2, 15, 10)

        mean, variance, log_likelihood = model(obs)
        assert mean.shape == (2, 4)
        assert variance.shape == (2, 4)
        assert log_likelihood.shape == (2,)


# ---------------------------------------------------------------------------
# OODDetector
# ---------------------------------------------------------------------------


class TestOODDetector:
    """OOD detector flags extreme inputs, passes normal inputs."""

    def test_normal_input_is_not_ood(self):
        """Input close to training states gets low OOD score."""
        from midas.state_inference.ood_detector import OODDetector

        rng = np.random.default_rng(42)
        training_states = rng.standard_normal((50, 4))

        detector = OODDetector(distance_threshold=3.0, variance_threshold=2.0)
        # Pick a point near the training data mean
        current_z = training_states.mean(axis=0)

        result = detector.detect(current_z, training_states, posterior_variance=np.array([0.1] * 4))
        assert result.is_ood is False
        assert result.score < 0.5

    def test_extreme_input_is_ood(self):
        """Input far from all training states gets high OOD score."""
        from midas.state_inference.ood_detector import OODDetector

        rng = np.random.default_rng(42)
        training_states = rng.standard_normal((50, 4))

        detector = OODDetector(distance_threshold=3.0, variance_threshold=2.0)
        # A point 20 standard deviations away
        current_z = np.array([50.0, -50.0, 50.0, -50.0])

        result = detector.detect(current_z, training_states, posterior_variance=np.array([0.1] * 4))
        assert result.is_ood is True
        assert result.score > 0.8

    def test_ood_score_is_bounded_zero_to_one(self):
        """OOD score is always in [0, 1]."""
        from midas.state_inference.ood_detector import OODDetector

        rng = np.random.default_rng(42)
        training_states = rng.standard_normal((30, 3))

        detector = OODDetector(distance_threshold=3.0, variance_threshold=2.0)
        for _ in range(20):
            z = rng.standard_normal(3) * rng.uniform(0.1, 10)
            score = detector.compute_ood_score(z, training_states)
            assert 0.0 <= score <= 1.0

    def test_detect_returns_ood_result_with_all_fields(self):
        """detect returns an OODResult with all required fields."""
        from midas.state_inference.ood_detector import OODDetector

        rng = np.random.default_rng(42)
        training_states = rng.standard_normal((20, 4))

        detector = OODDetector()
        result = detector.detect(
            current_z=rng.standard_normal(4),
            training_states=training_states,
            posterior_variance=np.array([0.1] * 4),
        )
        assert hasattr(result, "score")
        assert hasattr(result, "is_ood")
        assert hasattr(result, "nearest_distance")
        assert hasattr(result, "variance_ratio")

    def test_wide_posterior_variance_reduces_ood_score(self):
        """A wider posterior (more uncertain) should reduce OOD alarm."""
        from midas.state_inference.ood_detector import OODDetector

        rng = np.random.default_rng(42)
        training_states = rng.standard_normal((50, 4))
        current_z = training_states[0] + 3.0  # somewhat far

        detector = OODDetector(distance_threshold=3.0, variance_threshold=2.0)
        narrow_result = detector.detect(
            current_z, training_states, posterior_variance=np.array([0.01] * 4)
        )
        wide_result = detector.detect(
            current_z, training_states, posterior_variance=np.array([5.0] * 4)
        )

        assert wide_result.score < narrow_result.score


# ---------------------------------------------------------------------------
# ChangePointDetector
# ---------------------------------------------------------------------------


class TestChangePointDetector:
    """Changepoint detector detects regime flip in synthetic data."""

    def test_detects_regime_flip(self):
        """A clear mean-shift in the data produces a changepoint."""
        from midas.state_inference.changepoint import ChangePointDetector

        rng = np.random.default_rng(42)
        detector = ChangePointDetector()

        # Regime 1: mean=0, regime 2: mean=5
        regime1 = rng.normal(0, 0.5, size=20)
        regime2 = rng.normal(5, 0.5, size=20)
        data = np.concatenate([regime1, regime2])

        changepoint_found = False
        for obs in data:
            is_cp, prob, _ = detector.update(float(obs))
            if is_cp and prob > 0.5:
                changepoint_found = True

        assert changepoint_found, "Detector failed to find regime flip"

    def test_no_changepoint_in_stationary_data(self):
        """Stationary data should not produce high-probability changepoints."""
        from midas.state_inference.changepoint import ChangePointDetector

        rng = np.random.default_rng(42)
        detector = ChangePointDetector()

        stationary_data = rng.normal(0, 1.0, size=30)
        cps = []
        for obs in stationary_data:
            is_cp, prob, _ = detector.update(float(obs))
            if is_cp:
                cps.append(prob)

        # Allow at most one weak changepoint in stationary data
        high_prob_cps = [p for p in cps if p > 0.7]
        assert len(high_prob_cps) == 0, f"False changepoints in stationary data: {high_prob_cps}"

    def test_get_most_likely_changepoints_returns_list(self):
        """get_most_likely_changepoints returns a list of (index, probability)."""
        from midas.state_inference.changepoint import ChangePointDetector

        rng = np.random.default_rng(42)
        detector = ChangePointDetector()

        data = rng.normal(0, 1.0, size=10)
        for i, obs in enumerate(data):
            detector.update(float(obs))

        cps = detector.get_most_likely_changepoints()
        assert isinstance(cps, list)
        for idx, prob in cps:
            assert isinstance(idx, int)
            assert isinstance(prob, float)
            assert 0.0 <= prob <= 1.0

    def test_update_returns_run_length_distribution(self):
        """update returns the run-length distribution."""
        from midas.state_inference.changepoint import ChangePointDetector

        detector = ChangePointDetector()
        _, _, run_lengths = detector.update(1.0)

        assert isinstance(run_lengths, np.ndarray)
        # After one observation, run-length distribution has one entry
        assert len(run_lengths) >= 1


# ---------------------------------------------------------------------------
# PosteriorCombination
# ---------------------------------------------------------------------------


class TestPosteriorCombination:
    """Posterior combination methods produce valid outputs."""

    def test_mixture_average(self):
        """mixture_average returns mean/variance of the mixture."""
        from midas.state_inference.posterior_combination import PosteriorCombination

        combiner = PosteriorCombination()
        posteriors = [
            {"mean": np.array([1.0, 2.0]), "variance": np.array([0.1, 0.2])},
            {"mean": np.array([3.0, 4.0]), "variance": np.array([0.3, 0.4])},
        ]
        weights = [0.6, 0.4]

        result = combiner.mixture_average(posteriors, weights)
        assert "mean" in result
        assert "variance" in result
        # Mixture mean is weighted average of means
        expected_mean = 0.6 * np.array([1.0, 2.0]) + 0.4 * np.array([3.0, 4.0])
        np.testing.assert_allclose(result["mean"], expected_mean, atol=1e-6)

    def test_weighted_average(self):
        """weighted_average returns precision-weighted combination."""
        from midas.state_inference.posterior_combination import PosteriorCombination

        combiner = PosteriorCombination()
        posteriors = [
            {"mean": np.array([1.0, 2.0]), "variance": np.array([0.1, 0.2])},
            {"mean": np.array([3.0, 4.0]), "variance": np.array([0.3, 0.4])},
        ]
        weights = [0.5, 0.5]

        result = combiner.weighted_average(posteriors, weights)
        assert "mean" in result
        assert "variance" in result
        # Result variance should be less than any input variance (fusion reduces uncertainty)
        assert np.all(result["variance"] < 0.3)

    def test_router_selected(self):
        """router_selected picks the posterior with highest router score."""
        from midas.state_inference.posterior_combination import PosteriorCombination

        combiner = PosteriorCombination()
        posteriors = [
            {"mean": np.array([1.0, 2.0]), "variance": np.array([0.1, 0.2])},
            {"mean": np.array([3.0, 4.0]), "variance": np.array([0.3, 0.4])},
        ]
        router_scores = [0.3, 0.7]

        result = combiner.router_selected(posteriors, router_scores, z_t=np.array([0.5, 0.5]))
        # Should select the posterior with score 0.7 (index 1)
        np.testing.assert_array_equal(result["mean"], np.array([3.0, 4.0]))
        np.testing.assert_array_equal(result["variance"], np.array([0.3, 0.4]))

    def test_mixture_average_with_single_posterior(self):
        """mixture_average with one posterior returns it unchanged."""
        from midas.state_inference.posterior_combination import PosteriorCombination

        combiner = PosteriorCombination()
        posteriors = [
            {"mean": np.array([1.0, 2.0]), "variance": np.array([0.1, 0.2])},
        ]
        weights = [1.0]

        result = combiner.mixture_average(posteriors, weights)
        np.testing.assert_allclose(result["mean"], np.array([1.0, 2.0]))
        np.testing.assert_allclose(result["variance"], np.array([0.1, 0.2]))

    def test_weighted_average_variance_is_positive(self):
        """Fused posterior variance must be positive."""
        from midas.state_inference.posterior_combination import PosteriorCombination

        combiner = PosteriorCombination()
        posteriors = [
            {"mean": np.array([1.0]), "variance": np.array([0.5])},
            {"mean": np.array([2.0]), "variance": np.array([0.3])},
        ]
        weights = [0.5, 0.5]

        result = combiner.weighted_average(posteriors, weights)
        assert np.all(result["variance"] > 0)
