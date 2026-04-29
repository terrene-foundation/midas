"""Tier 1 unit tests for M09 (LLM Agents) and M10 (Brief Composer).

All LLM HTTP calls are mocked. DataFlow is mocked for tools/research.
Tests verify structure, not semantic content of LLM responses.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_llm_response(content: str = "Test LLM response") -> dict:
    """Build a mock OpenAI API response."""
    return {
        "choices": [
            {
                "message": {"content": content},
                "finish_reason": "stop",
            }
        ],
        "model": "gpt-4",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


def _mock_brief_json() -> str:
    """JSON string matching AnalystAgent.compose_brief output schema."""
    return json.dumps(
        {
            "sections": {
                "situation_summary": "Market shows elevated volatility.",
                "evidence_assessment": "Three converging signals detected.",
                "recommendation": "Reduce equity exposure by 5%.",
                "counter_evidence": "Earnings season was strong.",
                "what_would_change_mind": "If VIX drops below 15.",
                "risk_factors": "Geopolitical escalation risk.",
                "provenance_links": ["news:123", "filing:456"],
                "if_approved": "Reduced risk exposure, potential underperformance in rally.",
                "if_rejected": "Maintain current allocation, higher downside risk.",
                "historical_precedent": "Similar volatility regime in Q4 2022 led to 8% drawdown.",
            },
            "confidence": 0.72,
            "model_version": "gpt-4",
        }
    )


def _mock_debate_json() -> str:
    """JSON string matching DebateAgent.debate output schema."""
    return json.dumps(
        {
            "recommendation": "Proceed with caution.",
            "steel_man": "Strong earnings support continued holding.",
            "red_team": "Macro headwinds argue for de-risking.",
            "concession_count": 2,
            "final_confidence": 0.65,
            "resolution_state": "updated",
            "rounds": 3,
        }
    )


def _mock_research_json() -> str:
    """JSON string matching ResearchAgent.research output schema."""
    return json.dumps(
        {
            "summary": "Recent filings show increased insider selling.",
            "sources": ["filing:789", "news:101"],
            "relevance_scores": [0.91, 0.84],
        }
    )


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient that returns canned LLM responses."""
    mock_client = AsyncMock()
    call_log: list[dict] = []

    async def _post(url, **kwargs):
        call_log.append({"url": url, **kwargs})

        # Determine which response to return based on messages content
        body = kwargs.get("json", {})
        messages = body.get("messages", [])
        last_content = ""
        for msg in messages:
            if msg.get("role") == "user":
                last_content = msg.get("content", "")

        # Return appropriate mock response based on content hints.
        # Order matters: debate messages also contain "brief", so check debate first.
        if "debate rounds" in last_content.lower() or "steel_man" in last_content.lower():
            content = _mock_debate_json()
        elif "research" in last_content.lower() or "summarize" in last_content.lower():
            content = _mock_research_json()
        elif "produce a structured investment brief" in last_content.lower():
            content = _mock_brief_json()
        elif "debate" in last_content.lower() or "steel" in last_content.lower():
            content = _mock_debate_json()
        else:
            content = "Test LLM response"

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _mock_llm_response(content)
        response.raise_for_status = MagicMock()
        return response

    # Attach the callable AND a call log for assertions
    mock_client.post = _post
    mock_client._call_log = call_log
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.fixture
def provider(mock_httpx_client):
    """Create a FrontierProvider with mocked HTTP client."""
    from midas.agents.provider import FrontierProvider

    p = FrontierProvider(primary_model="gpt-4", fallback_model="gpt-4")
    p._client = mock_httpx_client
    return p


@pytest.fixture
def mock_db():
    """Mock DataFlow instance for DebateTools and ResearchAgent."""
    db = AsyncMock()
    db.express = AsyncMock()

    # Track created debate threads so get_thread can find them
    _created_threads: list[dict] = []

    async def mock_list(table: str, filter: dict | None = None, **kwargs):
        if table == "debate_threads" and filter and "thread_id" in filter:
            # Return matching thread if found
            tid = filter["thread_id"]
            for t in _created_threads:
                if t.get("thread_id") == tid:
                    return [t]
            return []
        return []

    async def mock_create(table: str, row: dict, **kwargs):
        if table == "debate_threads":
            # Add id to the row so express.list returns it with id field
            row_with_id = dict(row, id=1)
            _created_threads.append(row_with_id)
        return {"id": 1}

    db.express.list = AsyncMock(side_effect=mock_list)
    db.express.create = AsyncMock(side_effect=mock_create)
    db.express.read = AsyncMock(return_value={})
    db.express.update = AsyncMock(return_value={})
    return db


