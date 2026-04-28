"""Tier 2 integration tests for MultiTurnDebateRouter HTTP endpoints.

Tests the HTTP router layer for multi-turn debate threads:
- POST /debate/thread — create_thread
- GET /debate/thread/{thread_id} — get_thread
- POST /debate/thread/{thread_id}/turn — add_turn
- GET /debate/thread/{thread_id}/context — get_thread_context

DebateAgent methods are tested via test_debate_agent_wiring.py — these tests
exercise the HTTP router wiring (status codes, response shapes, error handling).

Ref: specs/07 S3.5 (live portfolio context), S3.6 (stateful threads)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midas.agents.debate import DebateAgent
from midas.api.routes_extended import MultiTurnDebateRouter


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


class MockProvider:
    """Deterministic mock LLM provider for integration tests."""

    def __init__(self, response_content: str = "") -> None:
        self._response_content = response_content
        self.call_history: list[dict] = []

    async def complete(self, messages: list[dict], **kwargs) -> dict:
        self.call_history.append({"messages": messages, "kwargs": kwargs})
        return {"content": self._response_content, "model": "test", "provider": "mock"}


# ---------------------------------------------------------------------------
# Mock DataFlow (Tier 2 — real DataFlow-like interface, in-memory store)
# ---------------------------------------------------------------------------


class MockExpress:
    """In-memory express layer for router tests."""

    def __init__(self, store: dict[str, list[dict]]) -> None:
        self._store = store

    async def create(self, table: str, row: dict) -> dict:
        if table not in self._store:
            self._store[table] = []
        record = dict(row)
        record["id"] = len(self._store[table]) + 1
        self._store[table].append(record)
        return record

    async def list(self, table: str, filter: dict | None = None) -> list[dict]:
        rows = self._store.get(table, [])
        if filter:
            filtered = []
            for row in rows:
                if all(str(row.get(k, "")) == str(v) for k, v in filter.items()):
                    filtered.append(row)
            return filtered
        return list(rows)

    async def read(self, table: str, record_id: str) -> dict | None:
        rows = self._store.get(table, [])
        for row in rows:
            if str(row.get("id")) == str(record_id):
                return dict(row)
        return None

    async def update(self, table: str, record_id: str, updates: dict) -> dict:
        rows = self._store.get(table, [])
        for row in rows:
            if str(row.get("id")) == str(record_id):
                row.update(updates)
                return row
        raise ValueError(f"Record {record_id} not found in {table}")


def mock_db() -> MagicMock:
    """In-memory mock DataFlow with MockExpress."""
    store: dict[str, list[dict]] = {}
    db = MagicMock()
    db.express = MockExpress(store)
    db._test_store = store
    return db


# ---------------------------------------------------------------------------
# Module-level _get_db patching
# ---------------------------------------------------------------------------


async def _patch_get_db(db: MagicMock):
    """Patch _get_db in routes_extended to return the given mock db."""
    import midas.api.routes as routes_mod
    import midas.api.routes_extended as ext_mod

    original = routes_mod._get_db
    routes_mod._get_db = AsyncMock(return_value=db)
    ext_mod._get_db = AsyncMock(return_value=db)
    return original, routes_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider():
    """Returns a deterministic mock LLM provider."""
    return MockProvider(
        response_content=json.dumps(
            {
                "recommendation": "overweight SPY",
                "steel_man": "Strong case for increasing equity exposure given momentum signals.",
                "red_team": "Risk is elevated due to OOD regime and concentration risk.",
                "concession_count": 1,
                "final_confidence": 0.65,
                "resolution_state": "open",
                "rounds": 3,
            }
        )
    )


@pytest.fixture
def debate_agent(mock_provider):
    """DebateAgent wired with mock provider and tools."""
    return DebateAgent(mock_provider, tools=None)


# ---------------------------------------------------------------------------
# Tests: POST /debate/thread — create_thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_thread_returns_thread_with_decision_id(debate_agent):
    """POST /debate/thread must return a thread with the given decision_id."""
    db = mock_db()
    orig, routes_mod = await _patch_get_db(db)
    try:
        # Patch the agent on the router so it uses our debate_agent
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        result = await router.create_thread({"decision_id": "dec-42"})

        assert result["thread_id"] != ""
        assert result["decision_id"] == "dec-42"
        assert result["status"] == "open"
        assert result["turns"] == []
    finally:
        routes_mod._get_db = orig


@pytest.mark.asyncio
async def test_create_thread_with_brief_includes_portfolio_context(debate_agent):
    """Thread creation must inject portfolio context when brief is provided."""
    db = mock_db()
    # Seed positions
    await db.express.create(
        "positions",
        {
            "ticker": "SPY",
            "market_value": 50000.0,
            "unrealized_pnl": 2500.0,
            "quantity": 100.0,
            "avg_cost": 475.0,
            "as_of_date": "2026-04-25",
        },
    )
    await db.express.create(
        "latent_state",
        {
            "z_scale": 1.2,
            "ood_score": 0.3,
            "z_dim": 8,
            "period_end": "2026-04-25",
        },
    )

    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        result = await router.create_thread(
            {"decision_id": "dec-43", "brief": {"instruments": ["SPY"]}}
        )

        assert "portfolio_context" in result
        ctx = result["portfolio_context"]
        assert ctx["nav"] == 50000.0
        assert len(ctx["positions"]) == 1
        assert ctx["positions"][0]["ticker"] == "SPY"
    finally:
        routes_mod._get_db = orig


@pytest.mark.asyncio
async def test_create_thread_503_when_db_unavailable():
    """Router must return 503 when database is unavailable."""
    orig, routes_mod = await _patch_get_db(None)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(None, None))

        with pytest.raises(Exception) as exc_info:
            await router.create_thread({"decision_id": "dec-44"})
        assert exc_info.value.status_code == 503
        assert "Database unavailable" in exc_info.value.detail
    finally:
        routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# Tests: GET /debate/thread/{thread_id} — get_thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_thread_returns_thread_with_turns_empty(debate_agent):
    """GET /debate/thread/{id} must return thread with empty turns on creation."""
    db = mock_db()
    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        # Create first
        created = await router.create_thread({"decision_id": "dec-get"})
        thread_id = created["thread_id"]

        # Then retrieve
        retrieved = await router.get_thread(thread_id)

        assert retrieved["thread_id"] == thread_id
        assert retrieved["decision_id"] == "dec-get"
        assert retrieved["turns"] == []
        assert retrieved["status"] == "open"
    finally:
        routes_mod._get_db = orig


@pytest.mark.asyncio
async def test_get_thread_404_for_unknown_id(debate_agent):
    """GET /debate/thread/{id} must return 404 for unknown thread_id."""
    db = mock_db()
    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        with pytest.raises(Exception) as exc_info:
            await router.get_thread("nonexistent-uuid")
        assert exc_info.value.status_code == 404
        assert "Thread not found" in exc_info.value.detail
    finally:
        routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# Tests: POST /debate/thread/{thread_id}/turn — add_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_turn_returns_ai_response_structure(debate_agent):
    """POST /debate/thread/{id}/turn must call DebateAgent and return AI response."""
    db = mock_db()
    # Seed context so agent has data to work with
    await db.express.create(
        "positions",
        {
            "ticker": "SPY",
            "market_value": 50000.0,
            "unrealized_pnl": 2500.0,
            "quantity": 100.0,
            "avg_cost": 475.0,
            "as_of_date": "2026-04-25",
        },
    )
    await db.express.create(
        "latent_state",
        {
            "z_scale": 1.0,
            "ood_score": 0.25,
            "z_dim": 8,
            "period_end": "2026-04-25",
        },
    )

    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        # Create thread
        created = await router.create_thread({"decision_id": "dec-turn"})
        thread_id = created["thread_id"]

        # Add a turn
        turn_result = await router.add_turn(
            thread_id, {"user_message": "Why should we overweight SPY?"}
        )

        assert turn_result["thread_id"] == thread_id
        assert turn_result["turn_number"] == 1
        assert "response" in turn_result
        assert "portfolio_context" in turn_result
        assert "provenance_pointers" in turn_result
        assert turn_result["status"] == "open"
    finally:
        routes_mod._get_db = orig


@pytest.mark.asyncio
async def test_add_turn_accumulates_multiple_turns(debate_agent):
    """Multiple add_turn calls must accumulate in the thread's turns list."""
    db = mock_db()
    await db.express.create(
        "positions",
        {
            "ticker": "SPY",
            "market_value": 50000.0,
            "unrealized_pnl": 2500.0,
            "quantity": 100.0,
            "avg_cost": 475.0,
            "as_of_date": "2026-04-25",
        },
    )
    await db.express.create(
        "latent_state",
        {
            "z_scale": 1.0,
            "ood_score": 0.25,
            "z_dim": 8,
            "period_end": "2026-04-25",
        },
    )

    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        created = await router.create_thread({"decision_id": "dec-multi"})
        thread_id = created["thread_id"]

        turn1 = await router.add_turn(thread_id, {"user_message": "First argument"})
        assert turn1["turn_number"] == 1

        turn2 = await router.add_turn(thread_id, {"user_message": "Second argument"})
        assert turn2["turn_number"] == 2
        assert len(turn2["turns"]) == 2

        # Verify persistence via get_thread
        thread = await router.get_thread(thread_id)
        assert len(thread["turns"]) == 2
        assert thread["turns"][0]["user_message"] == "First argument"
        assert thread["turns"][1]["user_message"] == "Second argument"
    finally:
        routes_mod._get_db = orig


