"""Tier 2 integration tests for DebateAgent multi-turn wiring.

Tests the full DebateAgent pipeline:
- Thread creation with live portfolio context injection
- Multi-turn debate accumulation in DataFlow-backed debate_threads table
- Provenance pointers on each turn
- Portfolio context refresh on each turn

Ref: specs/07 S3.5 (live portfolio context), S3.6 (stateful threads)
Ref: facade-manager-detection.md (manager-shape wiring rules)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midas.agents.debate import DebateAgent


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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """In-memory mock DataFlow backed by a dict store."""
    store: dict[str, list[dict]] = {}

    class MockExpress:
        async def create(self, table: str, row: dict) -> dict:
            if table not in store:
                store[table] = []
            record = dict(row)
            record["id"] = len(store[table]) + 1
            store[table].append(record)
            return record

        async def list(self, table: str, filter: dict | None = None) -> list[dict]:
            rows = store.get(table, [])
            if filter:
                # Simple containment filter
                filtered = []
                for row in rows:
                    match = all(str(row.get(k, "")) == str(v) for k, v in filter.items())
                    if match:
                        filtered.append(row)
                return filtered
            return list(rows)

        async def read(self, table: str, record_id: str) -> dict | None:
            rows = store.get(table, [])
            for row in rows:
                if str(row.get("id")) == str(record_id):
                    return dict(row)
            return None

        async def update(self, table: str, record_id: str, updates: dict) -> dict:
            rows = store.get(table, [])
            for row in rows:
                if str(row.get("id")) == str(record_id):
                    row.update(updates)
                    return row
            raise ValueError(f"Record {record_id} not found in {table}")

    mock = MagicMock()
    mock.express = MockExpress()
    # Expose store for assertions
    mock._test_store = store
    return mock


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
# Tests: thread creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_thread_persists_to_db(mock_db, debate_agent):
    """Thread creation must persist a debate_threads record in DataFlow."""
    thread = await debate_agent.create_thread(mock_db, decision_id="dec-42")

    assert thread["thread_id"] != ""
    assert thread["decision_id"] == "dec-42"
    assert thread["status"] == "open"
    assert thread["turns"] == []

    # Verify DB persistence
    store = mock_db._test_store
    assert "debate_threads" in store
    rows = store["debate_threads"]
    assert len(rows) == 1
    assert rows[0]["decision_id"] == "dec-42"
    assert rows[0]["status"] == "open"


@pytest.mark.asyncio
async def test_create_thread_injects_portfolio_context(mock_db, debate_agent):
    """Thread creation must fetch and store live portfolio context."""
    # Seed positions
    await mock_db.express.create(
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
    await mock_db.express.create(
        "latent_state",
        {
            "z_scale": 1.2,
            "ood_score": 0.3,
            "z_dim": 8,
            "period_end": "2026-04-25",
        },
    )

    thread = await debate_agent.create_thread(mock_db, decision_id="dec-42")

    assert "portfolio_context" in thread
    ctx = thread["portfolio_context"]
    assert ctx["nav"] == 50000.0
    assert len(ctx["positions"]) == 1
    assert ctx["positions"][0]["ticker"] == "SPY"
    assert ctx["regime"]["z_scale"] == 1.2
    assert ctx["regime"]["ood_score"] == 0.3


@pytest.mark.asyncio
async def test_get_thread_returns_persisted_thread(mock_db, debate_agent):
    """get_thread must return the full thread including turns history."""
    created = await debate_agent.create_thread(mock_db, decision_id="dec-99")
    thread_id = created["thread_id"]

    retrieved = await debate_agent.get_thread(mock_db, thread_id)

    assert retrieved is not None
    assert retrieved["thread_id"] == thread_id
    assert retrieved["decision_id"] == "dec-99"
    assert retrieved["status"] == "open"
    assert retrieved["turns"] == []


@pytest.mark.asyncio
async def test_get_thread_returns_none_for_unknown_id(mock_db, debate_agent):
    """get_thread returns None for unknown thread_id."""
    result = await debate_agent.get_thread(mock_db, "nonexistent-uuid")
    assert result is None


# ---------------------------------------------------------------------------
# Tests: multi-turn accumulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_turn_appends_to_thread(mock_db, debate_agent):
    """Each add_turn must append to the thread's turns list in DataFlow."""
    created = await debate_agent.create_thread(mock_db, decision_id="dec-turns")
    thread_id = created["thread_id"]

    turn1 = await debate_agent.add_turn(mock_db, thread_id, user_message="Why overweight SPY?")
    assert turn1["turn_number"] == 1
    assert len(turn1["turns"]) == 1

    turn2 = await debate_agent.add_turn(mock_db, thread_id, user_message="What about rising rates?")
    assert turn2["turn_number"] == 2
    assert len(turn2["turns"]) == 2

    # Verify persistence
    stored = await debate_agent.get_thread(mock_db, thread_id)
    assert len(stored["turns"]) == 2
    assert stored["turns"][0]["user_message"] == "Why overweight SPY?"
    assert stored["turns"][1]["user_message"] == "What about rising rates?"


