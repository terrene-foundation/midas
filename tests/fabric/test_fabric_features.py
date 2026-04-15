"""Tier 1 tests for FeatureStore (src/midas/fabric/features.py)."""

from __future__ import annotations

import os
import tempfile
from datetime import date

import pytest

from midas.fabric.engine import create_fabric, reset_fabric


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def fs():
    """Create a FeatureStore backed by a temp-file SQLite DataFlow with models registered."""
    from midas.fabric.features import FeatureStore

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_features.db")
    db_url = f"sqlite:///{db_path}"

    db = create_fabric(database_url=db_url, auto_migrate=True)
    await db.start()
    store = FeatureStore(db=db)

    yield store

    await store.close()
    reset_fabric()

    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(db_path + suffix)
        except OSError:
            pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# FeatureStore.write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_creates_feature_row(fs):
    """write() creates a row and returns it with an id."""
    result = await fs.write(
        instrument="SPY",
        feature_name="momentum_20d",
        value=0.032,
        as_of_date="2024-01-15",
        version="feature_v1",
    )
    assert result is not None
    # DataFlow returns a dict with 'id' or 'rows_affected'
    assert result.get("id") is not None or result.get("rows_affected", 0) >= 1


@pytest.mark.asyncio
async def test_read_returns_none_for_missing(fs):
    """read() returns None when no matching feature exists."""
    result = await fs.read(
        instrument="NONEXISTENT",
        feature_name="momentum_20d",
        as_of_date="2024-01-15",
        version="feature_v1",
    )
    assert result is None


@pytest.mark.asyncio
async def test_read_returns_written_feature(fs):
    """write() then read() returns the same feature value.

    Uses today as as_of_date so the PIT check (filed_at <= as_of_date) passes.
    """
    today = date.today().isoformat()
    await fs.write(
        instrument="SPY",
        feature_name="momentum_20d",
        value=0.032,
        as_of_date=today,
        version="feature_v1",
    )

    row = await fs.read(
        instrument="SPY",
        feature_name="momentum_20d",
        as_of_date=today,
        version="feature_v1",
    )

    assert row is not None
    assert row["instrument"] == "SPY"
    assert row["feature_name"] == "momentum_20d"
    assert row["value"] == 0.032
    assert row["feature_version"] == "feature_v1"


@pytest.mark.asyncio
async def test_read_enforces_pit_discipline(fs):
    """write() with a future as_of_date raises ValueError."""
    with pytest.raises(ValueError, match="future"):
        await fs.write(
            instrument="SPY",
            feature_name="momentum_20d",
            value=0.032,
            as_of_date="2099-12-31",
            version="feature_v1",
        )


@pytest.mark.asyncio
async def test_version_bump_creates_new_version(fs):
    """Writing the same instrument/feature with a new version creates a new row."""
    today = date.today().isoformat()
    await fs.write(
        instrument="SPY",
        feature_name="momentum_20d",
        value=0.032,
        as_of_date=today,
        version="feature_v1",
    )
    await fs.write(
        instrument="SPY",
        feature_name="momentum_20d",
        value=0.028,
        as_of_date=today,
        version="feature_v2",
    )

    v1_row = await fs.read(
        instrument="SPY",
        feature_name="momentum_20d",
        as_of_date=today,
        version="feature_v1",
    )
    v2_row = await fs.read(
        instrument="SPY",
        feature_name="momentum_20d",
        as_of_date=today,
        version="feature_v2",
    )

    assert v1_row is not None
    assert v2_row is not None
    assert v1_row["value"] == 0.032
    assert v2_row["value"] == 0.028


@pytest.mark.asyncio
async def test_retire_version_marks_retired(fs):
    """retire_version() updates rows to status='retired' but they remain readable."""
    today = date.today().isoformat()
    await fs.write(
        instrument="SPY",
        feature_name="momentum_20d",
        value=0.032,
        as_of_date=today,
        version="feature_v1",
    )

    updated = await fs.retire_version("feature_v1")
    assert updated >= 1

    # Read still works — retire is soft, not a delete
    row = await fs.read(
        instrument="SPY",
        feature_name="momentum_20d",
        as_of_date=today,
        version="feature_v1",
    )
    assert row is not None
    assert row["status"] == "retired"


# ---------------------------------------------------------------------------
# FeatureStore.read_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_batch_returns_all_instruments(fs):
    """read_batch() returns a dict keyed by instrument with all requested features."""
    today = date.today().isoformat()
    for ticker in ("SPY", "QQQ", "IWM"):
        await fs.write(
            instrument=ticker,
            feature_name="momentum_20d",
            value=0.05,
            as_of_date=today,
            version="feature_v1",
        )

    result = await fs.read_batch(
        instruments=["SPY", "QQQ", "IWM"],
        feature_names=["momentum_20d"],
        as_of_date=today,
        version="feature_v1",
    )

    assert "SPY" in result
    assert "QQQ" in result
    assert "IWM" in result
    assert "momentum_20d" in result["SPY"]


# ---------------------------------------------------------------------------
# FeatureStore.list_versions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_versions_returns_sorted(fs):
    """list_versions() returns all versions sorted alphabetically (v1, v2, v10)."""
    today = date.today().isoformat()
    for v in ("feature_v1", "feature_v3", "feature_v10", "feature_v2"):
        await fs.write(
            instrument="SPY",
            feature_name="momentum_20d",
            value=0.03,
            as_of_date=today,
            version=v,
        )

    versions = await fs.list_versions("momentum_20d")

    assert versions == sorted(versions)
    assert "feature_v1" in versions
    assert "feature_v2" in versions
    assert "feature_v3" in versions
    assert "feature_v10" in versions