@pytest.mark.asyncio
async def test_add_turn_422_when_user_message_missing(debate_agent):
    """POST /debate/thread/{id}/turn must return 422 when user_message is empty."""
    db = mock_db()
    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        created = await router.create_thread({"decision_id": "dec-no-msg"})
        thread_id = created["thread_id"]

        with pytest.raises(Exception) as exc_info:
            await router.add_turn(thread_id, {"user_message": ""})
        assert exc_info.value.status_code == 422
        assert "user_message is required" in exc_info.value.detail
    finally:
        routes_mod._get_db = orig


@pytest.mark.asyncio
async def test_add_turn_404_for_unknown_thread(debate_agent):
    """POST /debate/thread/{id}/turn must return 404 for unknown thread_id."""
    db = mock_db()
    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        with pytest.raises(Exception) as exc_info:
            await router.add_turn("nonexistent-thread", {"user_message": "Hello?"})
        assert exc_info.value.status_code == 404
    finally:
        routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# Tests: GET /debate/thread/{thread_id}/context — get_thread_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_thread_context_returns_portfolio_context(debate_agent):
    """GET /debate/thread/{id}/context must return current portfolio context."""
    db = mock_db()
    await db.express.create(
        "positions",
        {
            "ticker": "SPY",
            "market_value": 75000.0,
            "unrealized_pnl": 3000.0,
            "quantity": 150.0,
            "avg_cost": 480.0,
            "as_of_date": "2026-04-25",
        },
    )
    await db.express.create(
        "latent_state",
        {
            "z_scale": 0.8,
            "ood_score": 0.2,
            "z_dim": 8,
            "period_end": "2026-04-25",
        },
    )

    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        created = await router.create_thread({"decision_id": "dec-ctx"})
        thread_id = created["thread_id"]

        context = await router.get_thread_context(thread_id)

        assert context["thread_id"] == thread_id
        assert context["status"] == "open"
        assert "portfolio_context" in context
        ctx = context["portfolio_context"]
        assert ctx["nav"] == 75000.0
        assert len(ctx["positions"]) == 1
        assert ctx["positions"][0]["ticker"] == "SPY"
    finally:
        routes_mod._get_db = orig


