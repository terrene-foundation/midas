from __future__ import annotations

"""Regression: Multi-turn debate produces multiple rounds with tool dispatch.

Validates:
- debate produces multiple rounds
- tool results injected into context
- resolution state is one of the 4 spec values
- concession count accumulates
- update_decision triggers 'updated' resolution
- orchestrator passes tools to DebateAgent
- DebateSession dispatches tools correctly

Ref: specs/07 S3.3 (10-tool table), S3.5 (live context), wave2 GROUP E
"""

import json

import pytest

from midas.agents.debate_session import (
    DebateSession,
    TOOL_REGISTRY,
    VALID_RESOLUTION_STATES,
)


class FakeProvider:
    """Fake LLM provider returning structured debate responses."""

    def __init__(self, responses: list[dict] | None = None):
        self._responses = responses or []
        self._call_count = 0

    async def complete(self, messages, **kwargs):
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return {"content": json.dumps(resp)}
        return {
            "content": json.dumps(
                {
                    "steel_man": "advocacy",
                    "red_team": "criticism",
                    "tool_calls": [],
                    "concession_count": 0,
                    "resolution_state": "maintained",
                    "summary": "default",
                }
            )
        }


class FakeTools:
    """Fake DebateTools with all 10 tools stubbed."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def query_fabric(self, table, filter):
        self.calls.append(("query_fabric", {"table": table}))
        return [{"mock": True}]

    async def query_head(self, head_name, z_t):
        self.calls.append(("query_head", {"head_name": head_name}))
        return {"mock": True}

    async def query_calibration(self, head_name):
        self.calls.append(("query_calibration", {"head_name": head_name}))
        return {"mock": True}

    async def retrieve_analogue(self, z_t, **kw):
        self.calls.append(("retrieve_analogue", {"z_t": z_t}))
        return [{"mock": True}]

    async def backtest_scenario(self, weights, period):
        self.calls.append(("backtest_scenario", {"period": period}))
        return {"mock": True}

    async def update_decision(self, decision_id, updates):
        self.calls.append(("update_decision", {"decision_id": decision_id}))
        return {"mock": True}

    async def generate_counterfactual(self, **kw):
        self.calls.append(("generate_counterfactual", {}))
        return {"mock": True}

    async def surface_override_pattern(self, user_id):
        self.calls.append(("surface_override_pattern", {"user_id": user_id}))
        return {"mock": True}

    async def propose_alternative_allocation(self, **kw):
        self.calls.append(("propose_alternative_allocation", {}))
        return {"mock": True}

    async def recompute_with_constraint(self, scenario, constraint):
        self.calls.append(("recompute_with_constraint", {}))
        return {"mock": True}


class FakeDB:
    """In-memory fake DataFlow for debate thread persistence."""

    def __init__(self):
        self._tables: dict[str, list[dict]] = {"debate_threads": []}
        self._next_id = 1

    @property
    def express(self):
        return self

    async def create(self, table, row):
        row["id"] = self._next_id
        self._next_id += 1
        self._tables.setdefault(table, []).append(dict(row))
        return row

    async def list(self, table, **kwargs):
        rows = self._tables.get(table, [])
        f = kwargs.get("filter") or {}
        if f:
            return [r for r in rows if all(r.get(k) == v for k, v in f.items())]
        return list(rows)

    async def update(self, table, row_id, fields):
        for row in self._tables.get(table, []):
            if row.get("id") == row_id:
                row.update(fields)
                return row
        return None

    async def upsert(self, table, row):
        target_id = row.get("id")
        for existing in self._tables.get(table, []):
            if existing.get("id") == target_id:
                existing.update(row)
                return existing
        return await self.create(table, row)


class FakeDebateAgent:
    """Minimal DebateAgent stub that delegates thread management to FakeDB."""

    def __init__(self, provider=None, tools=None):
        self._provider = provider
        self._tools = tools
        self._turn_count = 0

    async def create_thread(self, db, decision_id, brief=None):
        thread_id = f"thread-{decision_id}"
        await db.express.create(
            "debate_threads",
            {
                "thread_id": thread_id,
                "decision_id": decision_id,
                "status": "open",
                "turns_json": "[]",
                "portfolio_context_json": "{}",
            },
        )
        return {"thread_id": thread_id, "decision_id": decision_id}

    async def get_thread(self, db, thread_id):
        rows = await db.express.list("debate_threads", filter={"thread_id": thread_id})
        return rows[0] if rows else None

    async def update_thread_status(self, db, thread_id, status):
        rows = await db.express.list("debate_threads", filter={"thread_id": thread_id})
        if rows:
            await db.express.update("debate_threads", rows[0]["id"], {"status": status})

    async def add_turn(self, db, thread_id, user_message, brief=None):
        self._turn_count += 1
        if self._provider:
            result = await self._provider.complete(messages=[])
            response = result.get("content", "")
        else:
            response = json.dumps(
                {
                    "steel_man": f"round {self._turn_count} advocacy",
                    "red_team": f"round {self._turn_count} criticism",
                    "tool_calls": [],
                    "concession_count": self._turn_count,
                    "resolution_state": "maintained",
                    "summary": f"Round {self._turn_count} complete",
                }
            )
        # Persist turn
        rows = await db.express.list("debate_threads", filter={"thread_id": thread_id})
        if rows:
            turns = json.loads(rows[0].get("turns_json", "[]"))
            turns.append(
                {"role": "user", "content": user_message[:100], "response": response[:200]}
            )
            await db.express.update(
                "debate_threads", rows[0]["id"], {"turns_json": json.dumps(turns)}
            )
        return {
            "thread_id": thread_id,
            "turn_number": self._turn_count,
            "response": response,
        }


# --- Tests ---


@pytest.mark.asyncio
@pytest.mark.regression
async def test_debate_produces_multiple_rounds():
    db = FakeDB()
    agent = FakeDebateAgent()
    tools = FakeTools()
    session = DebateSession(agent, tools, "dec-1", max_turns=3)

    result = await session.run(db, {"sections": {"recommendation": "buy AAPL"}}, debate_rounds=3)

    assert result["rounds"] == 3
    assert result["thread_id"] is not None


@pytest.mark.asyncio
@pytest.mark.regression
async def test_resolution_state_is_valid():
    db = FakeDB()
    agent = FakeDebateAgent()
    tools = FakeTools()
    session = DebateSession(agent, tools, "dec-2")

    result = await session.run(db, {"sections": {"recommendation": "sell TSLA"}})

    assert result["resolution_state"] in VALID_RESOLUTION_STATES


@pytest.mark.asyncio
@pytest.mark.regression
async def test_concession_count_accumulates():
    provider = FakeProvider(
        [
            {
                "steel_man": "s1",
                "red_team": "r1",
                "tool_calls": [],
                "concession_count": 2,
                "resolution_state": "open",
                "summary": "r1",
            },
            {
                "steel_man": "s2",
                "red_team": "r2",
                "tool_calls": [],
                "concession_count": 4,
                "resolution_state": "maintained",
                "summary": "r2",
            },
            {
                "steel_man": "s3",
                "red_team": "r3",
                "tool_calls": [],
                "concession_count": 1,
                "resolution_state": "maintained",
                "summary": "r3",
            },
        ]
    )
    db = FakeDB()
    agent = FakeDebateAgent(provider=provider)
    tools = FakeTools()
    session = DebateSession(agent, tools, "dec-3")

    result = await session.run(db, {"sections": {}}, debate_rounds=3)

    assert result["concession_count"] == 4  # max across rounds


@pytest.mark.asyncio
@pytest.mark.regression
async def test_update_decision_triggers_updated_resolution():
    provider = FakeProvider(
        [
            {
                "steel_man": "s1",
                "red_team": "r1",
                "tool_calls": [
                    {"tool": "update_decision", "args": {"decision_id": "dec-4", "updates": {}}}
                ],
                "concession_count": 1,
                "resolution_state": "open",
                "summary": "updated",
            },
        ]
    )
    db = FakeDB()
    agent = FakeDebateAgent(provider=provider)
    tools = FakeTools()
    session = DebateSession(agent, tools, "dec-4")

    result = await session.run(db, {"sections": {}}, debate_rounds=1)

    assert result["resolution_state"] == "updated"
    assert any(c[0] == "update_decision" for c in tools.calls)


@pytest.mark.asyncio
@pytest.mark.regression
async def test_tool_dispatch_logs_results():
    provider = FakeProvider(
        [
            {
                "steel_man": "s1",
                "red_team": "r1",
                "tool_calls": [
                    {"tool": "query_fabric", "args": {"table": "positions", "filter": {}}},
                    {"tool": "backtest_scenario", "args": {"weights": {}, "period": "1Y"}},
                ],
                "concession_count": 0,
                "resolution_state": "maintained",
                "summary": "tools",
            },
        ]
    )
    db = FakeDB()
    agent = FakeDebateAgent(provider=provider)
    tools = FakeTools()
    session = DebateSession(agent, tools, "dec-5")

    result = await session.run(db, {"sections": {}}, debate_rounds=1)

    assert len(result["tool_calls_log"]) == 2
    assert result["tool_calls_log"][0]["status"] == "ok"
    assert result["tool_calls_log"][0]["tool"] == "query_fabric"


@pytest.mark.asyncio
@pytest.mark.regression
async def test_unknown_tool_returns_error():
    provider = FakeProvider(
        [
            {
                "steel_man": "s1",
                "red_team": "r1",
                "tool_calls": [{"tool": "nonexistent_tool", "args": {}}],
                "concession_count": 0,
                "resolution_state": "open",
                "summary": "bad tool",
            },
        ]
    )
    db = FakeDB()
    agent = FakeDebateAgent(provider=provider)
    tools = FakeTools()
    session = DebateSession(agent, tools, "dec-6")

    result = await session.run(db, {"sections": {}}, debate_rounds=1)

    assert len(result["tool_calls_log"]) == 1
    assert result["tool_calls_log"][0]["status"] == "error"
    assert "Unknown tool" in result["tool_calls_log"][0]["error"]


@pytest.mark.asyncio
@pytest.mark.regression
async def test_tool_registry_has_all_10_tools():
    expected = {
        "query_fabric",
        "query_head",
        "query_calibration",
        "retrieve_analogue",
        "backtest_scenario",
        "update_decision",
        "generate_counterfactual",
        "surface_override_pattern",
        "propose_alternative_allocation",
        "recompute_with_constraint",
    }
    assert set(TOOL_REGISTRY.keys()) == expected


@pytest.mark.asyncio
@pytest.mark.regression
async def test_orchestrator_passes_tools_to_debate_agent():
    from midas.agents.orchestrator import AgentOrchestrator

    db = FakeDB()
    provider = FakeProvider()
    orch = AgentOrchestrator(provider, db)

    assert orch.debate._tools is orch.tools
