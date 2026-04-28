"""Brief enricher — inject fabric data into analyst prompt context.

Before the analyst LLM call, this module fetches:
1. Current positions and weights from the `positions` fabric table
2. Latent-state risk metrics from the `latent_state` fabric table
3. Historical decisions by latent similarity from the `decisions` fabric table

These become the grounding context that ensures the LLM produces
dollar-amounts, risk metrics, and analogue outcomes rather than placeholders.

Ref: specs/07-evidence-first-decision.md S2.3-S2.6
Ref: T-00-01 (PIT discipline)
"""

from __future__ import annotations

import structlog
from datetime import date

from midas.fabric.models import (
    AS_OF_DATE_KEY,
    DecisionRecord,
    FabricReader,
    LatentStateRecord,
    PositionRecord,
)

logger = structlog.get_logger("midas.brief.enricher")


class BriefEnricher:
    """Fetches grounding data from fabric for analyst prompt enrichment.

    Parameters
    ----------
    fabric_reader:
        A FabricReader (e.g. DataFlowFabricReader) for fabric queries.
    as_of:
        Point-in-time date for PIT-compliant reads. Defaults to today.
    max_analogues:
        Maximum number of historical analogues to return.
    """

    def __init__(
        self,
        fabric_reader: FabricReader,
        as_of: date | None = None,
        max_analogues: int = 5,
    ) -> None:
        self._reader = fabric_reader
        self._as_of = as_of or date.today()
        self._max_analogues = max_analogues

    async def enrich(
        self,
        instruments: list[str],
        learner_family: str = "ssl_transformer_v1",
    ) -> dict:
        """Fetch all grounding context for a brief.

        Parameters
        ----------
        instruments:
            List of instrument tickers to fetch positions for.
        learner_family:
            Latent state learner family to query.

        Returns
        -------
        dict
            Keys: positions_text, risk_text, analogues_text.
            Each value is a formatted string for injection into the analyst prompt.
            Empty strings when fabric reads fail (graceful degradation).
        """
        positions_text, risk_text, analogues_text = await self._fetch_all(
            instruments, learner_family
        )

        logger.info(
            "brief.enricher.done",
            as_of=self._as_of.isoformat(),
            has_positions=bool(positions_text),
            has_risk=bool(risk_text),
            has_analogues=bool(analogues_text),
        )

        return {
            "positions_text": positions_text,
            "risk_text": risk_text,
            "analogues_text": analogues_text,
        }

    async def _fetch_all(self, instruments: list[str], learner_family: str) -> tuple[str, str, str]:
        """Fetch all three context types, handling per-type failures gracefully."""
        positions_text, risk_text = await self._fetch_positions_and_risk(
            instruments, learner_family
        )
        analogues_text = await self._fetch_analogues(instruments)
        return positions_text, risk_text, analogues_text

    async def _fetch_positions_and_risk(
        self, instruments: list[str], learner_family: str
    ) -> tuple[str, str]:
        """Fetch positions and latent state risk metrics concurrently."""
        positions_text = ""
        risk_text = ""

        # Fetch positions for each instrument
        all_position_lines: list[str] = []
        for ticker in instruments:
            try:
                rows = await self._reader.read_positions(ticker, self._as_of)
                for row in rows:
                    line = self._format_position(row)
                    if line:
                        all_position_lines.append(line)
            except Exception as exc:
                logger.warning(
                    "brief.enricher.positions_fetch_failed",
                    instrument=ticker,
                    error=str(exc),
                )

        if all_position_lines:
            positions_text = "CURRENT PORTFOLIO POSITIONS:\n" + "\n".join(all_position_lines)
        else:
            positions_text = "CURRENT PORTFOLIO: No position data available."

        # Fetch latent state risk metrics
        try:
            z_rows = await self._reader.read_latent_state(learner_family, self._as_of)
            risk_lines = [self._format_latent_state(z) for z in z_rows]
            if risk_lines:
                risk_text = "LATENT STATE RISK METRICS:\n" + "\n".join(risk_lines)
            else:
                risk_text = "RISK METRICS: No latent state data available."
        except Exception as exc:
            logger.warning(
                "brief.enricher.latent_state_fetch_failed",
                learner_family=learner_family,
                error=str(exc),
            )
            risk_text = "RISK METRICS: Unable to fetch latent state (graceful degradation)."

        return positions_text, risk_text

    async def _fetch_analogues(self, instruments: list[str]) -> str:
        """Fetch historical decisions by instrument for analogue grounding."""
        analogue_lines: list[str] = []

        for ticker in instruments:
            try:
                rows = await self._reader.read_decisions(
                    ticker, self._as_of, lookback_days=730, limit=self._max_analogues
                )
                for row in rows:
                    line = self._format_decision(row)
                    if line:
                        analogue_lines.append(line)
            except Exception as exc:
                logger.warning(
                    "brief.enricher.analogues_fetch_failed",
                    instrument=ticker,
                    error=str(exc),
                )

        if analogue_lines:
            header = f"HISTORICAL DECISIONS (up to {self._max_analogues} analogues):\n"
            return header + "\n".join(analogue_lines)
        else:
            return (
                "HISTORICAL DECISIONS: No prior decision records found "
                "for the requested instruments."
            )

    def _format_position(self, record: PositionRecord) -> str:
        """Format a position record as a prompt-readable line."""
        if isinstance(record, dict):
            qty = record.get("quantity", 0)
            entry = record.get("entry_price", 0)
            current = record.get("current_price", 0)
            pnl = record.get("unrealised_pnl", 0)
            inst = record.get("instrument", "?")
        else:
            qty = record.quantity
            entry = record.entry_price
            current = record.current_price
            pnl = record.unrealised_pnl
            inst = record.instrument

        return (
            f"  {inst}: qty={qty}, entry=${entry:.2f}, "
            f"current=${current:.2f}, unrealised_pnl=${pnl:.2f}"
        )

    def _format_latent_state(self, record: LatentStateRecord | dict) -> str:
        """Format a latent state record for risk metric grounding."""
        if isinstance(record, dict):
            family = record.get("learner_family", "?")
            role = record.get("learner_role", "?")
            z_scale = record.get("z_scale")
            pool_idx = record.get("pool_index")
        else:
            family = record.learner_family
            role = record.learner_role
            z_scale = record.z_scale
            pool_idx = record.pool_index

        scale_str = f"{z_scale:.4f}" if z_scale is not None else "N/A"
        pool_str = f"pool={pool_idx}" if pool_idx is not None else "champion"
        return f"  {family}/{role} ({pool_str}): z_scale={scale_str}"

    def _format_decision(self, row: DecisionRecord | dict) -> str:
        """Format a decision record as an analogue line."""
        if isinstance(row, dict):
            decision_id = row.get("decision_id", "?")
            pit_str = row.get(AS_OF_DATE_KEY, "?")
            autonomy = row.get("autonomy_level", "?")
            user_action = row.get("user_action", "?")
            exec_result = row.get("execution_result") or {}
        else:
            decision_id = row.decision_id
            pit_str = row.pit.period_end.isoformat() if row.pit else "?"
            autonomy = row.autonomy_level
            user_action = row.user_action
            exec_result = row.execution_result or {}

        if isinstance(exec_result, str):
            import json

            try:
                exec_result = json.loads(exec_result)
            except Exception:
                exec_result = {}

        outcome_str = ""
        if exec_result:
            pnl = exec_result.get("realised_pnl") or exec_result.get("pnl")
            if pnl is not None:
                outcome_str = f", outcome=${pnl:.2f}"

        return (
            f"  [{pit_str}] id={decision_id[:8]}... | "
            f"autonomy={autonomy} | action={user_action}{outcome_str}"
        )