@pytest.mark.asyncio
async def test_get_thread_context_404_for_unknown_thread(debate_agent):
    """GET /debate/thread/{id}/context must return 404 for unknown thread_id."""
    db = mock_db()
    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        with pytest.raises(Exception) as exc_info:
            await router.get_thread_context("nonexistent-uuid")
        assert exc_info.value.status_code == 404
        assert "Thread not found" in exc_info.value.detail
    finally:
        routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# Tests: thread context refresh on each turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_context_fresh_after_position_change(debate_agent):
    """Portfolio context must refresh on each turn — new positions visible."""
    db = mock_db()
    # Initial position
    await db.express.create(
        "positions",
        {
            "ticker": "SPY",
            "market_value": 50000.0,
            "unrealized_pnl": 2500.0,
            "quantity": 100.0,
            "avg_cost": 475.0,
            "as_of_date": "2026-04-25",
        },
    )
    await db.express.create(
        "latent_state",
        {
            "z_scale": 1.0,
            "ood_score": 0.25,
            "z_dim": 8,
            "period_end": "2026-04-25",
        },
    )

    orig, routes_mod = await _patch_get_db(db)
    try:
        router = MultiTurnDebateRouter()
        router._get_debate_agent = AsyncMock(return_value=(debate_agent, db))

        created = await router.create_thread({"decision_id": "dec-fresh"})
        thread_id = created["thread_id"]

        # Add first turn with SPY only
        turn1 = await router.add_turn(thread_id, {"user_message": "First turn"})
        ctx1 = turn1["portfolio_context"]
        assert {p["ticker"] for p in ctx1["positions"]} == {"SPY"}

        # Add a new position between turns
        await db.express.create(
            "positions",
            {
                "ticker": "TLT",
                "market_value": 20000.0,
                "unrealized_pnl": -500.0,
                "quantity": 200.0,
                "avg_cost": 102.5,
                "as_of_date": "2026-04-25",
            },
        )

        # Second turn should see both positions
        turn2 = await router.add_turn(thread_id, {"user_message": "Second turn"})
        ctx2 = turn2["portfolio_context"]
        assert {p["ticker"] for p in ctx2["positions"]} == {"SPY", "TLT"}
    finally:
        routes_mod._get_db = orig
