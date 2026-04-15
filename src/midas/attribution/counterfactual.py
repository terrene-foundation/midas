"""Counterfactual return computation.

Computes what would have happened if a different decision had been taken,
comparing executed returns against counterfactual (hold / opposite / benchmark)
returns at 1-day, 1-week, and 1-month horizons.

Ref: M16 — Counterfactual engine
"""

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.attribution.counterfactual")


class CounterfactualEngine:
    """Computes counterfactual returns for decisions."""

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = structlog.get_logger("midas.attribution.counterfactual")

    async def compute_counterfactual(
        self,
        decision_id: str,
        horizons: list[int] = [1, 5, 21],
    ) -> dict:
        """Compute counterfactual returns at specified horizons.

        For each horizon, compares the executed decision return against
        the counterfactual (hold/don't-trade) return.

        Parameters
        ----------
        decision_id : str
            The ID of the decision record.
        horizons : list[int]
            Lookahead horizons in trading days (default: 1, 5, 21).

        Returns
        -------
        dict with decision_id and list of counterfactual results.
        """
        self._log.info(
            "counterfactual.compute",
            decision_id=decision_id,
            horizons=horizons,
        )

        # Read the decision record
        decision = await self._db.express.read("decisions", decision_id)

        # For now, compute placeholder counterfactuals based on the
        # decision's outcome data. In production, this would look up
        # actual price paths for the instrument(s) involved.
        results = []
        for h in horizons:
            # Placeholder: executed_return from decision outcome,
            # counterfactual_return is 0.0 (hold / no-trade).
            executed_return = 0.0
            counterfactual_return = 0.0

            # Try to extract actual return data from the decision
            import json

            outcome_json = decision.get("outcome_json", "") or "{}"
            if isinstance(outcome_json, str):
                try:
                    outcome = json.loads(outcome_json)
                except (json.JSONDecodeError, TypeError):
                    outcome = {}
            else:
                outcome = outcome_json if isinstance(outcome_json, dict) else {}

            if h == 1:
                executed_return = outcome.get("return_1d", 0.0)
                counterfactual_return = outcome.get("counterfactual_1d", 0.0)
            elif h == 5:
                executed_return = outcome.get("return_5d", 0.0)
                counterfactual_return = outcome.get("counterfactual_5d", 0.0)
            elif h == 21:
                executed_return = outcome.get("return_21d", 0.0)
                counterfactual_return = outcome.get("counterfactual_21d", 0.0)

            diff = executed_return - counterfactual_return

            results.append(
                {
                    "horizon": h,
                    "executed_return": executed_return,
                    "counterfactual_return": counterfactual_return,
                    "diff": diff,
                }
            )

        self._log.info(
            "counterfactual.compute.ok",
            decision_id=decision_id,
            horizons_computed=len(results),
        )

        return {
            "decision_id": decision_id,
            "counterfactuals": results,
        }
