"""Agent runtime orchestrator — coordinates Analyst, Debate, Research agents.

Provides the top-level process_decision pipeline that runs research,
brief composition, multi-turn debate with tool dispatch, and produces
a final recommendation.
"""

import structlog

logger = structlog.get_logger("midas.agents.orchestrator")


class AgentOrchestrator:
    """Orchestrates Analyst, Debate, Research agents.

    Runs the full decision processing pipeline:
    1. Research — gather relevant documents and context
    2. Brief — compose structured analyst brief
    3. Debate — run multi-turn steelman/red-team debate with tool access
    4. Final recommendation — aggregate all outputs
    """

    def __init__(self, provider, db):
        from midas.agents.analyst import AnalystAgent
        from midas.agents.debate import DebateAgent
        from midas.agents.research import ResearchAgent
        from midas.agents.tools import DebateTools

        self.tools = DebateTools(db)
        self.analyst = AnalystAgent(provider)
        self.debate = DebateAgent(provider, tools=self.tools)
        self.research = ResearchAgent(provider, db)
        self._db = db

    async def process_decision(self, decision_context: dict) -> dict:
        """Full pipeline: research -> brief -> debate -> final recommendation.

        Parameters
        ----------
        decision_context:
            Dict with decision_type, instruments, evidence, and optional
            regime/market metadata.

        Returns
        -------
        dict
            Keys: 'research', 'brief', 'debate', 'recommendation'.
        """
        instruments = decision_context.get("instruments", [])
        decision_id = decision_context.get("decision_id", "default")

        logger.info(
            "orchestrator.process_decision",
            decision_type=decision_context.get("decision_type"),
            instruments=instruments,
        )

        # Stage 1: Research
        research_result = await self.research.research(
            query=str(decision_context.get("decision_type", "general")),
            tickers=instruments if instruments else None,
        )
        logger.info(
            "orchestrator.research_complete",
            sources=len(research_result.get("sources", [])),
        )

        # Enrich context with research findings
        enriched_context = dict(decision_context)
        enriched_context["research_summary"] = research_result.get("summary", "")
        enriched_context["research_sources"] = research_result.get("sources", [])

        # Stage 2: Brief
        brief = await self.analyst.compose_brief(enriched_context)
        logger.info(
            "orchestrator.brief_complete",
            confidence=brief.get("confidence"),
        )

        # Stage 3: Multi-turn debate with tool dispatch
        from midas.agents.debate_session import DebateSession

        session = DebateSession(
            agent=self.debate,
            tools=self.tools,
            decision_id=decision_id,
        )
        debate_rounds = decision_context.get("debate_rounds", 3)
        debate_result = await session.run(
            db=self._db,
            brief=brief,
            debate_rounds=debate_rounds,
        )
        logger.info(
            "orchestrator.debate_complete",
            final_confidence=debate_result.get("final_confidence"),
            concessions=debate_result.get("concession_count"),
            resolution=debate_result.get("resolution_state"),
            tool_calls=len(debate_result.get("tool_calls_log", [])),
        )

        # Stage 4: Final recommendation
        recommendation = {
            "action": debate_result.get(
                "recommendation", brief.get("sections", {}).get("recommendation", "")
            ),
            "confidence": debate_result.get("final_confidence", brief.get("confidence", 0.0)),
            "steel_man": debate_result.get("steel_man", ""),
            "red_team": debate_result.get("red_team", ""),
            "concession_count": debate_result.get("concession_count", 0),
            "instruments": instruments,
            "decision_type": decision_context.get("decision_type", ""),
            "resolution_state": debate_result.get("resolution_state", "open"),
        }

        logger.info(
            "orchestrator.process_decision_complete",
            action=recommendation["action"][:80],
            confidence=recommendation["confidence"],
        )

        return {
            "research": research_result,
            "brief": brief,
            "debate": debate_result,
            "recommendation": recommendation,
        }
