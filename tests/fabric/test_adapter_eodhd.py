"""Tier 2 integration tests for EODHDAdapter.

Tests EODHDAdapter against a real SQLite DataFlow instance (not mocked).
Validates that: prices, fundamentals, news, and corporate_actions paths
write correct rows to the fabric, and that auth failures return empty
results rather than raising exceptions.

Ref: specs/03-universe-and-data.md §2.1 — EODHD is the primary price source.
"""

import os
import tempfile

import httpx
import pytest

from midas.fabric.adapters.eodhd import EODHDAdapter
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_eodhd.db")
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


class TestEODHDAdapterHealth:
    """Health check tests."""

    @pytest.mark.asyncio
    async def test_health_check_returns_unhealthy_when_no_key(self, db):
        """EODHDAdapter reports unhealthy when EODHD_API_KEY is not set."""
        adapter = EODHDAdapter(db=db, api_key=None)
        result = await adapter.health_check()
        assert result["source"] == "eodhd"
        assert result["healthy"] is False
        assert "not configured" in result["detail"]

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_on_mock_api_response(self, started_db):
        """EODHDAdapter reports healthy when API key is present and mock returns rows."""
        adapter = EODHDAdapter(db=started_db, api_key="test-key-123")

        mock_prices_response = [
            {
                "date": "2024-01-02",
                "open": 185.50,
                "high": 186.20,
                "low": 184.80,
                "close": 185.90,
                "volume": 50_000_000,
                "adjusted_close": 185.90,
            },
        ]

        async def mock_get(*args, **kwargs):
            return httpx.Response(200, json=mock_prices_response)

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        result = await adapter.health_check()
        assert result["source"] == "eodhd"
        assert result["healthy"] is True
        assert "returned 1 rows" in result["detail"]
        await adapter.close()