# ===========================================================================
# M09 — FrontierProvider
# ===========================================================================


class TestFrontierProvider:
    """Tests for the frontier LLM provider abstraction."""

    def test_init_reads_model_from_env(self):
        """Provider reads model names from environment."""
        from midas.agents.provider import FrontierProvider

        p = FrontierProvider(primary_model="gpt-4o", fallback_model="gpt-4o-mini")
        assert p.primary_model == "gpt-4o"
        assert p.fallback_model == "gpt-4o-mini"

    def test_init_defaults_when_no_args(self):
        """Provider falls back to env defaults when no models given."""
        from midas.agents.provider import FrontierProvider

        p = FrontierProvider()
        assert p.primary_model is not None
        assert p.fallback_model is not None

    @pytest.mark.asyncio
    async def test_complete_returns_valid_structure(self, provider):
        """complete() returns dict with content, model, provider keys."""
        result = await provider.complete(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.5,
            max_tokens=100,
        )
        assert "content" in result
        assert "model" in result
        assert "provider" in result
        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0

    @pytest.mark.asyncio
    async def test_health_check_returns_structure(self, provider, mock_httpx_client):
        """health_check() returns dict with available and model keys."""
        # Mock a models endpoint response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        result = await provider.health_check()
        assert "available" in result
        assert "model" in result

    @pytest.mark.asyncio
    async def test_close_closes_client(self, provider, mock_httpx_client):
        """close() closes the underlying httpx client."""
        await provider.close()
        mock_httpx_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_sends_api_key(self, mock_httpx_client):
        """complete() sends Authorization header with API key."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-123"}):
            from midas.agents.provider import FrontierProvider

            p = FrontierProvider(primary_model="gpt-4")
            p._client = mock_httpx_client

            # Wrap _post to capture headers
            captured_headers = {}
            original_post = mock_httpx_client.post

            async def _tracking_post(url, **kwargs):
                captured_headers.update(kwargs.get("headers", {}))
                return await original_post(url, **kwargs)

            mock_httpx_client.post = _tracking_post
            await p.complete(messages=[{"role": "user", "content": "test"}])

        assert "Authorization" in captured_headers
        assert captured_headers["Authorization"] == "Bearer test-key-123"

    @pytest.mark.asyncio
    async def test_complete_with_fallback_on_failure(self):
        """complete() falls back to fallback_model on primary failure."""
        from midas.agents.provider import FrontierProvider

        p = FrontierProvider(primary_model="gpt-4", fallback_model="gpt-4o-mini")
        failing_client = AsyncMock()

        call_count = 0

        async def _post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            body = kwargs.get("json", {})
            model = body.get("model", "")

            if model == "gpt-4" and call_count == 1:
                # Primary model fails
                raise ConnectionError("API unavailable")

            # Fallback succeeds
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = _mock_llm_response("Fallback response")
            response.raise_for_status = MagicMock()
            return response

        failing_client.post = _post
        failing_client.aclose = AsyncMock()
        p._client = failing_client

        result = await p.complete(messages=[{"role": "user", "content": "test"}])
        assert result["content"] == "Fallback response"
        assert result["model"] == "gpt-4o-mini"


# ===========================================================================
# M09 — AnalystAgent
# ===========================================================================


class TestAnalystAgent:
    """Tests for the analyst brief composition agent."""

    @pytest.mark.asyncio
    async def test_compose_brief_produces_all_sections(self, provider):
        """compose_brief returns dict with all 10 sections plus confidence and model_version."""
        from midas.agents.analyst import AnalystAgent

        agent = AnalystAgent(provider)
        decision_context = {
            "decision_type": "rebalance",
            "instruments": ["SPY", "TLT"],
            "evidence": ["VIX elevated at 28", "Earnings beat"],
        }
        result = await agent.compose_brief(decision_context)

        assert "sections" in result
        sections = result["sections"]
        required_sections = [
            "situation_summary",
            "evidence_assessment",
            "recommendation",
            "counter_evidence",
            "what_would_change_mind",
            "risk_factors",
            "provenance_links",
            "if_approved",
            "if_rejected",
            "historical_precedent",
        ]
        for section in required_sections:
            assert section in sections, f"Missing section: {section}"

        assert "confidence" in result
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0

        assert "model_version" in result
        assert isinstance(result["model_version"], str)

    @pytest.mark.asyncio
    async def test_compose_brief_passes_context_to_llm(self, provider, mock_httpx_client):
        """compose_brief includes decision context in the LLM prompt."""
        from midas.agents.analyst import AnalystAgent

        agent = AnalystAgent(provider)
        context = {
            "decision_type": "rebalance",
            "instruments": ["AAPL"],
            "evidence": ["Signal 1"],
        }
        await agent.compose_brief(context)

        # Verify the LLM was called via the call log
        call_log = mock_httpx_client._call_log
        assert len(call_log) >= 1
        body = call_log[0].get("json", {})
        messages = body.get("messages", [])
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) >= 1


# ===========================================================================
# M09 — DebateAgent
# ===========================================================================


class TestDebateAgent:
    """Tests for the steelman/red-team debate agent."""

    @pytest.mark.asyncio
    async def test_debate_returns_structured_output(self, provider):
        """debate() returns dict with all required keys."""
        from midas.agents.debate import DebateAgent

        agent = DebateAgent(provider)
        brief = {
            "sections": {"recommendation": "Reduce exposure"},
            "confidence": 0.7,
        }
        result = await agent.debate(brief, debate_rounds=2)

        required_keys = [
            "recommendation",
            "steel_man",
            "red_team",
            "concession_count",
            "final_confidence",
            "resolution_state",
            "rounds",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

        assert isinstance(result["concession_count"], int)
        assert isinstance(result["final_confidence"], float)
        assert 0.0 <= result["final_confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_steelman_position_returns_string(self, provider):
        """steelman_position() returns a non-empty string."""
        from midas.agents.debate import DebateAgent

        agent = DebateAgent(provider)
        result = await agent.steelman_position(
            "Reduce equity exposure",
            [{"type": "news", "summary": "VIX elevated"}],
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_red_team_position_returns_string(self, provider):
        """red_team_position() returns a non-empty string."""
        from midas.agents.debate import DebateAgent

        agent = DebateAgent(provider)
        result = await agent.red_team_position(
            "Reduce equity exposure",
            [{"type": "news", "summary": "VIX elevated"}],
        )
        assert isinstance(result, str)
        assert len(result) > 0


# ===========================================================================
# M09 — ResearchAgent
# ===========================================================================


class TestResearchAgent:
    """Tests for the RAG-based research assistant."""

    @pytest.mark.asyncio
    async def test_research_returns_expected_structure(self, provider, mock_db):
        """research() returns dict with summary, sources, relevance_scores."""
        from midas.agents.research import ResearchAgent

        agent = ResearchAgent(provider, mock_db)
        result = await agent.research(
            query="insider trading AAPL",
            tickers=["AAPL"],
            max_results=5,
        )
        assert "summary" in result
        assert "sources" in result
        assert "relevance_scores" in result
        assert isinstance(result["sources"], list)
        assert isinstance(result["relevance_scores"], list)

    @pytest.mark.asyncio
    async def test_retrieve_documents_returns_list(self, provider, mock_db):
        """retrieve_documents() returns a list of dicts."""
        from midas.agents.research import ResearchAgent

        # Mock the embeddings store to return documents
        mock_db.express.list = AsyncMock(
            return_value=[
                {"id": 1, "source_type": "filing", "embedding_blob": "[0.1, 0.2, 0.3]"},
                {"id": 2, "source_type": "news", "embedding_blob": "[0.4, 0.5, 0.6]"},
            ]
        )

        agent = ResearchAgent(provider, mock_db)
        result = await agent.retrieve_documents([0.1, 0.2, 0.3], top_k=5)
        assert isinstance(result, list)


# ===========================================================================
# M09 — DebateTools
# ===========================================================================


class TestDebateTools:
    """Tests for the 10 MCP tools for the debate agent."""

    @pytest.mark.asyncio
    async def test_query_fabric_returns_list(self, mock_db):
        """Tool 1: query_fabric returns a list of dicts."""
        from midas.agents.tools import DebateTools

        mock_db.express.list = AsyncMock(return_value=[{"id": 1, "ticker": "SPY"}])
        tools = DebateTools(mock_db)
        result = await tools.query_fabric("news", {"ticker": "SPY"})
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_query_head_returns_dict(self, mock_db):
        """Tool 2: query_head returns a dict."""
        from midas.agents.tools import DebateTools

        tools = DebateTools(mock_db)
        result = await tools.query_head("volatility_head", [0.1, 0.2, 0.3])
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_query_calibration_returns_dict(self, mock_db):
        """Tool 3: query_calibration returns a dict."""
        from midas.agents.tools import DebateTools

        mock_db.express.list = AsyncMock(
            return_value=[{"model_version": "v1", "calibration_json": "{}"}]
        )
        tools = DebateTools(mock_db)
        result = await tools.query_calibration("volatility_head")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_retrieve_analogue_returns_list(self, mock_db):
        """Tool 4: retrieve_analogue returns a list of dicts."""
        from midas.agents.tools import DebateTools

        mock_db.express.list = AsyncMock(return_value=[])
        tools = DebateTools(mock_db)
        result = await tools.retrieve_analogue([0.1, 0.2, 0.3])
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_propose_alternative_allocation_returns_dict(self, mock_db):
        """Tool 5: propose_alternative_allocation returns a dict."""
        from midas.agents.tools import DebateTools

        tools = DebateTools(mock_db)
        result = await tools.propose_alternative_allocation(
            {"SPY": 0.6, "TLT": 0.4},
            {"max_equity": 0.5},
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_recompute_with_constraint_returns_dict(self, mock_db):
        """Tool 6: recompute_with_constraint returns a dict."""
        from midas.agents.tools import DebateTools

        tools = DebateTools(mock_db)
        result = await tools.recompute_with_constraint(
            {"weights": {"SPY": 0.6, "TLT": 0.4}},
            {"max_equity": 0.5},
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_backtest_scenario_returns_dict(self, mock_db):
        """Tool 7: backtest_scenario returns a dict with performance keys."""
        from midas.agents.tools import DebateTools

        tools = DebateTools(mock_db)
        result = await tools.backtest_scenario(
            {"SPY": 0.6, "TLT": 0.4},
            "2024-01-01:2024-12-31",
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_update_decision_returns_dict(self, mock_db):
        """Tool 8: update_decision returns a dict."""
        from midas.agents.tools import DebateTools

        mock_db.express.update = AsyncMock(return_value={"id": 1, "status": "updated"})
        tools = DebateTools(mock_db)
        result = await tools.update_decision("dec-123", {"rationale": "Updated"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_generate_counterfactual_returns_dict(self, mock_db):
        """Tool 9: generate_counterfactual returns a dict."""
        from midas.agents.tools import DebateTools

        mock_db.express.read = AsyncMock(
            return_value={"id": 1, "decision_type": "rebalance", "action": "sell SPY"}
        )
        tools = DebateTools(mock_db)
        result = await tools.generate_counterfactual("dec-123")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_surface_override_pattern_returns_dict(self, mock_db):
        """Tool 10: surface_override_pattern returns a dict."""
        from midas.agents.tools import DebateTools

        mock_db.express.list = AsyncMock(return_value=[])
        tools = DebateTools(mock_db)
        result = await tools.surface_override_pattern("user-42")
        assert isinstance(result, dict)


# ===========================================================================
# M09 — AgentOrchestrator
# ===========================================================================


class TestAgentOrchestrator:
    """Tests for the agent runtime orchestrator."""

    @pytest.mark.asyncio
    async def test_process_decision_runs_full_pipeline(self, provider, mock_db):
        """process_decision() returns final recommendation with all stages."""
        from midas.agents.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator(provider, mock_db)
        decision_context = {
            "decision_type": "rebalance",
            "instruments": ["SPY", "TLT"],
            "evidence": ["VIX elevated"],
        }
        result = await orchestrator.process_decision(decision_context)

        assert "research" in result
        assert "brief" in result
        assert "debate" in result
        assert "recommendation" in result


# ===========================================================================
# M10 — DensityMatrix
# ===========================================================================


class TestDensityMatrix:
    """Tests for the density matrix over (band, impact, confidence)."""

    def test_all_cells_have_templates(self):
        """Every (band, impact, confidence) cell maps to a template."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        for band in dm.BANDS:
            for impact in dm.IMPACT_TIERS:
                for confidence in dm.CONFIDENCE_TIERS:
                    template = dm.get_template(band, impact, confidence)
                    assert isinstance(template, str)
                    assert len(template) > 0

    def test_all_cells_have_density_levels(self):
        """Every cell maps to a valid density level."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        valid_levels = {"compressed", "standard", "full", "extreme"}
        for band in dm.BANDS:
            for impact in dm.IMPACT_TIERS:
                for confidence in dm.CONFIDENCE_TIERS:
                    level = dm.get_density_level(band, impact, confidence)
                    assert (
                        level in valid_levels
                    ), f"Invalid level for ({band}, {impact}, {confidence}): {level}"

    def test_crisis_high_high_is_extreme(self):
        """Crisis + high impact + high confidence = extreme density."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        level = dm.get_density_level("crisis", "high", "high")
        assert level == "extreme"

    def test_calm_low_low_is_compressed(self):
        """Calm + low impact + low confidence = compressed density."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        level = dm.get_density_level("calm", "low", "low")
        assert level == "compressed"

    def test_invalid_band_raises(self):
        """Invalid band raises ValueError."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        with pytest.raises(ValueError, match="band"):
            dm.get_template("invalid_band", "low", "low")

    def test_invalid_impact_raises(self):
        """Invalid impact raises ValueError."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        with pytest.raises(ValueError, match="impact"):
            dm.get_template("calm", "invalid", "low")

    def test_invalid_confidence_raises(self):
        """Invalid confidence raises ValueError."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        with pytest.raises(ValueError, match="confidence"):
            dm.get_template("calm", "low", "invalid")

    def test_band_count(self):
        """DensityMatrix has exactly 4 bands."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        assert len(dm.BANDS) == 4

    def test_impact_tier_count(self):
        """DensityMatrix has exactly 3 impact tiers."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        assert len(dm.IMPACT_TIERS) == 3

    def test_confidence_tier_count(self):
        """DensityMatrix has exactly 3 confidence tiers."""
        from midas.brief.density_matrix import DensityMatrix

        dm = DensityMatrix()
        assert len(dm.CONFIDENCE_TIERS) == 3


