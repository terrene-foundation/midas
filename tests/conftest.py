"""
Test fixtures for Midas API tests.

Uses file-based SQLite (not :memory:) for test isolation because
the TestClient processes requests in thread-pool threads, and SQLite
:memory: connections are not shareable across threads.
"""

import os
import tempfile

import pytest
from starlette.testclient import TestClient

from midas.api.app import create_app
from midas.fabric.engine import reset_fabric


# Use a temp file for test DB — avoids SQLite :memory: threading issues
_test_db_file = None


def _get_test_db_url():
    """Get a file URL for the test SQLite database."""
    global _test_db_file
    if _test_db_file is None:
        fd, _test_db_file = tempfile.mkstemp(suffix=".db")
        os.close(fd)
    return f"sqlite:///{_test_db_file}"


@pytest.fixture(scope="function")
def app():
    """Create a fresh FastAPI app instance for each test."""
    # Reset any stale fabric singletons to ensure clean state
    reset_fabric()

    # Tell _get_db() to use test_mode=False so it uses the file-based SQLite
    # (from DATABASE_URL) instead of :memory: SQLite (which DataFlow auto-selects
    # in pytest via PYTEST_CURRENT_TEST, breaking the pool in TestClient threads).
    old_midas_test_db = os.environ.get("MIDAS_TEST_DB", "")
    os.environ["MIDAS_TEST_DB"] = "true"

    # Override DATABASE_URL for this process so get_fabric() uses test file
    old_db_url = os.environ.get("DATABASE_URL", "")
    os.environ["DATABASE_URL"] = _get_test_db_url()

    # Patch the module-level DATABASE_URL so create_fabric() uses the test URL
    import midas.config as config_module

    old_url = getattr(config_module, "DATABASE_URL", "")
    config_module.DATABASE_URL = _get_test_db_url()

    try:
        app = create_app()
        yield app
    finally:
        # Restore
        if old_midas_test_db:
            os.environ["MIDAS_TEST_DB"] = old_midas_test_db
        else:
            os.environ.pop("MIDAS_TEST_DB", None)
        config_module.DATABASE_URL = old_url
        if old_db_url:
            os.environ["DATABASE_URL"] = old_db_url
        # Reset singletons so next test gets fresh state
        reset_fabric()


@pytest.fixture
def client(app):
    """TestClient wired to the app."""
    with TestClient(app) as c:
        yield c