class TestEODHDAdapterPrices:
    """fetch_prices integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_prices_writes_to_prices_table(self, started_db):
        """fetch_prices writes OHLCV rows to the prices fabric table and returns them."""
        adapter = EODHDAdapter(db=started_db, api_key="test-key-123")

        mock_response = [
            {
                "date": "2024-01-02",
                "open": 185.50,
                "high": 186.20,
                "low": 184.80,
                "close": 185.90,
                "volume": 50_000_000,
                "dividend": 0.0,
                "split_factor": 1.0,
            },
            {
                "date": "2024-01-03",
                "open": 186.00,
                "high": 187.10,
                "low": 185.50,
                "close": 186.75,
                "volume": 48_000_000,
                "dividend": 0.24,
                "split_factor": 1.0,
            },
        ]

        async def mock_get(*args, **kwargs):
            return httpx.Response(200, json=mock_response)

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_prices("AAPL.US", "2024-01-02", "2024-01-03")

        assert len(rows) == 2
        assert rows[0]["instrument"] == "AAPL.US"
        assert rows[0]["period_end"] == "2024-01-02"
        assert rows[0]["close"] == 185.90
        assert rows[1]["close"] == 186.75

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_prices_handles_split_factor(self, started_db):
        """fetch_prices writes split_ratio when split_factor != 1.0."""
        adapter = EODHDAdapter(db=started_db, api_key="test-key-123")

        mock_response = [
            {
                "date": "2024-06-10",
                "open": 200.00,
                "high": 201.00,
                "low": 199.00,
                "close": 200.50,
                "volume": 10_000_000,
                "dividend": 0.0,
                "split_factor": 4.0,  # 4:1 split
            },
        ]

        async def mock_get(*args, **kwargs):
            return httpx.Response(200, json=mock_response)

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_prices("AAPL.US", "2024-06-10", "2024-06-10")
        assert len(rows) == 1
        assert rows[0]["split_ratio"] == 4.0

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_prices_returns_empty_on_auth_failure(self, started_db):
        """fetch_prices returns [] when API key is invalid (auth failure)."""
        adapter = EODHDAdapter(db=started_db, api_key="invalid-key")

        async def mock_get(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_prices("AAPL.US", "2024-01-02", "2024-01-03")
        assert rows == []

        # Verify no prices were written to the fabric
        prices = await started_db.express.list("prices", filter={"instrument": "AAPL.US"})
        assert len(prices) == 0

        await adapter.close()


class TestEODHDAdapterFundamentals:
    """fetch_fundamentals integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_fundamentals_writes_to_fabric(self, started_db):
        """fetch_fundamentals writes to the fundamentals table and returns the written row."""
        adapter = EODHDAdapter(db=started_db, api_key="test-key-123")

        mock_response = {
            "General": {
                "SharesOutstanding": 15_500_000_000,
                "Code": "AAPL.US",
                "Name": "Apple Inc.",
            },
            "Highlights": {
                "PERatio": 28.5,
                "PriceToBookRatio": 45.2,
                "DebtToEquity": 1.23,
            },
            "Financials": {
                "Income_Statement": {
                    "annual": {
                        "2023": {
                            "totalRevenue": 385_000_000_000,
                            "ebitda": 125_000_000_000,
                            "netIncome": 97_000_000_000,
                            "date": "2023-09-30",
                        },
                    }
                },
                "Balance_Sheet": {
                    "annual": {
                        "2023": {
                            "totalStockholderEquity": 290_000_000_000,
                        },
                    }
                },
                "Cash_Flow": {"annual": {}},
            },
        }

        async def mock_get(*args, **kwargs):
            return httpx.Response(200, json=mock_response)

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        result = await adapter.fetch_fundamentals("AAPL.US")

        assert result["instrument"] == "AAPL.US"
        assert result["period_end"] == "2023-09-30"
        assert result["revenue"] == 385_000_000_000
        assert result["pe_ratio"] == 28.5
        assert result["shares_outstanding"] == 15_500_000_000
        # ROE = net_income / book_value = 97000 / 290000
        assert result["roe"] == pytest.approx(0.3345, rel=1e-3)

        # Verify row was persisted
        funds = await started_db.express.list("fundamentals", filter={"instrument": "AAPL.US"})
        assert len(funds) == 1

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_fundamentals_returns_empty_on_auth_failure(self, started_db):
        """fetch_fundamentals returns {} when API key is invalid."""
        adapter = EODHDAdapter(db=started_db, api_key="invalid-key")

        async def mock_get(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        result = await adapter.fetch_fundamentals("AAPL.US")
        assert result == {}

        await adapter.close()


class TestEODHDAdapterNews:
    """fetch_news integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_news_writes_to_news_table(self, started_db):
        """fetch_news writes headline rows to the news fabric table."""
        adapter = EODHDAdapter(db=started_db, api_key="test-key-123")

        mock_response = [
            {
                "id": "news-001",
                "title": "Apple Reports Record Q4 Revenue",
                "date": "2024-11-01T14:30:00Z",
                "symbols": "AAPL.US",
            },
            {
                "id": "news-002",
                "title": "Apple Announces New Product Launch",
                "date": "2024-11-02T09:15:00Z",
                "symbols": "AAPL.US,META.US",
            },
        ]

        async def mock_get(*args, **kwargs):
            return httpx.Response(200, json=mock_response)

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_news("AAPL.US", limit=10)

        assert len(rows) == 2
        assert rows[0]["headline"] == "Apple Reports Record Q4 Revenue"
        assert rows[0]["tickers"] == ("AAPL.US",)
        assert rows[1]["tickers"] == ("AAPL.US", "META.US")

        # Verify rows were persisted
        news = await started_db.express.list("news")
        assert len(news) == 2

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_news_returns_empty_on_auth_failure(self, started_db):
        """fetch_news returns [] when API key is invalid."""
        adapter = EODHDAdapter(db=started_db, api_key="invalid-key")

        async def mock_get(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_news("AAPL.US")
        assert rows == []

        await adapter.close()


class TestEODHDAdapterCorporateActions:
    """fetch_corporate_actions integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_corporate_actions_writes_dividends_and_splits(self, started_db):
        """fetch_corporate_actions writes both dividends and splits to the fabric."""
        adapter = EODHDAdapter(db=started_db, api_key="test-key-123")

        # Simulate the adapter calling _request twice (once for div, once for splits)
        call_count = 0
        mock_responses = [
            httpx.Response(
                200,
                json=[
                    {"date": "2024-02-15", "exDate": "2024-02-16", "value": 0.24},
                    {"date": "2024-05-16", "exDate": "2024-05-17", "value": 0.25},
                ],
            ),
            httpx.Response(200, json=[]),  # no splits
        ]

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            response = (
                mock_responses[call_count]
                if call_count < len(mock_responses)
                else mock_responses[-1]
            )
            call_count += 1
            return response

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_corporate_actions("AAPL.US")

        assert len(rows) == 2
        assert all(r["action_type"] == "DIVIDEND" for r in rows)
        assert all(r["instrument"] == "AAPL.US" for r in rows)
        assert rows[0]["ratio_or_amount"] == 0.24
        assert rows[1]["ratio_or_amount"] == 0.25

        # Verify rows were persisted
        cas = await started_db.express.list("corporate_actions", filter={"instrument": "AAPL.US"})
        assert len(cas) == 2

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_corporate_actions_parses_split_ratio(self, started_db):
        """fetch_corporate_actions parses '2:1' and '2/1' split ratio formats."""
        adapter = EODHDAdapter(db=started_db, api_key="test-key-123")

        call_count = 0
        mock_responses = [
            httpx.Response(200, json=[]),  # no dividends
            httpx.Response(
                200,
                json=[
                    {"date": "2024-06-10", "splitRatio": "4:1"},
                    {"date": "2020-08-31", "splitRatio": "4/1"},
                ],
            ),
        ]

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            response = mock_responses[call_count]
            call_count += 1
            return response

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_corporate_actions("AAPL.US")

        assert len(rows) == 2
        assert all(r["action_type"] == "SPLIT" for r in rows)
        assert rows[0]["ratio_or_amount"] == 4.0
        assert rows[1]["ratio_or_amount"] == 4.0

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_corporate_actions_returns_empty_on_auth_failure(self, started_db):
        """fetch_corporate_actions returns [] when API key is invalid."""
        adapter = EODHDAdapter(db=started_db, api_key="invalid-key")

        async def mock_get(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_corporate_actions("AAPL.US")
        assert rows == []

        await adapter.close()
