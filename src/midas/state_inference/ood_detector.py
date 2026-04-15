"""
Out-of-Distribution detection for latent states.

Uses Mahalanobis distance to the nearest training state combined with
posterior width to produce a bounded [0, 1] OOD score. OOD detection is
always on and never bypassable.

Ref: M04 State Inference Pool specification
Ref: specs/04-latent-first-architecture.md SS3 (OOD guard)
"""

from dataclasses import dataclass

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class OODResult:
    """Result of an OOD detection check."""

    score: float
    is_ood: bool
    nearest_distance: float
    variance_ratio: float


class OODDetector:
    """Detect out-of-distribution latent states using Mahalanobis distance.

    The OOD score combines distance to the nearest training state with
    posterior width (uncertainty). A wider posterior dampens the OOD alarm
    because high uncertainty already signals that the model is unsure.

    Parameters
    ----------
    distance_threshold:
        Mahalanobis distance beyond which a point is considered OOD.
    variance_threshold:
        Posterior variance ratio above which the uncertainty component
        triggers OOD.
    """

    def __init__(
        self,
        distance_threshold: float = 3.0,
        variance_threshold: float = 2.0,
    ) -> None:
        if distance_threshold <= 0:
            raise ValueError(f"distance_threshold must be positive, got {distance_threshold}")
        if variance_threshold <= 0:
            raise ValueError(f"variance_threshold must be positive, got {variance_threshold}")
        self._distance_threshold = distance_threshold
        self._variance_threshold = variance_threshold

    def compute_ood_score(
        self,
        current_z: np.ndarray,
        training_states: np.ndarray,
    ) -> float:
        """Compute OOD score in [0, 1] based on Mahalanobis distance.

        Parameters
        ----------
        current_z:
            The current latent vector, shape (latent_dim,).
        training_states:
            Matrix of training latent vectors, shape (n_samples, latent_dim).

        Returns
        -------
        float
            Bounded OOD score in [0, 1]. Higher means more out-of-distribution.
        """
        if training_states.ndim != 2:
            raise ValueError(f"training_states must be 2D, got shape {training_states.shape}")
        if current_z.shape[0] != training_states.shape[1]:
            raise ValueError(
                f"Dimension mismatch: current_z has {current_z.shape[0]} dims "
                f"but training_states has {training_states.shape[1]} dims"
            )

        # Compute Mahalanobis distance to each training state
        # Use the inverse of the training covariance matrix
        cov = np.cov(training_states.T)
        # If only one sample or degenerate, fall back to Euclidean
        if training_states.shape[0] < 2 or np.linalg.det(cov) < 1e-12:
            diff = training_states - current_z
            distances = np.linalg.norm(diff, axis=1)
            nearest_dist = float(np.min(distances))
        else:
            try:
                cov_inv = np.linalg.inv(cov)
                diff = training_states - current_z
                # Mahalanobis: sqrt(diff @ cov_inv @ diff^T) for each row
                mahal_sq = np.sum((diff @ cov_inv) * diff, axis=1)
                distances = np.sqrt(np.clip(mahal_sq, 0, None))
                nearest_dist = float(np.min(distances))
            except np.linalg.LinAlgError:
                diff = training_states - current_z
                distances = np.linalg.norm(diff, axis=1)
                nearest_dist = float(np.min(distances))

        # Map distance to [0, 1] via sigmoid-like transformation
        # centered at the threshold
        score = float(_sigmoid(nearest_dist - self._distance_threshold))

        logger.debug(
            "ood.compute_score",
            nearest_distance=nearest_dist,
            threshold=self._distance_threshold,
            score=score,
        )
        return score

    def is_ood(self, score: float) -> bool:
        """Return True if the score exceeds the OOD threshold (0.5 on sigmoid)."""
        return score > 0.5

    def detect(
        self,
        current_z: np.ndarray,
        training_states: np.ndarray,
        posterior_variance: np.ndarray,
    ) -> OODResult:
        """Run full OOD detection combining distance and variance.

        Parameters
        ----------
        current_z:
            Current latent vector, shape (latent_dim,).
        training_states:
            Training latent vectors, shape (n_samples, latent_dim).
        posterior_variance:
            Diagonal posterior variance, shape (latent_dim,).

        Returns
        -------
        OODResult
            Score, is_ood flag, nearest distance, and variance ratio.
        """
        current_z = np.asarray(current_z, dtype=np.float64)
        training_states = np.asarray(training_states, dtype=np.float64)
        posterior_variance = np.asarray(posterior_variance, dtype=np.float64)

        # Compute base distance score
        base_score = self.compute_ood_score(current_z, training_states)

        # Compute nearest distance for reporting
        diff = training_states - current_z
        distances = np.linalg.norm(diff, axis=1)
        nearest_distance = float(np.min(distances))

        # Variance ratio: how much wider is the posterior vs training variance
        training_var = np.var(training_states, axis=0)
        # Avoid division by zero
        training_var_safe = np.where(training_var < 1e-12, 1e-12, training_var)
        variance_ratio = float(np.mean(posterior_variance / training_var_safe))

        # Dampen OOD score when posterior is wide (model already uncertain)
        # Higher posterior variance -> lower effective OOD alarm
        variance_dampener = 1.0 / (1.0 + np.clip(variance_ratio - 1.0, 0, None))
        adjusted_score = base_score * variance_dampener

        # Re-bound to [0, 1]
        adjusted_score = float(np.clip(adjusted_score, 0.0, 1.0))

        result = OODResult(
            score=adjusted_score,
            is_ood=self.is_ood(adjusted_score),
            nearest_distance=nearest_distance,
            variance_ratio=variance_ratio,
        )

        logger.info(
            "ood.detect",
            score=adjusted_score,
            is_ood=result.is_ood,
            nearest_distance=nearest_distance,
            variance_ratio=variance_ratio,
        )
        return result


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + np.exp(-x))
    else:
        exp_x = np.exp(x)
        return exp_x / (1.0 + exp_x)
