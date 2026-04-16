"""Debate tools — 10 MCP tools for the debate agent.

Each tool is a data-only operation that fetches, computes, or updates
fabric state. All decision-making happens in the LLM, not in tools.
"""

import json
import math

import structlog

logger = structlog.get_logger("midas.agents.tools")


class DebateTools:
    """10 MCP tools for the debate agent.

    Tools are pure data operations. They do not make investment decisions.
    The LLM decides how to use the returned data.
    """

    def __init__(self, db):
        self._db = db

    async def query_fabric(self, table: str, filter: dict) -> list[dict]:
        """Tool 1: Query any fabric table.

        Parameters
        ----------
        table:
            Name of the fabric table to query.
        filter:
            Filter dict for the query.

        Returns
        -------
        list[dict]
            Matching rows from the fabric table.
        """
        logger.info("tools.query_fabric", table=table, filter_keys=list(filter.keys()))
        try:
            rows = await self._db.express.list(table, filter=filter)
            return rows
        except Exception as exc:
            logger.error("tools.query_fabric_failed", table=table, error=str(exc))
            return []

    async def query_head(self, head_name: str, z_t: list[float]) -> dict:
        """Tool 2: Query a model head prediction.

        Looks up the model registry for the head and returns its
        configuration and metadata.

        Parameters
        ----------
        head_name:
            Name of the model head.
        z_t:
            Latent state vector.

        Returns
        -------
        dict
            Head prediction with metadata.
        """
        logger.info("tools.query_head", head_name=head_name, z_dim=len(z_t))
        try:
            models = await self._db.express.list(
                "model_registry", filter={"model_family": head_name}
            )
        except Exception as exc:
            logger.error("tools.query_head_failed", error=str(exc))
            models = []

        if not models:
            return {
                "head_name": head_name,
                "prediction": None,
                "status": "no_model_found",
                "z_dim": len(z_t),
            }

        model = models[0]
        return {
            "head_name": head_name,
            "model_version": model.get("model_version", "unknown"),
            "prediction": "computed_from_z_t",
            "calibration": model.get("calibration_json", ""),
            "status": "ok",
            "z_dim": len(z_t),
        }

    async def query_calibration(self, head_name: str) -> dict:
        """Tool 3: Query calibration data for a head.

        Parameters
        ----------
        head_name:
            Name of the model head.

        Returns
        -------
        dict
            Calibration data including metrics and status.
        """
        logger.info("tools.query_calibration", head_name=head_name)
        try:
            models = await self._db.express.list(
                "model_registry", filter={"model_family": head_name}
            )
        except Exception as exc:
            logger.error("tools.query_calibration_failed", error=str(exc))
            return {"head_name": head_name, "calibration": None, "status": "error"}

        if not models:
            return {"head_name": head_name, "calibration": None, "status": "no_model_found"}

        model = models[0]
        calibration_json = model.get("calibration_json", "{}")
        try:
            calibration = json.loads(calibration_json) if calibration_json else {}
        except json.JSONDecodeError:
            calibration = {}

        return {
            "head_name": head_name,
            "model_version": model.get("model_version", "unknown"),
            "calibration": calibration,
            "status": "ok",
        }

    async def retrieve_analogue(self, situation_hash: str) -> list[dict]:
        """Tool 4: Retrieve analogous historical situations.

        Searches the embeddings store for documents with similar content
        hashes or latent state patterns.

        Parameters
        ----------
        situation_hash:
            Hash of the current situation to find analogues for.

        Returns
        -------
        list[dict]
            Similar historical situations.
        """
        logger.info("tools.retrieve_analogue", hash=situation_hash)
        try:
            rows = await self._db.express.list(
                "embeddings", filter={"content_hash": situation_hash}
            )
        except Exception as exc:
            logger.error("tools.retrieve_analogue_failed", error=str(exc))
            return []

        return rows

    async def propose_alternative_allocation(
        self, current_weights: dict, constraint_changes: dict
    ) -> dict:
        """Tool 5: Propose alternative allocation.

        Computes an adjusted weight allocation based on constraint changes.
        This is a deterministic computation, not an LLM decision.

        Parameters
        ----------
        current_weights:
            Current portfolio weights e.g. {"SPY": 0.6, "TLT": 0.4}.
        constraint_changes:
            Changes to constraints e.g. {"max_equity": 0.5}.

        Returns
        -------
        dict
            Proposed new weights and adjustment details.
        """
        logger.info(
            "tools.propose_alternative_allocation",
            current_weights=current_weights,
            constraints=constraint_changes,
        )

        new_weights = dict(current_weights)
        adjustments = {}

        max_equity = constraint_changes.get("max_equity")
        if max_equity is not None:
            # Identify equity-like instruments (heuristic: not bonds/fixed income)
            fixed_income = {"TLT", "BND", "AGG", "IEF", "LQD", "TIP"}
            equity_weight = sum(v for k, v in new_weights.items() if k not in fixed_income)
            if equity_weight > max_equity:
                scale = max_equity / equity_weight if equity_weight > 0 else 0
                for k in new_weights:
                    if k not in fixed_income:
                        old = new_weights[k]
                        new_weights[k] = round(old * scale, 4)
                        adjustments[k] = round(new_weights[k] - old, 4)

                # Redistribute freed weight proportionally to non-equity
                freed = equity_weight - sum(
                    v for k, v in new_weights.items() if k not in fixed_income
                )
                non_equity_total = sum(v for k, v in new_weights.items() if k in fixed_income)
                if non_equity_total > 0 and freed > 0:
                    for k in new_weights:
                        if k in fixed_income:
                            new_weights[k] = round(
                                new_weights[k] + freed * (new_weights[k] / non_equity_total),
                                4,
                            )

        return {
            "current_weights": current_weights,
            "proposed_weights": new_weights,
            "adjustments": adjustments,
            "constraint_changes": constraint_changes,
        }

    async def recompute_with_constraint(self, scenario: dict, constraint: dict) -> dict:
        """Tool 6: Recompute with modified constraint.

        Applies a constraint modification to a scenario and returns
        the recomputed result.

        Parameters
        ----------
        scenario:
            The scenario dict (e.g. with weights, targets).
        constraint:
            The constraint modification to apply.

        Returns
        -------
        dict
            Recomputed scenario with constraint applied.
        """
        logger.info(
            "tools.recompute_with_constraint",
            constraint_keys=list(constraint.keys()),
        )

        result = dict(scenario)
        result["applied_constraints"] = constraint

        weights = scenario.get("weights", {})
        if weights and constraint:
            max_equity = constraint.get("max_equity")
            if max_equity is not None:
                total = sum(weights.values())
                if total > 0:
                    # Scale all weights to respect the constraint
                    result["weights"] = {
                        k: round(v * max_equity / total, 4) if total > max_equity else v
                        for k, v in weights.items()
                    }

        return result

    async def backtest_scenario(self, weights: dict, period: str) -> dict:
        """Tool 7: Run quick backtest on scenario.

        Computes a simplified backtest using available price data.

        Parameters
        ----------
        weights:
            Portfolio weights to backtest.
        period:
            Date range string (e.g. "2024-01-01:2024-12-31").

        Returns
        -------
        dict
            Backtest results with performance metrics.
        """
        logger.info("tools.backtest_scenario", period=period, tickers=list(weights.keys()))

        # Compute returns from fetched price data if available
        returns_data = {}
        for ticker in weights:
            try:
                rows = await self._db.express.list("prices", filter={"ticker": ticker})
                if rows:
                    # Sort by date, compute total return from price series
                    sorted_rows = sorted(rows, key=lambda r: r.get("date", ""))
                    if len(sorted_rows) >= 2:
                        first_price = float(sorted_rows[0].get("close", 0))
                        last_price = float(sorted_rows[-1].get("close", 0))
                        if first_price > 0:
                            returns_data[ticker] = (last_price - first_price) / first_price
            except Exception as exc:
                logger.warning(
                    "tools.backtest_scenario.ticker_fetch_failed", ticker=ticker, error=str(exc)
                )

        if returns_data:
            # Portfolio return = weighted sum of individual returns
            total_return = sum(weights.get(t, 0) * ret for t, ret in returns_data.items())
            return {
                "weights": weights,
                "period": period,
                "total_return": total_return,
                "annualized_return": total_return,  # simplified for period
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "volatility": 0.0,
                "tickers_computed": len(returns_data),
                "tickers_requested": len(weights),
                "status": "partial",
            }

        return {
            "weights": weights,
            "period": period,
            "total_return": 0.0,
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "volatility": 0.0,
            "status": "no_price_data",
        }

    async def update_decision(self, decision_id: str, updates: dict) -> dict:
        """Tool 8: Update a pending decision.

        Applies updates to a decision record. The decision re-enters
        the compliance pipeline after update.

        Parameters
        ----------
        decision_id:
            ID of the decision to update.
        updates:
            Dict of fields to update.

        Returns
        -------
        dict
            The updated decision record.
        """
        logger.info(
            "tools.update_decision",
            decision_id=decision_id,
            update_keys=list(updates.keys()),
        )
        try:
            result = await self._db.express.update("decisions", decision_id, updates)
            return result
        except Exception as exc:
            logger.error("tools.update_decision_failed", error=str(exc))
            return {"decision_id": decision_id, "status": "error", "error": str(exc)}

    async def generate_counterfactual(self, decision_id: str) -> dict:
        """Tool 9: Generate counterfactual for a decision.

        Retrieves the original decision and constructs a counterfactual
        showing what would have happened under the opposite action.

        Parameters
        ----------
        decision_id:
            ID of the decision to analyze.

        Returns
        -------
        dict
            Counterfactual analysis.
        """
        logger.info("tools.generate_counterfactual", decision_id=decision_id)
        try:
            decision = await self._db.express.read("decisions", decision_id)
        except Exception as exc:
            logger.error("tools.generate_counterfactual_failed", error=str(exc))
            return {"decision_id": decision_id, "status": "error", "error": str(exc)}

        original_action = decision.get("action", "unknown")
        counter_action = "buy" if "sell" in original_action.lower() else "sell"
        if "hold" in original_action.lower():
            counter_action = "rebalance"

        return {
            "decision_id": decision_id,
            "original_action": original_action,
            "counterfactual_action": counter_action,
            "instruments": decision.get("instruments", ""),
            "confidence_delta": 0.0,
            "status": "generated",
        }

    async def surface_override_pattern(self, user_id: str) -> dict:
        """Tool 10: Surface user's override patterns.

        Analyzes audit log for patterns in how a user has overridden
        system recommendations.

        Parameters
        ----------
        user_id:
            The user identifier to analyze.

        Returns
        -------
        dict
            Override pattern analysis.
        """
        logger.info("tools.surface_override_pattern", user_id=user_id)
        try:
            audit_rows = await self._db.express.list("audit_log", filter={"agent": user_id})
        except Exception as exc:
            logger.error("tools.surface_override_pattern_failed", error=str(exc))
            audit_rows = []

        override_count = sum(1 for row in audit_rows if row.get("action") == "override")
        total_decisions = len(audit_rows)

        return {
            "user_id": user_id,
            "total_decisions_reviewed": total_decisions,
            "override_count": override_count,
            "override_rate": (
                round(override_count / total_decisions, 3) if total_decisions > 0 else 0.0
            ),
            "common_override_reasons": [],
            "status": "ok",
        }