@pytest.mark.asyncio
async def test_add_turn_injects_fresh_portfolio_context(mock_db, debate_agent):
    """Each turn must receive fresh portfolio context from DataFlow."""
    created = await debate_agent.create_thread(mock_db, decision_id="dec-fresh")
    thread_id = created["thread_id"]

    # Add a position between turns to verify fresh fetch
    await mock_db.express.create(
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

    turn1 = await debate_agent.add_turn(mock_db, thread_id, user_message="First turn")

    # Portfolio context must include both positions
    ctx = turn1["portfolio_context"]
    tickers = {p["ticker"] for p in ctx["positions"]}
    assert "TLT" in tickers


@pytest.mark.asyncio
async def test_add_turn_includes_provenance_pointers(mock_db, debate_agent):
    """Each turn must return provenance pointers to data sources used."""
    await mock_db.express.create(
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
    await mock_db.express.create(
        "latent_state",
        {
            "z_scale": 1.0,
            "ood_score": 0.25,
            "z_dim": 8,
            "period_end": "2026-04-25",
        },
    )

    created = await debate_agent.create_thread(mock_db, decision_id="dec-prov")
    thread_id = created["thread_id"]

    turn = await debate_agent.add_turn(mock_db, thread_id, user_message="Show me the evidence")

    pointers = turn["provenance_pointers"]
    assert len(pointers) >= 2  # positions + latent_state
    sources = {p["source"] for p in pointers}
    assert any("positions" in s for s in sources)
    assert any("latent_state" in s for s in sources)


@pytest.mark.asyncio
async def test_add_turn_updates_thread_status(mock_db, debate_agent):
    """Thread status must update based on resolution_state from LLM response."""
    created = await debate_agent.create_thread(mock_db, decision_id="dec-status")
    thread_id = created["thread_id"]

    await debate_agent.add_turn(mock_db, thread_id, user_message="Turn 1")

    thread = await debate_agent.get_thread(mock_db, thread_id)
    assert thread["status"] == "open"  # LLM returns "open"


@pytest.mark.asyncio
async def test_add_turn_prior_turns_injected_in_context(mock_db, debate_agent):
    """Prior turns must be injected into the LLM context for subsequent turns."""
    created = await debate_agent.create_thread(mock_db, decision_id="dec-prior")
    thread_id = created["thread_id"]

    provider = debate_agent._provider
    provider.call_history.clear()  # Reset call history

    await debate_agent.add_turn(mock_db, thread_id, user_message="First argument")
    await debate_agent.add_turn(mock_db, thread_id, user_message="Second argument")

    # Check that the second LLM call included prior turns
    second_call = provider.call_history[-1]
    prior_turns_text = second_call["messages"][1]["content"]
    assert "First argument" in prior_turns_text
    assert "Turn 1" in prior_turns_text or "prior" in prior_turns_text.lower()


@pytest.mark.asyncio
async def test_add_turn_raises_for_unknown_thread(mock_db, debate_agent):
    """add_turn must raise ValueError for unknown thread_id."""
    with pytest.raises(ValueError, match="not found"):
        await debate_agent.add_turn(mock_db, "nonexistent-thread", user_message="Hello?")


# ---------------------------------------------------------------------------
# Tests: portfolio context formatting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portfolio_context_formats_positions_with_weights(mock_db, debate_agent):
    """_format_portfolio_context must include ticker, weight, and P&L."""
    await mock_db.express.create(
        "positions",
        {
            "ticker": "SPY",
            "market_value": 60000.0,
            "unrealized_pnl": 3000.0,
            "quantity": 120.0,
            "avg_cost": 475.0,
            "as_of_date": "2026-04-25",
        },
    )
    await mock_db.express.create(
        "positions",
        {
            "ticker": "TLT",
            "market_value": 40000.0,
            "unrealized_pnl": -800.0,
            "quantity": 400.0,
            "avg_cost": 102.0,
            "as_of_date": "2026-04-25",
        },
    )

    ctx = await debate_agent._build_portfolio_context(mock_db, brief=None)
    formatted = debate_agent._format_portfolio_context(ctx)

    assert "SPY" in formatted
    assert "TLT" in formatted
    assert "P&L" in formatted or "P&L" in formatted.replace(" ", "")
    assert "60,000" in formatted or "60000" in formatted


@pytest.mark.asyncio
async def test_portfolio_context_includes_relevant_instruments(mock_db, debate_agent):
    """When brief has instruments, only relevant positions are flagged."""
    await mock_db.express.create(
        "positions",
        {
            "ticker": "SPY",
            "market_value": 50000.0,
            "unrealized_pnl": 1000.0,
            "quantity": 100.0,
            "avg_cost": 490.0,
            "as_of_date": "2026-04-25",
        },
    )
    await mock_db.express.create(
        "positions",
        {
            "ticker": "TLT",
            "market_value": 30000.0,
            "unrealized_pnl": -500.0,
            "quantity": 300.0,
            "avg_cost": 101.67,
            "as_of_date": "2026-04-25",
        },
    )

    brief = {"instruments": ["SPY"]}
    ctx = await debate_agent._build_portfolio_context(mock_db, brief=brief)

    assert len(ctx["relevant_positions"]) == 1
    assert ctx["relevant_positions"][0]["ticker"] == "SPY"


# ---------------------------------------------------------------------------
# Tests: LLM prompt construction
# ---------------------------------------------------------------------------


def test_build_turn_prompt_includes_prior_turns(mock_provider, debate_agent):
    """_build_turn_prompt must include prior turns in the prompt."""
    prior_turns = [
        {
            "turn_number": 1,
            "user_message": "Why overweight?",
            "response": {
                "steel_man": "Momentum is strong.",
                "red_team": "Concentration risk.",
                "concession_count": 0,
                "final_confidence": 0.7,
                "resolution_state": "open",
            },
        }
    ]

    prompt = debate_agent._build_turn_prompt(
        user_message="What about rates?",
        prior_turns=prior_turns,
        brief_summary="",
        live_context="Portfolio: 2 positions, NAV $100,000",
    )

    assert "Why overweight?" in prompt
    assert "Momentum is strong" in prompt
    assert "What about rates?" in prompt
    assert "Portfolio: 2 positions" in prompt


def test_build_turn_prompt_includes_brief_and_context(mock_provider, debate_agent):
    """_build_turn_prompt must include brief summary and live context."""
    prompt = debate_agent._build_turn_prompt(
        user_message="Debate this",
        prior_turns=[],
        brief_summary="recommendation: overweight SPY",
        live_context="Regime: calm, z_scale=0.8",
    )

    assert "recommendation: overweight SPY" in prompt
    assert "Regime: calm" in prompt
    assert "Debate this" in prompt


# ---------------------------------------------------------------------------
# Tests: provenance pointer construction
# ---------------------------------------------------------------------------


def test_provenance_pointers_include_positions_source(mock_provider, debate_agent):
    """_build_provenance_pointers must include fabric:positions pointer."""
    portfolio_context = {
        "positions": [{"ticker": "SPY", "market_value": 50000}],
        "regime": {},
    }

    pointers = debate_agent._build_provenance_pointers(portfolio_context, brief=None)

    assert any("positions" in p["source"] for p in pointers)


def test_provenance_pointers_include_regime_source(mock_provider, debate_agent):
    """_build_provenance_pointers must include fabric:latent_state pointer."""
    portfolio_context = {
        "positions": [],
        "regime": {"z_scale": 1.2, "ood_score": 0.3},
    }

    pointers = debate_agent._build_provenance_pointers(portfolio_context, brief=None)

    assert any("latent_state" in p["source"] for p in pointers)


def test_provenance_pointers_include_decision_id_if_present(mock_provider, debate_agent):
    """_build_provenance_pointers includes decisions source when brief has decision_id."""
    portfolio_context = {"positions": [], "regime": {}}
    brief = {"decision_id": "dec-123"}

    pointers = debate_agent._build_provenance_pointers(portfolio_context, brief=brief)

    assert any("decisions" in p["source"] for p in pointers)


# ---------------------------------------------------------------------------
# Tests: single-turn debate (legacy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debate_single_turn_returns_structured_result(mock_provider, debate_agent):
    """Legacy debate() method returns the expected structured keys."""
    brief = {
        "sections": {"recommendation": "overweight SPY"},
        "instruments": ["SPY"],
    }

    result = await debate_agent.debate(brief, debate_rounds=3)

    assert "recommendation" in result
    assert "steel_man" in result
    assert "red_team" in result
    assert "concession_count" in result
    assert "final_confidence" in result
    assert "resolution_state" in result
    assert result["concession_count"] == 1
    assert result["final_confidence"] == 0.65


# ---------------------------------------------------------------------------
# Tests: API endpoint round-trip (mock HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thread_status_update_round_trip(mock_db, debate_agent):
    """Thread status must be queryable after being updated by add_turn."""
    created = await debate_agent.create_thread(mock_db, decision_id="dec-roundtrip")
    thread_id = created["thread_id"]

    # Verify initial status
    thread_before = await debate_agent.get_thread(mock_db, thread_id)
    assert thread_before["status"] == "open"

    # Add turn (which may update status)
    await debate_agent.add_turn(mock_db, thread_id, user_message="Test message")

    # Verify updated status is queryable
    thread_after = await debate_agent.get_thread(mock_db, thread_id)
    assert thread_after["status"] != ""
    assert "turns" in thread_after
    assert len(thread_after["turns"]) == 1
