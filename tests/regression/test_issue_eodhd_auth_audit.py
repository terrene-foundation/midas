"""Regression: EODHD auth failure must produce a FAILURE audit row.

Verifies that a 401 on any adapter operation writes an audit_log row
with action="FAILURE" and rule_name matching the operation, using a
real SQLite DataFlow instance.

Ref: specs/03-universe-and-data.md §2.1 — audit contract on auth failure.
"""

import os
import tempfile

import httpx
import pytest

from midas.fabric.adapters.eodhd import EODHDAdapter
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for regression tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_eodhd_auth.db")
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
class TestEODHDAuthAuditRegression:
    """Auth failure on any adapter operation must produce a FAILURE audit row."""

    @pytest.mark.asyncio
    async def test_fetch_prices_auth_failure_writes_failure_audit(self, started_db):
        """401 on fetch_prices writes audit_log row with action=FAILURE and rule_name."""
        adapter = EODHDAdapter(db=started_db, api_key="invalid-key")

        async def mock_get(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_prices("AAPL.US", "2024-01-02", "2024-01-03")
        assert rows == []

        # Verify audit_log has a FAILURE row for fetch_prices
        audit_rows = await started_db.express.list("audit_log")
        failure_audits = [
            r
            for r in audit_rows
            if r.get("rule_name") == "fetch_prices" and r.get("action") == "FAILURE"
        ]
        assert len(failure_audits) >= 1, (
            f"Expected at least 1 FAILURE audit row for fetch_prices, "
            f"found {len(failure_audits)} among {len(audit_rows)} total audit rows"
        )

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_fundamentals_auth_failure_writes_failure_audit(self, started_db):
        """401 on fetch_fundamentals writes audit_log row with action=FAILURE."""
        adapter = EODHDAdapter(db=started_db, api_key="invalid-key")

        async def mock_get(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        result = await adapter.fetch_fundamentals("AAPL.US")
        assert result == {}

        audit_rows = await started_db.express.list("audit_log")
        failure_audits = [
            r
            for r in audit_rows
            if r.get("rule_name") == "fetch_fundamentals" and r.get("action") == "FAILURE"
        ]
        assert len(failure_audits) >= 1, (
            f"Expected at least 1 FAILURE audit row for fetch_fundamentals, "
            f"found {len(failure_audits)} among {len(audit_rows)} total audit rows"
        )

        await adapter.close()

    @pytest.mark.asyncio
    async def test_fetch_news_auth_failure_writes_failure_audit(self, started_db):
        """401 on fetch_news writes audit_log row with action=FAILURE."""
        adapter = EODHDAdapter(db=started_db, api_key="invalid-key")

        async def mock_get(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_news("AAPL.US")
        assert rows == []

        audit_rows = await started_db.express.list("audit_log")
        failure_audits = [
            r
            for r in audit_rows
            if r.get("rule_name") == "fetch_news" and r.get("action") == "FAILURE"
        ]
        assert len(failure_audits) >= 1, (
            f"Expected at least 1 FAILURE audit row for fetch_news, "
            f"found {len(failure_audits)} among {len(audit_rows)} total audit rows"
        )

        await adapter.close()

    @pytest.mark.asyncio
    async def test_corporate_actions_auth_failure_writes_failure_audit(self, started_db):
        """401 on fetch_corporate_actions writes audit_log row with action=FAILURE."""
        adapter = EODHDAdapter(db=started_db, api_key="invalid-key")

        async def mock_get(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})

        adapter._get_client = lambda: type("MockClient", (), {"get": mock_get})()

        rows = await adapter.fetch_corporate_actions("AAPL.US")
        assert rows == []

        audit_rows = await started_db.express.list("audit_log")
        # Corporate actions operation name includes the sub-operation
        failure_audits = [
            r
            for r in audit_rows
            if r.get("action") == "FAILURE" and "corporate_actions" in (r.get("rule_name") or "")
        ]
        assert len(failure_audits) >= 1, (
            f"Expected at least 1 FAILURE audit row for corporate_actions, "
            f"found {len(failure_audits)} among {len(audit_rows)} total audit rows"
        )

        await adapter.close()