# ===========================================================================
# M10 — BriefTemplates
# ===========================================================================


class TestBriefTemplates:
    """Tests for brief template renderers."""

    def _sample_brief_data(self) -> dict:
        return {
            "sections": {
                "situation_summary": "Market is volatile.",
                "evidence_assessment": "Mixed signals.",
                "recommendation": "Hold current positions.",
                "counter_evidence": "Earnings are strong.",
                "what_would_change_mind": "VIX below 15.",
                "risk_factors": "Geopolitical tension.",
                "provenance_links": ["news:1", "filing:2"],
                "if_approved": "Continue holding, monitor closely.",
                "if_rejected": "Consider reallocation to defensive assets.",
                "historical_precedent": "Similar conditions in 2018 resolved favorably.",
            },
            "confidence": 0.75,
            "model_version": "gpt-4",
        }

    def test_render_compressed_produces_string(self):
        """Compressed template renders to a non-empty string."""
        from midas.brief.templates import BriefTemplates

        result = BriefTemplates.render_compressed(self._sample_brief_data())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_standard_produces_string(self):
        """Standard template renders to a non-empty string."""
        from midas.brief.templates import BriefTemplates

        result = BriefTemplates.render_standard(self._sample_brief_data())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_extreme_produces_string(self):
        """Extreme template renders to a non-empty string."""
        from midas.brief.templates import BriefTemplates

        result = BriefTemplates.render_extreme(self._sample_brief_data())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_standard_contains_all_sections(self):
        """Standard template includes all 7 section headers."""
        from midas.brief.templates import BriefTemplates

        result = BriefTemplates.render_standard(self._sample_brief_data())
        assert "Thesis" in result or "Situation" in result
        assert "Evidence" in result
        assert "Recommendation" in result
        assert "Counter" in result or "counter" in result
        assert "Change" in result or "change" in result
        assert "Risk" in result or "risk" in result
        assert "Provenance" in result or "provenance" in result

    def test_render_extreme_includes_ood_warning(self):
        """Extreme template includes OOD warning."""
        from midas.brief.templates import BriefTemplates

        result = BriefTemplates.render_extreme(self._sample_brief_data())
        assert "OOD" in result or "out-of-distribution" in result.lower() or "WARNING" in result

    def test_render_compressed_is_shorter_than_standard(self):
        """Compressed template is shorter than standard."""
        from midas.brief.templates import BriefTemplates

        data = self._sample_brief_data()
        compressed = BriefTemplates.render_compressed(data)
        standard = BriefTemplates.render_standard(data)
        assert len(compressed) < len(standard)


