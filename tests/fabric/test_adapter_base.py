"""Tier 1 tests for BaseAdapter retry, rate-limit, and audit infrastructure."""

import asyncio
import os
import tempfile

import pytest

from midas.fabric.adapters.base import (
    AdapterError,
    AuthenticationError,
    BaseAdapter,
    RateLimitExceeded,
)
from midas.fabric.engine import create_fabric, reset_fabric


class _ConcreteAdapter(BaseAdapter):
    """Concrete implementation of BaseAdapter for testing."""

    SOURCE_NAME = "test_adapter"

    async def health_check(self):
        return {"source": self.SOURCE_NAME, "healthy": True, "detail": "ok"}


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_base.db")
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


class TestBaseAdapterRetry:
    """Retry logic tests."""

    @pytest.mark.asyncio
    async def test_retry_retries_on_failure(self, started_db):
        """_retry() calls the function multiple times until it succeeds."""
        adapter = _ConcreteAdapter(db=started_db, max_retries=3, base_delay_s=0.01)

        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return "success"

        result = await adapter._retry("flaky_op", flaky_operation)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_raises_after_exhaustion(self, started_db):
        """_retry() raises AdapterError after exhausting all retries."""
        adapter = _ConcreteAdapter(db=started_db, max_retries=3, base_delay_s=0.01)

        async def always_fails():
            raise RuntimeError("permanent error")

        with pytest.raises(AdapterError) as exc_info:
            await adapter._retry("always_fails", always_fails)

        assert "exhausted" in str(exc_info.value).lower()
        assert "permanent error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retry_does_not_retry_auth_errors(self, started_db):
        """_retry() propagates AuthenticationError immediately without retrying."""
        adapter = _ConcreteAdapter(db=started_db, max_retries=3, base_delay_s=0.01)

        call_count = 0

        async def auth_fails():
            nonlocal call_count
            call_count += 1
            raise AuthenticationError("test_adapter", "op", status_code=401)

        with pytest.raises(AuthenticationError):
            await adapter._retry("auth_op", auth_fails)

        # Should have been called exactly once — no retries for auth errors
        assert call_count == 1


class TestBaseAdapterRateLimit:
    """Rate-limit enforcement tests."""

    @pytest.mark.asyncio
    async def test_rate_limit_enforces_min_interval(self, started_db):
        """_enforce_rate_limit() sleeps when calls are too frequent."""
        adapter = _ConcreteAdapter(db=started_db, min_call_interval_s=0.1)

        t0 = asyncio.get_event_loop().time()

        await adapter._enforce_rate_limit()
        await adapter._enforce_rate_limit()
        await adapter._enforce_rate_limit()

        elapsed = asyncio.get_event_loop().time() - t0

        # Three calls at 100ms interval minimum → at least 200ms elapsed
        assert elapsed >= 0.18, f"Expected >= 0.18s, got {elapsed:.3f}s (rate limit not enforced)"


class TestBaseAdapterAudit:
    """Audit logging tests."""

    @pytest.mark.asyncio
    async def test_write_audit_creates_audit_row(self, started_db):
        """_write_audit() writes a row to the audit_log fabric table."""
        adapter = _ConcreteAdapter(db=started_db)

        await adapter._write_audit(
            operation="test_op",
            success=True,
            detail="test detail",
            rows_written=5,
        )

        audit_rows = await started_db.express.list("audit_log", filter={})
        assert len(audit_rows) >= 1

        # Verify the audit entry content
        row = audit_rows[0]
        assert row["rule_name"] == "test_op"
        assert row["agent"] == "adapter:test_adapter"
        assert row["action"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_write_audit_does_not_raise_on_failure(self, started_db):
        """_write_audit() must not raise even when the audit write fails."""
        adapter = _ConcreteAdapter(db=started_db)

        # Pass a closed/broken DB to cause the write to fail
        bad_adapter = _ConcreteAdapter(db=None)  # no DB
        bad_adapter._get_db = lambda: None  # type: ignore

        # Should not raise — audit failures are swallowed
        await bad_adapter._write_audit(
            operation="failing_op",
            success=False,
            detail="this audit will fail to write",
        )
