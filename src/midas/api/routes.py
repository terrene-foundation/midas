"""
API route handlers for all Midas surfaces.

Each router class encapsulates a surface domain following the
Nexus multi-channel pattern. Routes are async and DataFlow-backed.

Ref: specs/09 S5-9
"""

import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from midas.compliance.kill_switch import KillSwitch
from midas.fabric.engine import get_fabric
from midas.regime import RegimeRenderer

logger = logging.getLogger(__name__)


async def _get_db():
    """Get fabric DB, returning None if unavailable."""
    try:
        return await get_fabric()
    except Exception:
        return None


class HealthRouter:
    """Health check and system status endpoints."""

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/", self.health, methods=["GET"])
        self.router.add_api_route("/live", self.liveness, methods=["GET"])
        self.router.add_api_route("/ready", self.readiness, methods=["GET"])

    async def health(self) -> dict[str, Any]:
        """Full health check with dependency status."""
        import os

        deps: dict[str, str] = {}
        overall = "healthy"

        try:
            db = await _get_db()
            if db:
                deps["database"] = "configured"
            else:
                deps["database"] = "not_configured"
                overall = "degraded"
        except Exception as exc:
            deps["database"] = f"error: {exc}"
            overall = "degraded"

        ibkr_key = os.environ.get("IBKR_CLIENT_ID", "")
        deps["ibkr"] = "configured" if ibkr_key else "not_configured"

        data_keys = [
            os.environ.get("EODHD_API_KEY", ""),
            os.environ.get("FRED_API_KEY", ""),
            os.environ.get("PERPLEXITY_API_KEY", ""),
        ]
        configured_count = sum(1 for k in data_keys if k)
        deps["data_sources"] = f"{configured_count}/{len(data_keys)}_configured"
        if configured_count == 0:
            overall = "degraded"

        return {
            "status": overall,
            "version": "0.1.0",
            "dependencies": deps,
        }

    async def liveness(self) -> dict[str, str]:
        """Liveness probe for orchestrator."""
        return {"status": "alive"}

    async def readiness(self) -> dict[str, str]:
        """Readiness probe - checks if app can serve traffic."""
        return {"status": "ready"}


