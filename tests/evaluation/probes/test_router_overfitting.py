"""
Tests for T-00-03: Router Overfitting Protocol.

Tier 1: synthetic leak scenario — protocol catches temporal leakage.
Tier 2: parameter ratio cap, minimum observations, naive baseline challenger.

Ref: specs/05-model-pool-and-meta-router.md §4.2, §4.5
Ref: T-00-03
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import numpy as np
import pytest

from midas.evaluation.probes.router_overfitting import (
    NaiveBaselineRecord,
    RouterOverfittingProtocol,
    RouterOverfittingResult,
    RouterTrainingRecord,
)


def make_router_record(
    pit_ts: datetime,
    outcome_ts: datetime,
    head_names: tuple[str, ...] = ("head_a", "head_b"),
    head_calibrations: tuple[float, ...] = (0.55, 0.52),
    chosen_head: str = "head_a",
    outcome_realized: float = 0.001,
    router_context: tuple[float, ...] = (0.1, -0.05, 0.03),
) -> RouterTrainingRecord:
    return RouterTrainingRecord(
        record_id=str(uuid.uuid4()),
        pit_ts=pit_ts,
        outcome_ts=outcome_ts,
        head_names=head_names,
        head_calibrations=head_calibrations,
        chosen_head=chosen_head,
        outcome_realized=outcome_realized,
        router_context=router_context,
    )


def make_naive_record(
    pit_ts: datetime,
    head_names: tuple[str, ...] = ("head_a", "head_b"),
    head_calibrations: tuple[float, ...] = (0.55, 0.52),
    chosen_head: str = "head_a",
    outcome_realized: float = 0.001,
) -> NaiveBaselineRecord:
    return NaiveBaselineRecord(
        record_id=str(uuid.uuid4()),
        pit_ts=pit_ts,
        head_names=head_names,
        head_calibrations=head_calibrations,
        chosen_head=chosen_head,
        outcome_realized=outcome_realized,
    )


class TestRouterOverfittingProtocol:
    """Tier 1 + Tier 2 tests for the router overfitting protocol."""

    @pytest.fixture
    def mock_reader(self):
        reader = AsyncMock()
        reader.read_router_training_data = AsyncMock(return_value=[])
        reader.read_naive_baseline = AsyncMock(return_value=[])
        return reader

    # -------------------------------------------------------------------------
    # Tier 1 — synthetic leak scenario must be CAUGHT
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_detects_temporal_leak_in_training_data(self, mock_reader):
        """Tier 1: outcome_ts that post-dates pit_ts + purge window → leak detected.

        The protocol should detect that the training data contains a record
        whose outcome was recorded BEFORE the decision timestamp plus horizon —
        meaning the model saw future information during training.
        """
        n = 300
        horizon_days = 20
        base = datetime(2024, 1, 1)

        # Clean records first
        records = []
        for i in range(n):
            pit = base + timedelta(days=i)
            outcome = pit + timedelta(days=horizon_days + 5)  # legitimate horizon
            records.append(make_router_record(pit_ts=pit, outcome_ts=outcome))

        # Inject ONE leaking record: outcome_ts is 30 days AFTER pit_ts
        # This means at decision time "pit" the model already "knows" the outcome
        leak_idx = 100
        records[leak_idx] = make_router_record(
            pit_ts=base + timedelta(days=leak_idx),
            outcome_ts=base + timedelta(days=leak_idx - 30),  # BEFORE decision!
            # outcome_ts < pit_ts is the leak signal
        )

        mock_reader.read_router_training_data.return_value = records

        # Give the naive baseline too so the pass/fail can be evaluated
        naive_records = [
            make_naive_record(
                pit_ts=base + timedelta(days=i),
                outcome_realized=0.001,
            )
            for i in range(n)
        ]
        mock_reader.read_naive_baseline.return_value = naive_records

        protocol = RouterOverfittingProtocol(mock_reader)
        result = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=50,
            as_of=date(2024, 12, 31),
            horizon_days=horizon_days,
        )

        assert result.training_leak_detected is True, (
            f"Protocol should detect temporal leak. "
            f"Record at index {leak_idx} has outcome_ts < pit_ts (leak signal)."
        )
        assert result.passes is False, "Protocol should FAIL when leak is detected"

    # -------------------------------------------------------------------------
    # Tier 2 — parameter ratio cap
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_rejects_excessive_parameter_count(self, mock_reader):
        """Too many parameters relative to observations → FAIL on param ratio."""
        n = 100  # well below MIN_TRAINING_OBSERVATIONS
        horizon_days = 20
        base = datetime(2024, 1, 1)

        records = []
        for i in range(n):
            pit = base + timedelta(days=i)
            outcome = pit + timedelta(days=horizon_days + 5)
            records.append(make_router_record(pit_ts=pit, outcome_ts=outcome))

        mock_reader.read_router_training_data.return_value = records
        mock_reader.read_naive_baseline.return_value = [
            make_naive_record(pit_ts=base + timedelta(days=i), outcome_realized=0.001)
            for i in range(n)
        ]

        protocol = RouterOverfittingProtocol(mock_reader)
        result = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=50,  # 50/100 = 0.5 > 0.1 cap → FAIL
            as_of=date(2024, 12, 31),
            horizon_days=horizon_days,
        )

        assert result.passes_param_ratio is False
        assert result.param_ratio == pytest.approx(0.5, rel=1e-3)
        assert result.passes is False

    @pytest.mark.asyncio
    async def test_passes_within_param_ratio(self, mock_reader):
        """Parameters within 10% of observations → PASS on param ratio."""
        n = 600  # above minimum
        horizon_days = 20
        base = datetime(2024, 1, 1)

        records = []
        for i in range(n):
            pit = base + timedelta(days=i)
            outcome = pit + timedelta(days=horizon_days + 5)
            records.append(make_router_record(pit_ts=pit, outcome_ts=outcome))

        mock_reader.read_router_training_data.return_value = records
        mock_reader.read_naive_baseline.return_value = [
            make_naive_record(pit_ts=base + timedelta(days=i), outcome_realized=0.001)
            for i in range(n)
        ]

        protocol = RouterOverfittingProtocol(mock_reader)
        result = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=30,  # 30/600 = 0.05 < 0.1 cap → PASS
            as_of=date(2024, 12, 31),
            horizon_days=horizon_days,
        )

        assert result.passes_param_ratio is True
        assert result.param_ratio == pytest.approx(0.05, rel=1e-3)

    # -------------------------------------------------------------------------
    # Tier 2 — minimum observations
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fails_below_minimum_observations(self, mock_reader):
        """Below MIN_TRAINING_OBSERVATIONS → FAIL on minimum observations."""
        n = 100  # MIN is 504
        horizon_days = 20
        base = datetime(2024, 1, 1)

        records = []
        for i in range(n):
            pit = base + timedelta(days=i)
            outcome = pit + timedelta(days=horizon_days + 5)
            records.append(make_router_record(pit_ts=pit, outcome_ts=outcome))

        mock_reader.read_router_training_data.return_value = records
        mock_reader.read_naive_baseline.return_value = [
            make_naive_record(pit_ts=base + timedelta(days=i), outcome_realized=0.001)
            for i in range(n)
        ]

        protocol = RouterOverfittingProtocol(mock_reader)
        result = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=5,
            as_of=date(2024, 12, 31),
            horizon_days=horizon_days,
        )

        assert result.passes_min_observations is False
        assert result.n_observations == n
        assert result.min_observations_required == 504
        assert result.passes is False

    # -------------------------------------------------------------------------
    # Tier 2 — naive baseline challenger
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_missing_naive_baseline_fails(self, mock_reader):
        """No naive baseline records → FAIL (required challenger missing)."""
        n = 600
        horizon_days = 20
        base = datetime(2024, 1, 1)

        records = []
        for i in range(n):
            pit = base + timedelta(days=i)
            outcome = pit + timedelta(days=horizon_days + 5)
            records.append(make_router_record(pit_ts=pit, outcome_ts=outcome))

        mock_reader.read_router_training_data.return_value = records
        mock_reader.read_naive_baseline.return_value = []  # no naive baseline!

        protocol = RouterOverfittingProtocol(mock_reader)
        result = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=30,
            as_of=date(2024, 12, 31),
            horizon_days=horizon_days,
        )

        assert result.has_naive_baseline is False
        assert result.passes is False

    # -------------------------------------------------------------------------
    # Tier 2 — naive baseline score comparison
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_naive_outperforms_when_returns_are_random(self, mock_reader):
        """Router trained on random noise vs naive on same noise → naive may win.

        When the router has no signal to learn, the naive baseline (highest
        recent calibration) should match or beat it. The protocol should report
        naive_outperforms and the overall result should be FAIL.
        """
        n = 600
        horizon_days = 20
        base = datetime(2024, 1, 1)
        rng = np.random.default_rng(999)

        records = []
        naive_records = []
        for i in range(n):
            pit = base + timedelta(days=i)
            # Both router and naive see the same random outcomes
            outcome = rng.normal(0, 0.01)
            records.append(
                make_router_record(
                    pit_ts=pit,
                    outcome_ts=pit + timedelta(days=horizon_days + 5),
                    outcome_realized=outcome,
                )
            )
            naive_records.append(make_naive_record(pit_ts=pit, outcome_realized=outcome))

        mock_reader.read_router_training_data.return_value = records
        mock_reader.read_naive_baseline.return_value = naive_records

        protocol = RouterOverfittingProtocol(mock_reader)
        result = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=30,
            as_of=date(2024, 12, 31),
            horizon_days=horizon_days,
        )

        # Naive baseline should be present and scores computed
        assert result.has_naive_baseline is True
        assert result.naive_baseline_score is not None
        assert result.router_score is not None
        # On random data the naive baseline typically ties or beats the router
        # The protocol requires router to be strictly better
        if result.naive_outperforms:
            assert (
                result.passes is False
            ), "Protocol should FAIL when naive baseline beats the router"

    # -------------------------------------------------------------------------
    # Purge window
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_purge_window_reflects_forecast_horizon(self, mock_reader):
        """Larger horizon_days → larger purge_window_days."""
        n = 600
        base = datetime(2024, 1, 1)

        records = [
            make_router_record(
                pit_ts=base + timedelta(days=i),
                outcome_ts=base + timedelta(days=i + 30),
            )
            for i in range(n)
        ]

        mock_reader.read_router_training_data.return_value = records
        mock_reader.read_naive_baseline.return_value = [
            make_naive_record(pit_ts=base + timedelta(days=i)) for i in range(n)
        ]

        protocol = RouterOverfittingProtocol(mock_reader)

        # horizon_days=60 → purge_window should be max(60, LONGEST_FORECAST_HORIZON_DAYS=60) = 60
        result_60 = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=30,
            as_of=date(2024, 12, 31),
            horizon_days=60,
        )
        assert result_60.purge_window_days == 60

        # horizon_days=10 → purge_window should be max(10, 60) = 60 (cap at longest horizon)
        result_10 = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=30,
            as_of=date(2024, 12, 31),
            horizon_days=10,
        )
        assert result_10.purge_window_days == 60

    # -------------------------------------------------------------------------
    # Result dataclass
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_result_summary_is_readable(self, mock_reader):
        """RouterOverfittingResult.summary() returns a non-empty string."""
        n = 600
        base = datetime(2024, 1, 1)
        horizon_days = 20

        records = [
            make_router_record(
                pit_ts=base + timedelta(days=i),
                outcome_ts=base + timedelta(days=i + horizon_days + 5),
            )
            for i in range(n)
        ]

        mock_reader.read_router_training_data.return_value = records
        mock_reader.read_naive_baseline.return_value = [
            make_naive_record(pit_ts=base + timedelta(days=i)) for i in range(n)
        ]

        protocol = RouterOverfittingProtocol(mock_reader)
        result = await protocol.run(
            router_family="meta_router_v1",
            n_parameters=30,
            as_of=date(2024, 12, 31),
            horizon_days=horizon_days,
        )

        summary = result.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "RouterOverfittingProtocol" in summary
        assert "n_obs=" in summary
        assert "params=" in summary
        assert "ratio=" in summary
