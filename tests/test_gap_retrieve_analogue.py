"""Tests for Gap 1: retrieve_analogue tool upgrade.

Verifies the spec-compliant retrieve_analogue that accepts a z_t vector
and uses cosine similarity to find historical analogues.
"""

import json
from unittest.mock import AsyncMock

import pytest

from midas.agents.tools import DebateTools


def _make_db_with_decisions(decisions: list[dict]) -> AsyncMock:
    """Create a mock DB that returns the given decisions."""
    db = AsyncMock()
    db.express = AsyncMock()
    db.express.list = AsyncMock(return_value=decisions)
    return db


def _z_t(dim: int = 4, fill: float = 0.5) -> list[float]:
    """Create a simple z_t vector for testing."""
    return [fill] * dim


class TestRetrieveAnalogueSpecCompliance:
    """Tests for the z_t-based retrieve_analogue tool."""

    @pytest.mark.asyncio
    async def test_returns_list(self):
        """retrieve_analogue returns a list."""
        db = _make_db_with_decisions([])
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(_z_t())
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_z_t_returns_empty(self):
        """Empty z_t vector returns empty list."""
        db = _make_db_with_decisions([])
        tools = DebateTools(db)
        result = await tools.retrieve_analogue([])
        assert result == []

    @pytest.mark.asyncio
    async def test_finds_similar_decision(self):
        """Finds a decision with similar z_t vector."""
        query_z = [0.1, 0.2, 0.3, 0.4]
        stored_z = [0.11, 0.21, 0.31, 0.41]  # very similar

        decisions = [
            {
                "id": "dec-1",
                "action": "reduce_equity",
                "outcome": "avoided 3% drawdown",
                "instruments": "SPY,TLT",
                "brief_summary": "Reduced equity on tail risk signal.",
                "decided_at": "2025-06-15T10:00:00Z",
                "z_t_snapshot": json.dumps(stored_z),
            },
        ]
        db = _make_db_with_decisions(decisions)
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(query_z, similarity_threshold=0.5)

        assert len(result) == 1
        assert result[0]["decision_id"] == "dec-1"
        assert result[0]["similarity"] >= 0.5

    @pytest.mark.asyncio
    async def test_filters_below_threshold(self):
        """Decisions below similarity threshold are excluded."""
        query_z = [1.0, 0.0, 0.0, 0.0]
        orthogonal_z = [0.0, 1.0, 0.0, 0.0]  # cosine similarity = 0

        decisions = [
            {
                "id": "dec-orthogonal",
                "action": "hold",
                "z_t_snapshot": json.dumps(orthogonal_z),
            },
        ]
        db = _make_db_with_decisions(decisions)
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(query_z, similarity_threshold=0.5)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_respects_top_k(self):
        """Returns at most top_k results."""
        query_z = [0.5, 0.5, 0.5, 0.5]
        decisions = [
            {
                "id": f"dec-{i}",
                "action": "rebalance",
                "z_t_snapshot": json.dumps([0.5, 0.5, 0.5, 0.5]),
            }
            for i in range(10)
        ]
        db = _make_db_with_decisions(decisions)
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(query_z, top_k=3)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_sorts_by_similarity_descending(self):
        """Results are sorted by similarity, highest first."""
        query_z = [1.0, 0.0, 0.0, 0.0]

        decisions = [
            {
                "id": "dec-low",
                "z_t_snapshot": json.dumps([0.7, 0.3, 0.0, 0.0]),  # cos ~0.92
            },
            {
                "id": "dec-high",
                "z_t_snapshot": json.dumps([0.99, 0.01, 0.0, 0.0]),  # cos ~0.999
            },
            {
                "id": "dec-mid",
                "z_t_snapshot": json.dumps([0.85, 0.15, 0.0, 0.0]),  # cos ~0.98
            },
        ]
        db = _make_db_with_decisions(decisions)
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(query_z, similarity_threshold=0.5)

        assert len(result) == 3
        assert result[0]["decision_id"] == "dec-high"
        assert result[1]["decision_id"] == "dec-mid"
        assert result[2]["decision_id"] == "dec-low"

    @pytest.mark.asyncio
    async def test_handles_corrupt_z_t_snapshot(self):
        """Corrupt z_t_snapshot entries are skipped gracefully."""
        query_z = [0.5, 0.5, 0.5, 0.5]
        decisions = [
            {"id": "dec-corrupt", "z_t_snapshot": "not_json"},
            {"id": "dec-valid", "z_t_snapshot": json.dumps([0.5, 0.5, 0.5, 0.5])},
        ]
        db = _make_db_with_decisions(decisions)
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(query_z)

        assert len(result) == 1
        assert result[0]["decision_id"] == "dec-valid"

    @pytest.mark.asyncio
    async def test_handles_missing_z_t_snapshot(self):
        """Decisions without z_t_snapshot are skipped."""
        query_z = [0.5, 0.5, 0.5, 0.5]
        decisions = [
            {"id": "dec-no-snapshot", "action": "hold"},
        ]
        db = _make_db_with_decisions(decisions)
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(query_z)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_handles_dimension_mismatch(self):
        """Decisions with different z_t dimension are skipped."""
        query_z = [0.5, 0.5, 0.5, 0.5]
        decisions = [
            {"id": "dec-wrong-dim", "z_t_snapshot": json.dumps([0.5, 0.5, 0.5])},
        ]
        db = _make_db_with_decisions(decisions)
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(query_z)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self):
        """Database errors return empty list, not exception."""
        db = AsyncMock()
        db.express = AsyncMock()
        db.express.list = AsyncMock(side_effect=Exception("DB down"))
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(_z_t())

        assert result == []

    @pytest.mark.asyncio
    async def test_result_contains_required_fields(self):
        """Each analogue result has the expected fields."""
        query_z = [0.5, 0.5, 0.5, 0.5]
        decisions = [
            {
                "id": "dec-1",
                "action": "reduce_equity",
                "outcome": "avoided drawdown",
                "instruments": "SPY",
                "brief_summary": "Reduced on signal.",
                "decided_at": "2025-06-15T10:00:00Z",
                "z_t_snapshot": json.dumps([0.5, 0.5, 0.5, 0.5]),
            },
        ]
        db = _make_db_with_decisions(decisions)
        tools = DebateTools(db)
        result = await tools.retrieve_analogue(query_z)

        assert len(result) == 1
        analogue = result[0]
        assert "similarity" in analogue
        assert "decision_id" in analogue
        assert "action" in analogue
        assert "outcome" in analogue


class TestRetrieveAnalogueCosineSimilarity:
    """Tests for the cosine similarity helper on DebateTools."""

    def test_identical_vectors(self):
        a = [1.0, 2.0, 3.0]
        sim = DebateTools._cosine_similarity(a, a)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        sim = DebateTools._cosine_similarity(a, b)
        assert abs(sim) < 1e-6

    def test_zero_vector(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        sim = DebateTools._cosine_similarity(a, b)
        assert sim == 0.0

    def test_opposite_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        sim = DebateTools._cosine_similarity(a, b)
        assert abs(sim + 1.0) < 1e-6
