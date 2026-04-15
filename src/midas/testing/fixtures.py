"""
Shared test fixtures for all Midas test tiers.

Provides DataFlow instances, fabric tables, and test data helpers.
Uses temp file SQLite to avoid in-memory migration hangs.

Ref: rules/testing.md § Tier 1-3
"""

import os
import tempfile
from typing import Any

from dataflow import DataFlow

from midas.fabric.engine import create_fabric, reset_fabric


class FabricTestFixture:
    """Manages a test DataFlow instance with all fabric tables.

    Uses a temp file SQLite database that is cleaned up on teardown.
    """

    def __init__(self) -> None:
        self._tmpdir: str = ""
        self._db_path: str = ""
        self.db: DataFlow | None = None

    async def setup(self) -> DataFlow:
        """Create and initialize the test database.

        Returns
        -------
        DataFlow
            Initialized database with all fabric tables.
        """
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test_fabric.db")
        db_url = f"sqlite:///{self._db_path}"
        self.db = create_fabric(database_url=db_url, auto_migrate=True)
        await self.db.start()
        return self.db

    async def teardown(self) -> None:
        """Clean up the test database."""
        if self.db is not None:
            try:
                await self.db.close_async()
            except Exception:
                pass
            self.db = None

        reset_fabric()

        # Remove SQLite files
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self._db_path + suffix)
            except OSError:
                pass

        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    async def create_row(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        """Helper to create a row and return it."""
        assert self.db is not None, "Call setup() first"
        await self.db.express.create(table, data)
        rows = await self.db.express.list(table, filter=data)
        return rows[-1] if rows else {}

    async def create_rows(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Helper to create multiple rows."""
        results = []
        for row in rows:
            result = await self.create_row(table, row)
            results.append(result)
        return results


async def create_test_fabric() -> tuple[DataFlow, FabricTestFixture]:
    """Create a test fabric instance with all tables.

    Usage::

        db, fixture = await create_test_fabric()
        try:
            await db.express.create("prices", {...})
        finally:
            await fixture.teardown()

    Returns
    -------
    tuple[DataFlow, FabricTestFixture]
        The database and its fixture for cleanup.
    """
    fixture = FabricTestFixture()
    db = await fixture.setup()
    return db, fixture