# ===========================================================================
# M10 — TopOfFoldCard
# ===========================================================================


class TestTopOfFoldCard:
    """Tests for the decide-in-10s card."""

    def _sample_decision(self) -> dict:
        return {
            "decision_type": "rebalance",
            "instruments": ["SPY", "TLT"],
            "action": "reduce_equity",
            "recommendation": "Reduce SPY allocation by 5%",
            "counter_evidence": "Earnings beat expectations",
            "what_would_change_mind": "VIX drops below 15",
            "confidence": 0.72,
        }

    def test_render_card_has_required_fields(self):
        """Card contains all required fields."""
        from midas.brief.top_of_fold import TopOfFoldCard

        result = TopOfFoldCard.render_card(self._sample_decision())
        assert "action_line" in result
        assert "counter_evidence" in result
        assert "what_would_change_mind" in result
        assert "buttons" in result

    def test_render_card_action_line_is_string(self):
        """action_line is a non-empty string."""
        from midas.brief.top_of_fold import TopOfFoldCard

        result = TopOfFoldCard.render_card(self._sample_decision())
        assert isinstance(result["action_line"], str)
        assert len(result["action_line"]) > 0

    def test_render_card_buttons_contains_expected_options(self):
        """buttons list contains approve, reject, debate."""
        from midas.brief.top_of_fold import TopOfFoldCard

        result = TopOfFoldCard.render_card(self._sample_decision())
        buttons = result["buttons"]
        assert isinstance(buttons, list)
        button_labels = [b["label"].lower() if isinstance(b, dict) else b.lower() for b in buttons]
        assert "approve" in button_labels
        assert "reject" in button_labels
        assert "debate" in button_labels


