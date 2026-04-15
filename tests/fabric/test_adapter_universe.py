"""Tier 1 tests for UniverseAdapter."""

import json
import os
import tempfile

import pytest

from midas.fabric.adapters.universe import UniverseAdapter
from midas.fabric.engine import create_fabric, reset_fabric


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
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
    """Start the database for async adapter tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


class TestUniverseAdapter:
    """Tests for UniverseAdapter."""

    @pytest.mark.asyncio
    async def test_fetch_membership_writes_universe_changelog(self, started_db):
        """fetch_constituents() writes rows to the universe_changelog fabric table."""
        adapter = UniverseAdapter(db=started_db)

        tickers = await adapter.fetch_constituents(index_name="sp500", as_of_date="2024-06-01")

        # Should return the tickers
        assert len(tickers) > 0
        assert "AAPL" in tickers
        assert "MSFT" in tickers

        # Verify changelog table was written
        changelog_rows = await started_db.express.list(
            "universe_changelog",
            filter={"action": "member"},
        )
        assert len(changelog_rows) >= 1

        # Verify structure
        row = changelog_rows[0]
        assert "ticker" in row
        assert row["action"] == "member"
        assert row["effective_date"] == "2024-06-01"

    @pytest.mark.asyncio
    async def test_fetch_membership_pit_discipline(self, started_db):
        """fetch_constituents() uses as_of_date for effective_date (PIT discipline)."""
        adapter = UniverseAdapter(db=started_db)

        # Fetch with a specific date
        as_of = "2024-01-15"
        await adapter.fetch_constituents(index_name="sp500", as_of_date=as_of)

        changelog_rows = await started_db.express.list(
            "universe_changelog",
            filter={"action": "member"},
        )

        # All entries should use the requested as_of_date
        for row in changelog_rows:
            assert row["effective_date"] == as_of

    @pytest.mark.asyncio
    async def test_get_membership_filters_by_action(self, started_db):
        """get_membership() retrieves only 'member' action entries."""
        adapter = UniverseAdapter(db=started_db)

        # Write a mix of member and removed entries directly
        await started_db.express.create(
            "universe_changelog",
            {
                "ticker": "XYZ",
                "action": "member",
                "reason": "sp500_constituent_2024",
                "effective_date": "2024-06-01",
            },
        )
        await started_db.express.create(
            "universe_changelog",
            {
                "ticker": "XYZ",
                "action": "removed",
                "reason": "delisted",
                "effective_date": "2024-07-01",
            },
        )

        # get_membership should only return member tickers
        membership = await adapter.get_membership("2024-07-01", started_db)

        assert "XYZ" in membership

    @pytest.mark.asyncio
    async def test_health_check(self, db):
        """health_check returns correct structure for UniverseAdapter."""
        adapter = UniverseAdapter(db=db)
        result = await adapter.health_check()

        assert result["source"] == "universe"
        assert result["healthy"] is True
        assert "detail" in result
