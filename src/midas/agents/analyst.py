"""Analyst agent — produces structured briefs from decision context.

Generates a 10-section brief with confidence assessment using the frontier
LLM provider. The brief is the primary output that feeds into the debate
and composition pipeline.
"""

import json

import structlog

logger = structlog.get_logger("midas.agents.analyst")


class AnalystAgent:
    """Produces structured briefs from decision context.

    The brief contains 10 sections:
    1. Situation summary
    2. Evidence assessment (with confidence distribution)
    3. Recommendation
    4. Counter-evidence
    5. What would change my mind
    6. Risk factors
    7. Provenance links
    8. If approved — expected outcomes and next steps
    9. If rejected — alternative actions and consequences
    10. Historical precedent — analogous past decisions and outcomes
    """

    BRIEF_SYSTEM_PROMPT = (
        "You are an investment analyst producing structured briefs. "
        "You MUST respond with valid JSON only, no markdown fences. "
        "The JSON must have keys: "
        '"sections" (an object with keys: situation_summary, evidence_assessment, '
        "recommendation, counter_evidence, what_would_change_mind, risk_factors, "
        "provenance_links, if_approved, if_rejected, historical_precedent), "
        '"confidence" (a float between 0.0 and 1.0), '
        'and "model_version" (a string).'
    )

    def __init__(self, provider):
        self._provider = provider

    async def compose_brief(self, decision_context: dict) -> dict:
        """Produce structured brief from decision context.

        Parameters
        ----------
        decision_context:
            Dict with decision_type, instruments, evidence, and optional
            regime/market metadata.

        Returns
        -------
        dict
            Keys: 'sections', 'confidence', 'model_version'.
        """
        user_message = (
            f"Decision type: {decision_context.get('decision_type', 'unknown')}\n"
            f"Instruments: {json.dumps(decision_context.get('instruments', []))}\n"
            f"Evidence: {json.dumps(decision_context.get('evidence', []))}\n"
            f"Market context: {json.dumps(decision_context.get('market_context', {}))}\n"
            f"Produce a structured investment brief in JSON format."
        )

        messages = [
            {"role": "system", "content": self.BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        result = await self._provider.complete(
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )

        try:
            parsed = json.loads(result["content"])
        except json.JSONDecodeError:
            logger.warning("analyst.brief.parse_failed", content=result["content"][:200])
            parsed = {
                "sections": {
                    "situation_summary": result["content"],
                    "evidence_assessment": "Unable to parse structured assessment.",
                    "recommendation": "Review raw LLM output manually.",
                    "counter_evidence": "N/A",
                    "what_would_change_mind": "N/A",
                    "risk_factors": "Parsing failure indicates uncertain output.",
                    "provenance_links": [],
                    "if_approved": "N/A",
                    "if_rejected": "N/A",
                    "historical_precedent": "N/A",
                },
                "confidence": 0.0,
                "model_version": result.get("model", "unknown"),
            }

        parsed.setdefault("model_version", result.get("model", "unknown"))

        logger.info(
            "analyst.compose_brief",
            confidence=parsed.get("confidence"),
            model=parsed.get("model_version"),
        )

        return parsed
