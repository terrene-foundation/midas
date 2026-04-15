"""Agent runtime orchestrator — coordinates Analyst, Debate, Research agents.

Provides the top-level process_decision pipeline that runs research,
brief composition, debate, and produces a final recommendation.
"""

import structlog

logger = structlog.get_logger("midas.agents.orchestrator")


class AgentOrchestrator:
    """Orchestrates Analyst, Debate, Research agents.

    Runs the full decision processing pipeline:
    1. Research — gather relevant documents and context
    2. Brief — compose structured analyst brief
    3. Debate — run steelman/red-team debate
    4. Final recommendation — aggregate all outputs
    """

    def __init__(self, provider, db):
        from midas.agents.analyst import AnalystAgent
        from midas.agents.debate import DebateAgent
        from midas.agents.research import ResearchAgent
        from midas.agents.tools import DebateTools

        self.analyst = AnalystAgent(provider)
        self.debate = DebateAgent(provider)
        self.research = ResearchAgent(provider, db)
        self.tools = DebateTools(db)

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

        # Stage 3: Debate
        debate_result = await self.debate.debate(brief)
        logger.info(
            "orchestrator.debate_complete",
            final_confidence=debate_result.get("final_confidence"),
            concessions=debate_result.get("concession_count"),
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
