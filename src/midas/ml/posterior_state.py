"""
Posterior-maintenance service for the state-inference pool.

Consumes z_t posterior candidates from representation learners and maintains
the running posterior p(z_t | x_{1:t}) under a Bayesian filter.  Every pool
member gets its own posterior stream; the combined posterior is written to
the fabric latent_state table.

Ref: specs/04-latent-first-architecture.md §5
Ref: T-04-01
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import structlog

from midas.fabric.adapters.dataflow_adapter import DataFlowFabricReader, DataFlowFabricWriter
from midas.fabric.models import LatentStateRecord, PITKey

logger = structlog.get_logger(__name__)


# Default Bayesian filter hyperparameters
DEFAULT_PROCESS_VARIANCE = 1e-3  # Q — how fast the latent state drifts
DEFAULT_OBSERVATION_VARIANCE = 1e-2  # R — observation noise on z_t candidates


@dataclass
class PosteriorState:
    """Current posterior state for one learner."""

    learner_family: str
    learner_role: str
    # Gaussian posterior parameters
    z_mean: np.ndarray  # (latent_dim,)
    z_cov: np.ndarray  # (latent_dim, latent_dim) — full covariance
    # PIT metadata
    last_period_end: date
    last_filed_at: datetime
    update_count: int = 0


@dataclass
class PosteriorUpdate:
    """Output of a single posterior update."""

    learner_family: str
    z_mean: list[float]
    z_covariance: list[list[float]]
    posterior_width: float
    state_id: str
    period_end: date
    filed_at: datetime
    update_count: int


class PosteriorMaintenanceService:
    """Bayesian filter that maintains p(z_t | x_{1:t}) for each representation learner.

    Uses a Kalman-style linear-Gaussian filter as the baseline posterior estimator.
    The filter processes each new z_t candidate (from `infer_all_pool`) as an
    observation and updates the posterior in O(latent_dim²).
    """

    def __init__(
        self,
        fabric_reader: DataFlowFabricReader,
        fabric_writer: DataFlowFabricWriter,
        process_variance: float = DEFAULT_PROCESS_VARIANCE,
        observation_variance: float = DEFAULT_OBSERVATION_VARIANCE,
    ) -> None:
        self._reader = fabric_reader
        self._writer = fabric_writer
        self._Q = process_variance
        self._R = observation_variance
        self._posteriors: dict[str, PosteriorState] = {}

    def _init_posterior(
        self,
        learner_family: str,
        learner_role: str,
        z_candidate: np.ndarray,
        period_end: date,
        filed_at: datetime,
    ) -> PosteriorState:
        """Initialize posterior from first z_t candidate."""
        latent_dim = len(z_candidate)
        z_cov = np.eye(latent_dim) * self._R  # start with observation noise
        return PosteriorState(
            learner_family=learner_family,
            learner_role=learner_role,
            z_mean=z_candidate,
            z_cov=z_cov,
            last_period_end=period_end,
            last_filed_at=filed_at,
            update_count=0,
        )

    def _kalman_update(
        self,
        prior_mean: np.ndarray,
        prior_cov: np.ndarray,
        z_obs: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Single Kalman update step.

        Prediction: prior stays the same (random walk model)
        Update: p(z | obs) ∝ N(z | obs, R) * N(z | prior_mean, prior_cov)
        """
        S = prior_cov + np.eye(len(prior_mean)) * self._R  # innovation covariance
        K = prior_cov @ np.linalg.inv(S)  # Kalman gain
        post_mean = prior_mean + K @ (z_obs - prior_mean)
        post_cov = (np.eye(len(prior_mean)) - K) @ prior_cov
        # Ensure symmetric
        post_cov = 0.5 * (post_cov + post_cov.T)
        return post_mean, post_cov

    def _posterior_to_record(
        self,
        state: PosteriorState,
        state_id: str,
    ) -> LatentStateRecord:
        """Serialize PosteriorState to a LatentStateRecord."""
        # Diagonal covariance for storage efficiency
        cov_diag = [[float(state.z_cov[i, i])] for i in range(state.z_cov.shape[0])]
        posterior_width = float(np.mean(np.sqrt(np.diag(state.z_cov))))
        return LatentStateRecord(
            state_id=state_id,
            pit=PITKey(
                period_end=state.last_period_end,
                filed_at=state.last_filed_at,
            ),
            learner_family=state.learner_family,
            learner_role=state.learner_role,
            z_dim=len(state.z_mean),
            z_vector=tuple(float(v) for v in state.z_mean),
            z_covariance=tuple(tuple(c) for c in cov_diag),
            z_scale=posterior_width,
            pool_index=None,
        )

    async def update(
        self,
        z_candidate: LatentStateRecord,
    ) -> PosteriorUpdate:
        """Process one z_t candidate and update the posterior.

        Parameters
        ----------
        z_candidate : LatentStateRecord
            A z_t posterior candidate from a representation learner
            (written by RepresentationInferenceService).

        Returns
        -------
        PosteriorUpdate with the updated posterior parameters.
        """
        learner = z_candidate.learner_family
        z_vec = np.array(z_candidate.z_vector)
        period_end = z_candidate.pit.period_end
        filed_at = z_candidate.pit.filed_at

        if learner not in self._posteriors:
            # Cold start: initialize from first candidate
            self._posteriors[learner] = self._init_posterior(
                learner,
                z_candidate.learner_role,
                z_vec,
                period_end,
                filed_at,
            )
            state = self._posteriors[learner]
        else:
            # Kalman update
            state = self._posteriors[learner]
            post_mean, post_cov = self._kalman_update(state.z_mean, state.z_cov, z_vec)
            state.z_mean = post_mean
            state.z_cov = post_cov
            state.last_period_end = period_end
            state.last_filed_at = filed_at
            state.update_count += 1

        # Compute posterior width
        posterior_width = float(np.mean(np.sqrt(np.diag(state.z_cov))))

        update = PosteriorUpdate(
            learner_family=learner,
            z_mean=list(state.z_mean),
            z_covariance=[
                [float(state.z_cov[i, j]) for j in range(state.z_cov.shape[1])]
                for i in range(state.z_cov.shape[0])
            ],
            posterior_width=posterior_width,
            state_id=f"{learner}_{state.update_count}",
            period_end=period_end,
            filed_at=filed_at,
            update_count=state.update_count,
        )

        # Write updated posterior to fabric
        record = self._posterior_to_record(state, update.state_id)
        await self._writer.write_latent_state(record)

        logger.info(
            "posterior.updated",
            learner=learner,
            update_count=state.update_count,
            posterior_width=posterior_width,
        )
        return update

    async def warm_start(self, learner_family: str, as_of: date) -> bool:
        """Load the last posterior for a learner from fabric.

        Returns True if a prior was found and loaded; False if cold-start.
        """
        rows = await self._reader.read_latent_state(learner_family, as_of)
        if not rows:
            return False

        latest = rows[-1]  # most recent by period_end
        z_vec = np.array(latest.z_vector)
        latent_dim = len(z_vec)

        # Reconstruct covariance from z_covariance (diagonal form)
        z_cov = np.eye(latent_dim)
        if latest.z_covariance:
            for i, row in enumerate(latest.z_covariance):
                if row:
                    z_cov[i, i] = row[0] if isinstance(row, (list, tuple)) else float(row)

        self._posteriors[learner_family] = PosteriorState(
            learner_family=learner_family,
            learner_role=latest.learner_role,
            z_mean=z_vec,
            z_cov=z_cov,
            last_period_end=latest.pit.period_end,
            last_filed_at=latest.pit.filed_at,
            update_count=0,
        )
        logger.info(
            "posterior.warm_started",
            learner=learner_family,
            period_end=latest.pit.period_end,
        )
        return True

    def get_posterior(self, learner_family: str) -> PosteriorState | None:
        """Return the current posterior for a learner, if any."""
        return self._posteriors.get(learner_family)

    def posteriors_summary(self) -> dict[str, dict[str, Any]]:
        """Return a dict of all current posteriors."""
        return {
            learner: {
                "z_dim": state.z_mean.shape[0],
                "posterior_width": float(np.mean(np.sqrt(np.diag(state.z_cov)))),
                "update_count": state.update_count,
                "last_period_end": state.last_period_end.isoformat(),
            }
            for learner, state in self._posteriors.items()
        }
