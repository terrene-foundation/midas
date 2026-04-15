"""Tier 1 tests for universe construction module."""

import os
import tempfile

import pytest

from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for universe tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_universe.db")
    db_url = f"sqlite:///{db_path}"
    database = create_fabric(database_url=db_url, auto_migrate=True)
    yield database
    try:
        database.close()
    except Exception:
        pass
    reset_fabric()
    for suffix in ("-wal", "-shm"):
        try:
            os.unlink(db_path + suffix)
        except OSError:
            pass
    try:
        os.unlink(db_path)
    except OSError:
        pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


@pytest.fixture
async def started_db(db):
    """Start the database for async tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


class TestETFSelection:
    """Tests for ETF selection engine."""

    def test_score_etf_passes_all_criteria(self):
        """ETF passing all thresholds gets positive score."""
        from midas.universe.etf_selection import ETFCandidate, score_etf

        etf = ETFCandidate(
            ticker="SPY",
            name="SPDR S&P 500",
            aum=400e9,
            expense_ratio=0.0009,
            avg_daily_volume=30e9,
            tracking_error=0.0002,
            fund_age_years=30,
            category="us_large_cap",
        )
        score = score_etf(etf)
        assert score > 0

    def test_score_etf_below_minimum_aum(self):
        """ETF below AUM floor gets no AUM points but still scores on other criteria."""
        from midas.universe.etf_selection import ETFCandidate, score_etf

        etf = ETFCandidate(
            ticker="TINY",
            name="Tiny ETF",
            aum=1e6,  # 1M — way below 500M minimum
            expense_ratio=0.0009,
            avg_daily_volume=30e9,
            tracking_error=0.0002,
            fund_age_years=30,
            category="us_small",
        )
        score = score_etf(etf)
        # No AUM points (1e6 < 500M), but gets expense + volume + tracking_error + age
        # (0.004-0.0009)*1000=3.1 + min(30e9/1e7,5)=5 + (0.0015-0.0002)*1000=1.3 + 2.0 = 11.4
        assert 11.0 < score < 12.0

    def test_score_etf_high_expense(self):
        """ETF with expense ratio above cap gets no expense points."""
        from midas.universe.etf_selection import ETFCandidate, score_etf

        etf = ETFCandidate(
            ticker="EXPensive",
            name="Expensive ETF",
            aum=400e9,
            expense_ratio=0.0100,  # 1% — above 0.40% cap
            avg_daily_volume=30e9,
            tracking_error=0.0002,
            fund_age_years=30,
            category="us_large_cap",
        )
        score = score_etf(etf)
        # No points from expense ratio, but gets AUM + volume + tracking error + age
        assert score > 0

    @pytest.mark.asyncio
    async def test_detect_missing_exposures_finds_gap(self):
        """detect_missing_exposures returns missing factors."""
        from midas.universe.etf_selection import detect_missing_exposures

        current = ["SPY", "QQQ"]  # No small-cap exposure
        target = ["us_small_cap", "us_large_cap"]
        missing = await detect_missing_exposures(current, target)
        assert "us_small_cap" in missing


class TestOverlapAnalysis:
    """Tests for holdings overlap analyzer."""

    def test_compute_overlap_identical_returns(self):
        """Two identical return series have correlation 1.0."""
        from midas.universe.overlap import compute_overlap

        returns_a = [0.01, 0.02, -0.01, 0.03, 0.015]
        returns_b = [0.01, 0.02, -0.01, 0.03, 0.015]
        overlap = compute_overlap(returns_a, returns_b)
        assert abs(overlap - 1.0) < 0.0001

    def test_compute_overlap_opposite_returns(self):
        """Two perfectly opposite return series have correlation -1.0."""
        from midas.universe.overlap import compute_overlap

        returns_a = [0.01, 0.02, -0.01, 0.03, 0.015]
        returns_b = [-0.01, -0.02, 0.01, -0.03, -0.015]
        overlap = compute_overlap(returns_a, returns_b)
        assert abs(overlap - (-1.0)) < 0.0001

    def test_compute_overlap_zero_returns(self):
        """Two zero-return series have zero correlation."""
        from midas.universe.overlap import compute_overlap

        returns_a = [0.0, 0.0, 0.0]
        returns_b = [0.0, 0.0, 0.0]
        overlap = compute_overlap(returns_a, returns_b)
        assert overlap == 0.0

    def test_compute_overlap_insufficient_data(self):
        """Series shorter than 2 returns get zero correlation."""
        from midas.universe.overlap import compute_overlap

        assert compute_overlap([0.01], [0.01]) == 0.0
        assert compute_overlap([], []) == 0.0

    def test_dedupe_overlapping_removes_duplicates(self):
        """dedupe_overlapping removes ETFs with correlation above threshold."""
        from midas.universe.overlap import dedupe_overlapping

        etfs = [
            {"ticker": "SPY", "score": 100, "category": "us_large_cap"},
            {"ticker": "IVV", "score": 90, "category": "us_large_cap"},
        ]
        returns = {
            "SPY": [0.01, 0.02, 0.03],
            "IVV": [0.0101, 0.0201, 0.0301],  # Very similar to SPY
        }
        result = dedupe_overlapping(etfs, returns, threshold=0.8)
        assert len(result) == 1
        # Higher score wins
        assert result[0]["ticker"] == "SPY"

    def test_dedupe_overlapping_different_etfs_kept(self):
        """ETF with correlation below threshold is kept."""
        from midas.universe.overlap import dedupe_overlapping

        etfs = [
            {"ticker": "SPY", "score": 100, "category": "us_large_cap"},
            {"ticker": "TLT", "score": 80, "category": "us_bond"},
        ]
        returns = {
            "SPY": [0.01, 0.02, 0.03, 0.04],
            "TLT": [-0.01, -0.02, 0.01, -0.01],  # Negatively correlated
        }
        result = dedupe_overlapping(etfs, returns, threshold=0.8)
        assert len(result) == 2


class TestFactorGapDetector:
    """Tests for factor gap detector."""

    @pytest.mark.asyncio
    async def test_detect_factor_gaps_returns_list(self):
        """detect_factor_gaps returns a list of FactorGaps."""
        from midas.universe.factor_gap import detect_factor_gaps

        current = ["SPY"]
        target_factors = ["momentum"]
        returns_data = {
            "SPY": [0.01, 0.02, 0.03, 0.04, 0.05, 0.01, 0.02, 0.03, 0.04, 0.05],
            "MTUM": [0.012, 0.022, 0.032, 0.042, 0.052, 0.012, 0.022, 0.032, 0.042, 0.052],
        }
        gaps = await detect_factor_gaps(current, target_factors, returns_data)
        assert isinstance(gaps, list)
        assert len(gaps) >= 1

    @pytest.mark.asyncio
    async def test_detect_factor_gaps_empty_universe(self):
        """detect_factor_gaps handles empty current universe."""
        from midas.universe.factor_gap import detect_factor_gaps

        current = []
        target_factors = ["value", "momentum"]
        returns_data = {
            "VTV": [0.01, 0.02, 0.03],
            "MTUM": [0.01, 0.02, 0.03],
        }
        gaps = await detect_factor_gaps(current, target_factors, returns_data)
        assert len(gaps) >= 1


class TestUniverseChangelog:
    """Tests for universe changelog writer."""

    @pytest.mark.asyncio
    async def test_record_addition_writes_row(self, started_db):
        """record_addition writes to universe_changelog fabric table."""
        from midas.universe.changelog import record_addition

        result = await record_addition(
            ticker="NEWETF",
            reason="fills_factor_gap",
            effective_date="2024-06-01",
            backtest_impact="positive",
            fabric_db=started_db,
        )
        assert result.get("rows_affected", 0) >= 1

        rows = await started_db.express.list(
            "universe_changelog",
            filter={"ticker": "NEWETF"},
        )
        assert len(rows) >= 1
        assert rows[0]["action"] == "added"
        assert rows[0]["reason"] == "fills_factor_gap"

    @pytest.mark.asyncio
    async def test_record_removal_writes_row(self, started_db):
        """record_removal writes to universe_changelog fabric table."""
        from midas.universe.changelog import record_removal

        result = await record_removal(
            ticker="OLDFUND",
            reason="liquidity_failure",
            effective_date="2024-07-01",
            backtest_impact="minimal",
            fabric_db=started_db,
        )
        assert result.get("rows_affected", 0) >= 1

        rows = await started_db.express.list(
            "universe_changelog",
            filter={"ticker": "OLDFUND"},
        )
        assert len(rows) >= 1
        assert rows[0]["action"] == "removed"


class TestScheduler:
    """Tests for universe review scheduler."""

    def test_compute_next_review_dates(self):
        """compute_next_review_dates returns valid ISO date strings."""
        from midas.universe.scheduler import compute_next_review_dates

        schedule = compute_next_review_dates()
        assert schedule.next_etf_review
        assert schedule.next_full_reeval
        assert schedule.next_sp1500_scan

        # Validate ISO format
        for date_str in [
            schedule.next_etf_review,
            schedule.next_full_reeval,
            schedule.next_sp1500_scan,
        ]:
            parts = date_str.split("-")
            assert len(parts) == 3
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            assert 2020 <= year <= 2030
            assert 1 <= month <= 12
            assert 1 <= day <= 31

    def test_first_monday(self):
        """_first_monday returns Monday date in valid ISO format."""
        from midas.universe.scheduler import _first_monday

        # January 2026: first Monday is the 5th
        result = _first_monday(2026, 1)
        assert result == "2026-01-05"

        # December 2025: first Monday is the 1st
        result = _first_monday(2025, 12)
        assert result == "2025-12-01"

    def test_third_friday(self):
        """_third_friday returns third Friday of the given month."""
        from midas.universe.scheduler import _third_friday

        # March 2026: third Friday is the 20th
        result = _third_friday(2026, 3)
        assert result == "2026-03-20"


class TestUniverseConstraints:
    """Tests for universe constraint enforcement."""

    @pytest.mark.asyncio
    async def test_universe_constraint_is_allowed(self, started_db):
        """UniverseConstraint.is_allowed returns True for in-universe tickers."""
        from midas.fabric.adapters.universe import UniverseAdapter
        from midas.universe.constraints import UniverseConstraint

        adapter = UniverseAdapter(db=started_db)
        constraint = UniverseConstraint(adapter)

        await constraint.refresh("2024-06-01")

        # SPY and AAPL should be in the universe from mock data
        assert constraint.is_allowed("AAPL")
        assert constraint.is_allowed("MSFT")

    @pytest.mark.asyncio
    async def test_universe_constraint_blocks_unknown_ticker(self, started_db):
        """UniverseConstraint blocks tickers not in universe."""
        from midas.fabric.adapters.universe import UniverseAdapter
        from midas.universe.constraints import UniverseConstraint

        adapter = UniverseAdapter(db=started_db)
        constraint = UniverseConstraint(adapter)

        await constraint.refresh("2024-06-01")

        # XYZ is never in the universe
        assert not constraint.is_allowed("XYZ")

    @pytest.mark.asyncio
    async def test_universe_constraint_filter_allowed(self, started_db):
        """UniverseConstraint.filter_allowed returns only allowed tickers."""
        from midas.fabric.adapters.universe import UniverseAdapter
        from midas.universe.constraints import UniverseConstraint

        adapter = UniverseAdapter(db=started_db)
        constraint = UniverseConstraint(adapter)

        await constraint.refresh("2024-06-01")

        tickers = ["AAPL", "XYZ", "MSFT", "INVALID"]
        allowed = constraint.filter_allowed(tickers)
        assert "XYZ" not in allowed
        assert "INVALID" not in allowed
        assert "AAPL" in allowed
        assert "MSFT" in allowed

    @pytest.mark.asyncio
    async def test_check_trade_blocks_outside_universe(self, started_db):
        """check_trade returns (False, reason) for out-of-universe ticker."""
        from midas.fabric.adapters.universe import UniverseAdapter
        from midas.universe.constraints import UniverseConstraint

        adapter = UniverseAdapter(db=started_db)
        constraint = UniverseConstraint(adapter)

        await constraint.refresh("2024-06-01")

        allowed, reason = constraint.check_trade("XYZ", "buy")
        assert not allowed
        assert "XYZ" in reason

    @pytest.mark.asyncio
    async def test_check_trade_allows_in_universe(self, started_db):
        """check_trade returns (True, '') for in-universe ticker."""
        from midas.fabric.adapters.universe import UniverseAdapter
        from midas.universe.constraints import UniverseConstraint

        adapter = UniverseAdapter(db=started_db)
        constraint = UniverseConstraint(adapter)

        await constraint.refresh("2024-06-01")

        allowed, reason = constraint.check_trade("AAPL", "buy")
        assert allowed
        assert reason == ""
