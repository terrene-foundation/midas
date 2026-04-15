"""Tier 1 tests for EmbeddingStore (src/midas/fabric/embeddings.py)."""

from __future__ import annotations

import os
import tempfile

import pytest

from midas.fabric.engine import create_fabric, reset_fabric


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def es():
    """Create an EmbeddingStore backed by a temp-file SQLite DataFlow with models registered."""
    from midas.fabric.embeddings import EmbeddingStore

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_embeddings.db")
    db_url = f"sqlite:///{db_path}"

    db = create_fabric(database_url=db_url, auto_migrate=True)
    await db.start()
    store = EmbeddingStore(db=db)

    yield store

    try:
        await store._db.close_async()
    except Exception:
        pass
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
# EmbeddingStore.store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_creates_embedding_row(es):
    """store() writes an embedding row and returns it."""
    result = await es.store(
        source_type="filing",
        source_id="f-123",
        content="Apple reported earnings of $2.10 per share.",
        embedding=[0.1, 0.2, 0.3],
        model_name="text-embedding-3-small",
    )

    assert result is not None
    assert result.get("id") is not None or result.get("rows_affected", 0) >= 1


# ---------------------------------------------------------------------------
# EmbeddingStore.search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_top_k_by_similarity(es):
    """store 3 vectors; search returns them ordered by cosine similarity descending."""
    # Vector for "earnings" — very close to itself
    earnings_vec = [1.0, 0.0, 0.0]
    # Vector for "weather" — orthogonal to earnings
    weather_vec = [0.0, 1.0, 0.0]
    # Vector for "opposite" — opposite of earnings
    opposite_vec = [-1.0, 0.0, 0.0]

    await es.store(
        source_type="news",
        source_id="n-earnings",
        content="AAPL earnings report",
        embedding=earnings_vec,
        model_name="test",
    )
    await es.store(
        source_type="news",
        source_id="n-weather",
        content="Weather forecast sunny",
        embedding=weather_vec,
        model_name="test",
    )
    await es.store(
        source_type="news",
        source_id="n-opposite",
        content="AAPL losses report",
        embedding=opposite_vec,
        model_name="test",
    )

    results = await es.search(
        query_embedding=[0.9, 0.0, 0.0],  # almost same as earnings
        top_k=3,
    )

    assert len(results) == 3
    # Top result should be earnings (highest similarity)
    assert results[0]["source_id"] == "n-earnings"
    assert results[0]["similarity"] == pytest.approx(1.0, abs=1e-6)
    # Second result should be opposite (similarity = -1.0), sorted last
    assert results[-1]["source_id"] == "n-opposite"
    assert results[-1]["similarity"] == pytest.approx(-1.0, abs=1e-6)


@pytest.mark.asyncio
async def test_search_filters_by_source_type(es):
    """search(source_type=...) returns only rows matching that source_type."""
    await es.store(
        source_type="filing",
        source_id="f-1",
        content="Filing content",
        embedding=[1.0, 0.0],
        model_name="test",
    )
    await es.store(
        source_type="news",
        source_id="n-1",
        content="News content",
        embedding=[1.0, 0.0],
        model_name="test",
    )

    filing_results = await es.search(
        query_embedding=[1.0, 0.0],
        top_k=10,
        source_type="filing",
    )

    assert all(r["source_type"] == "filing" for r in filing_results)
    assert len(filing_results) == 1
    assert filing_results[0]["source_id"] == "f-1"


# ---------------------------------------------------------------------------
# EmbeddingStore._cosine_similarity
# ---------------------------------------------------------------------------


def test_cosine_similarity_exactly_equal_returns_1():
    """Cosine similarity of identical unit vectors is exactly 1."""
    from midas.fabric.embeddings import EmbeddingStore

    sim = EmbeddingStore._cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert sim == pytest.approx(1.0, abs=1e-9)


def test_cosine_similarity_opposite_returns_minus_1():
    """Cosine similarity of opposite-direction vectors is -1."""
    from midas.fabric.embeddings import EmbeddingStore

    sim = EmbeddingStore._cosine_similarity([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0])
    assert sim == pytest.approx(-1.0, abs=1e-9)


def test_cosine_similarity_orthogonal_returns_0():
    """Cosine similarity of orthogonal vectors is exactly 0."""
    from midas.fabric.embeddings import EmbeddingStore

    sim = EmbeddingStore._cosine_similarity([1.0, 0.0, 0.0], [0.0, 1.0, 0.0])
    assert sim == pytest.approx(0.0, abs=1e-9)


def test_cosine_similarity_zero_vector_returns_0():
    """Cosine similarity involving a zero vector is 0 (no magnitude)."""
    from midas.fabric.embeddings import EmbeddingStore

    assert EmbeddingStore._cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
    assert EmbeddingStore._cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0


def test_cosine_similarity_known_values():
    """Verify against a known cosine similarity value."""
    from midas.fabric.embeddings import EmbeddingStore

    # cos(45deg) = sqrt(2)/2 ≈ 0.7071
    a = [1.0, 1.0]
    b = [1.0, 0.0]
    sim = EmbeddingStore._cosine_similarity(a, b)
    assert sim == pytest.approx(0.7071, abs=1e-4)
