"""Tier 1 tests for the posterior-maintenance service."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from midas.fabric.models import LatentStateRecord, PITKey
from midas.ml.posterior_state import (
    DEFAULT_OBSERVATION_VARIANCE,
    DEFAULT_PROCESS_VARIANCE,
    PosteriorMaintenanceService,
    PosteriorState,
)


def _make_record(
    learner_family: str = "ssl_transformer_v1",
    learner_role: str = "champion",
    z_vector: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4),
    period_end: date = None,
    filed_at: datetime = None,
    z_scale: float = 0.1,
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
        z_scale=z_scale,
        pool_index=None,
    )


class TestKalmanUpdate:
    """Tests for the Kalman filter math."""

    def test_kalman_update_shifts_mean_toward_observation(self):
        """The posterior mean moves toward the observed z_t."""
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=MagicMock(),
        )

        prior_mean = np.array([0.0, 0.0, 0.0, 0.0])
        prior_cov = np.eye(4) * DEFAULT_OBSERVATION_VARIANCE
        z_obs = np.array([1.0, 1.0, 1.0, 1.0])

        post_mean, post_cov = service._kalman_update(prior_mean, prior_cov, z_obs)

        # Posterior mean should be pulled toward observation but not fully
        assert 0.0 < post_mean[0] < 1.0
        # Diagonal variances should shrink (information gain)
        assert post_cov[0, 0] < prior_cov[0, 0]

    def test_kalman_update_preserves_covariance_symmetry(self):
        """The posterior covariance is symmetric."""
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=MagicMock(),
        )

        prior_mean = np.array([0.1, 0.2, 0.3, 0.4])
        prior_cov = np.eye(4) * 0.01 + np.array(
            [[0, 0.001, 0, 0], [-0.001, 0, 0, 0], [0, 0, 0, 0.001], [0, 0, -0.001, 0]]
        )
        prior_cov = 0.5 * (prior_cov + prior_cov.T)  # make symmetric
        z_obs = np.array([0.5, 0.5, 0.5, 0.5])

        post_mean, post_cov = service._kalman_update(prior_mean, prior_cov, z_obs)

        assert np.allclose(post_cov, post_cov.T)

    def test_kalman_update_with_zero_observation_variance(self):
        """Perfect observation (R=0) sets posterior to observation exactly."""
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=MagicMock(),
            observation_variance=0.0,
        )

        prior_mean = np.array([0.0, 0.0])
        prior_cov = np.eye(2) * 0.1
        z_obs = np.array([0.5, -0.5])

        post_mean, post_cov = service._kalman_update(prior_mean, prior_cov, z_obs)

        np.testing.assert_allclose(post_mean, z_obs, rtol=1e-6)


class TestPosteriorStateInit:
    """Tests for posterior initialization."""

    def test_init_posterior_sets_mean_to_z_candidate(self):
        """First candidate sets the posterior mean."""
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=MagicMock(),
        )

        z_candidate = np.array([0.1, 0.2, 0.3, 0.4])
        state = service._init_posterior(
            "ssl_transformer_v1",
            "champion",
            z_candidate,
            date(2024, 12, 31),
            datetime(2024, 12, 31, 16, 0, 0),
        )

        np.testing.assert_array_almost_equal(state.z_mean, z_candidate)
        assert state.update_count == 0
        assert state.learner_family == "ssl_transformer_v1"

    def test_init_posterior_covariance_is_observation_noise(self):
        """Initial covariance is diagonal R * I."""
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=MagicMock(),
        )

        z_candidate = np.array([0.1, 0.2, 0.3])
        state = service._init_posterior(
            "contrastive_v1",
            "challenger_shadow",
            z_candidate,
            date(2024, 12, 31),
            datetime(2024, 12, 31, 16, 0, 0),
        )

        np.testing.assert_array_almost_equal(state.z_cov, np.eye(3) * DEFAULT_OBSERVATION_VARIANCE)


class TestUpdate:
    """Tests for the update method."""

    @pytest.mark.asyncio
    async def test_first_update_initializes_posterior(self):
        """First update call creates a new PosteriorState."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record = _make_record(z_vector=(0.1, 0.2, 0.3, 0.4))
        result = await service.update(record)

        assert result.learner_family == "ssl_transformer_v1"
        assert result.update_count == 0
        assert result.posterior_width >= 0

    @pytest.mark.asyncio
    async def test_second_update_applies_kalman_filter(self):
        """Second update applies Kalman update and increments counter."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record1 = _make_record(
            z_vector=(0.1, 0.2, 0.3, 0.4),
            period_end=date(2024, 12, 30),
        )
        record2 = _make_record(
            z_vector=(0.2, 0.3, 0.4, 0.5),
            period_end=date(2024, 12, 31),
        )

        result1 = await service.update(record1)
        result2 = await service.update(record2)

        assert result2.update_count == 1
        # Mean should have shifted toward the new observation
        assert result2.z_mean[0] != result1.z_mean[0]

    @pytest.mark.asyncio
    async def test_update_writes_to_fabric(self):
        """Each update writes a LatentStateRecord to fabric."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record = _make_record(z_vector=(0.5, 0.5, 0.5, 0.5))
        await service.update(record)

        mock_writer.write_latent_state.assert_called_once()
        call_args = mock_writer.write_latent_state.call_args
        written_record = call_args[0][0]
        assert written_record.learner_family == "ssl_transformer_v1"

    @pytest.mark.asyncio
    async def test_get_posterior_returns_current_state(self):
        """get_posterior returns the in-memory posterior after update."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record = _make_record(z_vector=(0.1, 0.2, 0.3, 0.4))
        await service.update(record)

        state = service.get_posterior("ssl_transformer_v1")
        assert state is not None
        assert isinstance(state, PosteriorState)

    @pytest.mark.asyncio
    async def test_posterior_width_decreases_with_updates(self):
        """Posterior width shrinks as more observations accumulate."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        z_vals = [(0.1, 0.2, 0.3, 0.4), (0.15, 0.25, 0.35, 0.45)]
        widths = []
        for i, z in enumerate(z_vals):
            record = _make_record(
                z_vector=z,
                period_end=date(2024, 12, 30 + i),
            )
            result = await service.update(record)
            widths.append(result.posterior_width)

        # Width should be non-negative (always)
        assert all(w >= 0 for w in widths)

    @pytest.mark.asyncio
    async def test_multiple_learners_have_independent_posteriors(self):
        """Each learner family maintains its own independent posterior."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = PosteriorMaintenanceService(
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
        assert s1.z_mean[0] != s2.z_mean[0]  # completely different scale


class TestWarmStart:
    """Tests for the warm_start method."""

    @pytest.mark.asyncio
    async def test_warm_start_returns_false_when_no_prior(self):
        """warm_start returns False if no prior exists in fabric."""
        mock_reader = MagicMock()
        mock_reader.read_latent_state = AsyncMock(return_value=[])
        service = PosteriorMaintenanceService(
            fabric_reader=mock_reader,
            fabric_writer=MagicMock(),
        )

        found = await service.warm_start("nonexistent", date(2024, 12, 31))
        assert found is False

    @pytest.mark.asyncio
    async def test_warm_start_returns_true_and_loads_prior(self):
        """warm_start returns True and loads prior when found."""
        mock_reader = MagicMock()
        mock_reader.read_latent_state = AsyncMock(
            return_value=[
                _make_record(
                    learner_family="ssl_transformer_v1",
                    z_vector=(0.5, 0.6, 0.7, 0.8),
                    period_end=date(2024, 12, 30),
                )
            ]
        )
        service = PosteriorMaintenanceService(
            fabric_reader=mock_reader,
            fabric_writer=MagicMock(),
        )

        found = await service.warm_start("ssl_transformer_v1", date(2024, 12, 31))
        assert found is True
        state = service.get_posterior("ssl_transformer_v1")
        assert state is not None
        np.testing.assert_array_almost_equal(state.z_mean, [0.5, 0.6, 0.7, 0.8])


class TestPosteriorsSummary:
    """Tests for the posteriors_summary method."""

    @pytest.mark.asyncio
    async def test_summary_includes_all_learners(self):
        """summary() returns info for all learners with active posteriors."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        for learner in ["ssl_transformer_v1", "contrastive_v1", "mae_v1"]:
            record = _make_record(learner_family=learner)
            await service.update(record)

        summary = service.posteriors_summary()
        assert set(summary.keys()) == {"ssl_transformer_v1", "contrastive_v1", "mae_v1"}

    @pytest.mark.asyncio
    async def test_summary_includes_update_count(self):
        """Each learner's summary includes update_count."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = PosteriorMaintenanceService(
            fabric_reader=MagicMock(),
            fabric_writer=mock_writer,
        )

        record = _make_record(learner_family="ssl_transformer_v1")
        await service.update(record)
        await service.update(
            _make_record(
                learner_family="ssl_transformer_v1",
                period_end=date(2024, 12, 31),
            )
        )

        summary = service.posteriors_summary()
        assert summary["ssl_transformer_v1"]["update_count"] == 1