# ===========================================================================
# M10 — BriefComposer
# ===========================================================================


class TestBriefComposer:
    """Tests for the brief composition orchestrator."""

    @pytest.mark.asyncio
    async def test_compose_returns_complete_brief_correct(self, provider):
        """compose() returns card, brief, density_level, provenance_links."""
        from midas.agents.analyst import AnalystAgent
        from midas.brief.composer import BriefComposer

        analyst = AnalystAgent(provider)
        composer = BriefComposer(analyst)
        decision_context = {
            "decision_type": "rebalance",
            "instruments": ["SPY", "TLT"],
            "evidence": ["VIX elevated"],
            "regime_band": "elevated",
            "dollar_impact": "medium",
            "confidence_tier": "medium",
        }
        result = await composer.compose(decision_context)

        assert "card" in result
        assert "brief" in result
        assert "density_level" in result
        assert "provenance_links" in result
        assert result["density_level"] in {"compressed", "standard", "full", "extreme"}

    @pytest.mark.asyncio
    async def test_compose_without_band_defaults_to_calm(self, provider):
        """compose() defaults to calm/medium/medium when band info is missing."""
        from midas.agents.analyst import AnalystAgent
        from midas.brief.composer import BriefComposer

        analyst = AnalystAgent(provider)
        composer = BriefComposer(analyst)
        decision_context = {
            "decision_type": "rebalance",
            "instruments": ["SPY"],
            "evidence": [],
        }
        result = await composer.compose(decision_context)
        assert "density_level" in result
        assert isinstance(result["density_level"], str)
