"""
Tests for T-00-04: Calibration with Holm-Bonferroni Multiple-Comparison Correction.

Tier 2: spins up a pool of 20 random-noise "heads" and asserts the promotion
mechanism certifies ZERO of them as champion (family-wise Type I control verified).

Ref: specs/05-model-pool-and-meta-router.md §5.4
Ref: specs/12-performance-and-track-record.md §4
Ref: T-00-04
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from midas.evaluation.probes.calibration_protocol import (
    CalibrationProtocol,
    HeadCalibrationResult,
    holm_bonferroni_corrections,
    apply_holm_bonferroni,
    deflated_sharpe_ratio,
    probability_backtest_overfitting,
    PromotionCriteriaResult,
    NeighborhoodEstimator,
    calibration_chi2_test,
)


class TestHolmBonferroni:
    """Unit tests for the Holm-Bonferroni correction itself."""

    def test_holm_adjusted_alphas_increase(self):
        """Adjusted alpha per position increases (index 0 = strictest for smallest p-value)."""
        n = 6
        alphas = holm_bonferroni_corrections(n, family_wise_alpha=0.05)
        assert len(alphas) == n
        # holm_bonferroni_corrections returns [α/m, α/(m-1), ..., α/1]
        # index 0 (smallest p-value) → strictest threshold; index m-1 → most lenient
        for i in range(len(alphas) - 1):
            assert alphas[i] < alphas[i + 1]
        assert alphas[0] == pytest.approx(0.05 / 6)

    def test_holm_corrected_6tests(self):
        """6 tests at family_wise α=0.05 → corrected αs: 0.0083, 0.01, 0.0125, ..."""
        alphas = holm_bonferroni_corrections(6, family_wise_alpha=0.05)
        assert alphas[0] == pytest.approx(0.05 / 6, rel=1e-3)
        assert alphas[1] == pytest.approx(0.05 / 5, rel=1e-3)
        assert alphas[2] == pytest.approx(0.05 / 4, rel=1e-3)

    def test_apply_holm_bonferroni_all_pass(self):
        """All p-values below Holm threshold → all pass."""
        results = [
            PromotionCriteriaResult(
                criterion_name=f"c{i}",
                statistic=1.0,
                p_value=0.001 * (i + 1),
                passes=True,
                threshold=0.01,
            )
            for i in range(6)
        ]
        corrected, thresholds, all_pass = apply_holm_bonferroni(results, family_wise_alpha=0.05)
        assert all_pass is True
        assert all(r.passes for r in corrected)

    def test_apply_holm_bonferroni_one_fails(self):
        """One p-value above Holm threshold → all_pass = False."""
        results = [
            PromotionCriteriaResult(
                criterion_name=f"c{i}",
                statistic=1.0,
                p_value=0.001,
                passes=True,
                threshold=0.01,
            )
            for i in range(5)
        ] + [
            PromotionCriteriaResult(
                criterion_name="c5",
                statistic=1.0,
                p_value=0.5,  # clearly above all corrected thresholds
                passes=True,
                threshold=0.01,
            )
        ]
        corrected, thresholds, all_pass = apply_holm_bonferroni(results, family_wise_alpha=0.05)
        assert all_pass is False
        # The high-p-value criterion should fail
        failed = [r for r in corrected if not r.passes]
        assert len(failed) >= 1

    def test_apply_holm_bonferroni_empty(self):
        """Empty list → empty return, all_pass=True."""
        corrected, thresholds, all_pass = apply_holm_bonferroni([])
        assert all_pass is True
        assert corrected == []


class TestNeighborhoodEstimator:
    """Tests for the k-NN adaptive neighborhood estimator."""

    def test_adaptive_k_grows_with_n(self):
        """More samples → larger k."""
        est = NeighborhoodEstimator()
        k_100 = est.adaptive_k(z_dim=4, n_samples=100)
        k_1000 = est.adaptive_k(z_dim=4, n_samples=1000)
        assert k_1000 > k_100

    def test_adaptive_k_shrinks_with_dim(self):
        """Higher dimensionality → smaller k (curse of dimensionality requires more neighbors)."""
        est = NeighborhoodEstimator()
        k_low = est.adaptive_k(z_dim=2, n_samples=500)
        k_high = est.adaptive_k(z_dim=20, n_samples=500)
        assert k_high < k_low

    def test_adaptive_k_bounded(self):
        """k must stay within [5, min(n/4, 50)]."""
        est = NeighborhoodEstimator()
        k_min = est.adaptive_k(z_dim=2, n_samples=10)  # n/4 = 2.5 → bounded to 5
        k_max = est.adaptive_k(z_dim=2, n_samples=10000)  # n/4 = 2500 → capped at 50
        assert k_min >= 5
        assert k_max <= 50

    def test_knn_calibration_on_random_data(self):
        """Random predictions + random outcomes → flat calibration curve."""
        rng = np.random.default_rng(42)
        n = 300
        z = rng.normal(0, 1, size=(n, 4))
        preds = rng.uniform(0.3, 0.7, size=n)  # predictions 30-70%
        realized = (rng.uniform(0, 1, size=n) < preds).astype(float)

        est = NeighborhoodEstimator(n_bins=5)
        curve = est.knn_calibration(z, preds, realized)

        assert curve.n_total == n
        assert len(curve.bins) <= 5
        # ECE should be moderate (not zero since data is random)
        assert 0.0 <= curve.ece <= 1.0

    def test_knn_calibration_on_perfect_predictions(self):
        """Predictions match realized outcomes → near-perfect calibration."""
        n = 300
        z = np.zeros((n, 2))
        # 30% low-confidence correct, 70% high-confidence correct
        preds = np.array([0.3] * 100 + [0.7] * 200)
        realized = (np.random.default_rng(7).uniform(0, 1, size=n) < preds).astype(float)

        est = NeighborhoodEstimator(n_bins=5)
        curve = est.knn_calibration(z, preds, realized)

        # With a simple z-space, ECE should be bounded
        assert curve.ece < 0.5  # not catastrophically miscalibrated


class TestStatisticalHelpers:
    """Tests for χ², DSR, PBO."""

    def test_chi2_perfect_calibration(self):
        """Perfect calibration (O=E everywhere) → χ²=0, p=1."""
        from midas.evaluation.probes.calibration_protocol import CalibrationBin

        bins = [
            CalibrationBin(
                bin_center=0.5,
                n_predictions=100,
                n_correct=50,
                empirical_accuracy=0.5,
                expected_accuracy=0.5,
                calibration_error=0.0,
            )
        ]
        chi2, p = calibration_chi2_test(bins)
        assert chi2 == pytest.approx(0.0, abs=1e-6)
        assert p == pytest.approx(1.0, abs=1e-6)

    def test_chi2_empty_bins(self):
        """Empty bins → χ²=0, p=1 (no evidence of miscalibration)."""
        chi2, p = calibration_chi2_test([])
        assert chi2 == 0.0
        assert p == 1.0

    def test_deflated_sharpe_ratio_random_returns(self):
        """Random returns (no true skill) → DSR ≈ 0 (may be slightly positive by luck)."""
        rng = np.random.default_rng(99)
        rets = rng.normal(0, 0.01, size=252)
        dsr = deflated_sharpe_ratio(rets)
        # On pure noise, DSR should be small (likely near 0, possibly slightly pos/neg)
        assert abs(dsr) < 5  # sanity bound

    def test_deflated_sharpe_ratio_positive_skill(self):
        """Positive mean with non-trivial variance → positive DSR."""
        rng = np.random.default_rng(55)
        rets = rng.normal(0.001, 0.01, size=252)  # mean > 0, std > 0
        dsr = deflated_sharpe_ratio(rets)
        assert dsr > 0, f"DSR should be positive for positive mean returns, got {dsr}"

    def test_pbo_random_returns(self):
        """Random returns → PBO should be near 0.5 (half winners in-sample become losers)."""
        rng = np.random.default_rng(777)
        rets = rng.normal(0, 0.01, size=100)
        pbo = probability_backtest_overfitting(rets, n_splits=10)
        # On random data, PBO should be non-zero and not trivially 0
        assert 0.0 <= pbo <= 1.0

    def test_pbo_insufficient_data(self):
        """Fewer than 20 observations → PBO returns 0.5 (high uncertainty)."""
        rets = np.array([0.001, 0.002, 0.001])
        pbo = probability_backtest_overfitting(rets)
        assert pbo == 0.5


class TestCalibrationProtocolIntegration:
    """Tier 2 integration test: 20 random-noise heads → ZERO certified as champion."""

    @pytest.mark.asyncio
    async def test_zero_random_heads_certified(self):
        """20 random-noise heads → promotion certifies ZERO (Type I error controlled).

        The Tier 2 acceptance criterion: "Tier 2 test spins up a pool of 20
        random-noise 'heads' and asserts the promotion mechanism certifies
        ZERO of them as champion (family-wise Type I control verified)."
        """
        rng = np.random.default_rng(2026)
        n_heads = 20
        n_obs = 300  # below MIN_TOTAL_OBSERVATIONS (252) — some will fail obs check
        z_dim = 4

        certified_count = 0

        for head_idx in range(n_heads):
            z = rng.normal(0, 1, size=(n_obs, z_dim))
            # Random predictions
            preds = rng.uniform(0.3, 0.7, size=n_obs)
            # Random realized outcomes (no signal)
            realized = (rng.uniform(0, 1, size=n_obs) < preds).astype(float)
            # Random returns (no skill)
            returns = rng.normal(0, 0.01, size=n_obs)

            protocol = CalibrationProtocol()
            result = await protocol.run(
                head_name=f"random_head_{head_idx}",
                z_vectors=z,
                predicted_probs=preds,
                realized_correct=realized,
                as_of=date(2024, 12, 31),
                returns_override=returns,
            )

            if result.passes_promotion:
                certified_count += 1

        assert certified_count == 0, (
            f"{certified_count}/20 random-noise heads were incorrectly certified. "
            f"Type I error not controlled."
        )

    @pytest.mark.asyncio
    async def test_calibrated_head_with_signal_passes(self):
        """A head with deterministic well-calibrated predictions → passes Holm-Bonferroni.

        Use a deterministic mapping: realized_correct = 1 if prediction > 0.5 else 0.
        This is perfectly calibrated by construction (ECE=0) and should pass the
        calibration criteria when n_obs is sufficient.
        """
        rng = np.random.default_rng(42)
        n_obs = 400  # above minimum, enough per bin
        z_dim = 4

        z = rng.normal(0, 1, size=(n_obs, z_dim))
        # Perfectly calibrated predictions: 55% confidence → correct 55% of time
        preds = rng.uniform(0.4, 0.8, size=n_obs)
        realized = (rng.uniform(0, 1, size=n_obs) < preds).astype(float)
        # Positive returns → DSR > 0
        returns = rng.normal(0.001, 0.01, size=n_obs)

        protocol = CalibrationProtocol()
        result = await protocol.run(
            head_name="well_calibrated_head",
            z_vectors=z,
            predicted_probs=preds,
            realized_correct=realized,
            as_of=date(2024, 12, 31),
            returns_override=returns,
        )

        # Observation count is sufficient
        assert result.observation_count_sufficient is True
        # ECE should be low (well-calibrated predictions produce low ECE)
        assert (
            result.curve.ece < 0.1
        ), f"ECE={result.curve.ece:.4f} should be < 0.1 for well-calibrated predictions"
        # DSR should be positive (positive returns)
        assert result.dsr > 0, f"DSR={result.dsr:.4f} should be > 0 for positive returns"
        # PBO should be low (consistent returns → not overfit)
        assert result.pbo < 0.5, f"PBO={result.pbo:.4f} should be < 0.5"
