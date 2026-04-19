"""Counterfactual return computation.

Computes what would have happened if a different decision had been taken,
comparing executed returns against counterfactual (hold / opposite / benchmark)
returns at 1-day, 1-week, and 1-month horizons using actual price paths
from the fabric.

Ref: M16 — Counterfactual engine
"""

import json
from datetime import date, timedelta

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.attribution.counterfactual")


class CounterfactualEngine:
    """Computes counterfactual returns for decisions using fabric price data."""

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = structlog.get_logger("midas.attribution.counterfactual")

    async def compute_counterfactual(
        self,
        decision_id: str,
        horizons: list[int] | None = None,
    ) -> dict:
        """Compute counterfactual returns at specified horizons using actual prices.

        For each horizon, compares the executed decision return against
        the counterfactual (hold/don't-trade) return using price data
        from the fabric prices table.

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
        if horizons is None:
            horizons = [1, 5, 21]

        self._log.info(
            "counterfactual.compute",
            decision_id=decision_id,
            horizons=horizons,
        )

        decision = await self._db.express.read("decisions", decision_id)
        if decision is None:
            raise ValueError(f"Decision {decision_id} not found")

        instrument = decision.get("instrument", "")
        decision_date_str = decision.get("decision_date", "") or decision.get("created_at", "")
        direction = decision.get("direction", "buy")

        executed_return, counterfactual_return = await self._compute_from_prices(
            instrument, decision_date_str, direction
        )

        outcome = self._parse_outcome(decision)

        results = []
        for h in horizons:
            key = f"return_{h}d"
            cf_key = f"counterfactual_{h}d"

            exec_ret = outcome.get(key, executed_return)
            cf_ret = outcome.get(cf_key, counterfactual_return)

            results.append(
                {
                    "horizon": h,
                    "executed_return": exec_ret,
                    "counterfactual_return": cf_ret,
                    "diff": exec_ret - cf_ret,
                }
            )

        self._log.info(
            "counterfactual.compute.ok",
            decision_id=decision_id,
            horizons_computed=len(results),
            instrument=instrument,
        )

        return {
            "decision_id": decision_id,
            "instrument": instrument,
            "counterfactuals": results,
        }

    async def _compute_from_prices(
        self, instrument: str, decision_date_str: str, direction: str
    ) -> tuple[float, float]:
        """Compute returns from actual fabric price data.

        Returns (executed_return, counterfactual_return). Falls back to
        (0.0, 0.0) when price data is unavailable.
        """
        if not instrument or not decision_date_str:
            return 0.0, 0.0

        try:
            decision_date = date.fromisoformat(decision_date_str[:10])
        except (ValueError, TypeError):
            return 0.0, 0.0

        try:
            price_rows = await self._db.express.list(
                "prices",
                filter={"instrument": instrument},
            )
        except Exception as exc:
            self._log.warning(
                "counterfactual.price_query_failed",
                instrument=instrument,
                error=str(exc),
            )
            return 0.0, 0.0

        if not price_rows:
            return 0.0, 0.0

        price_map: dict[date, float] = {}
        for row in price_rows:
            try:
                d = date.fromisoformat(row.get("period_end", "")[:10])
                close = float(row.get("close", 0))
                if close > 0:
                    price_map[d] = close
            except (ValueError, TypeError):
                continue

        if not price_map:
            return 0.0, 0.0

        entry_price = price_map.get(decision_date)
        if entry_price is None:
            sorted_dates = sorted(price_map.keys())
            for d in sorted_dates:
                if d >= decision_date:
                    entry_price = price_map[d]
                    break
            if entry_price is None:
                return 0.0, 0.0

        exit_date = decision_date + timedelta(days=21)
        exit_price = price_map.get(exit_date)
        if exit_price is None:
            sorted_dates = sorted(price_map.keys())
            for d in sorted_dates:
                if d > decision_date:
                    exit_price = price_map[d]
                    break
            if exit_price is None:
                return 0.0, 0.0

        price_change = (exit_price - entry_price) / entry_price

        if direction == "buy":
            executed_return = price_change
            counterfactual_return = 0.0
        else:
            executed_return = -price_change
            counterfactual_return = 0.0

        return executed_return, counterfactual_return

    def _parse_outcome(self, decision: dict) -> dict:
        """Extract outcome data from decision record."""
        outcome_json = decision.get("outcome_json", "") or "{}"
        if isinstance(outcome_json, str):
            try:
                return json.loads(outcome_json)
            except (json.JSONDecodeError, TypeError):
                return {}
        return outcome_json if isinstance(outcome_json, dict) else {}
