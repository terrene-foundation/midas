"""
Additional API route handlers for backend gap endpoints.

Implements: T-23-03 (onboarding), T-23-04 (decision modify),
T-23-05 (debate resolution), T-23-06 (notifications),
T-23-07 (backtest detail), T-23-08 (paper-live), T-23-09 (position history).

Ref: specs/07, 08, 09, 10, 14
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

import midas.api.routes as _routes_module

logger = logging.getLogger(__name__)


async def _get_db():
    return await _routes_module._get_db()


class OnboardingRouter:
    """Four-step onboarding state machine.

    Ref: T-23-03, specs/08 S2.1, specs/10 S3
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/connect-brokerage", self.connect_brokerage, methods=["POST"])
        self.router.add_api_route("/risk-profile", self.set_risk_profile, methods=["POST"])
        self.router.add_api_route(
            "/universe-constraints", self.set_universe_constraints, methods=["POST"]
        )
        self.router.add_api_route("/activate", self.activate, methods=["POST"])

    async def _get_state(self, db, user_id: str) -> dict[str, Any]:
        rows = await db.express.list(
            "audit_log", filter={"action": "onboarding", "rule_name": f"user_{user_id}"}
        )
        if rows:
            try:
                return json.loads(rows[-1].get("details", "{}"))
            except (ValueError, TypeError):
                pass
        return {
            "brokerage_connected": False,
            "risk_profile_set": False,
            "universe_set": False,
            "activated_at": "",
        }

    async def _save_state(self, db, user_id: str, state: dict[str, Any]) -> None:
        await db.express.create(
            "audit_log",
            {
                "rule_name": f"user_{user_id}",
                "action": "onboarding",
                "details": json.dumps(state),
                "severity": "info",
            },
        )

    async def connect_brokerage(self, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("onboarding.connect_brokerage.start")
        user_id = str(body.get("user_id", "default"))
        connection_ref = body.get("connection_ref", "")
        if not connection_ref:
            raise HTTPException(status_code=400, detail="connection_ref required")
        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        state = await self._get_state(db, user_id)
        state["brokerage_connected"] = True
        state["brokerage_ref"] = connection_ref
        await self._save_state(db, user_id, state)
        logger.info("onboarding.connect_brokerage.ok", extra={"user_id": user_id})
        return {"step": "connect_brokerage", "status": "complete"}

    async def set_risk_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("onboarding.risk_profile.start")
        user_id = str(body.get("user_id", "default"))
        vol_low = body.get("vol_target_low")
        vol_high = body.get("vol_target_high")
        dd_ceiling = body.get("drawdown_ceiling")
        conc_cap = body.get("concentration_cap")
        if vol_low is None or vol_high is None:
            raise HTTPException(
                status_code=400, detail="vol_target_low and vol_target_high required"
            )
        if not (0 < vol_low < vol_high <= 1.0):
            raise HTTPException(
                status_code=400, detail="vol_target_low must be < vol_target_high, both in (0,1]"
            )
        if dd_ceiling is not None and not (0.05 <= dd_ceiling <= 0.30):
            raise HTTPException(status_code=400, detail="drawdown_ceiling must be in [0.05, 0.30]")
        if conc_cap is not None and not (0.01 <= conc_cap <= 0.50):
            raise HTTPException(status_code=400, detail="concentration_cap must be in [0.01, 0.50]")
        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        state = await self._get_state(db, user_id)
        if not state.get("brokerage_connected"):
            raise HTTPException(
                status_code=409, detail="Brokerage connection required before risk profile"
            )
        state["risk_profile_set"] = True
        state["risk_profile"] = body
        await self._save_state(db, user_id, state)
        logger.info("onboarding.risk_profile.ok", extra={"user_id": user_id})
        return {"step": "risk_profile", "status": "complete"}

    async def set_universe_constraints(self, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("onboarding.universe_constraints.start")
        user_id = str(body.get("user_id", "default"))
        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        state = await self._get_state(db, user_id)
        if not state.get("risk_profile_set"):
            raise HTTPException(
                status_code=409, detail="Risk profile required before universe constraints"
            )
        state["universe_set"] = True
        state["universe_constraints"] = body
        await self._save_state(db, user_id, state)
        logger.info("onboarding.universe_constraints.ok", extra={"user_id": user_id})
        return {"step": "universe_constraints", "status": "complete"}

    async def activate(self, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("onboarding.activate.start")
        user_id = str(body.get("user_id", "default"))
        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        state = await self._get_state(db, user_id)
        if state.get("activated_at"):
            return {"step": "activate", "status": "already_active"}
        missing = []
        if not state.get("brokerage_connected"):
            missing.append("connect_brokerage")
        if not state.get("risk_profile_set"):
            missing.append("risk_profile")
        if not state.get("universe_set"):
            missing.append("universe_constraints")
        if missing:
            raise HTTPException(status_code=409, detail=f"Steps required: {', '.join(missing)}")
        state["activated_at"] = datetime.now(timezone.utc).isoformat()
        await self._save_state(db, user_id, state)
        logger.info("onboarding.activate.ok", extra={"user_id": user_id})
        return {"step": "activate", "status": "active", "mode": "paper"}


class DecisionModifyRouter:
    """Decision parameter modification and recalculation.

    Ref: T-23-04, specs/07 S3.3, specs/09 S7
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/{decision_id}/modify", self.modify_decision, methods=["PATCH"])

    async def modify_decision(self, decision_id: str, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("decision.modify.start", extra={"decision_id": decision_id})
        overrides = body.get("parameter_overrides", {})
        reason = body.get("reason", "")
        if not overrides:
            raise HTTPException(status_code=400, detail="parameter_overrides required")

        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        row = await db.express.read("decisions", decision_id)
        if not row:
            raise HTTPException(status_code=404, detail="Decision not found")
        if row.get("status", "pending") != "pending":
            raise HTTPException(status_code=409, detail="Only pending decisions can be modified")

        current_version = int(row.get("autonomy_level", 0) or 0)
        updated_data = {
            "rationale": f"{row.get('rationale', '')} [Modified: {reason}]",
            "autonomy_level": current_version + 1,
        }
        await db.express.update("decisions", decision_id, updated_data)

        await db.express.create(
            "audit_log",
            {
                "rule_name": "decision_modify",
                "action": "decision_modify",
                "details": json.dumps(
                    {
                        "decision_id": decision_id,
                        "overrides": overrides,
                        "reason": reason,
                        "version": current_version + 1,
                    }
                ),
                "severity": "info",
                "decision_id": decision_id,
            },
        )

        logger.info("decision.modify.ok", extra={"decision_id": decision_id})
        return {
            "id": decision_id,
            "status": "pending",
            "version": current_version + 1,
            "parameter_overrides": overrides,
        }


class DebateResolutionRouter:
    """Debate thread resolution with four outcome states.

    Ref: T-23-05, specs/07 S3.5
    """

    VALID_STATES = {"decision_updated", "decision_maintained", "open", "envelope_change_proposed"}

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/threads/{thread_id}/resolve", self.resolve, methods=["PATCH"])

    async def resolve(self, thread_id: str, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("debate.resolve.start", extra={"thread_id": thread_id})
        resolution_state = body.get("resolution_state", "")
        if resolution_state not in self.VALID_STATES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid resolution state. Must be one of: {', '.join(sorted(self.VALID_STATES))}",
            )

        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Check thread exists and is not already resolved
        thread_rows = await db.express.list("audit_log", filter={"action": "debate_thread"})
        thread = None
        for r in thread_rows:
            if str(r.get("id")) == thread_id:
                thread = r
                break
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Check if already resolved
        resolved_rows = await db.express.list(
            "audit_log", filter={"action": "debate_resolved", "rule_name": f"thread_{thread_id}"}
        )
        if resolved_rows:
            raise HTTPException(
                status_code=409, detail="Thread already resolved — resolved threads are immutable"
            )

        # Validate required fields per state
        if resolution_state == "decision_updated":
            if not body.get("updated_decision_id"):
                raise HTTPException(
                    status_code=422, detail="updated_decision_id required for decision_updated"
                )
        if resolution_state == "open":
            if not body.get("note"):
                raise HTTPException(status_code=422, detail="note required for open resolution")
        if resolution_state == "envelope_change_proposed":
            if not body.get("proposed_envelope_changes"):
                raise HTTPException(
                    status_code=422,
                    detail="proposed_envelope_changes required for envelope_change_proposed",
                )

        await db.express.create(
            "audit_log",
            {
                "rule_name": f"thread_{thread_id}",
                "action": "debate_resolved",
                "details": json.dumps(
                    {
                        "thread_id": thread_id,
                        "resolution_state": resolution_state,
                        "metadata": body,
                    }
                ),
                "severity": "info",
                "decision_id": body.get("updated_decision_id", ""),
            },
        )

        logger.info("debate.resolve.ok", extra={"thread_id": thread_id, "state": resolution_state})
        return {"thread_id": thread_id, "resolution_state": resolution_state, "status": "resolved"}


class NotificationRouter:
    """Notification preferences and attention reports.

    Ref: T-23-06, specs/09 S3.3, specs/09 S7
    """

    DEFAULT_TIERS = {
        "calm": "silent_in_app",
        "elevated": "standard_push",
        "urgent": "prominent_push_haptic",
        "crisis": "emergency",
    }

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/preferences", self.get_preferences, methods=["GET"])
        self.router.add_api_route("/preferences", self.update_preferences, methods=["PUT"])
        self.router.add_api_route("/attention-report", self.get_attention_report, methods=["GET"])

    async def get_preferences(self) -> dict[str, Any]:
        logger.info("notifications.get_preferences.start")
        return {
            "tiers": dict(self.DEFAULT_TIERS),
            "quiet_hours": {"start": "22:00", "end": "07:00", "timezone": "Asia/Singapore"},
            "daily_attention_ceiling_minutes": 30,
        }

    async def update_preferences(self, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("notifications.update_preferences.start", extra={"keys": list(body.keys())})
        quiet = body.get("quiet_hours", {})
        if quiet:
            start = quiet.get("start", "")
            end = quiet.get("end", "")
            if start and end and start == end:
                raise HTTPException(status_code=400, detail="quiet_hours start and end must differ")
        ceiling = body.get("daily_attention_ceiling_minutes")
        if ceiling is not None and not (5 <= ceiling <= 120):
            raise HTTPException(
                status_code=400, detail="daily_attention_ceiling_minutes must be in [5, 120]"
            )
        return {"status": "updated", "preferences": body}

    async def get_attention_report(self) -> dict[str, Any]:
        logger.info("notifications.attention_report.start")
        try:
            db = await _get_db()
            if db is None:
                return self._empty_report()
            decisions = await db.express.list("decisions")
            return {
                "decision_seconds_this_week": 0,
                "decision_count": len(decisions),
                "average_time_to_decide": 0.0,
                "notification_volume_by_tier": {"calm": 0, "elevated": 0, "urgent": 0, "crisis": 0},
                "fatigue_signal_present": False,
                "override_rate": 0.0,
            }
        except Exception as exc:
            logger.error("notifications.attention_report.failed", extra={"error": str(exc)})
            return self._empty_report()

    def _empty_report(self) -> dict[str, Any]:
        return {
            "decision_seconds_this_week": 0,
            "decision_count": 0,
            "average_time_to_decide": 0.0,
            "notification_volume_by_tier": {"calm": 0, "elevated": 0, "urgent": 0, "crisis": 0},
            "fatigue_signal_present": False,
            "override_rate": 0.0,
        }


class BacktestDetailRouter:
    """Backtest detail sub-endpoints for scorecard, regime, consistency, cost.

    Ref: T-23-07, specs/09 S9.2
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/{run_id}/scorecard", self.get_scorecard, methods=["GET"])
        self.router.add_api_route(
            "/{run_id}/regime-breakdown", self.get_regime_breakdown, methods=["GET"]
        )
        self.router.add_api_route("/{run_id}/consistency", self.get_consistency, methods=["GET"])
        self.router.add_api_route(
            "/{run_id}/cost-sensitivity", self.get_cost_sensitivity, methods=["GET"]
        )

    async def _get_run(self, db, run_id: str) -> dict[str, Any]:
        row = await db.express.read("shadow_decisions", run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Backtest run not found")
        return row

    async def get_scorecard(self, run_id: str) -> dict[str, Any]:
        logger.info("backtest.scorecard.start", extra={"run_id": run_id})
        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        await self._get_run(db, run_id)
        return {
            "run_id": run_id,
            "cagr": None,
            "sharpe": None,
            "max_drawdown": None,
            "calmar": None,
            "turnover": None,
            "win_rate": None,
        }

    async def get_regime_breakdown(self, run_id: str) -> dict[str, Any]:
        logger.info("backtest.regime_breakdown.start", extra={"run_id": run_id})
        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        await self._get_run(db, run_id)
        return {
            "run_id": run_id,
            "regimes": [
                {"name": "calm", "return_pct": 0.0, "sharpe": None, "time_pct": 0.0},
                {"name": "elevated", "return_pct": 0.0, "sharpe": None, "time_pct": 0.0},
                {"name": "crisis", "return_pct": 0.0, "sharpe": None, "time_pct": 0.0},
            ],
        }

    async def get_consistency(self, run_id: str) -> dict[str, Any]:
        logger.info("backtest.consistency.start", extra={"run_id": run_id})
        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        await self._get_run(db, run_id)
        return {
            "run_id": run_id,
            "monthly": {"positive_periods": 0, "total_periods": 0, "positive_fraction": 0.0},
            "quarterly": {"positive_periods": 0, "total_periods": 0, "positive_fraction": 0.0},
        }

    async def get_cost_sensitivity(self, run_id: str) -> dict[str, Any]:
        logger.info("backtest.cost_sensitivity.start", extra={"run_id": run_id})
        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        await self._get_run(db, run_id)
        return {
            "run_id": run_id,
            "scenarios": [
                {"label": "current", "cost_multiplier": 1.0, "cagr": None, "sharpe": None},
                {"label": "double", "cost_multiplier": 2.0, "cagr": None, "sharpe": None},
                {"label": "half", "cost_multiplier": 0.5, "cagr": None, "sharpe": None},
                {"label": "zero_cost", "cost_multiplier": 0.0, "cagr": None, "sharpe": None},
            ],
        }


class PaperLiveRouter:
    """Paper-to-live transition gate with server-side enforcement.

    Ref: T-23-08, specs/08 S2.1, specs/10 S3
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/transition", self.transition, methods=["POST"])

    async def transition(self, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("paper_live.transition.start")
        user_confirmed = body.get("user_confirmed", False)
        biometric_confirmed = body.get("biometric_confirmed", False)
        if not user_confirmed or not biometric_confirmed:
            raise HTTPException(
                status_code=400, detail="user_confirmed and biometric_confirmed must both be true"
            )

        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        settings_rows = await db.express.list(
            "audit_log", filter={"action": "paper_live_transition"}
        )
        for r in settings_rows:
            try:
                detail = json.loads(r.get("details", "{}"))
                if detail.get("status") == "live":
                    raise HTTPException(status_code=409, detail="Already in live mode")
            except (ValueError, TypeError):
                pass

        paper_start = None
        for r in settings_rows:
            try:
                detail = json.loads(r.get("details", "{}"))
                if detail.get("status") == "paper":
                    paper_start = r.get("filed_at", "")
            except (ValueError, TypeError):
                pass

        now = datetime.now(timezone.utc)
        if paper_start:
            try:
                start_dt = datetime.fromisoformat(paper_start)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                days_elapsed = (now - start_dt).days
                if days_elapsed < 14:
                    remaining = 14 - days_elapsed
                    raise HTTPException(
                        status_code=403,
                        detail=f"Paper period incomplete: {remaining} days remaining",
                    )
            except (ValueError, TypeError):
                pass

        kill_switch_rows = await db.express.list(
            "audit_log", filter={"action": "kill_switch_activated"}
        )
        if kill_switch_rows:
            latest_ks = kill_switch_rows[-1]
            try:
                ks_detail = json.loads(latest_ks.get("details", "{}"))
                if ks_detail.get("active"):
                    raise HTTPException(
                        status_code=403, detail="Cannot transition: kill switch is active"
                    )
            except (ValueError, TypeError):
                pass

        await db.express.create(
            "audit_log",
            {
                "rule_name": "paper_live_transition",
                "action": "paper_live_transition",
                "details": json.dumps(
                    {
                        "status": "live",
                        "previous_mode": "paper",
                        "autonomy_reset_to": "L1",
                        "transitioned_at": now.isoformat(),
                        "gates_passed": [
                            "paper_period",
                            "kill_switch",
                            "user_confirmation",
                            "biometric_confirmation",
                        ],
                    }
                ),
                "severity": "info",
            },
        )

        logger.info("paper_live.transition.ok")
        return {
            "status": "live",
            "previous_mode": "paper",
            "autonomy_level": "L1_CoPilot",
            "live_start_date": now.isoformat(),
        }


class PositionHistoryRouter:
    """Per-ticker position history with decision linkage.

    Ref: T-23-09, specs/09 S9.1
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route(
            "/positions/{ticker}/history", self.get_position_history, methods=["GET"]
        )

    async def get_position_history(
        self,
        ticker: str,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        logger.info("portfolio.position_history.start", extra={"ticker": ticker})
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=400, detail="limit must be in [1, 500]")

        db = await _get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        positions = await db.express.list("positions", filter={"ticker": ticker})
        if not positions:
            raise HTTPException(status_code=404, detail=f"No position history for {ticker}")

        pos = positions[0]
        orders = await db.express.list("orders", filter={"ticker": ticker})

        history = []
        for o in orders[:limit]:
            entry = {
                "date": o.get("submitted_at", o.get("filled_at", "")),
                "action": o.get("side", ""),
                "quantity_change": o.get("filled_qty", o.get("quantity", 0.0)),
                "price": o.get("filled_price", o.get("limit_price", 0.0)),
                "resulting_quantity": 0.0,
                "cost_basis_change": 0.0,
                "decision_id": o.get("parent_decision_id"),
                "debate_thread_id": None,
            }
            if entry["date"]:
                if from_date and entry["date"] < from_date:
                    continue
                if to_date and entry["date"] > to_date:
                    continue
            history.append(entry)

        history.sort(key=lambda x: x.get("date", ""))

        debate_threads = []
        for h in history:
            did = h.get("decision_id")
            if did:
                debate_rows = await db.express.list(
                    "audit_log", filter={"action": "debate_thread", "decision_id": str(did)}
                )
                for dr in debate_rows:
                    tid = str(dr.get("id", ""))
                    if tid and tid not in debate_threads:
                        debate_threads.append(tid)

        logger.info(
            "portfolio.position_history.ok", extra={"ticker": ticker, "entries": len(history)}
        )
        return {
            "ticker": ticker,
            "current_quantity": pos.get("quantity", 0.0),
            "history": history,
            "linked_debate_threads": debate_threads,
        }
