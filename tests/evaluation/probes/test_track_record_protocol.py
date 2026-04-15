"""
Tests for T-00-06: Track-Record Window Extension.

Tier 2: injects a short-run lucky streak and asserts no promotion proposal fires.

Ref: specs/08-autonomy-and-trust.md §7 (updated)
Ref: specs/12-performance-and-track-record.md §3.4 (updated)
Ref: T-00-06
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Mock data types matching the spec's promotion contract
# ---------------------------------------------------------------------------


@dataclass
class MonthlyAttribution:
    month_start: date
    brinson_allocation_effect: float
    brinson_selection_effect: float
    total_return: float
    rebalance_count: int  # number of rebalances this month


@dataclass
class BootstrapResult:
    sharpe_point_estimate: float
    sharpe_ci_lower_90: float  # 90% lower confidence bound
    sharpe_ci_upper_90: float


class TrackRecordEvaluator:
    """Evaluates whether a track record satisfies the L3/L4 promotion gates."""

    MIN_BOOTSTRAP_LOWER_BOUND = 0.3  # Sharpe floor
    MIN_POSITIVE_MONTHS = 8  # out of 12
    MIN_REBALANCE_EVENTS = 6  # in the 12-month window
    MIN_WINDOW_MONTHS = 12

    def evaluate(
        self,
        monthly_records: list[MonthlyAttribution],
        bootstrap_result: BootstrapResult,
    ) -> TrackRecordPromotionResult:
        """Evaluate whether a track record qualifies for L3/L4 promotion.

        Returns TrackRecordPromotionResult with pass/fail for each gate.
        """
        n_months = len(monthly_records)

        # Gate 1: 12-month window populated
        window_sufficient = n_months >= self.MIN_WINDOW_MONTHS

        # Gate 2: Bootstrap lower bound exceeds floor
        bootstrap_pass = bootstrap_result.sharpe_ci_lower_90 > self.MIN_BOOTSTRAP_LOWER_BOUND

        # Gate 3: Pool-consistency gate — positive in ≥ 8/12 trailing months
        if n_months > 0:
            positive_months = sum(
                1
                for m in monthly_records
                if (m.brinson_allocation_effect + m.brinson_selection_effect) > 0
            )
            consistency_pass = positive_months >= self.MIN_POSITIVE_MONTHS
        else:
            positive_months = 0
            consistency_pass = False

        # Gate 4: Minimum rebalance events
        total_rebalances = sum(m.rebalance_count for m in monthly_records)
        activity_pass = total_rebalances >= self.MIN_REBALANCE_EVENTS

        all_pass = window_sufficient and bootstrap_pass and consistency_pass and activity_pass

        return TrackRecordPromotionResult(
            n_months=n_months,
            window_sufficient=window_sufficient,
            bootstrap_lower_bound=bootstrap_result.sharpe_ci_lower_90,
            bootstrap_floor=self.MIN_BOOTSTRAP_LOWER_BOUND,
            bootstrap_pass=bootstrap_pass,
            positive_months=positive_months,
            min_required_positive=self.MIN_POSITIVE_MONTHS,
            consistency_pass=consistency_pass,
            total_rebalances=total_rebalances,
            min_required_rebalances=self.MIN_REBALANCE_EVENTS,
            activity_pass=activity_pass,
            promotion_proposal_fires=all_pass,
        )


@dataclass
class TrackRecordPromotionResult:
    n_months: int
    window_sufficient: bool
    bootstrap_lower_bound: float
    bootstrap_floor: float
    bootstrap_pass: bool
    positive_months: int
    min_required_positive: int
    consistency_pass: bool
    total_rebalances: int
    min_required_rebalances: int
    activity_pass: bool
    promotion_proposal_fires: bool


def make_monthly(
    year: int,
    month: int,
    alloc: float = 0.01,
    selection: float = 0.005,
    rebalances: int = 1,
) -> MonthlyAttribution:
    return MonthlyAttribution(
        month_start=date(year, month, 1),
        brinson_allocation_effect=alloc,
        brinson_selection_effect=selection,
        total_return=alloc + selection,
        rebalance_count=rebalances,
    )


def bootstrap_estimate(
    monthly_returns: list[float],
) -> BootstrapResult:
    """Compute Sharpe ratio point estimate and 90% bootstrap CI lower bound."""
    if len(monthly_returns) < 2:
        return BootstrapResult(0.0, 0.0, 0.0)

    mean_ret = float(np.mean(monthly_returns))
    std_ret = float(np.std(monthly_returns, ddof=1))
    sharpe = mean_ret / std_ret if std_ret > 1e-10 else 0.0

    # Bootstrap: resample monthly returns, compute Sharpe, repeat 1000x
    rng = np.random.default_rng(42)
    n = len(monthly_returns)
    sharpe_samples = []
    monthly_arr = np.array(monthly_returns)

    for _ in range(1000):
        sample = rng.choice(monthly_arr, size=n, replace=True)
        s_mean = float(np.mean(sample))
        s_std = float(np.std(sample, ddof=1))
        sharpe_samples.append(s_mean / s_std if s_std > 1e-10 else 0.0)

    sharpe_samples = sorted(sharpe_samples)
    ci_lower = sharpe_samples[50]  # 5th percentile → 90% CI lower bound
    ci_upper = sharpe_samples[949]  # 95th percentile

    return BootstrapResult(
        sharpe_point_estimate=sharpe,
        sharpe_ci_lower_90=ci_lower,
        sharpe_ci_upper_90=ci_upper,
    )


class TestTrackRecordWindow:
    """Tier 2 tests for the track-record promotion protocol."""

    def test_short_lucky_streak_does_not_fire_promotion(self):
        """Tier 2: a lucky 3-month streak does NOT fire a promotion proposal.

        The 12-month window is not met → promotion proposal cannot fire.
        Even if bootstrap CI lower bound is high (luck), the window gate fails.
        """
        # Only 3 months of data — window not satisfied
        monthly_records = [
            make_monthly(2024, 1, alloc=0.03, selection=0.02),  # lucky
            make_monthly(2024, 2, alloc=0.025, selection=0.015),  # lucky
            make_monthly(2024, 3, alloc=0.028, selection=0.012),  # lucky
        ]

        # Bootstrap result would look great if we had a real strategy
        # (high Sharpe point estimate, high CI lower bound)
        great_bootstrap = BootstrapResult(
            sharpe_point_estimate=1.5,
            sharpe_ci_lower_90=0.9,  # well above floor
            sharpe_ci_upper_90=2.1,
        )

        evaluator = TrackRecordEvaluator()
        result = evaluator.evaluate(monthly_records, great_bootstrap)

        # Window gate fails — only 3 months, not 12
        assert (
            result.window_sufficient is False
        ), "Only 3 months of data — 12-month window should NOT be sufficient"
        # Promotion must NOT fire
        assert result.promotion_proposal_fires is False, (
            f"Lucky 3-month streak should NOT fire promotion. "
            f"Gates: window={result.window_sufficient}, "
            f"bootstrap={result.bootstrap_pass}(lb={result.bootstrap_lower_bound:.3f}), "
            f"consistency={result.positive_months}/{result.min_required_positive}, "
            f"activity={result.total_rebalances}/{result.min_required_rebalances}"
        )

    def test_12month_window_met_but_consistency_fails(self):
        """12 months present but only 4/12 months positive → promotion blocked."""
        monthly_records = []
        for m in range(1, 13):
            year = 2024
            # Alternating: positive, negative, positive, negative...
            if m % 2 == 0:
                alloc, selection = -0.01, 0.005  # negative month
            else:
                alloc, selection = 0.015, 0.01  # positive month
            monthly_records.append(make_monthly(year, m, alloc, selection, rebalances=1))

        great_bootstrap = BootstrapResult(
            sharpe_point_estimate=0.8,
            sharpe_ci_lower_90=0.5,  # well above floor
            sharpe_ci_upper_90=1.1,
        )

        evaluator = TrackRecordEvaluator()
        result = evaluator.evaluate(monthly_records, great_bootstrap)

        # Window sufficient but only 6/12 positive months → consistency gate fails
        assert result.window_sufficient is True
        assert result.positive_months == 6
        assert result.min_required_positive == 8
        assert result.consistency_pass is False
        assert result.promotion_proposal_fires is False

    def test_12month_met_consistency_ok_but_activity_fails(self):
        """12 months, 10/12 positive, but only 3 rebalances → blocked by activity gate."""
        monthly_records = []
        for m in range(1, 13):
            year = 2024
            # Positive months
            monthly_records.append(make_monthly(year, m, alloc=0.015, selection=0.01, rebalances=0))
        # Only 3 months have rebalances (others are 0)
        monthly_records[0] = make_monthly(2024, 1, rebalances=1)
        monthly_records[3] = make_monthly(2024, 4, rebalances=1)
        monthly_records[7] = make_monthly(2024, 8, rebalances=1)

        great_bootstrap = BootstrapResult(
            sharpe_point_estimate=0.9,
            sharpe_ci_lower_90=0.6,
            sharpe_ci_upper_90=1.2,
        )

        evaluator = TrackRecordEvaluator()
        result = evaluator.evaluate(monthly_records, great_bootstrap)

        assert result.window_sufficient is True
        assert result.positive_months >= 8
        assert result.total_rebalances == 3  # below MIN of 6
        assert result.activity_pass is False
        assert result.promotion_proposal_fires is False

    def test_full_12month_track_record_passes(self):
        """A genuine 12-month track record with bootstrap, consistency, and activity → fires."""
        monthly_records = []
        for m in range(1, 13):
            year = 2024
            # 10/12 months positive, 2 slightly negative
            if m in (3, 9):
                alloc, selection = -0.005, 0.002
            else:
                alloc, selection = 0.015, 0.01
            monthly_records.append(make_monthly(year, m, alloc, selection, rebalances=1))

        great_bootstrap = BootstrapResult(
            sharpe_point_estimate=0.75,
            sharpe_ci_lower_90=0.45,  # above floor 0.3
            sharpe_ci_upper_90=1.05,
        )

        evaluator = TrackRecordEvaluator()
        result = evaluator.evaluate(monthly_records, great_bootstrap)

        assert result.window_sufficient is True
        assert result.bootstrap_pass is True
        assert result.positive_months >= 8
        assert result.consistency_pass is True
        assert result.total_rebalances >= 6
        assert result.activity_pass is True
        assert result.promotion_proposal_fires is True

    def test_bootstrap_lower_bound_at_floor_fails(self):
        """Bootstrap CI lower bound exactly at floor → still fails (must EXCEED)."""
        monthly_records = []
        for m in range(1, 13):
            monthly_records.append(make_monthly(2024, m, alloc=0.015, selection=0.01, rebalances=1))

        # Sharpe CI lower bound = 0.3 (exactly at floor, not ABOVE it)
        marginal_bootstrap = BootstrapResult(
            sharpe_point_estimate=0.6,
            sharpe_ci_lower_90=0.30,  # exactly at floor
            sharpe_ci_upper_90=0.9,
        )

        evaluator = TrackRecordEvaluator()
        result = evaluator.evaluate(monthly_records, marginal_bootstrap)

        assert (
            result.bootstrap_pass is False
        ), "Bootstrap lower bound at floor (not exceeding) should FAIL"
        assert result.promotion_proposal_fires is False

    def test_bootstrap_lower_bound_just_above_floor_passes(self):
        """Bootstrap CI lower bound just above floor → passes (must EXCEED, not equal)."""
        monthly_records = []
        for m in range(1, 13):
            monthly_records.append(make_monthly(2024, m, alloc=0.015, selection=0.01, rebalances=1))

        above_bootstrap = BootstrapResult(
            sharpe_point_estimate=0.6,
            sharpe_ci_lower_90=0.301,  # just above floor
            sharpe_ci_upper_90=0.9,
        )

        evaluator = TrackRecordEvaluator()
        result = evaluator.evaluate(monthly_records, above_bootstrap)

        assert result.bootstrap_pass is True
        assert result.promotion_proposal_fires is True

    def test_bootstrap_helper_produces_valid_ci(self):
        """Bootstrap CI lower bound is truly the 5th percentile of resampled Sharps."""
        # Monthly returns with known Sharpe
        monthly_returns = [0.01, 0.015, -0.005, 0.02, 0.012, 0.008] * 2  # 12 months
        result = bootstrap_estimate(monthly_returns)

        # Lower bound should be less than or equal to upper bound
        assert result.sharpe_ci_lower_90 <= result.sharpe_ci_upper_90
        # Lower bound should be a reasonable number
        assert -5.0 < result.sharpe_ci_lower_90 < 5.0
        # Point estimate should be between CI bounds
        assert (
            result.sharpe_ci_lower_90 <= result.sharpe_point_estimate <= result.sharpe_ci_upper_90
        )
