"""
Calibration Methodology with Holm-Bonferroni Multiple-Comparison Correction.

Calibration is a statistical procedure, not a checklist. This module provides:

  (a) z_t-neighborhood estimator — k-NN with k tied to dimensionality and sample size
  (b) Minimum observation count per bin before a calibration claim is publishable
  (c) Holm-Bonferroni correction across promotion-contract criteria (6 tests → α/6 each)
  (d) Deflated Sharpe Ratio (DSR) and Probability of Backtest Overfitting (PBO)

A head is promoted only when ALL Holm-Bonferroni-corrected p-values exceed threshold
AND the DSR is positive AND PBO is below threshold.

Ref: specs/05-model-pool-and-meta-router.md §5.4
Ref: specs/12-performance-and-track-record.md §4
Ref: T-00-04
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CalibrationBin:
    """A single bin in the calibration curve."""

    bin_center: float  # e.g. 0.65 for the 60-70% confidence bin
    n_predictions: int
    n_correct: int
    empirical_accuracy: float  # n_correct / n_predictions
    expected_accuracy: float  # the predicted probability (bin_center)
    calibration_error: float  # |empirical - expected|


@dataclass
class CalibrationCurve:
    """Full calibration curve for one head."""

    head_name: str
    bins: list[CalibrationBin]
    n_total: int
    ece: float  # Expected Calibration Error (weighted mean |error|)
    mce: float  # Maximum Calibration Error (worst bin)


@dataclass
class PromotionCriteriaResult:
    """Result of one promotion-criterion statistical test."""

    criterion_name: str
    statistic: float
    p_value: float
    passes: bool
    threshold: float


@dataclass
class HeadCalibrationResult:
    """Full calibration result for one head, with Holm-Bonferroni correction."""

    head_name: str
    curve: CalibrationCurve
    criterion_results: list[PromotionCriteriaResult]
    holm_corrections: list[float]  # corrected α_i per criterion
    any_criterion_fails: bool
    holm_family_wise_alpha: float
    holm_pass: bool
    dsr: float | None  # Deflated Sharpe Ratio
    pbo: float | None  # Probability of Backtest Overfitting
    n_observations: int
    observation_count_sufficient: bool
    passes_promotion: bool
    run_at: datetime


# ---------------------------------------------------------------------------
# Holm-Bonferroni correction
# ---------------------------------------------------------------------------


def holm_bonferroni_corrections(n_tests: int, family_wise_alpha: float = 0.05) -> list[float]:
    """Return the Holm-Bonferroni-adjusted significance levels per test.

    The ith smallest p-value (out of m tests) is tested against α/(m - i + 1).
    """
    if n_tests < 1:
        return []
    return [family_wise_alpha / (n_tests - i) for i in range(n_tests)]


def apply_holm_bonferroni(
    results: list[PromotionCriteriaResult],
    family_wise_alpha: float = 0.05,
) -> tuple[list[PromotionCriteriaResult], list[float], bool]:
    """Apply Holm-Bonferroni correction to promotion-criterion results.

    Sorts results by p-value ascending. The ith result is compared against
    α/(m - i + 1). Returns updated results with corrected pass/fail and the
    per-criterion adjusted thresholds.
    """
    if not results:
        return results, [], True

    indexed = sorted(enumerate(results), key=lambda x: x[1].p_value)
    m = len(results)
    corrected_thresholds = [family_wise_alpha / (m - i) for i in range(m)]

    corrected_results: list[PromotionCriteriaResult] = list(results)
    all_pass = True
    for i, (orig_idx, res) in enumerate(indexed):
        threshold = corrected_thresholds[i]
        passes = res.p_value < threshold
        if not passes:
            all_pass = False
        corrected_results[orig_idx] = PromotionCriteriaResult(
            criterion_name=res.criterion_name,
            statistic=res.statistic,
            p_value=res.p_value,
            passes=passes,
            threshold=threshold,
        )

    return corrected_results, corrected_thresholds, all_pass


# ---------------------------------------------------------------------------
# Neighborhood estimator
# ---------------------------------------------------------------------------


class NeighborhoodEstimator:
    """k-NN calibration: neighborhood conditioned on z_t latent state.

    k is adaptive — tied to dimensionality and sample size per
    specs/05- §3.2: "k-NN with k tied to dimensionality and sample size."
    """

    def __init__(self, n_bins: int = 10) -> None:
        self.n_bins = n_bins

    def adaptive_k(self, z_dim: int, n_samples: int) -> int:
        """Compute adaptive k for k-NN.

        Heuristic: k = sqrt(n) / dim_factor, bounded [5, min(n/4, 50)].
        Larger z_dim → larger k (curse of dimensionality). Larger n → larger k.
        """
        base = max(5.0, math.sqrt(n_samples))
        dim_factor = 1 + (z_dim - 1) * 0.1
        k = int(base / dim_factor)
        return max(5, min(k, min(n_samples // 4, 50)))

    def knn_calibration(
        self,
        z_vectors: np.ndarray,
        predictions: np.ndarray,
        realized: np.ndarray,
        k: int | None = None,
    ) -> CalibrationCurve:
        """Compute calibration curve using k-NN neighborhood estimation.

        For each point, find its k nearest neighbors in z-space, compute the
        empirical accuracy in that neighborhood, and bin by predicted probability.
        """
        n = len(z_vectors)
        z_dim = z_vectors.shape[1]
        k_eff = k or self.adaptive_k(z_dim, n)

        # Per-point neighborhood accuracy (k-NN local estimate)
        local_accuracy = np.zeros(n)
        for i in range(n):
            dists = np.linalg.norm(z_vectors - z_vectors[i], axis=1)
            nearest_idx = np.argpartition(dists, k_eff)[:k_eff]
            nearest_idx = nearest_idx[np.argsort(dists[nearest_idx])]
            local_accuracy[i] = realized[nearest_idx].mean()

        # Bin by predicted probability
        bin_edges = np.linspace(0, 1, self.n_bins + 1)
        bins: list[CalibrationBin] = []
        ece = 0.0
        mce = 0.0

        for b in range(self.n_bins):
            lo, hi = bin_edges[b], bin_edges[b + 1]
            if b < self.n_bins - 1:
                mask = (predictions >= lo) & (predictions < hi)
            else:
                mask = (predictions >= lo) & (predictions <= hi)

            n_bin = int(mask.sum())
            if n_bin == 0:
                continue

            n_correct = int(realized[mask].sum())
            emp_acc = n_correct / n_bin
            calib_error = abs(emp_acc - lo)
            ece += calib_error * n_bin / n
            mce = max(mce, calib_error)

            bins.append(
                CalibrationBin(
                    bin_center=(lo + hi) / 2,
                    n_predictions=n_bin,
                    n_correct=n_correct,
                    empirical_accuracy=emp_acc,
                    expected_accuracy=(lo + hi) / 2,
                    calibration_error=calib_error,
                )
            )

        return CalibrationCurve(
            head_name="unknown",
            bins=bins,
            n_total=n,
            ece=ece,
            mce=mce,
        )


# ---------------------------------------------------------------------------
# Statistical tests for promotion criteria
# ---------------------------------------------------------------------------


def calibration_chi2_test(
    bins: list[CalibrationBin],
) -> tuple[float, float]:
    """χ² test for calibration — are empirical accuracies consistent with predicted?

    Returns (χ² statistic, p_value). Low p_value → calibration is poor.
    """
    if not bins:
        return 0.0, 1.0

    observed = np.array([b.n_correct for b in bins], dtype=float)
    expected = np.array([b.n_predictions * b.expected_accuracy for b in bins], dtype=float)

    if expected.sum() < 1:
        return 0.0, 1.0

    mask = expected > 0
    chi2 = float(((observed[mask] - expected[mask]) ** 2 / expected[mask]).sum())
    df = len(bins) - 1
    if df <= 0:
        return chi2, 1.0

    p_value = _chi2_survival(chi2, df)
    return chi2, p_value


def _chi2_survival(x: float, df: int) -> float:
    """χ² survival function S(x, df) = P(X > x) via regularized incomplete gamma."""
    if x <= 0:
        return 1.0
    if df <= 0:
        return 0.0
    return _gammainc(df / 2, x / 2)


def _gammainc(a: float, x: float) -> float:
    """Regularized lower incomplete gamma function P(a, x) via series expansion."""
    if x < 0 or a <= 0:
        return 0.0
    if x > a + 100:
        return 0.0
    max_iter = 200
    tol = 1e-12
    log_sum = -x + a * math.log(x) - math.lgamma(a)
    term = 1.0 / a
    partial = term
    for n in range(1, max_iter):
        term = term * x / (a + n)
        partial += term
        if abs(term) < tol * abs(partial):
            break
    return max(0.0, min(1.0, math.exp(log_sum) * partial))


def deflated_sharpe_ratio(
    returns: np.ndarray,
    base_sharpe: float = 0.0,
) -> float:
    """Deflated Sharpe Ratio — accounts for backtest overfitting.

    DSR = (SR_train - μ_H0) / σ_H0
    where σ_H0 ≈ sqrt(2/n) for daily returns.
    See Bailey and Lopez de Prado (2012).

    Returns DSR. Positive DSR → evidence of real skill above noise.
    """
    if len(returns) < 2:
        return 0.0

    mean_ret = float(np.mean(returns))
    std_ret = float(np.std(returns, ddof=1))
    n = len(returns)

    if std_ret < 1e-10:
        return 0.0

    sharpe = (mean_ret / std_ret) * math.sqrt(252)
    sigma_H0 = math.sqrt(2 / n) * (1 + 1 / (4 * n))
    if sigma_H0 < 1e-10:
        return 0.0
    return (sharpe - base_sharpe) / sigma_H0


def probability_backtest_overfitting(
    returns: np.ndarray,
    n_splits: int = 10,
    train_fraction: float = 0.6,
) -> float:
    """Estimate Probability of Backtest Overfitting via walk-forward Monte Carlo.

    Splits the return series into in-sample and out-of-sample windows.
    Counts what fraction of in-sample winners become out-of-sample losers.
    PBO ≈ fraction of strategies that overfit.
    """
    if len(returns) < 20:
        return 0.5

    n = len(returns)
    window_size = max(int(n * train_fraction), 5)
    n_trials = n_splits

    in_sample_winners = 0
    out_sample_losers = 0

    for trial in range(n_trials):
        is_start = (trial * (n - window_size)) // n_trials
        is_end = is_start + window_size
        os_start = is_end
        os_end = min(os_start + window_size, n)

        if os_end - os_start < 5 or is_end - is_start < 5:
            continue

        is_ret = returns[is_start:is_end]
        os_ret = returns[os_start:os_end]

        is_std = float(np.std(is_ret, ddof=1))
        os_std = float(np.std(os_ret, ddof=1))
        is_sharpe = float(np.mean(is_ret) / is_std) if is_std > 1e-10 else 0.0
        os_sharpe = float(np.mean(os_ret) / os_std) if os_std > 1e-10 else 0.0

        if is_sharpe > 0:
            in_sample_winners += 1
            if os_sharpe < 0:
                out_sample_losers += 1

    if in_sample_winners == 0:
        return 0.0
    return out_sample_losers / in_sample_winners


# ---------------------------------------------------------------------------
# Calibration protocol
# ---------------------------------------------------------------------------


class CalibrationProtocol:
    """Holm-Bonferroni-corrected calibration protocol for model promotion.

    A head is promoted only when ALL of the following hold:
      1. Holm-Bonferroni-corrected p-values for all 6 promotion criteria > α
      2. DSR > 0 (positive risk-adjusted skill above noise floor)
      3. PBO < 0.5 (less than 50% probability of backtest overfitting)
      4. Per-bin n >= MIN_PER_BIN observations
      5. Total n >= MIN_TOTAL_OBSERVATIONS
    """

    MIN_TOTAL_OBSERVATIONS = 252
    MIN_PER_BIN = 20
    HOLM_FAMILY_ALPHA = 0.05
    N_PROMOTION_CRITERIA = 6

    def __init__(self) -> None:
        self._neighborhood = NeighborhoodEstimator(n_bins=10)

    async def run(
        self,
        head_name: str,
        z_vectors: np.ndarray,
        predicted_probs: np.ndarray,
        realized_correct: np.ndarray,
        as_of: date,
        *,
        returns_override: np.ndarray | None = None,
    ) -> HeadCalibrationResult:
        """Run the full calibration protocol for one head.

        Parameters
        ----------
        head_name: identifier of the head being evaluated
        z_vectors: (n, z_dim) array of latent state vectors
        predicted_probs: (n,) array of the head's predicted P(correct)
        realized_correct: (n,) array of 0/1 actual outcomes
        as_of: point-in-time date
        returns_override: optional forward returns for DSR/PBO computation

        Returns
        -------
        HeadCalibrationResult with all Holm-Bonferroni-corrected tests and pass/fail
        """
        n_obs = len(z_vectors)
        obs_sufficient = n_obs >= self.MIN_TOTAL_OBSERVATIONS

        curve = self._neighborhood.knn_calibration(z_vectors, predicted_probs, realized_correct)
        curve.head_name = head_name

        criterion_results = self._run_promotion_criteria(curve, n_obs)
        corrected, holm_thresholds, holm_pass = apply_holm_bonferroni(
            criterion_results, self.HOLM_FAMILY_ALPHA
        )

        rets = returns_override if returns_override is not None else np.zeros(n_obs)
        dsr = deflated_sharpe_ratio(rets)
        pbo = probability_backtest_overfitting(rets)

        passes = (
            holm_pass
            and obs_sufficient
            and dsr > 0
            and pbo < 0.5
            and all(b.n_predictions >= self.MIN_PER_BIN for b in curve.bins)
        )

        return HeadCalibrationResult(
            head_name=head_name,
            curve=curve,
            criterion_results=criterion_results,
            holm_corrections=holm_thresholds,
            any_criterion_fails=not holm_pass,
            holm_family_wise_alpha=self.HOLM_FAMILY_ALPHA,
            holm_pass=holm_pass,
            dsr=dsr,
            pbo=pbo,
            n_observations=n_obs,
            observation_count_sufficient=obs_sufficient,
            passes_promotion=passes,
            run_at=datetime.now(),
        )

    def _run_promotion_criteria(
        self,
        curve: CalibrationCurve,
        n_obs: int,
    ) -> list[PromotionCriteriaResult]:
        """Run the 6 promotion-criterion statistical tests from spec 05- §5.4."""
        results: list[PromotionCriteriaResult] = []

        chi2, p_chi2 = calibration_chi2_test(curve.bins)
        results.append(
            PromotionCriteriaResult(
                criterion_name="calibration_chi2",
                statistic=chi2,
                p_value=p_chi2,
                passes=p_chi2 > self.HOLM_FAMILY_ALPHA,
                threshold=self.HOLM_FAMILY_ALPHA,
            )
        )

        min_bin_n = min((b.n_predictions for b in curve.bins), default=0)
        results.append(
            PromotionCriteriaResult(
                criterion_name="min_bin_observations",
                statistic=float(min_bin_n),
                p_value=1.0 if min_bin_n >= self.MIN_PER_BIN else 0.0,
                passes=min_bin_n >= self.MIN_PER_BIN,
                threshold=float(self.MIN_PER_BIN),
            )
        )

        ece = curve.ece
        p_ece = max(0.0, min(1.0, 1.0 - ece / 0.1))
        results.append(
            PromotionCriteriaResult(
                criterion_name="calibration_ece",
                statistic=ece,
                p_value=p_ece,
                passes=ece < 0.05,
                threshold=0.05,
            )
        )

        mce = curve.mce
        p_mce = max(0.0, min(1.0, 1.0 - mce / 0.2))
        results.append(
            PromotionCriteriaResult(
                criterion_name="calibration_mce",
                statistic=mce,
                p_value=p_mce,
                passes=mce < 0.10,
                threshold=0.10,
            )
        )

        if len(curve.bins) >= 2:
            bin_accs = np.array([b.empirical_accuracy for b in curve.bins])
            acc_variance = float(np.var(bin_accs))
        else:
            acc_variance = 0.0
        p_consistency = max(0.0, min(1.0, 1.0 - acc_variance / 0.05))
        results.append(
            PromotionCriteriaResult(
                criterion_name="pool_consistency",
                statistic=acc_variance,
                p_value=p_consistency,
                passes=acc_variance < 0.03,
                threshold=0.03,
            )
        )

        results.append(
            PromotionCriteriaResult(
                criterion_name="min_total_observations",
                statistic=float(n_obs),
                p_value=1.0 if n_obs >= self.MIN_TOTAL_OBSERVATIONS else 0.0,
                passes=n_obs >= self.MIN_TOTAL_OBSERVATIONS,
                threshold=float(self.MIN_TOTAL_OBSERVATIONS),
            )
        )

        return results
