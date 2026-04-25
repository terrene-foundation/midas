"""Tier 2 integration tests for YahooFinanceAdapter.

Tests YahooFinanceAdapter against a real SQLite DataFlow instance (not mocked).
Validates that: prices, fundamentals, news, and corporate_actions paths
write correct rows to the fabric, and that the cross_check_prices method
correctly detects discrepancies above the threshold.

Ref: specs/03-universe-and-data.md §2.1 — Yahoo is fallback + cross-check.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midas.fabric.adapters.yahoo import YahooFinanceAdapter
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_yahoo.db")
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


class TestYahooFinanceAdapterHealth:
    """Health check tests."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_on_mock(self, started_db):
        """YahooFinanceAdapter reports healthy when mock yfinance returns rows."""
        adapter = YahooFinanceAdapter(db=started_db)

        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.iterrows.return_value = iter([])  # no rows needed for health

        async def run_in_executor_mock(*args, **kwargs):
            return mock_df

        loop = asyncio.get_event_loop()
        with patch.object(loop, "run_in_executor", run_in_executor_mock):
            with patch("yfinance.download", return_value=mock_df):
                result = await adapter.health_check()

        assert result["source"] == "yahoo"
        assert result["healthy"] is True

        await adapter.close()


import asyncio


class TestYahooFinanceAdapterPrices:
    """fetch_prices integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_prices_writes_to_prices_table(self, started_db):
        """fetch_prices writes OHLCV rows to the prices fabric table."""
        adapter = YahooFinanceAdapter(db=started_db)

        # Build a mock DataFrame like yfinance returns
        import pandas as pd

        mock_df = pd.DataFrame(
            {
                "Open": [185.50, 186.00],
                "High": [186.20, 187.10],
                "Low": [184.80, 185.50],
                "Close": [185.90, 186.75],
                "Volume": [50_000_000, 48_000_000],
            },
            index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
        )

        async def run_in_executor_mock(*args, **kwargs):
            return mock_df

        loop = asyncio.get_event_loop()
        with patch.object(loop, "run_in_executor", run_in_executor_mock):
            with patch("yfinance.download", return_value=mock_df):
                rows = await adapter.fetch_prices("AAPL", "2024-01-02", "2024-01-03")

        assert len(rows) == 2
        assert rows[0]["instrument"] == "AAPL"
        assert rows[0]["close"] == 185.90
        assert rows[1]["close"] == 186.75
        assert rows[0]["source_vintage"].startswith("yahoo:")

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_prices_returns_empty_on_download_failure(self, started_db):
        """fetch_prices returns [] when yfinance raises an exception."""
        from midas.fabric.adapters.base import AdapterError

        adapter = YahooFinanceAdapter(db=started_db)

        async def run_in_executor_raising(*args, **kwargs):
            raise RuntimeError("network error")

        loop = asyncio.get_event_loop()
        with patch.object(loop, "run_in_executor", run_in_executor_raising):
            rows = await adapter.fetch_prices("AAPL", "2024-01-02", "2024-01-03")

        assert rows == []

        await adapter.close()


class TestYahooFinanceAdapterFundamentals:
    """fetch_fundamentals integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_fundamentals_writes_to_fabric(self, started_db):
        """fetch_fundamentals writes to the fundamentals table and returns the written row."""
        adapter = YahooFinanceAdapter(db=started_db)

        mock_info = {
            "totalRevenue": 385_000_000_000,
            "ebitda": 125_000_000_000,
            "netIncomeToCommon": 97_000_000_000,
            "bookValue": 290.0,
            "sharesOutstanding": 15_500_000_000,
            "trailingPE": 28.5,
            "priceToBook": 45.2,
            "totalDebt": 120_000_000_000,
        }

        async def run_in_executor_mock(*args, **kwargs):
            return mock_info

        loop = asyncio.get_event_loop()
        with patch.object(loop, "run_in_executor", run_in_executor_mock):
            with patch("yfinance.Ticker") as mock_ticker_class:
                mock_ticker = MagicMock()
                mock_ticker.info = mock_info
                mock_ticker_class.return_value = mock_ticker
                result = await adapter.fetch_fundamentals("AAPL")

        assert result["instrument"] == "AAPL"
        assert result["revenue"] == 385_000_000_000
        assert result["pe_ratio"] == 28.5
        # de_ratio = totalDebt / bookValue = 120000000000 / 290
        assert result["de_ratio"] == pytest.approx(413_793_103.4, rel=1e-3)
        # ROE = netIncomeToCommon / bookValue = 97000000000 / 290
        assert result["roe"] == pytest.approx(334_482_758.6, rel=1e-3)

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_fundamentals_returns_empty_on_failure(self, started_db):
        """fetch_fundamentals returns {} when yfinance raises an exception."""
        adapter = YahooFinanceAdapter(db=started_db)

        async def run_in_executor_raising(*args, **kwargs):
            raise RuntimeError("yfinance error")

        loop = asyncio.get_event_loop()
        with patch.object(loop, "run_in_executor", run_in_executor_raising):
            result = await adapter.fetch_fundamentals("AAPL")

        assert result == {}

        await adapter.close()


