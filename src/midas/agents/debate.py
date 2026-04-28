"""Debate agent — steelman/red-team structured debate.

Runs multi-round debate between a steel-man advocate and a red-team
critic, with live portfolio context injected before each turn.
Thread state is persisted in DataFlow for multi-turn conversations.

Ref: specs/07 S3.5 (live portfolio context), S3.6 (stateful threads)
"""

import json
import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger("midas.agents.debate")


class DebateAgent:
    """Steelman/red-team debate agent with tool access and multi-turn support.

    Runs structured debate rounds where the steel-man advocate builds the
    strongest case for the brief's recommendation and the red-team builds
    the strongest case against it. Tracks concessions and produces a final
    confidence-adjusted recommendation.

    Multi-turn: each turn receives the full portfolio context (positions,
    weights, regime state, P&L) injected before the LLM call. Thread state
    is persisted in DataFlow via the ``debate_threads`` fabric table.
    """

    DEBATE_SYSTEM_PROMPT = (
        "You are a debate moderator for investment decisions. "
        "You MUST disagree when evidence warrants it; do not confabulate or "
        "default to agreement. The red_team argument must be substantive and "
        "evidence-based, not perfunctory. "
        "You MUST respond with valid JSON only, no markdown fences. "
        "The JSON must have keys: "
        '"recommendation" (string), '
        '"steel_man" (string), '
        '"red_team" (string), '
        '"concession_count" (integer), '
        '"final_confidence" (float between 0.0 and 1.0), '
        '"resolution_state" (one of: "updated", "maintained", "open", "envelope_change"), '
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

    def __init__(self, provider, tools=None):
        self._provider = provider
        self._tools = tools

    # -------------------------------------------------------------------------
    # Thread management (DataFlow-backed)
    # -------------------------------------------------------------------------

    async def create_thread(
        self,
        db,
        decision_id: str,
        brief: dict | None = None,
    ) -> dict:
        """Create a new debate thread persisted in DataFlow.

        Parameters
        ----------
        db:
            DataFlow instance for persistence.
        decision_id:
            ID of the decision this thread is debating.
        brief:
            Optional initial brief/context for the debate.

        Returns
        -------
        dict
            Keys: 'thread_id', 'decision_id', 'status', 'turns', 'portfolio_context'.
        """
        thread_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Fetch initial portfolio context for the thread
        portfolio_context = await self._build_portfolio_context(db, brief)

        row = {
            "thread_id": thread_id,
            "decision_id": decision_id,
            "status": "open",
            "turns_json": "[]",
            "portfolio_context_json": json.dumps(portfolio_context),
            "created_at": now,
        }

        await db.express.create("debate_threads", row)

        logger.info(
            "debate.thread_created",
            thread_id=thread_id,
            decision_id=decision_id,
        )

        return {
            "thread_id": thread_id,
            "decision_id": decision_id,
            "status": "open",
            "turns": [],
            "portfolio_context": portfolio_context,
        }

    async def get_thread(self, db, thread_id: str) -> dict | None:
        """Retrieve a debate thread by thread_id.

        Parameters
        ----------
        db:
            DataFlow instance.
        thread_id:
            UUID of the thread.

        Returns
        -------
        dict | None
            Thread data or None if not found.
        """
        rows = await db.express.list("debate_threads", filter={"thread_id": thread_id})
        if not rows:
            return None

        row = rows[0]
        try:
            turns = json.loads(row.get("turns_json", "[]"))
        except json.JSONDecodeError:
            turns = []

        try:
            portfolio_context = json.loads(row.get("portfolio_context_json", "{}"))
        except json.JSONDecodeError:
            portfolio_context = {}

        return {
            "thread_id": row["thread_id"],
            "decision_id": row["decision_id"],
            "status": row.get("status", "open"),
            "turns": turns,
            "portfolio_context": portfolio_context,
            "created_at": row.get("created_at", ""),
        }

    async def update_thread_status(self, db, thread_id: str, status: str) -> None:
        """Update the status of a debate thread."""
        rows = await db.express.list("debate_threads", filter={"thread_id": thread_id})
        if rows:
            await db.express.update("debate_threads", str(rows[0]["id"]), {"status": status})
            logger.info("debate.thread_status_updated", thread_id=thread_id, status=status)

    # -------------------------------------------------------------------------
    # Multi-turn debate
    # -------------------------------------------------------------------------

    async def add_turn(
        self,
        db,
        thread_id: str,
        user_message: str,
        brief: dict | None = None,
    ) -> dict:
        """Add a debate turn to an existing thread with live portfolio context.

        Injects fresh portfolio positions, weights, regime state, and P&L
        before each LLM call. Appends the turn to the thread's turn history
        in DataFlow.

        Parameters
        ----------
        db:
            DataFlow instance for persistence.
        thread_id:
            UUID of the existing debate thread.
        user_message:
            The user's message or position for this turn.
        brief:
            Optional brief dict from AnalystAgent.compose_brief.

        Returns
        -------
        dict
            Keys: 'thread_id', 'turn_number', 'response', 'turns',
            'portfolio_context', 'provenance_pointers'.
        """
        # Retrieve existing thread
        thread = await self.get_thread(db, thread_id)
        if thread is None:
            raise ValueError(f"Thread {thread_id} not found")

        prior_turns = thread.get("turns", [])

        # Build live portfolio context (fresh data every turn)
        portfolio_context = await self._build_portfolio_context(db, brief)

        # Build the full context injected into the LLM
        live_context_str = self._format_portfolio_context(portfolio_context)
        brief_summary = json.dumps(brief.get("sections", {}), indent=2) if brief else ""

        # Construct the turn prompt with full context + prior turns
        turn_prompt = self._build_turn_prompt(
            user_message=user_message,
            prior_turns=prior_turns,
            brief_summary=brief_summary,
            live_context=live_context_str,
        )

        messages = [
            {"role": "system", "content": self.DEBATE_SYSTEM_PROMPT},
            {"role": "user", "content": turn_prompt},
        ]

        result = await self._provider.complete(
            messages=messages,
            temperature=0.5,
            max_tokens=2048,
        )

        try:
            parsed = json.loads(result["content"])
        except json.JSONDecodeError:
            logger.warning(
                "debate.turn.parse_failed",
                thread_id=thread_id,
                content=result["content"][:200],
            )
            parsed = {
                "recommendation": "parse_failed",
                "steel_man": "",
                "red_team": "",
                "concession_count": 0,
                "final_confidence": 0.0,
                "resolution_state": "open",
                "parse_error": True,
                "raw_content_preview": result["content"][:100],
            }

        # Build provenance pointers for this turn
        provenance = self._build_provenance_pointers(portfolio_context, brief)

        # Build the turn record
        turn_record = {
            "turn_number": len(prior_turns) + 1,
            "user_message": user_message,
            "response": parsed,
            "portfolio_context_snapshot": portfolio_context,
            "provenance_pointers": provenance,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Append turn to thread history
        updated_turns = prior_turns + [turn_record]
        rows = await db.express.list("debate_threads", filter={"thread_id": thread_id})
        if rows:
            await db.express.update(
                "debate_threads",
                str(rows[0]["id"]),
                {
                    "turns_json": json.dumps(updated_turns),
                    "portfolio_context_json": json.dumps(portfolio_context),
                },
            )

        # Update thread status based on resolution state
        resolution = parsed.get("resolution_state", "open")
        await self.update_thread_status(db, thread_id, resolution)

        logger.info(
            "debate.turn_added",
            thread_id=thread_id,
            turn_number=turn_record["turn_number"],
            resolution_state=resolution,
            final_confidence=parsed.get("final_confidence"),
        )

        return {
            "thread_id": thread_id,
            "turn_number": turn_record["turn_number"],
            "response": parsed,
            "turns": updated_turns,
            "portfolio_context": portfolio_context,
            "provenance_pointers": provenance,
            "status": resolution,
        }

    def _build_turn_prompt(
        self,
        user_message: str,
        prior_turns: list[dict],
        brief_summary: str,
        live_context: str,
    ) -> str:
        """Build the full prompt for a debate turn.

        Includes: user message, prior turns history, brief summary,
        and live portfolio context.
        """
        prompt_parts = [
            f"User message: {user_message}",
        ]

        # Prior turns history
        if prior_turns:
            prompt_parts.append("\n=== PRIOR DEBATE TURNS ===")
            for turn in prior_turns:
                resp = turn.get("response", {})
                prompt_parts.append(
                    f"\n--- Turn {turn.get('turn_number')} ---\n"
                    f"User: {turn.get('user_message', '')}\n"
                    f"Steel-man: {resp.get('steel_man', '')}\n"
                    f"Red-team: {resp.get('red_team', '')}\n"
                    f"Concessions: {resp.get('concession_count', 0)}, "
                    f"Confidence: {resp.get('final_confidence', 0.0)}, "
                    f"Resolution: {resp.get('resolution_state', 'open')}"
                )

        # Brief summary
        if brief_summary:
            prompt_parts.append(f"\n=== BRIEF ===\n{brief_summary}")

        # Live portfolio context
        if live_context:
            prompt_parts.append(f"\n=== LIVE PORTFOLIO CONTEXT ===\n{live_context}")

        prompt_parts.append(
            "\nRespond with a single JSON object with keys: "
            "recommendation, steel_man, red_team, concession_count, "
            "final_confidence, resolution_state, rounds."
        )

        return "\n".join(prompt_parts)

    # -------------------------------------------------------------------------
    # Portfolio context (live data from DataFlow)
    # -------------------------------------------------------------------------

    async def _build_portfolio_context(self, db, brief: dict | None = None) -> dict:
        """Build live portfolio context from DataFlow.

        Fetches current positions, weights, unrealized P&L, and regime state
        from the fabric database.

        Parameters
        ----------
        db:
            DataFlow instance.
        brief:
            Optional brief dict to extract relevant instruments.

        Returns
        -------
        dict
            Portfolio context with positions, weights, regime, and P&L.
        """
        instruments = []
        if brief:
            instruments_raw = brief.get("instruments", [])
            if isinstance(instruments_raw, str):
                instruments = [i.strip() for i in instruments_raw.split(",") if i.strip()]
            elif isinstance(instruments_raw, list):
                instruments = instruments_raw

        context: dict = {"positions": [], "regime": {}, "weights": {}}

        # Fetch positions
        try:
            positions = await db.express.list("positions")
            if positions:
                total_value = sum(float(p.get("market_value", 0) or 0) for p in positions)
                context["nav"] = total_value
                context["positions_count"] = len(positions)

                position_summaries = []
                for p in positions:
                    ticker = p.get("ticker", "?")
                    mv = float(p.get("market_value", 0) or 0)
                    pnl = float(p.get("unrealized_pnl", 0) or 0)
                    quantity = float(p.get("quantity", 0) or 0)
                    avg_cost = float(p.get("avg_cost", 0) or 0)
                    position_summaries.append(
                        {
                            "ticker": ticker,
                            "market_value": mv,
                            "unrealized_pnl": pnl,
                            "quantity": quantity,
                            "avg_cost": avg_cost,
                            "weight": (mv / total_value) if total_value > 0 else 0.0,
                        }
                    )
                context["positions"] = position_summaries

                # Weights dict for quick lookup
                context["weights"] = {
                    p["ticker"]: (p["market_value"] / total_value if total_value > 0 else 0.0)
                    for p in position_summaries
                }

                # Relevant positions for this decision
                if instruments:
                    relevant = [p for p in position_summaries if p["ticker"] in instruments]
                    context["relevant_positions"] = relevant
        except Exception as exc:
            logger.warning("debate.portfolio_context.positions_failed", error=str(exc))

        # Fetch regime state (latent state)
        try:
            latent_rows = await db.express.list("latent_state")
            if latent_rows:
                latest = latent_rows[-1]
                context["regime"] = {
                    "z_scale": float(latest.get("z_scale", 0) or 0),
                    "ood_score": float(latest.get("ood_score", 0) or 0),
                    "z_dim": int(latest.get("z_dim", 0) or 0),
                    "period_end": latest.get("period_end", ""),
                }
        except Exception as exc:
            logger.warning("debate.portfolio_context.regime_failed", error=str(exc))

        return context

    def _format_portfolio_context(self, context: dict) -> str:
        """Format portfolio context as a human-readable string for LLM injection."""
        lines = []

        # NAV and overview
        nav = context.get("nav", 0.0)
        positions_count = context.get("positions_count", 0)
        lines.append(f"Portfolio: {positions_count} positions, NAV ${nav:,.0f}")

        # Positions with weights and P&L
        positions = context.get("positions", [])
        if positions:
            lines.append("Current positions (with weights and unrealized P&L):")
            for p in positions[:10]:  # Top 10 positions
                ticker = p.get("ticker", "?")
                mv = p.get("market_value", 0)
                weight = p.get("weight", 0)
                pnl = p.get("unrealized_pnl", 0)
                lines.append(f"  {ticker}: ${mv:,.0f} ({weight:.1%}), P&L: ${pnl:,.0f}")

        # Relevant positions for this decision
        relevant = context.get("relevant_positions", [])
        if relevant:
            lines.append("Positions relevant to this decision:")
            for p in relevant:
                lines.append(
                    f"  {p['ticker']}: ${p['market_value']:,.0f} "
                    f"({p['weight']:.1%}), P&L: ${p['unrealized_pnl']:,.0f}"
                )

        # Regime state
        regime = context.get("regime", {})
        if regime:
            z_scale = regime.get("z_scale", 0)
            ood_score = regime.get("ood_score", 0)
            lines.append(f"Regime state: z_scale={z_scale:.2f}, OOD score={ood_score:.2f}")

        return "\n".join(lines) if lines else "No portfolio data available."

    def _build_provenance_pointers(self, portfolio_context: dict, brief: dict | None) -> list[dict]:
        """Build provenance pointers for the current turn's response.

        Points to the data sources used in the debate: positions table,
        latent_state table, and optionally the decision record.
        """
        pointers = []

        # Positions provenance
        positions = portfolio_context.get("positions", [])
        if positions:
            tickers = [p["ticker"] for p in positions[:10]]
            pointers.append(
                {
                    "source": "fabric:positions",
                    "reference": f"tickers={','.join(tickers)}",
                    "snippet": f"{len(positions)} positions loaded from positions table",
                }
            )

        # Regime provenance
        regime = portfolio_context.get("regime", {})
        if regime:
            pointers.append(
                {
                    "source": "fabric:latent_state",
                    "reference": f"z_scale={regime.get('z_scale', 0):.2f}",
                    "snippet": "Regime state (z_scale, OOD score) from latent_state table",
                }
            )

        # Decision provenance
        if brief:
            decision_id = brief.get("decision_id", "")
            if decision_id:
                pointers.append(
                    {
                        "source": "fabric:decisions",
                        "reference": str(decision_id),
                        "snippet": "Decision brief from AnalystAgent",
                    }
                )

        return pointers

    # -------------------------------------------------------------------------
    # Single-turn debate (legacy / one-shot)
    # -------------------------------------------------------------------------

    async def debate(
        self,
        brief: dict,
        user_position: str | None = None,
        debate_rounds: int = 3,
    ) -> dict:
        """Run structured single-turn debate (legacy one-shot mode).

        For multi-turn debates, use ``create_thread`` + ``add_turn`` instead.

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

        # Build a minimal portfolio context for single-turn (no DB access)
        live_context = ""
        if self._tools is not None:
            live_context = await self._build_live_context_legacy(brief)

        user_message = (
            f"Debate rounds requested: {debate_rounds}\n"
            f"Position to debate: {position}\n"
            f"Brief summary:\n{brief_summary}\n"
        )
        if live_context:
            user_message += f"\nLive portfolio data:\n{live_context}\n"
        user_message += f"Run the full debate and produce a final structured JSON result."

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
                "recommendation": "parse_failed",
                "steel_man": "",
                "red_team": "",
                "concession_count": 0,
                "final_confidence": 0.0,
                "resolution_state": "open",
                "rounds": debate_rounds,
                "parse_error": True,
                "raw_content_preview": result["content"][:100],
            }

        parsed.setdefault("rounds", debate_rounds)

        logger.info(
            "debate.complete",
            concession_count=parsed.get("concession_count"),
            final_confidence=parsed.get("final_confidence"),
            resolution_state=parsed.get("resolution_state"),
        )

        return parsed

    async def _build_live_context_legacy(self, brief: dict) -> str:
        """Fetch live portfolio and fabric data using tools (single-turn mode).

        Used only by the legacy ``debate()`` method when tools are available.
        For multi-turn, use ``_build_portfolio_context`` with direct DataFlow access.
        """
        if self._tools is None:
            return ""
        tools = self._tools
        sections: list[str] = []
        instruments = brief.get("instruments", [])
        if isinstance(instruments, str):
            instruments = [i.strip() for i in instruments.split(",") if i.strip()]

        try:
            positions = await tools.query_fabric("positions", {})
            if positions:
                total_value = sum(float(p.get("market_value", 0) or 0) for p in positions)
                sections.append(
                    f"Current portfolio ({len(positions)} positions, NAV ${total_value:,.0f}):"
                )
                for p in positions[:10]:
                    ticker = p.get("ticker", "?")
                    mv = float(p.get("market_value", 0) or 0)
                    pnl = float(p.get("unrealized_pnl", 0) or 0)
                    sections.append(f"  {ticker}: ${mv:,.0f} (P&L: ${pnl:,.0f})")
                if instruments:
                    relevant = [p for p in positions if p.get("ticker") in instruments]
                    if relevant:
                        sections.append("Positions relevant to this decision:")
                        for p in relevant:
                            sections.append(
                                f"  {p.get('ticker')}: ${float(p.get('market_value', 0) or 0):,.0f}"
                            )
        except Exception as exc:
            logger.warning("debate.live_context.positions_failed", error=str(exc))

        try:
            latent_rows = await tools.query_fabric("latent_state", {})
            if latent_rows:
                latest = latent_rows[-1]
                z_scale = float(latest.get("z_scale", 0) or 0)
                ood = float(latest.get("ood_score", 0) or 0)
                sections.append(f"Regime state: z_scale={z_scale:.2f}, OOD score={ood:.2f}")
        except Exception as exc:
            logger.warning("debate.live_context.regime_failed", error=str(exc))

        return "\n".join(sections)

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
