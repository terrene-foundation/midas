"""
Out-of-distribution detector for the state-inference pool.

Computes OOD scores from:
1. Distance-to-nearest-training-state (in latent space)
2. Posterior width

Feeds the `a_t` axis and the `state.ood` compliance rule (M12).

Ref: specs/04-latent-first-architecture.md §5, §11
Ref: T-04-06
"""

from __future__ import annotations

import numpy as np
import structlog

from midas.fabric.models import LatentStateRecord

logger = structlog.get_logger(__name__)


class OODResult:
    """Output of OOD detection."""

    def __init__(
        self,
        is_ood: bool,
        ood_score: float,
        posterior_width: float,
        distance_to_nearest: float | None = None,
    ):
        self.is_ood = is_ood
        self.ood_score = ood_score  # higher = more OOD
        self.posterior_width = posterior_width
        self.distance_to_nearest = distance_to_nearest  # None if no training states stored

    def __repr__(self) -> str:
        return (
            f"OODResult(is_ood={self.is_ood}, ood_score={self.ood_score:.4f}, "
            f"width={self.posterior_width:.4f})"
        )


class OODDetector:
    """Out-of-distribution detector for latent states.

    Combines two signals:
    1. Posterior width: wide posterior → uncertain state → elevated OOD
    2. Distance to nearest training state in latent space

    The detector is always on and cannot be bypassed per spec §11 invariants.
    """

    # Thresholds
    DEFAULT_WIDTH_THRESHOLD: float = 2.0  # posterior width above this → elevated
    DEFAULT_DISTANCE_THRESHOLD: float = 3.0  # z-score units from nearest training state

    def __init__(
        self,
        width_threshold: float = DEFAULT_WIDTH_THRESHOLD,
        distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
        ood_score_weight_width: float = 0.4,
        ood_score_weight_distance: float = 0.6,
    ):
        self._width_thresh = width_threshold
        self._dist_thresh = distance_threshold
        self._w_width = ood_score_weight_width
        self._w_dist = ood_score_weight_distance
        self._training_states: list[np.ndarray] = []
        self._training_widths: list[float] = []
        self._fitted = False

    def store_training_state(self, z_vector: np.ndarray, posterior_width: float) -> None:
        """Store a training latent state for distance computation.

        Call this during or after training to build the reference set.
        """
        self._training_states.append(z_vector.astype(np.float64))
        self._training_widths.append(posterior_width)
        if len(self._training_states) >= 10:
            self._fitted = True

    def _compute_statistics(self) -> tuple[float, float, float, float]:
        """Compute reference statistics from stored training states."""
        if not self._training_states:
            return 1.0, 0.01, 0.5, 0.1
        states = np.stack(self._training_states)
        widths = np.array(self._training_widths)

        # Mean and std of posterior widths across training states
        mean_width = float(np.mean(widths)) if len(widths) > 0 else 1.0
        std_width = float(np.std(widths)) if len(widths) > 1 else 0.5

        # For latent distances: compute pairwise distances (or use centroid)
        centroid = np.mean(states, axis=0)
        dists_to_centroid = np.linalg.norm(states - centroid, axis=1)
        mean_dist = float(np.mean(dists_to_centroid))
        std_dist = float(np.std(dists_to_centroid)) if len(dists_to_centroid) > 1 else 1.0

        return (
            max(mean_width, 0.01),
            max(std_width, 0.001),
            max(mean_dist, 0.01),
            max(std_dist, 0.001),
        )

    def detect(self, z_mean: np.ndarray, z_cov_diag: np.ndarray) -> OODResult:
        """Detect whether the current posterior is out-of-distribution.

        Parameters
        ----------
        z_mean : np.ndarray
            Current posterior mean (latent_dim,)
        z_cov_diag : np.ndarray
            Diagonal of posterior covariance (latent_dim,)

        Returns
        -------
        OODResult with is_ood flag, score, and components
        """
        # Component 1: posterior width
        posterior_width = float(np.mean(np.sqrt(z_cov_diag)))

        mean_width, std_width, mean_dist, std_dist = self._compute_statistics()

        # Z-score for width
        width_zscore = (posterior_width - mean_width) / std_width if std_width > 0 else 0.0

        # Component 2: distance to nearest training state
        if self._training_states and self._fitted:
            states = np.stack(self._training_states)
            distances = np.linalg.norm(states - z_mean.astype(np.float64), axis=1)
            nearest_dist = float(np.min(distances))
            dist_zscore = (nearest_dist - mean_dist) / std_dist if std_dist > 0 else 0.0
        else:
            # No training states yet — use width only, flag elevated uncertainty
            nearest_dist = None
            dist_zscore = 0.0

        # Combined OOD score (weighted average of z-scores)
        ood_score = self._w_width * max(width_zscore, 0) + self._w_dist * max(dist_zscore, 0)

        # Decision: OOD if EITHER threshold breached
        is_ood = bool(
            width_zscore > self._width_thresh
            or (nearest_dist is not None and dist_zscore > self._dist_thresh)
        )

        logger.debug(
            "ood.detect",
            ood_score=ood_score,
            width_zscore=width_zscore,
            dist_zscore=dist_zscore if nearest_dist is not None else None,
            posterior_width=posterior_width,
            is_ood=is_ood,
        )

        return OODResult(
            is_ood=is_ood,
            ood_score=ood_score,
            posterior_width=posterior_width,
            distance_to_nearest=nearest_dist,
        )

    def detect_from_record(self, record: LatentStateRecord) -> OODResult:
        """Detect OOD from a LatentStateRecord."""
        z_mean = np.array(record.z_vector)
        # Reconstruct diagonal covariance from z_covariance
        if record.z_covariance:
            cov_diag = np.array(
                [
                    row[0] if isinstance(row, (list, tuple)) else float(row)
                    for row in record.z_covariance
                ]
            )
        else:
            cov_diag = np.ones(len(z_mean)) * 0.1
        return self.detect(z_mean, cov_diag)

    @property
    def n_training_states(self) -> int:
        return len(self._training_states)

    def reset(self) -> None:
        """Clear training states."""
        self._training_states.clear()
        self._training_widths.clear()
        self._fitted = False
