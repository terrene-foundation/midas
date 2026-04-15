"""Tier 1 tests for PerplexityAdapter."""

import json
import os
import tempfile

import httpx
import pytest

from midas.fabric.adapters.perplexity import PerplexityAdapter
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_perplexity.db")
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


class TestPerplexityAdapterHealth:
    """Health check tests."""

    @pytest.mark.asyncio
    async def test_health_check_returns_unhealthy_when_no_key(self, db):
        """PerplexityAdapter reports unhealthy when PERPLEXITY_API_KEY is not set."""
        adapter = PerplexityAdapter(db=db, api_key=None)
        result = await adapter.health_check()
        assert result["source"] == "perplexity"
        assert result["healthy"] is False
        assert "not configured" in result["detail"]

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy(self, started_db):
        """PerplexityAdapter reports healthy when API key is set."""
        adapter = PerplexityAdapter(db=started_db, api_key="test-key")

        api_response = {
            "choices": [{"message": {"content": "Test response content about AAPL earnings."}}],
            "citations": ["https://example.com/article"],
        }

        async def mock_post(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"post": mock_post})()
        adapter._get_client = lambda: mock_client

        result = await adapter.health_check()
        assert result["source"] == "perplexity"
        assert result["healthy"] is True

        await adapter.close()


class TestPerplexityAdapterResearch:
    """Research method tests."""

    @pytest.mark.asyncio
    async def test_fetch_news_writes_to_news_table(self, started_db):
        """research() writes results to the news fabric table."""
        adapter = PerplexityAdapter(db=started_db, api_key="test-key")

        api_response = {
            "choices": [
                {"message": {"content": "AAPL reported strong Q4 earnings with revenue growth."}}
            ],
            "citations": ["https://example.com/apple-earnings"],
        }

        async def mock_post(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"post": mock_post})()
        adapter._get_client = lambda: mock_client

        rows = await adapter.research("AAPL Q4 earnings", tickers=["AAPL"])

        # Should return the created rows
        assert len(rows) == 1

        # Verify news table was written
        news_rows = await started_db.express.list("news", filter={})
        assert len(news_rows) >= 1

        # Verify the content
        news = news_rows[0]
        assert news["source"] == "perplexity"
        assert news["ticker"] == "AAPL"
        assert len(news["headline"]) > 0

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_news_writes_embeddings(self, started_db):
        """research() populates embedding_id field (even if empty for v1)."""
        adapter = PerplexityAdapter(db=started_db, api_key="test-key")

        api_response = {
            "choices": [{"message": {"content": "TSLA delivery numbers exceeded expectations."}}],
            "citations": ["https://example.com/tesla"],
        }

        async def mock_post(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"post": mock_post})()
        adapter._get_client = lambda: mock_client

        rows = await adapter.research("TSLA deliveries", tickers=["TSLA"])

        assert len(rows) == 1
        # embedding_id is populated (empty string for v1 since no embedder)
        assert "embedding_id" in rows[0]

        await adapter.close()

    @pytest.mark.asyncio
    async def test_health_check(self, started_db):
        """health_check returns correct structure."""
        adapter = PerplexityAdapter(db=started_db, api_key="test-key")

        api_response = {
            "choices": [{"message": {"content": "Response."}}],
            "citations": [],
        }

        async def mock_post(self, *args, **kwargs):
            return httpx.Response(200, json=api_response)

        mock_client = type("MockClient", (), {"post": mock_post})()
        adapter._get_client = lambda: mock_client

        result = await adapter.health_check()
        assert "source" in result
        assert "healthy" in result
        assert "detail" in result

        await adapter.close()
