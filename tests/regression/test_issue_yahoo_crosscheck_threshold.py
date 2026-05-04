"""Regression: Yahoo cross-check must flag prices exceeding the threshold.

Verifies that cross_check_prices sets flagged=True when price discrepancy
exceeds the configured threshold, and that an audit entry is written for
the discrepancy. Uses a real SQLite DataFlow instance.

Ref: specs/03-universe-and-data.md §2.1 — cross-check threshold enforcement.
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midas.fabric.adapters.yahoo import YahooFinanceAdapter
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for regression tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_yahoo_crosscheck.db")
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
    """Start the database for async adapter tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


@pytest.mark.regression
class TestYahooCrossCheckThresholdRegression:
    """Cross-check prices exceeding configured threshold must flag and audit."""

    @pytest.mark.asyncio
    async def test_cross_check_above_threshold_flags_and_audits(self, started_db):
        """Prices differing > threshold result in flagged=True and an audit entry."""
        import pandas as pd

        adapter = YahooFinanceAdapter(db=started_db, discrepancy_threshold_pct=1.0)

        # Yahoo close: 210.00, EODHD close: 185.00 -> ~13.5% diff (above 1%)
        yahoo_df = pd.DataFrame(
            {
                "Open": [209.0],
                "High": [211.0],
                "Low": [208.0],
                "Close": [210.00],
                "Volume": [50_000_000],
            },
            index=pd.to_datetime(["2024-01-02"]),
        )

        async def run_in_executor_mock(*args, **kwargs):
            return yahoo_df

        loop = asyncio.get_event_loop()

        with patch.object(loop, "run_in_executor", run_in_executor_mock):
            with patch("yfinance.download", return_value=yahoo_df):
                with patch("midas.fabric.adapters.eodhd.EODHDAdapter") as mock_eodhd_class:
                    mock_eodhd = MagicMock()
                    mock_eodhd.fetch_prices = AsyncMock(return_value=[{"close": 185.00}])
                    mock_eodhd.close = AsyncMock()
                    mock_eodhd_class.return_value = mock_eodhd

                    result = await adapter.cross_check_prices("AAPL", "2024-01-02")

        # Verify the result is flagged
        assert result["flagged"] is True
        assert result["discrepancy_pct"] is not None
        assert result["discrepancy_pct"] > 1.0

        # Verify an audit entry was written for the discrepancy
        audit_rows = await started_db.express.list("audit_log")
        cross_check_audits = [r for r in audit_rows if r.get("rule_name") == "cross_check_prices"]
        assert len(cross_check_audits) >= 1, (
            f"Expected at least 1 audit row for cross_check_prices, "
            f"found {len(cross_check_audits)} among {len(audit_rows)} total audit rows"
        )

        await adapter.close()

    @pytest.mark.asyncio
    async def test_cross_check_below_threshold_no_flag(self, started_db):
        """Prices differing < threshold result in flagged=False."""
        import pandas as pd

        adapter = YahooFinanceAdapter(db=started_db, discrepancy_threshold_pct=5.0)

        # Yahoo close: 186.00, EODHD close: 185.00 -> ~0.54% diff (below 5%)
        yahoo_df = pd.DataFrame(
            {
                "Open": [185.0],
                "High": [187.0],
                "Low": [184.0],
                "Close": [186.00],
                "Volume": [50_000_000],
            },
            index=pd.to_datetime(["2024-01-02"]),
        )

        async def run_in_executor_mock(*args, **kwargs):
            return yahoo_df

        loop = asyncio.get_event_loop()

        with patch.object(loop, "run_in_executor", run_in_executor_mock):
            with patch("yfinance.download", return_value=yahoo_df):
                with patch("midas.fabric.adapters.eodhd.EODHDAdapter") as mock_eodhd_class:
                    mock_eodhd = MagicMock()
                    mock_eodhd.fetch_prices = AsyncMock(return_value=[{"close": 185.00}])
                    mock_eodhd.close = AsyncMock()
                    mock_eodhd_class.return_value = mock_eodhd

                    result = await adapter.cross_check_prices("AAPL", "2024-01-02")

        assert result["flagged"] is False
        assert result["discrepancy_pct"] is not None
        assert result["discrepancy_pct"] < 5.0

        await adapter.close()