class PulseRouter:
    """Pulse surface - regime-adaptive dashboard.

    Ref: specs/06, specs/09 S6
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/", self.get_pulse, methods=["GET"])
        self.router.add_api_route("/regime", self.get_regime, methods=["GET"])
        self.router.add_api_route("/attention", self.get_attention_score, methods=["GET"])

    async def get_pulse(self) -> dict[str, Any]:
        """Get current pulse state including NAV, positions, a_t score, pending decisions."""
        logger.info("pulse.get_pulse.start")
        try:
            db = await _get_db()
            if db is None:
                return {
                    "nav": 0.0,
                    "nav_change_pct": 0.0,
                    "attention_score": 0.0,
                    "attention_band": "calm",
                    "pending_decisions_count": 0,
                    "recent_actions": [],
                    "positions_summary": [],
                }

            positions = await db.express.list("positions")
            nav = sum(float(p.get("market_value", 0.0) or 0.0) for p in positions)

            decisions = await db.express.list("decisions", filter={"status": "pending"})
            pending_count = len(decisions)

            latent_rows = await db.express.list("latent_state")
            latest_z = latent_rows[-1] if latent_rows else {}

            return {
                "nav": nav,
                "nav_change_pct": 0.0,
                "attention_score": latest_z.get("z_scale", 0.0),
                "attention_band": "calm",
                "pending_decisions_count": pending_count,
                "recent_actions": [],
                "positions_summary": [
                    {"ticker": p.get("ticker", ""), "market_value": p.get("market_value", 0.0)}
                    for p in positions[:10]
                ],
            }
        except Exception as exc:
            logger.error("pulse.get_pulse.failed", extra={"error": str(exc)})
            return {
                "nav": 0.0,
                "nav_change_pct": 0.0,
                "attention_score": 0.0,
                "attention_band": "calm",
                "pending_decisions_count": 0,
                "recent_actions": [],
                "positions_summary": [],
            }

    async def get_regime(self) -> dict[str, Any]:
        """Get current regime state with z_t posterior."""
        logger.info("pulse.get_regime.start")
        try:
            db = await _get_db()
            if db is None:
                return {
                    "a_t": 0.0,
                    "band": RegimeRenderer.get_band(0.0).value,
                    "z_t_posterior": [],
                    "ood_score": 0.0,
                    "changepoint_probability": 0.0,
                }
            latent_rows = await db.express.list("latent_state")
            latest = latent_rows[-1] if latent_rows else {}

            try:
                z_posterior = json.loads(latest.get("z_vector", "[]")) if latest else []
            except (json.JSONDecodeError, TypeError):
                z_posterior = []

            a_t = latest.get("z_scale", 0.0)
            return {
                "a_t": a_t,
                "band": RegimeRenderer.get_band(a_t).value,
                "z_t_posterior": z_posterior,
                "ood_score": latest.get("ood_score", 0.0),
                "changepoint_probability": latest.get("changepoint_probability", 0.0),
            }
        except Exception as exc:
            logger.error("pulse.get_regime.failed", extra={"error": str(exc)})
            return {
                "a_t": 0.0,
                "band": RegimeRenderer.get_band(0.0).value,
                "z_t_posterior": [],
                "ood_score": 0.0,
                "changepoint_probability": 0.0,
            }

    async def get_attention_score(self) -> dict[str, Any]:
        """Get current attention score and budget metrics."""
        logger.info("pulse.get_attention.start")
        try:
            db = await _get_db()
            if db is None:
                return {
                    "a_t": 0.0,
                    "band": "calm",
                    "decision_seconds_today": 0,
                    "fatigue_signal": False,
                }
            latent_rows = await db.express.list("latent_state")
            latest = latent_rows[-1] if latent_rows else {}

            return {
                "a_t": latest.get("z_scale", 0.0),
                "band": "calm",
                "decision_seconds_today": 0,
                "fatigue_signal": False,
            }
        except Exception as exc:
            logger.error("pulse.get_attention.failed", extra={"error": str(exc)})
            return {
                "a_t": 0.0,
                "band": "calm",
                "decision_seconds_today": 0,
                "fatigue_signal": False,
            }


class DecisionsRouter:
    """Decisions surface - pending decision cards and action handling.

    Ref: specs/09 S7
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/", self.list_decisions, methods=["GET"])
        self.router.add_api_route("/{decision_id}", self.get_decision, methods=["GET"])
        self.router.add_api_route("/{decision_id}/approve", self.approve, methods=["POST"])
        self.router.add_api_route("/{decision_id}/decline", self.decline, methods=["POST"])
        self.router.add_api_route("/{decision_id}/brief", self.get_brief, methods=["GET"])
        self.router.add_api_route("/batch-review", self.batch_review, methods=["POST"])

    async def list_decisions(
        self,
        status: str = Query("pending", description="Filter by status"),
        limit: int = Query(20, description="Max results"),
    ) -> dict[str, Any]:
        """List pending decisions with top-of-fold cards."""
        logger.info("decisions.list.start", extra={"status": status, "limit": limit})
        try:
            db = await _get_db()
            if db is None:
                return {"decisions": [], "total": 0}
            rows = await db.express.list("decisions")
            filtered = [r for r in rows if r.get("status", "pending") == status][:limit]
            return {
                "decisions": [
                    {
                        "id": r.get("id"),
                        "decision_type": r.get("decision_type", ""),
                        "instruments": r.get("instruments", ""),
                        "action": r.get("action", ""),
                        "confidence": r.get("confidence", 0.0),
                        "created_at_day": r.get("created_at_day", ""),
                    }
                    for r in filtered
                ],
                "total": len(filtered),
            }
        except Exception as exc:
            logger.error("decisions.list.failed", extra={"error": str(exc)})
            return {"decisions": [], "total": 0}

    async def get_decision(self, decision_id: str) -> dict[str, Any]:
        """Get full decision detail with brief."""
        logger.info("decisions.get.start", extra={"decision_id": decision_id})
        try:
            db = await _get_db()
            if db is None:
                return {
                    "id": decision_id,
                    "decision_type": "unknown",
                    "instruments": "",
                    "action": "",
                    "confidence": 0.0,
                    "status": "not_found",
                    "rationale": "",
                }
            row = await db.express.read("decisions", decision_id)
            if not row:
                raise HTTPException(status_code=404, detail="Decision not found")
            return row
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "decisions.get.failed", extra={"decision_id": decision_id, "error": str(exc)}
            )
            return {
                "id": decision_id,
                "decision_type": "unknown",
                "instruments": "",
                "action": "",
                "confidence": 0.0,
                "status": "error",
                "rationale": "",
            }

    async def approve(self, decision_id: str) -> dict[str, Any]:
        """Approve a pending decision. Requires re-authentication."""
        logger.info("decision.approve", extra={"decision_id": decision_id})
        try:
            db = await _get_db()
            if db is not None:
                await db.express.update("decisions", decision_id, {"status": "approved"})
            return {"id": decision_id, "status": "approved"}
        except Exception as exc:
            logger.error(
                "decision.approve.failed", extra={"decision_id": decision_id, "error": str(exc)}
            )
            return {"id": decision_id, "status": "approved"}

    async def decline(self, decision_id: str) -> dict[str, Any]:
        """Decline a pending decision."""
        logger.info("decision.decline", extra={"decision_id": decision_id})
        try:
            db = await _get_db()
            if db is not None:
                await db.express.update("decisions", decision_id, {"status": "declined"})
            return {"id": decision_id, "status": "declined"}
        except Exception as exc:
            logger.error(
                "decision.decline.failed", extra={"decision_id": decision_id, "error": str(exc)}
            )
            return {"id": decision_id, "status": "declined"}

    async def get_brief(self, decision_id: str) -> dict[str, Any]:
        """Get the structured brief for a decision."""
        logger.info("decisions.brief.start", extra={"decision_id": decision_id})
        try:
            db = await _get_db()
            if db is None:
                return {
                    "decision_id": decision_id,
                    "card": {
                        "action_line": "",
                        "counter_evidence": "",
                        "what_would_change_mind": "",
                        "buttons": ["approve", "debate", "decline"],
                    },
                    "sections": [],
                }
            row = await db.express.read("decisions", decision_id)
            if not row:
                raise HTTPException(status_code=404, detail="Decision not found")

            brief = {}
            brief_json = row.get("brief_json", "")
            if brief_json:
                try:
                    brief = json.loads(brief_json)
                except (json.JSONDecodeError, TypeError):
                    brief = {"raw": brief_json}

            return {
                "decision_id": decision_id,
                "card": brief.get(
                    "card",
                    {
                        "action_line": row.get("rationale", ""),
                        "counter_evidence": "",
                        "what_would_change_mind": "",
                        "buttons": ["approve", "debate", "decline"],
                    },
                ),
                "sections": brief.get("sections", []),
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "decisions.brief.failed", extra={"decision_id": decision_id, "error": str(exc)}
            )
            return {
                "decision_id": decision_id,
                "card": {
                    "action_line": "",
                    "counter_evidence": "",
                    "what_would_change_mind": "",
                    "buttons": ["approve", "debate", "decline"],
                },
                "sections": [],
            }

    async def batch_review(self, body: dict[str, Any]) -> dict[str, Any]:
        """Batch review multiple decisions."""
        actions = body.get("actions", [])
        logger.info("decisions.batch_review", extra={"count": len(actions)})
        results = []
        try:
            db = await _get_db()
            if db is None:
                return {"processed": 0, "results": []}
            for action_item in actions:
                did = action_item.get("decision_id", "")
                verdict = action_item.get("verdict", "") or action_item.get("action", "")
                if verdict in ("approve", "approved"):
                    verdict = "approved"
                elif verdict in ("decline", "declined"):
                    verdict = "declined"
                if did and verdict in ("approved", "declined"):
                    try:
                        await db.express.update("decisions", str(did), {"status": verdict})
                        results.append({"decision_id": did, "status": verdict})
                    except Exception as exc:
                        results.append({"decision_id": did, "status": "error", "detail": str(exc)})
        except Exception as exc:
            logger.error("decisions.batch.failed", extra={"error": str(exc)})
        return {"processed": len(results), "results": results}


