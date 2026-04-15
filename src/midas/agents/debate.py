"""Debate agent — steelman/red-team structured debate.

Runs a multi-round debate between a steel-man advocate and a red-team
critic, producing a final recommendation with concessions tracked.
"""

import json

import structlog

logger = structlog.get_logger("midas.agents.debate")


class DebateAgent:
    """Steelman/red-team debate agent with tool access.

    Runs structured debate rounds where the steel-man advocate builds the
    strongest case for the brief's recommendation and the red-team builds
    the strongest case against it. Tracks concessions and produces a final
    confidence-adjusted recommendation.
    """

    DEBATE_SYSTEM_PROMPT = (
        "You are a debate moderator for investment decisions. "
        "You MUST respond with valid JSON only, no markdown fences. "
        "The JSON must have keys: "
        '"recommendation" (string), '
        '"steel_man" (string), '
        '"red_team" (string), '
        '"concession_count" (integer), '
        '"final_confidence" (float between 0.0 and 1.0), '
        'and "rounds" (integer).'
    )

    STEELMAN_SYSTEM_PROMPT = (
        "You are the strongest possible advocate for a given investment position. "
        "Build the most compelling case using the provided evidence. "
        "Respond with a clear, persuasive paragraph."
    )

    RED_TEAM_SYSTEM_PROMPT = (
        "You are the strongest possible critic of a given investment position. "
        "Build the most compelling case against using the provided evidence. "
        "Respond with a clear, critical paragraph."
    )

    def __init__(self, provider):
        self._provider = provider

    async def debate(
        self,
        brief: dict,
        user_position: str | None = None,
        debate_rounds: int = 3,
    ) -> dict:
        """Run structured debate.

        Parameters
        ----------
        brief:
            The brief dict from AnalystAgent.compose_brief.
        user_position:
            Optional user-stated position to debate around.
        debate_rounds:
            Number of debate rounds (default 3).

        Returns
        -------
        dict
            Keys: 'recommendation', 'steel_man', 'red_team',
            'concession_count', 'final_confidence', 'rounds'.
        """
        brief_summary = json.dumps(brief.get("sections", {}), indent=2)
        position = user_position or brief.get("sections", {}).get(
            "recommendation", "the proposed action"
        )

        user_message = (
            f"Debate rounds requested: {debate_rounds}\n"
            f"Position to debate: {position}\n"
            f"Brief summary:\n{brief_summary}\n"
            f"Run the full debate and produce a final structured JSON result."
        )

        messages = [
            {"role": "system", "content": self.DEBATE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        result = await self._provider.complete(
            messages=messages,
            temperature=0.5,
            max_tokens=2048,
        )

        try:
            parsed = json.loads(result["content"])
        except json.JSONDecodeError:
            logger.warning("debate.result.parse_failed", content=result["content"][:200])
            parsed = {
                "recommendation": result["content"],
                "steel_man": "Parsing failed.",
                "red_team": "Parsing failed.",
                "concession_count": 0,
                "final_confidence": brief.get("confidence", 0.5),
                "rounds": debate_rounds,
            }

        parsed.setdefault("rounds", debate_rounds)

        logger.info(
            "debate.complete",
            concession_count=parsed.get("concession_count"),
            final_confidence=parsed.get("final_confidence"),
        )

        return parsed

    async def steelman_position(self, position: str, evidence: list[dict]) -> str:
        """Build strongest case for the given position.

        Parameters
        ----------
        position:
            The position to advocate for.
        evidence:
            List of evidence items to draw from.

        Returns
        -------
        str
            The steel-man argument.
        """
        messages = [
            {"role": "system", "content": self.STEELMAN_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Position: {position}\n"
                    f"Evidence: {json.dumps(evidence)}\n"
                    f"Build the strongest possible case for this position."
                ),
            },
        ]

        result = await self._provider.complete(
            messages=messages,
            temperature=0.5,
            max_tokens=1024,
        )

        logger.info("debate.steelman_complete", position=position[:80])
        return result["content"]

    async def red_team_position(self, position: str, evidence: list[dict]) -> str:
        """Build strongest case against the given position.

        Parameters
        ----------
        position:
            The position to argue against.
        evidence:
            List of evidence items to draw from.

        Returns
        -------
        str
            The red-team argument.
        """
        messages = [
            {"role": "system", "content": self.RED_TEAM_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Position: {position}\n"
                    f"Evidence: {json.dumps(evidence)}\n"
                    f"Build the strongest possible case against this position."
                ),
            },
        ]

        result = await self._provider.complete(
            messages=messages,
            temperature=0.5,
            max_tokens=1024,
        )

        logger.info("debate.red_team_complete", position=position[:80])
        return result["content"]
