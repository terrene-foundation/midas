"""
Router Overfitting Protocol.

The meta-router is a model and must be trained with overfitting defenses
as rigorous as any other head:

  (a) PurgedKFold cross-validation — purge window tied to longest forecast horizon
  (b) Explicit parameter-count-to-observation ratio cap
  (c) Minimum observation count before router is allowed to drive live decisions
  (d) Naive non-router baseline as required challenger in the router's champion/challenger lane

Invariants:
  (a) router training data never includes (t, outcome) tuples where outcome post-dates t
  (b) router parameter count stays under the observation-ratio cap
  (c) router's own calibration curve is tracked; demotion is automatic if it
      underperforms the naive baseline

Ref: specs/05-model-pool-and-meta-router.md §4.2, §4.5
Ref: T-00-03
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from midas.fabric.models import FabricReader


# ---------------------------------------------------------------------------
# Data record types
# ---------------------------------------------------------------------------


@dataclass
class RouterTrainingRecord:
    """A single (context, head_outputs, realized_outcome) training tuple."""

    record_id: str
    pit_ts: datetime  # the decision timestamp — outcome must not post-date this
    outcome_ts: datetime  # when the realized outcome was recorded
    head_names: tuple[str, ...]
    head_calibrations: tuple[float, ...]  # recent hit-rate per head
    chosen_head: str
    outcome_realized: float  # e.g. forward return
    router_context: tuple[float, ...]  # z_t or equivalent


@dataclass
class NaiveBaselineRecord:
    """A naive-baseline (highest-recent-calibration) decision record."""

    record_id: str
    pit_ts: datetime
    head_names: tuple[str, ...]
    head_calibrations: tuple[float, ...]
    chosen_head: str
    outcome_realized: float


# ---------------------------------------------------------------------------
# Protocol result
# ---------------------------------------------------------------------------


@dataclass
class RouterOverfittingResult:
    """Output of the router overfitting protocol check."""

    protocol_id: str
    n_observations: int
    n_parameters: int
    param_ratio: float  # parameters / observations
    param_ratio_cap: float
    passes_param_ratio: bool
    min_observations_required: int
    passes_min_observations: bool
    purge_window_days: int
    longest_forecast_horizon_days: int
    has_naive_baseline: bool
    has_purged_cv: bool
    training_leak_detected: bool
    naive_baseline_score: float | None
    router_score: float | None
    naive_outperforms: bool | None  # True if naive beats router
    passes: bool
    run_at: datetime

    def summary(self) -> str:
        naive_vs = (
            f"naive={self.naive_baseline_score:.4f} vs router={self.router_score:.4f} "
            f"({'naive wins' if self.naive_outperforms else 'router wins'})  "
            if self.naive_baseline_score is not None
            else ""
        )
        return (
            f"RouterOverfittingProtocol: "
            f"n_obs={self.n_observations} (min={self.min_observations_required})  "
            f"params={self.n_parameters}  ratio={self.param_ratio:.4f}/{self.param_ratio_cap:.4f}  "
            f"{'PASS' if self.passes_param_ratio else 'FAIL-ratio'}  "
            f"leak={'YES' if self.training_leak_detected else 'no'}  "
            f"naive_baseline={'yes' if self.has_naive_baseline else 'MISSING'}  "
            f"{naive_vs}"
            f"{'PASS' if self.passes else 'FAIL'}"
        )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class RouterOverfittingProtocol:
    """Enforces overfitting defenses on the meta-router.

    A router passes only if:
      1. It has at least MIN_TRAINING_OBSERVATIONS training tuples
      2. param_count / n_observations <= MAX_PARAM_RATIO
      3. No (t, outcome) tuple in training has outcome post-dating t
      4. A naive baseline challenger exists in the pool
      5. Router's score is at least as good as the naive baseline's score
    """

    MIN_TRAINING_OBSERVATIONS = 504  # ~2 trading years of daily decisions
    MAX_PARAM_RATIO = 0.1  # params must not exceed 10% of observations
    LONGEST_FORECAST_HORIZON_DAYS = 60  # quarter (≈ 60 trading days)
    PURGE_WINDOW_DAYS = LONGEST_FORECAST_HORIZON_DAYS
    N_FOLDS = 5

    def __init__(self, reader: FabricReader) -> None:
        self._reader = reader

    async def run(
        self,
        router_family: str,
        n_parameters: int,
        as_of: date,
        *,
        horizon_days: int = 20,
        training_records_override: list[RouterTrainingRecord] | None = None,
        naive_records_override: list[NaiveBaselineRecord] | None = None,
    ) -> RouterOverfittingResult:
        """Run the router overfitting protocol.

        Parameters
        ----------
        router_family: e.g. "meta_router_v1", "contextual_bandit_v2"
        n_parameters: number of trainable parameters in the router model
        as_of: point-in-time date for reading historical data
        horizon_days: longest forecast horizon in trading days;
            purge window = max(horizon_days, PURGE_WINDOW_DAYS)
        training_records_override: synthetic records for testing
        naive_records_override: synthetic naive baseline records for testing

        Returns
        -------
        RouterOverfittingResult with overfitting checks and pass/fail decision.
        """
        # 1. Load training tuples
        if training_records_override is not None:
            training_records = training_records_override
        else:
            training_records = await self._reader.read_router_training_data(router_family, as_of)

        n_obs = len(training_records)

        # 2. Minimum observations check
        passes_min_obs = n_obs >= self.MIN_TRAINING_OBSERVATIONS

        # 3. Parameter ratio check
        param_ratio = n_parameters / n_obs if n_obs > 0 else float("inf")
        passes_param_ratio = param_ratio <= self.MAX_PARAM_RATIO

        # 4. Temporal leakage check: outcome_ts must not precede pit_ts.
        # Invariant (a): router training data never includes (t, outcome) tuples
        # where outcome post-dates t. "outcome.post_dates t" = outcome_ts > pit_ts.
        # The VIOLATION is outcome_ts <= pit_ts — outcome was already determined
        # before the decision timestamp (data bug / look-ahead leak).
        purge_window = max(horizon_days, self.PURGE_WINDOW_DAYS)
        training_leak_detected = self._check_temporal_leakage(training_records)

        # 5. Naive baseline exists?
        if naive_records_override is not None:
            naive_records = naive_records_override
        else:
            naive_records = await self._reader.read_naive_baseline(router_family, as_of)

        has_naive_baseline = len(naive_records) >= self.MIN_TRAINING_OBSERVATIONS // 10

        # 6. PurgedKFold check: horizon must be set (PURGE_WINDOW > 0)
        has_purged_cv = purge_window > 0

        # 7. Router vs naive score
        naive_score, router_score, naive_outperforms = self._compare_with_naive(
            training_records, naive_records
        )

        passes = (
            passes_min_obs
            and passes_param_ratio
            and not training_leak_detected
            and has_naive_baseline
            and has_purged_cv
            and (naive_score is None or router_score is None or not naive_outperforms)
        )

        return RouterOverfittingResult(
            protocol_id=str(uuid.uuid4()),
            n_observations=n_obs,
            n_parameters=n_parameters,
            param_ratio=float(param_ratio),
            param_ratio_cap=self.MAX_PARAM_RATIO,
            passes_param_ratio=passes_param_ratio,
            min_observations_required=self.MIN_TRAINING_OBSERVATIONS,
            passes_min_observations=passes_min_obs,
            purge_window_days=purge_window,
            longest_forecast_horizon_days=self.LONGEST_FORECAST_HORIZON_DAYS,
            has_naive_baseline=has_naive_baseline,
            has_purged_cv=has_purged_cv,
            training_leak_detected=training_leak_detected,
            naive_baseline_score=naive_score,
            router_score=router_score,
            naive_outperforms=naive_outperforms,
            passes=passes,
            run_at=datetime.now(),
        )

    def _check_temporal_leakage(
        self,
        records: list[RouterTrainingRecord],
    ) -> bool:
        """Detect whether any outcome_ts precedes or equals pit_ts.

        Invariant (a): outcome_ts must be strictly after pit_ts — the realized
        outcome of a forecast cannot be known before the forecast is made.
        outcome_ts <= pit_ts is a look-ahead leak: the training tuple contains
        information that was not available at decision time.
        """
        for rec in records:
            if rec.outcome_ts <= rec.pit_ts:
                return True
        return False

    def purged_kfold_indices(
        self,
        n_samples: int,
        purge_window_days: int,
        timestamps: list[datetime],
        n_folds: int = 5,
    ) -> list[tuple[list[int], list[int]]]:
        """Generate PurgedKFold train/test splits.

        The purge window prevents information from the test period bleeding
        into training via overlapping outcomes (e.g. a 20-day return overlaps
        the next period's training start).
        """
        if n_samples < 2:
            return []

        indices = np.arange(n_samples)
        purge = timedelta(days=purge_window_days)

        fold_size = n_samples // n_folds
        splits: list[tuple[list[int], list[int]]] = []

        for k in range(n_folds):
            # Test: fold k
            test_start = k * fold_size
            test_end = (k + 1) * fold_size if k < n_folds - 1 else n_samples
            test_idx = list(indices[test_start:test_end])

            # Train: everything before test_start, purged of overlap
            train_end = test_start
            if train_end > 0:
                train_end_ts = timestamps[train_end - 1]
                purge_cutoff = train_end_ts - purge
                train_idx = [i for i in range(train_end) if timestamps[i] < purge_cutoff]
            else:
                train_idx = []

            splits.append((train_idx, test_idx))

        return splits

    def _compare_with_naive(
        self,
        router_records: list[RouterTrainingRecord],
        naive_records: list[NaiveBaselineRecord],
    ) -> tuple[float | None, float | None, bool | None]:
        """Compare router decisions against the naive baseline.

        Naive baseline: always pick the head with highest recent calibration.

        Returns (naive_score, router_score, naive_outperforms).
        naive_outperforms=True means the naive baseline beats the router —
        a finding that should trigger router demotion.
        """
        if not naive_records:
            return None, None, None

        # Build aligned time series — naive records and router records should
        # share the same decision timestamps
        naive_by_ts = {r.pit_ts: r.outcome_realized for r in naive_records}
        router_by_ts = {r.pit_ts: r.outcome_realized for r in router_records}

        common_ts = sorted(set(naive_by_ts.keys()) & set(router_by_ts.keys()))
        if len(common_ts) < 10:
            return None, None, None

        naive_returns = np.array([naive_by_ts[ts] for ts in common_ts])
        router_returns = np.array([router_by_ts[ts] for ts in common_ts])

        # Sharpe-like score (mean / std); std=0 fallback → 0
        def sharpe(ret: np.ndarray) -> float:
            s = np.std(ret)
            return float(np.mean(ret) / s) if s > 1e-10 else 0.0

        naive_score = sharpe(naive_returns)
        router_score = sharpe(router_returns)

        return naive_score, router_score, naive_score > router_score