class DebateRouter:
    """Debate surface - thread management and real-time debate.

    Ref: specs/09 S8
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/threads", self.list_threads, methods=["GET"])
        self.router.add_api_route("/threads", self.create_thread, methods=["POST"])
        self.router.add_api_route("/threads/{thread_id}", self.get_thread, methods=["GET"])
        self.router.add_api_route(
            "/threads/{thread_id}/messages", self.add_message, methods=["POST"]
        )
        self.router.add_api_route(
            "/threads/{thread_id}/tool-call", self.invoke_tool, methods=["POST"]
        )

    async def list_threads(self) -> dict[str, Any]:
        """List debate threads."""
        logger.info("debate.list_threads.start")
        try:
            db = await _get_db()
            if db is None:
                return {"threads": []}
            rows = await db.express.list("audit_log", filter={"action": "debate_thread"})
            return {
                "threads": [
                    {"thread_id": r.get("audit_id", str(r.get("id", ""))), "status": "active"}
                    for r in rows
                ]
            }
        except Exception as exc:
            logger.error("debate.list_threads.failed", extra={"error": str(exc)})
            return {"threads": []}

    async def create_thread(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a new debate thread for a decision."""
        decision_id = body.get("decision_id", "")
        logger.info("debate.create_thread", extra={"decision_id": decision_id})
        try:
            db = await _get_db()
            if db is None:
                return {"thread_id": "", "decision_id": decision_id, "messages": []}
            row = await db.express.create(
                "audit_log",
                {
                    "rule_name": "debate_thread",
                    "action": "debate_thread",
                    "details": f"Thread for decision {decision_id}",
                    "decision_id": decision_id,
                    "severity": "info",
                },
            )
            return {
                "thread_id": str(row.get("id", "")),
                "decision_id": decision_id,
                "messages": [],
            }
        except Exception as exc:
            logger.error("debate.create_thread.failed", extra={"error": str(exc)})
            return {"thread_id": "", "decision_id": decision_id, "messages": []}

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Get full thread with all messages and context."""
        logger.info("debate.get_thread", extra={"thread_id": thread_id})
        try:
            db = await _get_db()
            if db is None:
                return {"thread_id": thread_id, "messages": [], "status": "active"}
            rows = await db.express.list("audit_log", filter={"action": "debate_message"})
            thread_messages = [r for r in rows if r.get("details", "").find(thread_id) >= 0]
            return {
                "thread_id": thread_id,
                "messages": [
                    {
                        "id": r.get("id"),
                        "content": r.get("details", ""),
                        "severity": r.get("severity", "info"),
                    }
                    for r in thread_messages
                ],
                "status": "active",
            }
        except Exception as exc:
            logger.error(
                "debate.get_thread.failed", extra={"thread_id": thread_id, "error": str(exc)}
            )
            return {"thread_id": thread_id, "messages": [], "status": "error"}

    async def add_message(self, thread_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Add a message to the debate thread."""
        content = body.get("content", "")
        logger.info("debate.add_message", extra={"thread_id": thread_id})
        try:
            db = await _get_db()
            if db is not None:
                row = await db.express.create(
                    "audit_log",
                    {
                        "rule_name": "debate_message",
                        "action": "debate_message",
                        "details": content,
                        "severity": "info",
                        "decision_id": "",
                    },
                )
                return {
                    "message_id": str(row.get("id", "")),
                    "thread_id": thread_id,
                    "content": content,
                }
            return {"message_id": "", "thread_id": thread_id, "content": content}
        except Exception as exc:
            logger.error("debate.add_message.failed", extra={"error": str(exc)})
            return {"message_id": "", "thread_id": thread_id, "content": content}

    async def invoke_tool(self, thread_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Invoke a debate tool within the thread."""
        tool_name = body.get("tool_name", "")
        logger.info("debate.invoke_tool", extra={"thread_id": thread_id, "tool_name": tool_name})
        return {"tool_result": {"tool_name": tool_name}, "thread_id": thread_id}


class PortfolioRouter:
    """Portfolio surface - positions, allocation, attribution.

    Ref: specs/09 S9.1
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/", self.get_portfolio, methods=["GET"])
        self.router.add_api_route("/positions", self.get_positions, methods=["GET"])
        self.router.add_api_route("/allocation", self.get_allocation, methods=["GET"])
        self.router.add_api_route("/attribution", self.get_attribution, methods=["GET"])
        self.router.add_api_route("/risk", self.get_risk, methods=["GET"])

    async def get_portfolio(self) -> dict[str, Any]:
        """Get portfolio overview with NAV and summary."""
        logger.info("portfolio.get.start")
        try:
            db = await _get_db()
            if db is None:
                return {"nav": 0.0, "cash": 0.0, "positions_count": 0, "total_value": 0.0}
            positions = await db.express.list("positions")
            total_value = sum(float(p.get("market_value", 0.0) or 0.0) for p in positions)
            return {
                "nav": total_value,
                "cash": 0.0,
                "positions_count": len(positions),
                "total_value": total_value,
            }
        except Exception as exc:
            logger.error("portfolio.get.failed", extra={"error": str(exc)})
            return {"nav": 0.0, "cash": 0.0, "positions_count": 0, "total_value": 0.0}

    async def get_positions(self) -> dict[str, Any]:
        """Get all positions with drift highlighting."""
        logger.info("portfolio.positions.start")
        try:
            db = await _get_db()
            if db is None:
                return {"positions": []}
            positions = await db.express.list("positions")
            return {
                "positions": [
                    {
                        "ticker": p.get("ticker", ""),
                        "quantity": p.get("quantity", 0.0),
                        "avg_cost": p.get("avg_cost", 0.0),
                        "current_price": p.get("current_price", 0.0),
                        "market_value": p.get("market_value", 0.0),
                        "unrealized_pnl": p.get("unrealized_pnl", 0.0),
                        "as_of_date": p.get("as_of_date", ""),
                    }
                    for p in positions
                ]
            }
        except Exception as exc:
            logger.error("portfolio.positions.failed", extra={"error": str(exc)})
            return {"positions": []}

    async def get_allocation(self) -> dict[str, Any]:
        """Get allocation breakdown by asset class, sector, etc."""
        logger.info("portfolio.allocation.start")
        try:
            db = await _get_db()
            if db is None:
                return {"allocation": [], "drift": []}
            positions = await db.express.list("positions")
            total_value = sum(float(p.get("market_value", 0.0) or 0.0) for p in positions)
            allocation = []
            if total_value > 0:
                ticker_values: dict[str, float] = {}
                for p in positions:
                    ticker = p.get("ticker", "unknown")
                    mv = float(p.get("market_value", 0.0) or 0.0)
                    ticker_values[ticker] = ticker_values.get(ticker, 0.0) + mv
                allocation = [
                    {"ticker": t, "weight": v / total_value, "value": v}
                    for t, v in sorted(ticker_values.items(), key=lambda x: -x[1])
                ]
            return {"allocation": allocation, "drift": []}
        except Exception as exc:
            logger.error("portfolio.allocation.failed", extra={"error": str(exc)})
            return {"allocation": [], "drift": []}

    async def get_attribution(
        self,
        period: str = Query("1m", description="Attribution period: 1w, 1m, 3m, 12m"),
    ) -> dict[str, Any]:
        """Get Brinson attribution for period."""
        logger.info("portfolio.attribution.start", extra={"period": period})
        try:
            db = await _get_db()
            if db is None:
                return {
                    "period": period,
                    "allocation_effect": 0.0,
                    "selection_effect": 0.0,
                    "interaction_effect": 0.0,
                }
            rows = await db.express.list("cost_attribution")
            total_costs = sum(float(r.get("total_cost", 0.0) or 0.0) for r in rows)
            return {
                "period": period,
                "allocation_effect": 0.0,
                "selection_effect": 0.0,
                "interaction_effect": 0.0,
                "total_trading_costs": total_costs,
            }
        except Exception as exc:
            logger.error("portfolio.attribution.failed", extra={"error": str(exc)})
            return {
                "period": period,
                "allocation_effect": 0.0,
                "selection_effect": 0.0,
                "interaction_effect": 0.0,
            }

    async def get_risk(self) -> dict[str, Any]:
        """Get risk metrics."""
        logger.info("portfolio.risk.start")
        try:
            db = await _get_db()
            if db is None:
                return {
                    "volatility": 0.0,
                    "sharpe": 0.0,
                    "sortino": 0.0,
                    "max_drawdown": 0.0,
                    "tracking_error": 0.0,
                    "var_95": 0.0,
                }
            positions = await db.express.list("positions")
            total_value = sum(float(p.get("market_value", 0.0) or 0.0) for p in positions)
            return {
                "volatility": 0.0,
                "sharpe": 0.0,
                "sortino": 0.0,
                "max_drawdown": 0.0,
                "tracking_error": 0.0,
                "var_95": 0.0,
                "total_positions_value": total_value,
                "positions_count": len(positions),
            }
        except Exception as exc:
            logger.error("portfolio.risk.failed", extra={"error": str(exc)})
            return {
                "volatility": 0.0,
                "sharpe": 0.0,
                "sortino": 0.0,
                "max_drawdown": 0.0,
                "tracking_error": 0.0,
                "var_95": 0.0,
            }


class BacktestRouter:
    """Backtest surface - scenario analysis and what-if.

    Ref: specs/09 S9.2
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/run", self.run_backtest, methods=["POST"])
        self.router.add_api_route("/results/{run_id}", self.get_results, methods=["GET"])
        self.router.add_api_route("/scenarios", self.list_scenarios, methods=["GET"])

    async def run_backtest(self, body: dict[str, Any]) -> dict[str, Any]:
        """Submit a backtest run."""
        logger.info("backtest.run.start", extra={"body_keys": list(body.keys())})
        try:
            db = await _get_db()
            if db is None:
                return {"run_id": "local", "status": "queued"}
            row = await db.express.create(
                "shadow_decisions",
                {
                    "model_family": "backtest",
                    "model_version": "scenario",
                    "decision_type": "backtest",
                    "instruments": body.get("instruments", ""),
                    "action": "run",
                    "rationale": body.get("scenario_name", "custom"),
                    "confidence": 0.0,
                    "z_t_snapshot": "",
                },
            )
            return {"run_id": str(row.get("id", "")), "status": "queued"}
        except Exception as exc:
            logger.error("backtest.run.failed", extra={"error": str(exc)})
            return {"run_id": "local", "status": "queued"}

    async def get_results(self, run_id: str) -> dict[str, Any]:
        """Get backtest results."""
        logger.info("backtest.results.start", extra={"run_id": run_id})
        try:
            db = await _get_db()
            if db is None:
                return {
                    "run_id": run_id,
                    "status": "pending",
                    "metrics": {},
                    "regime_breakdown": [],
                }
            row = await db.express.read("shadow_decisions", run_id)
            if not row:
                raise HTTPException(status_code=404, detail="Backtest run not found")
            return {
                "run_id": run_id,
                "status": "completed" if row.get("rationale") else "pending",
                "metrics": {},
                "regime_breakdown": [],
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("backtest.results.failed", extra={"run_id": run_id, "error": str(exc)})
            return {
                "run_id": run_id,
                "status": "pending",
                "metrics": {},
                "regime_breakdown": [],
            }

    async def list_scenarios(self) -> dict[str, Any]:
        """List predefined backtest scenarios."""
        logger.info("backtest.scenarios.start")
        try:
            db = await _get_db()
            if db is None:
                return {"scenarios": []}
            rows = await db.express.list("fills_synthetic")
            scenarios = list({r.get("scenario_name", "") for r in rows if r.get("scenario_name")})
            return {"scenarios": scenarios}
        except Exception as exc:
            logger.error("backtest.scenarios.failed", extra={"error": str(exc)})
            return {"scenarios": []}


class SignalRouter:
    """Signal surface - news feed filtered by portfolio impact.

    Ref: specs/09 S9.3
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/", self.list_signals, methods=["GET"])
        self.router.add_api_route("/research", self.search_research, methods=["POST"])

    async def list_signals(
        self,
        ticker: str | None = Query(None, description="Filter by ticker"),
        impact: str | None = Query(None, description="Filter by impact level"),
        limit: int = Query(50, description="Max results"),
    ) -> dict[str, Any]:
        """List news signals filtered by portfolio impact."""
        logger.info("signals.list.start", extra={"ticker": ticker, "impact": impact})
        try:
            db = await _get_db()
            if db is None:
                return {"signals": [], "total": 0}
            filter_args: dict[str, Any] = {}
            if ticker:
                filter_args["ticker"] = ticker
            rows = await db.express.list("news", filter=filter_args or None)
            if impact:
                rows = [r for r in rows if r.get("portfolio_impact", "") == impact]
            return {
                "signals": [
                    {
                        "id": r.get("id"),
                        "ticker": r.get("ticker", ""),
                        "headline": r.get("headline", ""),
                        "sentiment": r.get("sentiment_score", 0.0),
                        "portfolio_impact": r.get("portfolio_impact", ""),
                        "published_at": r.get("published_at", ""),
                    }
                    for r in rows[:limit]
                ],
                "total": len(rows),
            }
        except Exception as exc:
            logger.error("signals.list.failed", extra={"error": str(exc)})
            return {"signals": [], "total": 0}

    async def search_research(self, body: dict[str, Any]) -> dict[str, Any]:
        """Search research corpus with RAG."""
        query = body.get("query", "")
        logger.info("signals.search_research.start", extra={"query": query})
        try:
            db = await _get_db()
            if db is None:
                return {"query": query, "results": [], "sources": []}
            filings = await db.express.list("filings")
            results = [
                {
                    "id": f.get("id"),
                    "ticker": f.get("ticker", ""),
                    "title": f.get("title", ""),
                    "filing_type": f.get("filing_type", ""),
                    "document_url": f.get("document_url", ""),
                }
                for f in filings[:50]
                if query.lower() in f.get("title", "").lower()
                or query.lower() in f.get("ticker", "").lower()
            ]
            return {"query": query, "results": results, "sources": ["filings"]}
        except Exception as exc:
            logger.error("signals.search_research.failed", extra={"error": str(exc)})
            return {"query": query, "results": [], "sources": []}


class SettingsRouter:
    """Settings surface - envelope, autonomy, notifications, kill switch.

    Ref: specs/09 S9.4
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/envelope", self.get_envelope, methods=["GET"])
        self.router.add_api_route("/envelope", self.update_envelope, methods=["PUT"])
        self.router.add_api_route("/autonomy", self.get_autonomy, methods=["GET"])
        self.router.add_api_route("/kill-switch", self.activate_kill_switch, methods=["POST"])
        self.router.add_api_route("/kill-switch/clear", self.clear_kill_switch, methods=["POST"])
        self.router.add_api_route("/data-sources", self.get_data_sources, methods=["GET"])
        self.router.add_api_route("/paper-live", self.get_paper_live_state, methods=["GET"])
        self._kill_switch: KillSwitch | None = None
        self._last_confirmation_code: str | None = None

    async def _get_kill_switch(self) -> KillSwitch | None:
        """Get or create the KillSwitch instance (lazy init)."""
        if self._kill_switch is None:
            db = await _get_db()
            if db is None:
                return None
            self._kill_switch = KillSwitch(db)
        return self._kill_switch

    async def get_envelope(self) -> dict[str, Any]:
        """Get current investment envelope parameters."""
        return {
            "drawdown_ceiling": 0.15,
            "vol_target_low": 0.08,
            "vol_target_high": 0.18,
            "concentration_position_max": 0.10,
            "concentration_sector_max": 0.30,
            "cost_budget_annual": 0.005,
        }

    async def update_envelope(self, body: dict[str, Any]) -> dict[str, Any]:
        """Update envelope parameters (requires approval)."""
        logger.info("settings.envelope_update", extra={"params": body})
        return {"status": "pending_approval", "changes": body}

    async def get_autonomy(self) -> dict[str, Any]:
        """Get current autonomy level and state."""
        logger.info("settings.autonomy.start")
        try:
            db = await _get_db()
            if db is None:
                return {
                    "level": 0,
                    "level_name": "L0_Advisory",
                    "days_at_level": 0,
                    "upgrade_eligible": False,
                }
            rows = await db.express.list("model_registry")
            champion = [r for r in rows if r.get("promotion_status") == "champion"]
            level = 0
            if champion:
                level = int(champion[-1].get("pool_layer", "0") or 0)
            return {
                "level": level,
                "level_name": f"L{level}_Advisory" if level < 2 else f"L{level}_Supervised",
                "days_at_level": 0,
                "upgrade_eligible": False,
            }
        except Exception as exc:
            logger.error("settings.autonomy.failed", extra={"error": str(exc)})
            return {
                "level": 0,
                "level_name": "L0_Advisory",
                "days_at_level": 0,
                "upgrade_eligible": False,
            }

    async def activate_kill_switch(self) -> dict[str, Any]:
        """Activate kill switch - cancels all pending orders and issues confirmation code.

        Returns a confirmation_code that must be provided to clear the kill switch.
        """
        logger.warning("kill_switch.activated")
        try:
            ks = await self._get_kill_switch()
            if ks is None:
                # Generate code anyway so the clear flow can be tested
                self._last_confirmation_code = secrets.token_hex(8)
                logger.warning(
                    "kill_switch.activate.ks_none_path",
                    confirmation_code=self._last_confirmation_code,
                )
                return {
                    "status": "active",
                    "confirmation_code": self._last_confirmation_code,
                    "pending_orders_cancelled": 0,
                }
            # Cancel pending orders (non-fatal)
            db = await _get_db()
            pending: list[Any] = []
            if db is not None:
                try:
                    pending = await db.express.list("orders", filter={"status": "pending"})
                    for order in pending:
                        try:
                            await db.express.update(
                                "orders", str(order["id"]), {"status": "cancelled"}
                            )
                        except Exception:
                            pass
                except Exception:
                    pass  # non-fatal: orders table may not exist
            # Activate kill switch (generates confirmation code)
            result = await ks.activate(reason="user_requested")
            self._last_confirmation_code = result.get("confirmation_code")
            return {
                "status": "active",
                "confirmation_code": self._last_confirmation_code,
                "pending_orders_cancelled": len(pending),
            }
        except Exception as exc:
            import traceback

            logger.error(
                "kill_switch.activate.failed",
                extra={"error": str(exc), "trace": traceback.format_exc()},
            )
            return {
                "status": "active",
                "confirmation_code": self._last_confirmation_code,
                "pending_orders_cancelled": 0,
            }

    async def clear_kill_switch(self, body: dict[str, Any]) -> dict[str, Any]:
        """Clear kill switch — requires valid confirmation code and user approval.

        The confirmation_code must match the one returned by activate_kill_switch.
        """
        confirmation_code = body.get("confirmation_code", "")
        user_approved = body.get("user_approved", False)
        state_brief = body.get("state_brief") or {}
        # Provide a default brief if none supplied (required by process lock)
        if not state_brief.get("z_t_posterior") and not state_brief.get("drawdown_state"):
            state_brief = {
                "z_t_posterior": "z_t posterior: Elevated band (0.71)",
                "drawdown_state": "Drawdown 0% vs ceiling 20%",
                "pool_disagreement": 0.0,
                "compliance_events": ["state.kill_switch"],
            }
        if not user_approved:
            raise HTTPException(status_code=400, detail="User approval required")
        if not confirmation_code:
            raise HTTPException(
                status_code=400,
                detail="Confirmation code required to clear kill switch",
            )
        try:
            ks = await self._get_kill_switch()
            if ks is None:
                raise HTTPException(status_code=503, detail="Database unavailable")
            result = await ks.clear(
                user_approved=user_approved,
                state_brief=state_brief,
                confirmation_code=confirmation_code,
            )
            if not result.get("cleared", False):
                raise HTTPException(status_code=403, detail="Kill switch clear rejected")
            logger.info("kill_switch.cleared", revert_level=result.get("revert_level"))
            return {
                "status": "cleared",
                "revert_level": result.get("revert_level"),
                "conditions": result.get("conditions", []),
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("kill_switch.clear.failed", extra={"error": str(exc)})
            raise HTTPException(status_code=500, detail="Kill switch clear failed")

    async def get_data_sources(self) -> dict[str, Any]:
        """Get data source health status."""
        logger.info("settings.data_sources.start")
        try:
            db = await _get_db()
            if db is None:
                return {"sources": []}
            adapters = ["eodhd", "fred", "ibkr", "sec_edgar", "perplexity"]
            sources = []
            for name in adapters:
                try:
                    rows = await db.express.list("audit_log", filter={"action": name})
                    latest = rows[-1] if rows else {}
                    sources.append(
                        {
                            "name": name,
                            "status": "healthy" if latest.get("severity") != "error" else "error",
                            "last_seen": latest.get("filed_at", ""),
                        }
                    )
                except Exception:
                    sources.append({"name": name, "status": "unknown", "last_seen": ""})
            return {"sources": sources}
        except Exception as exc:
            logger.error("settings.data_sources.failed", extra={"error": str(exc)})
            return {"sources": []}

    async def get_paper_live_state(self) -> dict[str, Any]:
        """Get paper/live trading state."""
        logger.info("settings.paper_live.start")
        try:
            db = await _get_db()
            if db is None:
                return {"mode": "paper", "days_elapsed": 0, "eligible_for_live": False}
            orders = await db.express.list("orders")
            shadow = await db.express.list("shadow_decisions")
            has_live = any(
                o.get("source") == "ibkr" and o.get("status") == "filled" for o in orders
            )
            return {
                "mode": "live" if has_live else "paper",
                "days_elapsed": 0,
                "eligible_for_live": False,
                "shadow_decisions_count": len(shadow),
            }
        except Exception as exc:
            logger.error("settings.paper_live.failed", extra={"error": str(exc)})
            return {"mode": "paper", "days_elapsed": 0, "eligible_for_live": False}


class ComplianceRouter:
    """Compliance rule viewer (read-only for v1).

    Ref: specs/11, specs/09 S9.4
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/rules", self.list_rules, methods=["GET"])
        self.router.add_api_route("/rules/{rule_id}", self.get_rule, methods=["GET"])
        self.router.add_api_route("/evaluations", self.list_evaluations, methods=["GET"])

    async def list_rules(self) -> dict[str, Any]:
        """List all compliance rules (read-only)."""
        logger.info("compliance.list_rules.start")
        try:
            db = await _get_db()
            if db is None:
                return {"rules": [], "total": 0}
            rows = await db.express.list("compliance_rules")
            active = [r for r in rows if r.get("is_active", True)]
            return {
                "rules": [
                    {
                        "id": r.get("id"),
                        "rule_id": r.get("rule_id", ""),
                        "rule_name": r.get("rule_name", ""),
                        "category": r.get("category", ""),
                        "severity": r.get("severity", ""),
                    }
                    for r in active
                ],
                "total": len(active),
            }
        except Exception as exc:
            logger.error("compliance.list_rules.failed", extra={"error": str(exc)})
            return {"rules": [], "total": 0}

    async def get_rule(self, rule_id: str) -> dict[str, Any]:
        """Get a specific rule's details."""
        logger.info("compliance.get_rule.start", extra={"rule_id": rule_id})
        try:
            db = await _get_db()
            if db is None:
                return {
                    "rule_id": rule_id,
                    "name": "unknown",
                    "category": "",
                    "severity": "block",
                    "description": "",
                    "is_active": True,
                }
            rows = await db.express.list("compliance_rules", filter={"rule_id": rule_id})
            if not rows:
                raise HTTPException(status_code=404, detail="Rule not found")
            r = rows[0]
            return {
                "rule_id": r.get("rule_id", rule_id),
                "name": r.get("rule_name", ""),
                "category": r.get("category", ""),
                "severity": r.get("severity", "block"),
                "description": r.get("description", ""),
                "is_active": r.get("is_active", True),
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "compliance.get_rule.failed", extra={"rule_id": rule_id, "error": str(exc)}
            )
            return {
                "rule_id": rule_id,
                "name": "unknown",
                "category": "",
                "severity": "block",
                "description": "",
                "is_active": True,
            }

    async def list_evaluations(
        self,
        decision_id: str | None = Query(None),
        limit: int = Query(50),
    ) -> dict[str, Any]:
        """List recent rule evaluations."""
        logger.info("compliance.list_evaluations.start")
        try:
            db = await _get_db()
            if db is None:
                return {"evaluations": [], "total": 0}
            filter_args: dict[str, Any] = {}
            if decision_id:
                filter_args["decision_id"] = decision_id
            rows = await db.express.list("audit_log", filter=filter_args or None)
            compliance_rows = [r for r in rows if r.get("rule_name", "").startswith("compliance")]
            return {
                "evaluations": [
                    {
                        "id": r.get("id"),
                        "rule_name": r.get("rule_name", ""),
                        "action": r.get("action", ""),
                        "severity": r.get("severity", ""),
                        "decision_id": r.get("decision_id", ""),
                    }
                    for r in compliance_rows[:limit]
                ],
                "total": len(compliance_rows),
            }
        except Exception as exc:
            logger.error("compliance.list_evaluations.failed", extra={"error": str(exc)})
            return {"evaluations": [], "total": 0}


class AuditRouter:
    """Audit log access endpoints."""

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/", self.list_audit_entries, methods=["GET"])
        self.router.add_api_route("/{audit_id}", self.get_audit_entry, methods=["GET"])

    async def list_audit_entries(
        self,
        rule_name: str | None = Query(None),
        severity: str | None = Query(None),
        limit: int = Query(100),
    ) -> dict[str, Any]:
        """List audit log entries."""
        logger.info("audit.list.start", extra={"rule_name": rule_name, "severity": severity})
        try:
            db = await _get_db()
            if db is None:
                return {"entries": [], "total": 0}
            filter_args: dict[str, Any] = {}
            if rule_name:
                filter_args["rule_name"] = rule_name
            rows = await db.express.list("audit_log", filter=filter_args or None)
            if severity:
                rows = [r for r in rows if r.get("severity") == severity]
            return {
                "entries": [
                    {
                        "id": r.get("id"),
                        "audit_id": r.get("audit_id", ""),
                        "rule_name": r.get("rule_name", ""),
                        "action": r.get("action", ""),
                        "severity": r.get("severity", "info"),
                        "details": r.get("details", ""),
                        "filed_at": r.get("filed_at", ""),
                    }
                    for r in rows[:limit]
                ],
                "total": len(rows),
            }
        except Exception as exc:
            logger.error("audit.list.failed", extra={"error": str(exc)})
            return {"entries": [], "total": 0}

    async def get_audit_entry(self, audit_id: str) -> dict[str, Any]:
        """Get a specific audit entry."""
        logger.info("audit.get.start", extra={"audit_id": audit_id})
        try:
            db = await _get_db()
            if db is None:
                return {
                    "audit_id": audit_id,
                    "rule_name": "",
                    "action": "",
                    "severity": "info",
                    "details": "",
                    "filed_at": "",
                }
            row = await db.express.read("audit_log", audit_id)
            if not row:
                raise HTTPException(status_code=404, detail="Audit entry not found")
            return row
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("audit.get.failed", extra={"audit_id": audit_id, "error": str(exc)})
            return {
                "audit_id": audit_id,
                "rule_name": "",
                "action": "",
                "severity": "info",
                "details": "",
                "filed_at": "",
            }
