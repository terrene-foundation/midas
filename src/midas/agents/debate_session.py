from __future__ import annotations

"""DebateSession — multi-turn debate with 10-tool dispatch.

Wraps DebateAgent + DebateTools so each turn the LLM may call any of
the 10 spec tools (query_fabric, query_head, query_calibration,
retrieve_analogue, backtest_scenario, update_decision,
generate_counterfactual, surface_override_pattern,
propose_alternative_allocation, recompute_with_constraint).

Tool results are injected back into the LLM context for evidence-grounded
conversation. The ``update_decision`` tool triggers "decision updated"
resolution state.

Ref: specs/07 S3.3 (10-tool table), S3.5 (live context)
"""

import json
import time

import structlog

logger = structlog.get_logger("midas.agents.debate_session")

TOOL_REGISTRY = {
    "query_fabric": "query_fabric",
    "query_head": "query_head",
    "query_calibration": "query_calibration",
    "retrieve_analogue": "retrieve_analogue",
    "backtest_scenario": "backtest_scenario",
    "update_decision": "update_decision",
    "generate_counterfactual": "generate_counterfactual",
    "surface_override_pattern": "surface_override_pattern",
    "propose_alternative_allocation": "propose_alternative_allocation",
    "recompute_with_constraint": "recompute_with_constraint",
}

VALID_RESOLUTION_STATES = frozenset({"updated", "maintained", "open", "envelope_change"})

DEBATE_SESSION_SYSTEM_PROMPT = (
    "You are a debate session manager for investment decisions. "
    "You run steelman/red-team debate rounds with tool access. "
    "Each turn you may call tools to gather evidence. "
    "Respond with valid JSON containing: "
    '"steel_man" (string), "red_team" (string), '
    '"tool_calls" (array of {tool, args} — may be empty), '
    '"concession_count" (integer), '
    '"resolution_state" (one of: "updated", "maintained", "open", "envelope_change"), '
    '"summary" (string — concise round summary).'
)


