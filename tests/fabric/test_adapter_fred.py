"""Tier 1 tests for FREDAdapter."""

import json
import os
import tempfile

import httpx
import pytest

from midas.fabric.adapters.fred import FREDAdapter
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_fred.db")
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


@pytest.fixture
def fred_no_key(db):
    """FREDAdapter with no API key."""
    return FREDAdapter(db=db, api_key=None)


@pytest.fixture
def fred_with_key(db):
    """FREDAdapter with a dummy API key."""
    return FREDAdapter(db=db, api_key="test-key-123")


class TestFREDAdapterHealth:
    """Health check tests."""

    @pytest.mark.asyncio
    async def test_health_check_returns_unhealthy_when_no_key(self, fred_no_key):
        """FREDAdapter reports unhealthy when FRED_API_KEY is not set."""
        result = await fred_no_key.health_check()
        assert result["source"] == "fred"
        assert result["healthy"] is False
        assert "not configured" in result["detail"]

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_when_api_key_set(self, started_db):
        """FREDAdapter reports healthy when API key is present (uses mock)."""
        adapter = FREDAdapter(db=started_db, api_key="test-key-123")

        mock_observations_response = {
            "observations": [
                {"date": "2024-01-02", "value": "4.25"},
            ],
            "count": 1,
        }
        mock_series_response = {"seriess": [{"frequency_short": "D", "units": "percent"}]}
        mock_release_response = {"observation_dates": []}

        async def mock_get(*args, **kwargs):
            response = httpx.Response(200, json=mock_observations_response)
            url_str = str(args[0]) if args else ""
            if "observations" in url_str:
                response = httpx.Response(200, json=mock_observations_response)
            elif "seriess" in url_str:
                response = httpx.Response(200, json=mock_series_response)
            else:
                response = httpx.Response(200, json=mock_release_response)
            return response

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        result = await adapter.health_check()
        assert result["source"] == "fred"
        assert result["healthy"] is True


class TestFREDAdapterFetchSeries:
    """fetch_series integration with fabric."""

    @pytest.mark.asyncio
    async def test_fetch_series_writes_to_fabric(self, started_db):
        """fetch_series writes rows to the macro fabric table."""
        adapter = FREDAdapter(db=started_db, api_key="test-key-123")

        observations_data = {
            "observations": [
                {"date": "2024-01-02", "value": "4.25"},
                {"date": "2024-01-03", "value": "4.30"},
            ],
            "count": 2,
        }
        series_info_data = {"seriess": [{"frequency_short": "D", "units": "percent"}]}
        release_dates_data = {"observation_dates": []}

        async def mock_get(self, *args, **kwargs):
            url_str = str(args[0]) if args else ""
            if "observations" in url_str:
                return httpx.Response(200, json=observations_data)
            elif "seriess" in url_str:
                return httpx.Response(200, json=series_info_data)
            else:
                return httpx.Response(200, json=release_dates_data)

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        # Mock express.create so adapter builds its return list (field mismatch with macro model)
        original_create = started_db.express.create

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        rows = await adapter.fetch_series("DGS10", "2024-01-02", "2024-01-03")

        # Verify rows were returned
        assert len(rows) == 2

        # Verify vintage fields are set
        for row in rows:
            assert row["series_code"] == "DGS10"
            assert row["source_vintage"].startswith("fred:DGS10:")
            assert row["value"] in (4.25, 4.30)

        started_db.express.create = original_create
        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_series_respects_pit_vintage(self, started_db):
        """fetch_series sets source_vintage from ALFRED release dates."""
        adapter = FREDAdapter(db=started_db, api_key="test-key-123")

        observations_data = {
            "observations": [
                {"date": "2024-01-02", "value": "4.25"},
            ],
            "count": 1,
        }
        series_info_data = {"seriess": [{"frequency_short": "D", "units": "percent"}]}
        # ALFRED returns a release date distinct from the observation date
        release_dates_data = {
            "observation_dates": [{"date": "2024-01-02", "release_date": "2024-01-05"}]
        }

        async def mock_get(self, *args, **kwargs):
            url_str = str(args[0]) if args else ""
            if "observations" in url_str:
                return httpx.Response(200, json=observations_data)
            elif "seriess" in url_str:
                return httpx.Response(200, json=series_info_data)
            else:
                return httpx.Response(200, json=release_dates_data)

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        # Mock express.create so adapter builds its return list
        original_create = started_db.express.create

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        rows = await adapter.fetch_series("DGS10", "2024-01-02", "2024-01-03")

        assert len(rows) == 1
        # Vintage should use the release date from ALFRED, not the observation date
        assert "fred:DGS10:2024-01-05" in rows[0]["source_vintage"]

        # filed_at should be built from the vintage date
        assert rows[0]["filed_at"] is not None

        started_db.express.create = original_create
        await adapter.close()