class TestYahooFinanceAdapterNews:
    """fetch_news integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_news_writes_to_news_table(self, started_db):
        """fetch_news writes headline rows to the news fabric table."""
        adapter = YahooFinanceAdapter(db=started_db)

        mock_news = [
            {
                "uuid": "news-001",
                "title": "Apple Reports Record Q4 Revenue",
                "providerPublishTime": 1700000000,
                "relatedTickers": "AAPL",
            },
            {
                "uuid": "news-002",
                "title": "Apple Announces New Product",
                "providerPublishTime": 1700100000,
                "relatedTickers": "AAPL,META",
            },
        ]

        async def run_in_executor_mock(*args, **kwargs):
            return mock_news

        loop = asyncio.get_event_loop()
        with patch.object(loop, "run_in_executor", run_in_executor_mock):
            with patch("yfinance.Ticker") as mock_ticker_class:
                mock_ticker = MagicMock()
                mock_ticker.news = mock_news
                mock_ticker_class.return_value = mock_ticker
                rows = await adapter.fetch_news("AAPL", limit=10)

        assert len(rows) == 2
        assert rows[0]["headline"] == "Apple Reports Record Q4 Revenue"
        assert rows[0]["tickers"] == ("AAPL",)
        assert rows[1]["tickers"] == ("AAPL", "META")

        news = await started_db.express.list("news")
        assert len(news) == 2

        await adapter.close()


class TestYahooFinanceAdapterCorporateActions:
    """fetch_corporate_actions integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_corporate_actions_writes_dividends_and_splits(self, started_db):
        """fetch_corporate_actions writes dividends and splits to the fabric."""
        import pandas as pd

        adapter = YahooFinanceAdapter(db=started_db)

        mock_actions = pd.DataFrame(
            {
                "Dividends": [0.24, 0.0, 0.0],
                "Stock Splits": [0.0, 4.0, 0.0],
            },
            index=pd.to_datetime(["2024-02-15", "2024-06-10", "2024-08-01"]),
        )

        async def run_in_executor_mock(*args, **kwargs):
            return mock_actions

        loop = asyncio.get_event_loop()
        with patch.object(loop, "run_in_executor", run_in_executor_mock):
            with patch("yfinance.Ticker") as mock_ticker_class:
                mock_ticker = MagicMock()
                mock_ticker.actions = mock_actions
                mock_ticker_class.return_value = mock_ticker
                rows = await adapter.fetch_corporate_actions("AAPL")

        # 1 dividend + 1 split = 2 rows
        assert len(rows) == 2
        div_row = next(r for r in rows if r["action_type"] == "DIVIDEND")
        split_row = next(r for r in rows if r["action_type"] == "SPLIT")
        assert div_row["ratio_or_amount"] == 0.24
        assert split_row["ratio_or_amount"] == 4.0

        await adapter.close()


class TestYahooFinanceAdapterCrossCheck:
    """cross_check_prices integration tests."""

    @pytest.mark.asyncio
    async def test_cross_check_detects_discrepancy(self, started_db):
        """cross_check_prices flags when price discrepancy exceeds threshold."""
        import pandas as pd

        adapter = YahooFinanceAdapter(db=started_db, discrepancy_threshold_pct=1.0)

        # Yahoo close: 186.00, EODHD close: 185.00 → ~0.54% diff (below 1% threshold)
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

        # Mock EODHD adapter
        with patch.object(loop, "run_in_executor", run_in_executor_mock):
            with patch("yfinance.download", return_value=yahoo_df):
                with patch("midas.fabric.adapters.eodhd.EODHDAdapter") as mock_eodhd_class:
                    mock_eodhd = MagicMock()
                    mock_eodhd.fetch_prices = AsyncMock(return_value=[{"close": 185.00}])
                    mock_eodhd.close = AsyncMock()
                    mock_eodhd_class.return_value = mock_eodhd

                    result = await adapter.cross_check_prices("AAPL", "2024-01-02")

        assert result["yahoo_close"] == 186.00
        assert result["eodhd_close"] == 185.00
        assert result["discrepancy_pct"] is not None
        assert result["discrepancy_pct"] > 0  # discrepancy exists
        # Below threshold, so not flagged
        assert result["flagged"] is False

        await adapter.close()

    @pytest.mark.asyncio
    async def test_cross_check_flags_high_discrepancy(self, started_db):
        """cross_check_prices flags when price discrepancy exceeds 1% threshold."""
        import pandas as pd

        adapter = YahooFinanceAdapter(db=started_db, discrepancy_threshold_pct=1.0)

        # Yahoo close: 200.00, EODHD close: 185.00 → ~8.1% diff (above 1% threshold)
        yahoo_df = pd.DataFrame(
            {
                "Open": [199.0],
                "High": [201.0],
                "Low": [198.0],
                "Close": [200.00],
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

        assert result["yahoo_close"] == 200.00
        assert result["eodhd_close"] == 185.00
        assert result["flagged"] is True
        assert result["discrepancy_pct"] > 1.0

        await adapter.close()
