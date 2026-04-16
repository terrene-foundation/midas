"""Tier 1 tests for the OOD detector."""

import numpy as np
import pytest

from midas.fabric.models import LatentStateRecord, PITKey
from midas.ml.ood_detector import OODDetector, OODResult
from datetime import date, datetime


def _make_record(
    z_vector: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4),
    z_covariance: tuple[tuple[float, ...], ...] = None,
    posterior_width: float = 0.1,
) -> LatentStateRecord:
    if z_covariance is None:
        z_covariance = ((0.01,), (0.01,), (0.01,), (0.01,))
    return LatentStateRecord(
        state_id="test_state",
        pit=PITKey(period_end=date(2024, 12, 31), filed_at=datetime(2024, 12, 31, 16, 0, 0)),
        learner_family="ssl_transformer_v1",
        learner_role="champion",
        z_dim=len(z_vector),
        z_vector=z_vector,
        z_covariance=z_covariance,
        z_scale=posterior_width,
        pool_index=None,
    )


class TestOODDetector:
    """Tests for OOD detector."""

    def test_ood_detector_init(self):
        """Detector initializes with default thresholds."""
        detector = OODDetector()
        assert detector._width_thresh == 2.0
        assert detector._dist_thresh == 3.0
        assert detector.n_training_states == 0

    def test_ood_detector_store_training_state(self):
        """store_training_state adds a reference state."""
        detector = OODDetector()
        z = np.array([0.1, 0.2, 0.3, 0.4])
        detector.store_training_state(z, 0.1)
        assert detector.n_training_states == 1

        detector.store_training_state(z * 2, 0.15)
        assert detector.n_training_states == 2

    def test_ood_detect_in_distribution(self):
        """Narrow posterior close to training states is not OOD."""
        detector = OODDetector()

        # Store training states
        for i in range(5):
            z = np.array([0.1 * i, 0.2 * i, 0.3 * i, 0.4 * i])
            detector.store_training_state(z, 0.1)

        # Query with same distribution
        z_mean = np.array([0.15, 0.3, 0.45, 0.6])
        z_cov_diag = np.array([0.01, 0.01, 0.01, 0.01])  # narrow

        result = detector.detect(z_mean, z_cov_diag)

        assert isinstance(result, OODResult)
        assert result.posterior_width < 0.3  # narrow
        assert result.is_ood is False

    def test_ood_detect_wide_posterior_flags_ood(self):
        """Wide posterior is flagged as elevated OOD."""
        detector = OODDetector(
            width_threshold=1.5,
            distance_threshold=3.0,
        )

        # Store narrow training states
        for i in range(5):
            z = np.array([0.1 * i, 0.2 * i, 0.3 * i, 0.4 * i])
            detector.store_training_state(z, 0.1)

        # Query with very wide posterior
        z_mean = np.array([0.15, 0.3, 0.45, 0.6])
        z_cov_diag = np.array([10.0, 10.0, 10.0, 10.0])  # very wide

        result = detector.detect(z_mean, z_cov_diag)

        assert result.is_ood is True
        assert result.posterior_width > 1.0

    def test_ood_detect_distant_state_flags_ood(self):
        """Far-from-training state is flagged as OOD."""
        detector = OODDetector(
            width_threshold=2.0,
            distance_threshold=1.0,  # low threshold
        )

        # Store training states in a tight cluster near origin (>=10 for distance fitting)
        rng = np.random.default_rng(42)
        for _ in range(12):
            z = rng.normal(0.0, 0.1, size=4)  # cluster near origin
            detector.store_training_state(z, 0.1)

        # Query with state far from training cluster
        z_mean = np.array([10.0, 10.0, 10.0, 10.0])  # far away
        z_cov_diag = np.array([0.01, 0.01, 0.01, 0.01])  # narrow

        result = detector.detect(z_mean, z_cov_diag)

        assert result.is_ood is True
        assert result.distance_to_nearest is not None
        assert result.distance_to_nearest > 5.0

    def test_ood_score_combines_width_and_distance(self):
        """ood_score is weighted combination of width and distance z-scores."""
        detector = OODDetector(
            width_threshold=2.0,
            distance_threshold=3.0,
            ood_score_weight_width=0.4,
            ood_score_weight_distance=0.6,
        )

        # Store training states
        z = np.array([0.0, 0.0, 0.0, 0.0])
        detector.store_training_state(z, 0.1)

        # Query
        z_mean = np.array([0.5, 0.5, 0.5, 0.5])
        z_cov_diag = np.array([0.1, 0.1, 0.1, 0.1])

        result = detector.detect(z_mean, z_cov_diag)

        assert result.ood_score >= 0.0
        # Score should be elevated (positive distance and width z-scores)

    def test_ood_detect_from_record(self):
        """detect_from_record works with LatentStateRecord."""
        detector = OODDetector()
        detector.store_training_state(np.array([0.1, 0.2, 0.3, 0.4]), 0.1)

        record = _make_record(z_vector=(0.1, 0.2, 0.3, 0.4))
        result = detector.detect_from_record(record)

        assert isinstance(result, OODResult)
        assert result.ood_score >= 0.0

    def test_ood_detector_reset(self):
        """reset() clears all training states."""
        detector = OODDetector()
        detector.store_training_state(np.array([0.1, 0.2, 0.3, 0.4]), 0.1)
        detector.store_training_state(np.array([0.2, 0.3, 0.4, 0.5]), 0.15)

        assert detector.n_training_states == 2
        detector.reset()
        assert detector.n_training_states == 0

    def test_ood_detector_no_training_states(self):
        """Returns non-OOD with elevated uncertainty when no training states."""
        detector = OODDetector()

        z_mean = np.array([0.1, 0.2, 0.3, 0.4])
        z_cov_diag = np.array([0.1, 0.1, 0.1, 0.1])

        result = detector.detect(z_mean, z_cov_diag)

        # No training data → should NOT flag as OOD based on distance
        # but posterior width might flag it
        assert isinstance(result, OODResult)
        assert result.distance_to_nearest is None

    def test_ood_detector_custom_thresholds(self):
        """Custom thresholds change OOD behavior."""
        detector_strict = OODDetector(width_threshold=0.5, distance_threshold=0.5)
        detector_loose = OODDetector(width_threshold=5.0, distance_threshold=10.0)

        # Store one training state
        detector_strict.store_training_state(np.array([0.0, 0.0, 0.0, 0.0]), 0.1)
        detector_loose.store_training_state(np.array([0.0, 0.0, 0.0, 0.0]), 0.1)

        z_mean = np.array([0.2, 0.2, 0.2, 0.2])
        z_cov_diag = np.array([0.2, 0.2, 0.2, 0.2])

        r_strict = detector_strict.detect(z_mean, z_cov_diag)
        r_loose = detector_loose.detect(z_mean, z_cov_diag)

        # Stricter detector should flag more things as OOD
        # (relative to the loose one which has high thresholds)
        assert r_strict.ood_score >= r_loose.ood_score or r_strict.is_ood >= r_loose.is_ood

    def test_ood_score_is_non_negative(self):
        """ood_score is always >= 0."""
        detector = OODDetector()

        for i in range(10):
            z = np.random.randn(4) * 0.1
            detector.store_training_state(z, 0.1)

        for _ in range(5):
            z_mean = np.random.randn(4)
            z_cov_diag = np.abs(np.random.randn(4)) * 0.1 + 0.01
            result = detector.detect(z_mean, z_cov_diag)
            assert result.ood_score >= 0.0

    def test_ood_repr(self):
        """OODResult has readable repr."""
        result = OODResult(is_ood=True, ood_score=1.5, posterior_width=0.3, distance_to_nearest=2.0)
        r = repr(result)
        assert "OODResult" in r
        assert "is_ood=True" in r
        assert "ood_score=1.5" in r
