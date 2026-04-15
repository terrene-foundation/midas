"""Tier 1 tests for SECEdgarAdapter."""

import json
import os
import tempfile

import httpx
import pytest

from midas.fabric.adapters.sec_edgar import SECEdgarAdapter
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_sec.db")
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


class TestSECEdgarAdapter:
    """Tests for SECEdgarAdapter."""

    @pytest.mark.asyncio
    async def test_fetch_filings_writes_to_filings_table(self, started_db):
        """fetch_filings() writes rows to the filings fabric table."""
        adapter = SECEdgarAdapter(db=started_db)

        api_response = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "file_num": "0001234567-24-001",
                            "file_date": "2024-01-15",
                            "display_names": ["Apple Inc."],
                        }
                    },
                    {
                        "_source": {
                            "file_num": "0001234567-24-002",
                            "file_date": "2024-02-10",
                            "display_names": ["Apple Inc."],
                        }
                    },
                ]
            }
        }

        async def mock_get(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        rows = await adapter.fetch_filings("AAPL", "10-K", "2024-01-01", "2024-12-31")

        assert len(rows) == 2

        # Verify filings table was written
        filings_rows = await started_db.express.list("filings", filter={"ticker": "AAPL"})
        assert len(filings_rows) >= 2

        # Verify fields
        assert filings_rows[0]["ticker"] == "AAPL"
        assert filings_rows[0]["filing_type"] == "10-K"
        assert filings_rows[0]["source"] == "sec_edgar"

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_10k_indexes_embedding(self, started_db):
        """fetch_filings() populates embedding_id field (empty for v1)."""
        adapter = SECEdgarAdapter(db=started_db)

        api_response = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "file_num": "0001234567-24-001",
                            "file_date": "2024-01-15",
                            "display_names": ["Apple Inc."],
                        }
                    },
                ]
            }
        }

        async def mock_get(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        rows = await adapter.fetch_filings("AAPL", "10-K", "2024-01-01", "2024-12-31")

        assert len(rows) == 1
        # embedding_id is set (empty string for v1)
        assert "embedding_id" in rows[0]
        assert rows[0]["embedding_id"] == ""

        await adapter.close()

    @pytest.mark.asyncio
    async def test_health_check(self, started_db):
        """health_check returns correct structure."""
        adapter = SECEdgarAdapter(db=started_db)

        api_response = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "file_num": "0001234567-24-001",
                            "file_date": "2024-01-15",
                            "display_names": ["Apple Inc."],
                        }
                    },
                ]
            }
        }

        async def mock_get(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"get": mock_get})()
        adapter._get_client = lambda: mock_client

        result = await adapter.health_check()
        assert "source" in result
        assert "healthy" in result
        assert "detail" in result

        await adapter.close()
