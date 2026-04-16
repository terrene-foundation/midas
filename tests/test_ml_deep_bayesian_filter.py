"""Tier 1 tests for the deep Bayesian filter."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import torch

from midas.fabric.models import LatentStateRecord, PITKey
from midas.ml.deep_bayesian_filter import (
    DeepBayesianFilter,
    DeepBayesianFilterService,
    DeepPosteriorState,
    PosteriorUpdate,
)


def _make_record(
    learner_family: str = "ssl_transformer_v1",
    learner_role: str = "champion",
    z_vector: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4),
    period_end: date = None,
    filed_at: datetime = None,
) -> LatentStateRecord:
    if period_end is None:
        period_end = date(2024, 12, 31)
    if filed_at is None:
        filed_at = datetime(2024, 12, 31, 16, 0, 0)
    return LatentStateRecord(
        state_id=f"state_{learner_family}",
        pit=PITKey(period_end=period_end, filed_at=filed_at),
        learner_family=learner_family,
        learner_role=learner_role,
        z_dim=len(z_vector),
        z_vector=z_vector,
        z_covariance=None,
        z_scale=0.1,
        pool_index=None,
    )


class TestDeepBayesianFilterInit:
    """Tests for DeepBayesianFilter initialization."""

    def test_deep_filter_init_creates_mlp(self):
        """MLP has correct dimensions for latent_dim=4."""
        dbf = DeepBayesianFilter(latent_dim=4, hidden_dim=64)

        assert dbf.latent_dim == 4
        assert dbf.hidden_dim == 64

        # Check gain_mlp input/output shapes
        gain_input = torch.randn(4 * 3)  # (z_obs, prior_mean, prior_diag)
        assert gain_input.shape == (12,)
        out = dbf.gain_mlp(gain_input)
        assert out.shape == (4,)  # one gain per dimension

        # Check noise_net: takes (prior_mean, prior_diag, z_obs) = 3 * latent_dim
        noise_input = torch.randn(4 * 3)  # (prior_mean, prior_diag, z_obs) = 12
        assert noise_input.shape == (12,)
        noise_out = dbf.noise_net(noise_input)
        assert noise_out.shape == (2,)  # log(R_diag), log(Q_diag)

    def test_deep_filter_init_different_latent_dims(self):
        """Initializes correctly for various latent dimensions."""
        for dim in [2, 8, 16, 32]:
            dbf = DeepBayesianFilter(latent_dim=dim, hidden_dim=32)
            assert dbf.latent_dim == dim


class TestDeepBayesianFilterUpdate:
    """Tests for DeepBayesianFilter.update()."""

    def test_deep_filter_update_returns_ndarray(self):
        """Returns numpy arrays."""
        dbf = DeepBayesianFilter(latent_dim=4)

        prior_mean = np.array([0.0, 0.0, 0.0, 0.0])
        prior_cov_diag = np.array([0.01, 0.01, 0.01, 0.01])
        z_obs = np.array([0.5, 0.5, 0.5, 0.5])

        post_mean, post_cov = dbf.update(prior_mean, prior_cov_diag, z_obs, 1e-3, 1e-2)

        assert isinstance(post_mean, np.ndarray)
        assert isinstance(post_cov, np.ndarray)
        assert post_mean.shape == (4,)
        assert post_cov.shape == (4,)

    def test_deep_filter_gain_is_bounded(self):
        """Adaptive gain is in [-1, 1] range (Tanh output)."""
        dbf = DeepBayesianFilter(latent_dim=4, hidden_dim=64)

        for _ in range(10):
            prior_mean = np.random.randn(4) * 0.5
            prior_cov_diag = np.abs(np.random.randn(4)) * 0.1 + 0.001
            z_obs = np.random.randn(4)

            gain_input = torch.tensor(
                np.concatenate([z_obs, prior_mean, prior_cov_diag]), dtype=torch.float32
            )
            adaptive_gain = dbf.gain_mlp(gain_input)

            assert torch.all(adaptive_gain >= -1.0 - 1e-5)
            assert torch.all(adaptive_gain <= 1.0 + 1e-5)

    def test_deep_filter_posterior_shrinks_with_repeated_obs(self):
        """Posterior narrows with consistent observations."""
        dbf = DeepBayesianFilter(latent_dim=4)

        # Start with wide prior
        prior_mean = np.array([0.0, 0.0, 0.0, 0.0])
        prior_cov_diag = np.array([1.0, 1.0, 1.0, 1.0])

        # Consistent observation
        z_obs = np.array([0.1, 0.2, 0.3, 0.4])

        post_mean1, post_cov1 = dbf.update(prior_mean, prior_cov_diag, z_obs, 1e-3, 1e-2)
        post_mean2, post_cov2 = dbf.update(post_mean1, post_cov1, z_obs, 1e-3, 1e-2)
        post_mean3, post_cov3 = dbf.update(post_mean2, post_cov2, z_obs, 1e-3, 1e-2)

        # Posterior should get closer to observation and narrower
        assert np.abs(post_mean3 - z_obs).mean() < np.abs(prior_mean - z_obs).mean()
        # Width should decrease
        assert post_cov3.mean() < prior_cov_diag.mean()

    def test_deep_filter_forward_alias(self):
        """forward() is an alias for update() with defaults."""
        dbf = DeepBayesianFilter(latent_dim=4)

        prior_mean = np.array([0.0, 0.0, 0.0, 0.0])
        prior_cov_diag = np.array([0.1, 0.1, 0.1, 0.1])
        z_obs = np.array([0.5, 0.5, 0.5, 0.5])

        post_mean1, post_cov1 = dbf.forward(prior_mean, prior_cov_diag, z_obs)
        post_mean2, post_cov2 = dbf.update(prior_mean, prior_cov_diag, z_obs, 1e-3, 1e-2)

        np.testing.assert_allclose(post_mean1, post_mean2)
        np.testing.assert_allclose(post_cov1, post_cov2)

    def test_deep_filter_noise_estimates_are_positive(self):
        """noise_net outputs are positive (exp of real values)."""
        dbf = DeepBayesianFilter(latent_dim=4)

        prior_mean = np.array([0.1, 0.2, 0.3, 0.4])
        prior_cov_diag = np.array([0.01, 0.01, 0.01, 0.01])
        z_obs = np.array([0.5, 0.5, 0.5, 0.5])

        noise_input = torch.tensor(
            np.concatenate([prior_mean, prior_cov_diag, z_obs]), dtype=torch.float32
        )
        noise_scales = torch.exp(dbf.noise_net(noise_input))

        assert torch.all(noise_scales > 0)


class TestDeepBayesianFilterService:
    """Tests for DeepBayesianFilterService."""

    @pytest.mark.asyncio
    async def test_service_same_interface_as_kalman(self):
        """Same async update() signature as PosteriorMaintenanceService."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = DeepBayesianFilterService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record = _make_record(z_vector=(0.1, 0.2, 0.3, 0.4))

        # Should return PosteriorUpdate (same as Kalman service)
        result = await service.update(record)

        assert isinstance(result, PosteriorUpdate)
        assert result.learner_family == "ssl_transformer_v1"
        assert result.posterior_width >= 0

    @pytest.mark.asyncio
    async def test_service_cold_start_uses_kalman(self):
        """First update (cold start) uses standard Kalman."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = DeepBayesianFilterService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record1 = _make_record(z_vector=(0.1, 0.2, 0.3, 0.4), period_end=date(2024, 12, 30))
        record2 = _make_record(z_vector=(0.2, 0.3, 0.4, 0.5), period_end=date(2024, 12, 31))

        result1 = await service.update(record1)
        result2 = await service.update(record2)

        # After cold start, update count should be 1 (Kalman applied on second call)
        assert result2.update_count == 1
        # Mean should have shifted
        assert result2.z_mean != result1.z_mean

    @pytest.mark.asyncio
    async def test_service_multiple_updates_work(self):
        """Multiple sequential updates work correctly."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = DeepBayesianFilterService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        dates = [
            date(2024, 12, 28),
            date(2024, 12, 29),
            date(2024, 12, 30),
            date(2024, 12, 31),
            date(2025, 1, 1),
        ]
        for i in range(5):
            record = _make_record(
                z_vector=(0.1 + i * 0.01, 0.2 + i * 0.01, 0.3 + i * 0.01, 0.4 + i * 0.01),
                period_end=dates[i],
            )
            result = await service.update(record)
            assert result.update_count == i  # 0, 1, 2, 3, 4

    @pytest.mark.asyncio
    async def test_service_writes_to_fabric(self):
        """Each update writes a LatentStateRecord to fabric."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = DeepBayesianFilterService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record = _make_record(z_vector=(0.5, 0.5, 0.5, 0.5))
        await service.update(record)

        mock_writer.write_latent_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_get_posterior_returns_state(self):
        """get_posterior returns the in-memory posterior."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = DeepBayesianFilterService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record = _make_record(z_vector=(0.1, 0.2, 0.3, 0.4))
        await service.update(record)

        state = service.get_posterior("ssl_transformer_v1")
        assert state is not None
        assert isinstance(state, DeepPosteriorState)

    @pytest.mark.asyncio
    async def test_service_independent_learners(self):
        """Different learners have independent posteriors."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = DeepBayesianFilterService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        r1 = _make_record(learner_family="ssl_transformer_v1", z_vector=(1.0, 2.0, 3.0, 4.0))
        r2 = _make_record(
            learner_family="contrastive_v1",
            learner_role="challenger_shadow",
            z_vector=(10.0, 20.0, 30.0, 40.0),
        )

        await service.update(r1)
        await service.update(r2)

        s1 = service.get_posterior("ssl_transformer_v1")
        s2 = service.get_posterior("contrastive_v1")

        assert s1 is not None
        assert s2 is not None
        assert s1.z_mean[0] != s2.z_mean[0]

    @pytest.mark.asyncio
    async def test_service_posteriors_summary(self):
        """posteriors_summary returns info for all learners."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = DeepBayesianFilterService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        for learner in ["ssl_transformer_v1", "contrastive_v1", "mae_v1"]:
            record = _make_record(learner_family=learner)
            await service.update(record)

        summary = service.posteriors_summary()
        assert set(summary.keys()) == {"ssl_transformer_v1", "contrastive_v1", "mae_v1"}
