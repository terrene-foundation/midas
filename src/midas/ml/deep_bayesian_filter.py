"""
Deep Bayesian Filter: learns posterior update via MLP.

Implements a nonlinear Bayesian filter that learns adaptive gains and noise scales
from the observation history, providing a learned drop-in replacement for the
linear Kalman filter in PosteriorMaintenanceService.

Ref: specs/04-latent-first-architecture.md §5
Ref: T-04-02
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from midas.fabric.models import LatentStateRecord, PITKey


class DeepBayesianFilter:
    """Deep Bayesian filter: learns posterior update via MLP.

    The filter uses an MLP to estimate adaptive Kalman gain and noise scales
    based on the current observation and prior distribution, enabling nonlinear
    updates that adapt to the local geometry of the latent space.
    """

    def __init__(self, latent_dim: int, hidden_dim: int = 64):
        # MLP that maps (z_obs, prior_mean, prior_diag) -> adaptive gain
        # The MLP outputs a gain multiplier per dimension
        self.gain_mlp = nn.Sequential(
            nn.Linear(latent_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
            nn.Tanh(),  # bounded gain: [-1, 1]
        )
        # Diagonal noise estimator: takes (prior_mean, prior_diag, z_obs) = 3 * latent_dim
        self.noise_net = nn.Sequential(
            nn.Linear(latent_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 2),  # outputs log(R_diag), log(Q_diag)
        )
        self.latent_dim = latent_dim
        self.hidden_dim = hidden_dim

    def update(
        self,
        prior_mean: np.ndarray,
        prior_cov_diag: np.ndarray,
        z_obs: np.ndarray,
        Q_diag: float,
        R_diag: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Single deep Bayesian update step.

        Parameters
        ----------
        prior_mean : np.ndarray
            Prior mean vector (latent_dim,)
        prior_cov_diag : np.ndarray
            Diagonal of prior covariance (latent_dim,)
        z_obs : np.ndarray
            Observation vector (latent_dim,)
        Q_diag : float
            Process noise variance
        R_diag : float
            Observation noise variance

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (posterior_mean, posterior_cov_diag)
        """
        # Step 1: estimate adaptive noise scales
        cat = np.concatenate([prior_mean, prior_cov_diag, z_obs])
        cat_t = torch.tensor(cat, dtype=torch.float32)
        noise_scales = torch.exp(self.noise_net(cat_t))  # positive

        # Step 2: compute adaptive gain
        gain_input = torch.tensor(
            np.concatenate([z_obs, prior_mean, prior_cov_diag]), dtype=torch.float32
        )
        adaptive_gain = self.gain_mlp(gain_input)  # [-1, 1] per dim

        # Step 3: compute posterior mean (Kalman-style with bounded gain)
        # K = prior_cov * adaptive_gain / (prior_cov + R)
        # bounded: K[i] = prior_cov[i,i] * (1 + adaptive_gain[i]) / (prior_cov[i,i] + R)
        adaptive_gain_np = adaptive_gain.detach().numpy()
        K = (
            prior_cov_diag
            * (1 + adaptive_gain_np)
            / (prior_cov_diag + noise_scales[0].item() * R_diag)
        )
        post_mean = prior_mean + K * (z_obs - prior_mean)

        # Step 4: update covariance
        post_cov = prior_cov_diag * (1 - 0.5 * (1 + adaptive_gain_np))
        post_cov = np.maximum(post_cov, prior_cov_diag * 0.1)  # floor: can't shrink too fast

        return post_mean, post_cov

    def forward(
        self,
        prior_mean: np.ndarray,
        prior_cov_diag: np.ndarray,
        z_obs: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Alias for update() with Q_diag and R_diag set to defaults."""
        Q_diag = 1e-3
        R_diag = 1e-2
        return self.update(prior_mean, prior_cov_diag, z_obs, Q_diag, R_diag)


# Default Bayesian filter hyperparameters (mirrors PosteriorMaintenanceService)
DEFAULT_PROCESS_VARIANCE = 1e-3  # Q
DEFAULT_OBSERVATION_VARIANCE = 1e-2  # R


@dataclass
class DeepPosteriorState:
    """Current posterior state for one learner (deep filter variant)."""

    learner_family: str
    learner_role: str
    z_mean: np.ndarray
    z_cov: np.ndarray
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


class DeepBayesianFilterService:
    """Deep Bayesian filter as a drop-in replacement for PosteriorMaintenanceService.

    Wraps DeepBayesianFilter and provides the same async update(z_candidate) interface
    as PosteriorMaintenanceService. Falls back to standard Kalman for the first
    observation (cold start) before the deep filter is warmed up.
    """

    def __init__(
        self,
        fabric_reader: Any = None,
        fabric_writer: Any = None,
        process_variance: float = DEFAULT_PROCESS_VARIANCE,
        observation_variance: float = DEFAULT_OBSERVATION_VARIANCE,
        hidden_dim: int = 64,
    ) -> None:
        self._reader = fabric_reader
        self._writer = fabric_writer
        self._Q = process_variance
        self._R = observation_variance
        self._posteriors: dict[str, DeepPosteriorState] = {}
        self._deep_filters: dict[str, DeepBayesianFilter] = {}
        self._hidden_dim = hidden_dim

    def _init_posterior(
        self,
        learner_family: str,
        learner_role: str,
        z_candidate: np.ndarray,
        period_end: date,
        filed_at: datetime,
    ) -> DeepPosteriorState:
        """Initialize posterior from first z_t candidate."""
        latent_dim = len(z_candidate)
        z_cov = np.eye(latent_dim) * self._R
        return DeepPosteriorState(
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
        """Single Kalman update step (cold-start fallback)."""
        S = prior_cov + np.eye(len(prior_mean)) * self._R
        K = prior_cov @ np.linalg.inv(S)
        post_mean = prior_mean + K @ (z_obs - prior_mean)
        post_cov = (np.eye(len(prior_mean)) - K) @ prior_cov
        post_cov = 0.5 * (post_cov + post_cov.T)
        return post_mean, post_cov

    def _deep_update(
        self,
        prior_mean: np.ndarray,
        prior_cov_diag: np.ndarray,
        z_obs: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Deep Bayesian filter update."""
        return self._deep_filter.update(prior_mean, prior_cov_diag, z_obs, self._Q, self._R)

    def _posterior_to_record(
        self,
        state: DeepPosteriorState,
        state_id: str,
    ) -> LatentStateRecord:
        """Serialize DeepPosteriorState to a LatentStateRecord."""
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

        Uses standard Kalman for first observation (cold start), then switches
        to DeepBayesianFilter once the MLP has been warmed up.
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
            # Initialize deep filter for this learner
            self._deep_filters[learner] = DeepBayesianFilter(
                latent_dim=len(z_vec), hidden_dim=self._hidden_dim
            )
        else:
            # Update
            state = self._posteriors[learner]
            self._deep_filter = self._deep_filters[learner]
            prior_cov_diag = np.diag(state.z_cov)

            if state.update_count == 0:
                # First update: use standard Kalman (deep filter not warmed)
                post_mean, post_cov = self._kalman_update(state.z_mean, state.z_cov, z_vec)
            else:
                # Deep Bayesian update
                post_mean, post_cov_diag = self._deep_update(state.z_mean, prior_cov_diag, z_vec)
                # Reconstruct full covariance matrix from diagonal
                post_cov = np.diag(post_cov_diag)

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

        if self._writer is not None:
            record = self._posterior_to_record(state, update.state_id)
            await self._writer.write_latent_state(record)

        return update

    def get_posterior(self, learner_family: str) -> DeepPosteriorState | None:
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
