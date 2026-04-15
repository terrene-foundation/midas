"""
Tests for T-00-02: Latent-State Learnability Probe.

Tier 1: Probe detects planted latent structure (z vectors correlated with returns).
Tier 2: Probe correctly rejects noise (no correlation between z and returns).

Ref: specs/04-latent-first-architecture.md §2.2
Ref: T-00-02
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock

import numpy as np
import pytest

from midas.evaluation.probes.latent_learnability import LatentLearnabilityProbe  # noqa: F401
from midas.fabric.models import LatentStateRecord, PITKey


def make_latent_record(
    z_vector: list[float],
    period_end: date,
    filed_at: datetime,
    learner_family: str = "ssl_transformer_v1",
    learner_role: str = "champion",
    z_dim: int | None = None,
) -> LatentStateRecord:
    """Construct a LatentStateRecord with the given z_vector."""
    dim = z_dim if z_dim is not None else len(z_vector)
    return LatentStateRecord(
        state_id=str(uuid.uuid4()),
        pit=PITKey(
            period_end=period_end,
            filed_at=filed_at,
            restated_at=None,
            source_vintage=None,
        ),
        learner_family=learner_family,
        learner_role=learner_role,
        z_dim=dim,
        z_vector=tuple(z_vector),
        z_covariance=None,
        z_scale=None,
        pool_index=None,
    )


class TestLatentLearnabilityProbe:
    """Tier 1 + Tier 2 tests for the learnability probe."""

    @pytest.fixture
    def mock_reader(self):
        """FabricReader stub that returns pre-loaded LatentStateRecords."""
        reader = AsyncMock()
        reader.read_latent_state = AsyncMock()
        return reader

    # -------------------------------------------------------------------------
    # Tier 1 — planted structure should PASS
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_probe_detects_planted_latent_structure(self, mock_reader):
        """Tier 1: z vectors encode sine wave, returns are positively correlated.

        The probe should detect the mutual information between z and returns
        and PASS (passes=True).
        """
        n_obs = 300  # more than MIN_OBSERVATIONS (252)

        # Plant synthetic latent states: 2D manifold (sin, cos) of angle
        z_records = []
        forward_returns = []
        for i in range(n_obs):
            angle = 2 * math.pi * i / n_obs
            z_vec = [math.sin(angle), math.cos(angle)]

            # Returns are monotonically related to sin(angle) — strong MI signal
            realized = math.sin(angle) + np.random.default_rng(i).normal(0, 0.05)

            record = make_latent_record(
                z_vector=z_vec,
                period_end=date(2024, 1, 1),
                filed_at=datetime(2024, 1, 1),
            )
            z_records.append(record)
            forward_returns.append(realized)

        mock_reader.read_latent_state.return_value = z_records

        probe = LatentLearnabilityProbe(mock_reader)
        result = await probe.run(
            learner_family="ssl_transformer_v1",
            z_dim=2,
            as_of=date(2024, 1, 1),
            forward_horizon=20,
            realized_returns_override=forward_returns,
        )

        assert result.passes is True, (
            f"Probe should PASS on planted structure. "
            f"MI={result.mi_actual:.4f} vs null μ={result.mi_null_mean:.4f} "
            f"(σ={result.mi_null_std:.4f}), z={result.z_statistic:.3f}, p={result.p_value:.4f}"
        )
        assert not math.isnan(result.mi_actual), "MI should be a finite value"
        assert result.mi_actual > result.mi_null_mean, "Actual MI should exceed null MI"

    # -------------------------------------------------------------------------
    # Tier 2 — pure noise should FAIL
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_probe_rejects_pure_noise(self, mock_reader):
        """Tier 2: z vectors and returns are independent Gaussian noise.

        The probe should fail to detect MI above the null and return
        passes=False.
        """
        n_obs = 300
        rng = np.random.default_rng(12345)

        z_records = []
        forward_returns = []
        for _ in range(n_obs):
            # z: independent random vectors
            z_vec = rng.normal(0, 1, size=4).tolist()

            # returns: completely independent random series
            realized = rng.normal(0, 1)

            record = make_latent_record(
                z_vector=z_vec,
                period_end=date(2024, 1, 1),
                filed_at=datetime(2024, 1, 1),
            )
            z_records.append(record)
            forward_returns.append(realized)

        mock_reader.read_latent_state.return_value = z_records

        probe = LatentLearnabilityProbe(mock_reader)
        result = await probe.run(
            learner_family="ssl_transformer_v1",
            z_dim=4,
            as_of=date(2024, 1, 1),
            forward_horizon=20,
            realized_returns_override=forward_returns,
        )

        # Noise should NOT produce a significant MI result
        assert result.passes is False, (
            f"Probe should FAIL on pure noise. "
            f"MI={result.mi_actual:.4f} vs null μ={result.mi_null_mean:.4f} "
            f"(σ={result.mi_null_std:.4f}), z={result.z_statistic:.3f}, p={result.p_value:.4f}"
        )

    # -------------------------------------------------------------------------
    # Edge cases
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_insufficient_observations_returns_fail(self, mock_reader):
        """Fewer than MIN_OBSERVATIONS records → passes=False, not an error."""
        n_obs = 50  # below MIN_OBSERVATIONS = 252

        z_records = [
            make_latent_record(
                z_vector=[1.0, 2.0],
                period_end=date(2024, 1, 1),
                filed_at=datetime(2024, 1, 1),
            )
            for _ in range(n_obs)
        ]
        mock_reader.read_latent_state.return_value = z_records

        probe = LatentLearnabilityProbe(mock_reader)
        result = await probe.run(
            learner_family="ssl_transformer_v1",
            z_dim=2,
            as_of=date(2024, 1, 1),
            forward_horizon=20,
            realized_returns_override=[1.0] * n_obs,
        )

        assert result.passes is False
        assert result.observation_count == n_obs
        assert result.min_observations_required == 252
        assert math.isnan(result.mi_actual)

    @pytest.mark.asyncio
    async def test_result_summary_is_readable(self, mock_reader):
        """LearnabilityProbeResult.summary() returns a non-empty string."""
        n_obs = 300
        rng = np.random.default_rng(42)

        z_records = []
        forward_returns = []
        for _ in range(n_obs):
            z_vec = rng.normal(0, 1, size=2).tolist()
            realized = rng.normal(0, 1)
            record = make_latent_record(
                z_vector=z_vec,
                period_end=date(2024, 1, 1),
                filed_at=datetime(2024, 1, 1),
            )
            z_records.append(record)
            forward_returns.append(realized)

        mock_reader.read_latent_state.return_value = z_records

        probe = LatentLearnabilityProbe(mock_reader)
        result = await probe.run(
            learner_family="ssl_transformer_v1",
            z_dim=2,
            as_of=date(2024, 1, 1),
            forward_horizon=20,
            realized_returns_override=forward_returns,
        )

        summary = result.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "MI=" in summary
        assert "z=" in summary
        assert "p=" in summary
        assert ("PASS" in summary) or ("FAIL" in summary)