class DebateSession:
    """Multi-turn debate with tool dispatch.

    Parameters
    ----------
    agent:
        A DebateAgent instance.
    tools:
        A DebateTools instance.
    decision_id:
        ID of the decision being debated (for update_decision targeting).
    max_turns:
        Maximum debate turns before forcing a resolution.
    """

    def __init__(
        self,
        agent,
        tools,
        decision_id: str,
        max_turns: int = 5,
    ) -> None:
        self._agent = agent
        self._tools = tools
        self._decision_id = decision_id
        self._max_turns = max_turns
        self._thread_id: str | None = None
        self._concession_count = 0

    async def run(
        self,
        db,
        brief: dict,
        user_position: str | None = None,
        debate_rounds: int = 3,
    ) -> dict:
        """Execute multi-turn debate with tool dispatch.

        Parameters
        ----------
        db:
            DataFlow instance for thread persistence.
        brief:
            The brief dict from AnalystAgent.compose_brief.
        user_position:
            Optional user-stated position.
        debate_rounds:
            Number of debate rounds (each round = steelman + red-team).

        Returns
        -------
        dict
            Keys: 'recommendation', 'steel_man', 'red_team',
            'concession_count', 'final_confidence', 'rounds',
            'resolution_state', 'tool_calls_log', 'thread_id'.
        """
        # Create persistent thread
        thread = await self._agent.create_thread(db, self._decision_id, brief)
        self._thread_id = thread["thread_id"]

        position = user_position or brief.get("sections", {}).get(
            "recommendation", "the proposed action"
        )
        brief_summary = json.dumps(brief.get("sections", {}), indent=2)

        tool_calls_log: list[dict] = []
        final_result: dict = {}

        for round_num in range(debate_rounds):
            round_prompt = self._build_round_prompt(
                round_num, debate_rounds, position, brief_summary, final_result
            )

            turn = await self._agent.add_turn(db, self._thread_id, round_prompt, brief)
            response_text = turn.get("response", "")

            # Parse LLM response for tool calls
            parsed = self._parse_response(response_text)
            if not parsed:
                final_result = {
                    "steel_man": response_text[:200],
                    "red_team": "",
                    "concession_count": self._concession_count,
                    "resolution_state": "open",
                    "summary": f"Round {round_num + 1}: parse failure, continuing",
                }
                continue

            # Dispatch tool calls
            if parsed.get("tool_calls"):
                tool_results = await self._dispatch_tools(parsed["tool_calls"])
                tool_calls_log.extend(tool_results)
                # Inject tool results back for next round context
                brief_summary += f"\n\n[Tool Results Round {round_num + 1}]\n"
                for tr in tool_results:
                    brief_summary += json.dumps(tr, default=str) + "\n"

            self._concession_count = max(self._concession_count, parsed.get("concession_count", 0))

            resolution = parsed.get("resolution_state", "open")
            if resolution not in VALID_RESOLUTION_STATES:
                resolution = "open"

            final_result = {
                "steel_man": parsed.get("steel_man", ""),
                "red_team": parsed.get("red_team", ""),
                "concession_count": self._concession_count,
                "resolution_state": resolution,
                "summary": parsed.get("summary", ""),
            }

            # If update_decision was called, mark resolution as updated
            if any(tc.get("tool") == "update_decision" for tc in parsed.get("tool_calls", [])):
                final_result["resolution_state"] = "updated"
                logger.info(
                    "debate_session.decision_updated",
                    decision_id=self._decision_id,
                    round=round_num + 1,
                )

            logger.info(
                "debate_session.round_complete",
                round=round_num + 1,
                resolution=resolution,
                tool_calls=len(parsed.get("tool_calls", [])),
            )

        # Final aggregation
        final_result.update(
            {
                "recommendation": position,
                "rounds": debate_rounds,
                "tool_calls_log": tool_calls_log,
                "thread_id": self._thread_id,
                "final_confidence": self._estimate_confidence(final_result),
            }
        )

        # Persist final state
        if self._thread_id:
            await self._agent.update_thread_status(
                db, self._thread_id, final_result["resolution_state"]
            )

        logger.info(
            "debate_session.complete",
            resolution=final_result["resolution_state"],
            rounds=debate_rounds,
            total_tool_calls=len(tool_calls_log),
            concessions=self._concession_count,
        )

        return final_result

    def _build_round_prompt(
        self,
        round_num: int,
        total_rounds: int,
        position: str,
        brief_summary: str,
        previous_result: dict,
    ) -> str:
        """Build the prompt for a specific debate round."""
        prompt = (
            f"Debate round {round_num + 1} of {total_rounds}.\n"
            f"Position: {position}\n"
            f"Brief:\n{brief_summary}\n"
        )
        if previous_result:
            prompt += (
                f"\nPrevious round summary: {previous_result.get('summary', 'N/A')}\n"
                f"Previous steelman: {previous_result.get('steel_man', 'N/A')[:200]}\n"
                f"Previous red-team: {previous_result.get('red_team', 'N/A')[:200]}\n"
            )
        if round_num == total_rounds - 1:
            prompt += (
                "\nThis is the final round. Provide your concluding assessment "
                "with a final resolution_state."
            )
        prompt += (
            "\nRespond with JSON: steel_man, red_team, tool_calls (array of "
            "{tool, args} or empty), concession_count, resolution_state, summary."
        )
        return prompt

    def _parse_response(self, text: str) -> dict | None:
        """Parse LLM response JSON, tolerating markdown fences."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON block in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return None

    async def _dispatch_tools(self, tool_calls: list[dict]) -> list[dict]:
        """Dispatch tool calls and return results."""
        results: list[dict] = []
        for call in tool_calls:
            tool_name = call.get("tool", "")
            args = call.get("args") or {}
            method_name = TOOL_REGISTRY.get(tool_name)
            if not method_name:
                results.append(
                    {
                        "tool": tool_name,
                        "status": "error",
                        "error": f"Unknown tool: {tool_name}",
                    }
                )
                continue

            method = getattr(self._tools, method_name, None)
            if method is None:
                results.append(
                    {
                        "tool": tool_name,
                        "status": "error",
                        "error": f"Tool method not found: {method_name}",
                    }
                )
                continue

            t0 = time.monotonic()
            try:
                if isinstance(args, dict):
                    result = await method(**args)
                elif isinstance(args, list):
                    result = await method(*args)
                else:
                    result = await method(args)
                elapsed = time.monotonic() - t0
                logger.info(
                    "debate_session.tool_dispatched",
                    tool=tool_name,
                    latency_ms=round(elapsed * 1000),
                    status="ok",
                )
                results.append(
                    {
                        "tool": tool_name,
                        "status": "ok",
                        "latency_ms": round(elapsed * 1000),
                        "result": _truncate(str(result), 500),
                    }
                )
            except Exception as exc:
                elapsed = time.monotonic() - t0
                logger.warning(
                    "debate_session.tool_failed",
                    tool=tool_name,
                    error=str(exc),
                    latency_ms=round(elapsed * 1000),
                )
                results.append(
                    {
                        "tool": tool_name,
                        "status": "error",
                        "latency_ms": round(elapsed * 1000),
                        "error": str(exc),
                    }
                )
        return results

    def _estimate_confidence(self, result: dict) -> float:
        """Estimate final confidence from resolution state and concessions."""
        base = 0.5
        state = result.get("resolution_state", "open")
        if state == "maintained":
            base = 0.7
        elif state == "updated":
            base = 0.6
        elif state == "envelope_change":
            base = 0.3
        # Each concession reduces confidence
        concessions = result.get("concession_count", 0)
        return max(0.05, min(1.0, base - concessions * 0.05))


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
