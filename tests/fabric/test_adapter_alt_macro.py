"""Tier 1 tests for AltMacro adapters (OECD, IMF, Google Trends, Truflation)."""

import json
import os
import tempfile

import httpx
import pytest

from midas.fabric.adapters.alt_macro import (
    GoogleTrendsAdapter,
    IMFAdapter,
    OECDAdapter,
    TruflationAdapter,
)
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_altmacro.db")
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


class TestOECDAdapter:
    """Tests for OECDAdapter."""

    @pytest.mark.asyncio
    async def test_ingest_oecd_cli_writes_to_macro(self, started_db):
        """OECDAdapter.fetch_indicator() writes rows to the macro fabric table."""
        adapter = OECDAdapter(db=started_db)

        api_response = {
            "dataSets": [
                {
                    "series": {
                        "0.0.M": {
                            "observations": {
                                "0": [100.5],
                                "1": [101.2],
                            }
                        }
                    }
                }
            ]
        }

        async def mock_get(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        # Mock express.create so the adapter can build its created_rows list
        original_create = started_db.express.create
        created_records = []

        async def mock_create(table, row):
            created_records.append(row)
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        rows = await adapter.fetch_indicator("MEI_CLI", "2024-01", "2024-02")

        # Adapter returns its created_rows list
        assert len(rows) == 2

        # Verify macro rows were passed to express.create (ignore audit_log calls)
        macro_records = [r for r in created_records if "series_name" in r]
        assert len(macro_records) == 2
        for row in macro_records:
            assert row["series_name"] == "OECD:MEI_CLI"
            assert row["value"] in (100.5, 101.2)
            assert row["vintage"] != ""
            assert row["source"] == "oecd"

        started_db.express.create = original_create
        await adapter.close()


class TestIMFAdapter:
    """Tests for IMFAdapter."""

    @pytest.mark.asyncio
    async def test_ingest_imf_weo_writes_to_macro(self, started_db):
        """IMFAdapter.fetch_series() writes rows to the macro fabric table."""
        adapter = IMFAdapter(db=started_db)

        api_response = {
            "CompactData": {
                "DataSet": {
                    "Series": {
                        "@frequency": "A",
                        "Obs": [
                            {"@timePeriod": "2023", "@OBS_VALUE": "2.5"},
                            {"@timePeriod": "2024", "@OBS_VALUE": "2.7"},
                        ],
                    }
                }
            }
        }

        async def mock_get(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        original_create = started_db.express.create
        created_records = []

        async def mock_create(table, row):
            created_records.append(row)
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        rows = await adapter.fetch_series("NGDP_RPCH", "US", "2023", "2024")

        assert len(rows) == 2

        # Filter out audit_log calls
        macro_records = [r for r in created_records if "series_name" in r]
        assert len(macro_records) == 2
        for row in macro_records:
            assert row["series_name"] == "IMF:NGDP_RPCH:US"
            assert row["value"] in (2.5, 2.7)
            assert row["vintage"] != ""
            assert row["source"] == "imf"

        started_db.express.create = original_create
        await adapter.close()


class TestGoogleTrendsAdapter:
    """Tests for GoogleTrendsAdapter."""

    @pytest.mark.asyncio
    async def test_ingest_google_trends_completes_without_raise(self, started_db):
        """GoogleTrendsAdapter.fetch_trend() completes without raising."""
        adapter = GoogleTrendsAdapter(db=started_db)

        async def mock_get(self, *args, **kwargs):
            return httpx.Response(200, text="<rss/>")

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        # Should not raise even though the HTTP response isn't meaningful for v1
        rows = await adapter.fetch_trend("inflation", "2024-01-01", "2024-12-31")
        assert isinstance(rows, list)

        await adapter.close()

    @pytest.mark.asyncio
    async def test_ingest_google_trends_writes_audit_entry(self, started_db):
        """GoogleTrendsAdapter writes an audit entry on fetch_trend."""
        adapter = GoogleTrendsAdapter(db=started_db)

        async def mock_get(self, *args, **kwargs):
            return httpx.Response(200, text="<rss/>")

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        # Track _write_audit calls
        write_audit_calls = []

        original_write_audit = adapter._write_audit

        async def tracking_write_audit(**kwargs):
            write_audit_calls.append(kwargs)

        adapter._write_audit = tracking_write_audit

        await adapter.fetch_trend("recession", "2024-01-01", "2024-12-31")

        # Verify _write_audit was called
        assert len(write_audit_calls) >= 1
        assert write_audit_calls[0]["operation"] == "fetch_trend"

        adapter._write_audit = original_write_audit
        await adapter.close()


class TestTruflationAdapter:
    """Tests for TruflationAdapter."""

    @pytest.mark.asyncio
    async def test_ingest_truflation_writes_to_macro(self, started_db):
        """TruflationAdapter.fetch_series() writes rows to the macro fabric table."""
        adapter = TruflationAdapter(db=started_db)

        api_response = {
            "data": [
                {"date": "2024-01-01", "value": 3.2},
                {"date": "2024-02-01", "value": 3.1},
            ]
        }

        async def mock_get(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        rows = await adapter.fetch_series("cpi", "2024-01-01", "2024-02-01")

        # Mock express.create to avoid field-name mismatch (adapter uses `date` vs model `period_end`)
        original_create = started_db.express.create

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        rows = await adapter.fetch_series("cpi", "2024-01-01", "2024-02-01")

        assert len(rows) == 2

        for row in rows:
            assert row["series_name"] == "truflation:cpi"
            assert row["value"] in (3.2, 3.1)
            assert row["vintage"] != ""
            assert row["source"] == "truflation"

        started_db.express.create = original_create
        await adapter.close()
