"""
Additional API route handlers for backend gap endpoints.

Implements: T-23-03 (onboarding), T-23-04 (decision modify),
T-23-05 (debate resolution), T-23-06 (notifications),
T-23-07 (backtest detail), T-23-08 (paper-live), T-23-09 (position history).

Ref: specs/07, 08, 09, 10, 14
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

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

    @staticmethod
    def _resolve_user(request: Request, body: dict[str, Any]) -> str:
        """Derive user_id from JWT state (preferred) or body fallback (dev mode)."""
        jwt_user = getattr(request.state, "user", None)
        if jwt_user and jwt_user.get("sub"):
            return str(jwt_user["sub"])
        return str(body.get("user_id") or "default")

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

    async def connect_brokerage(self, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("onboarding.connect_brokerage.start")
        user_id = self._resolve_user(request, body)
        connection_ref = body.get("connection_ref", "")
        if not connection_ref:
            raise HTTPException(status_code=400, detail="connection_ref required")
        db = await _get_db()
        state = await self._get_state(db, user_id)
        state["brokerage_connected"] = True
        state["brokerage_ref"] = connection_ref
        await self._save_state(db, user_id, state)
        logger.info("onboarding.connect_brokerage.ok", extra={"user_id": user_id})
        return {"step": "connect_brokerage", "status": "complete"}

    async def set_risk_profile(self, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("onboarding.risk_profile.start")
        user_id = self._resolve_user(request, body)
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

    async def set_universe_constraints(
        self, request: Request, body: dict[str, Any]
    ) -> dict[str, Any]:
        logger.info("onboarding.universe_constraints.start")
        user_id = self._resolve_user(request, body)
        db = await _get_db()
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

    async def activate(self, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        logger.info("onboarding.activate.start")
        user_id = self._resolve_user(request, body)
        db = await _get_db()
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

    async def modify_decision(
        self, decision_id: str, request: Request, body: dict[str, Any]
    ) -> dict[str, Any]:
        logger.info("decision.modify.start", extra={"decision_id": decision_id})
        user = getattr(request.state, "user", None)
        auth_required = bool(os.environ.get("JWT_SECRET", ""))
        if auth_required and not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        overrides = body.get("parameter_overrides", {})
        reason = body.get("reason", "")
        if not overrides:
            raise HTTPException(status_code=400, detail="parameter_overrides required")

        db = await _get_db()

        row = await db.express.read("decisions", decision_id)
        if not row:
            raise HTTPException(status_code=404, detail="Decision not found")

        # IDOR: verify ownership
        if user:
            owner_id = row.get("user_id", "")
            if owner_id and str(owner_id) != str(user.get("sub")):
                raise HTTPException(
                    status_code=403, detail="Not authorized to modify this decision"
                )

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

    async def resolve(
        self, thread_id: str, request: Request, body: dict[str, Any]
    ) -> dict[str, Any]:
        logger.info("debate.resolve.start", extra={"thread_id": thread_id})
        user = getattr(request.state, "user", None)
        auth_required = bool(os.environ.get("JWT_SECRET", ""))
        if auth_required and not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        resolution_state = body.get("resolution_state", "")
        if resolution_state not in self.VALID_STATES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid resolution state. Must be one of: {', '.join(sorted(self.VALID_STATES))}",
            )

        db = await _get_db()

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
        """Get notification preferences from DB, falling back to defaults."""
        logger.info("notifications.get_preferences.start")
        try:
            db = await _get_db()
            if db is not None:
                rows = await db.express.list("notification_settings", filter={"user_id": 0})
                if rows:
                    row = rows[0]
                    import json as _json

                    tiers = _json.loads(row.get("tiers_json", "{}"))
                    if not tiers:
                        tiers = dict(self.DEFAULT_TIERS)
                    return {
                        "tiers": tiers,
                        "quiet_hours": {
                            "start": row.get("quiet_hours_start", "22:00"),
                            "end": row.get("quiet_hours_end", "07:00"),
                            "timezone": row.get("quiet_hours_timezone", "Asia/Singapore"),
                        },
                        "daily_attention_ceiling_minutes": row.get(
                            "daily_attention_ceiling_minutes", 30
                        ),
                    }
        except Exception as exc:
            logger.warning(
                "notifications.get_preferences.db_error",
                extra={"error": str(exc)},
            )
        # Fall back to defaults
        return {
            "tiers": dict(self.DEFAULT_TIERS),
            "quiet_hours": {"start": "22:00", "end": "07:00", "timezone": "Asia/Singapore"},
            "daily_attention_ceiling_minutes": 30,
        }

    async def update_preferences(self, body: dict[str, Any]) -> dict[str, Any]:
        """Update notification preferences in DB."""
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

        # Persist to DB
        try:
            db = await _get_db()
            if db is not None:
                import json as _json

                tiers_json = _json.dumps(body.get("tiers", self.DEFAULT_TIERS))
                quiet_hours = body.get("quiet_hours", {})
                ceiling_val = body.get(
                    "daily_attention_ceiling_minutes",
                    quiet_hours.get("daily_attention_ceiling_minutes", 30),
                )

                # Check if settings exist
                existing = await db.express.list("notification_settings", filter={"user_id": 0})
                if existing:
                    await db.express.update(
                        "notification_settings",
                        existing[0]["id"],
                        {
                            "tiers_json": tiers_json,
                            "quiet_hours_start": quiet_hours.get("start", "22:00"),
                            "quiet_hours_end": quiet_hours.get("end", "07:00"),
                            "quiet_hours_timezone": quiet_hours.get("timezone", "Asia/Singapore"),
                            "daily_attention_ceiling_minutes": ceiling_val,
                        },
                    )
                else:
                    await db.express.create(
                        "notification_settings",
                        {
                            "user_id": 0,
                            "tiers_json": tiers_json,
                            "quiet_hours_start": quiet_hours.get("start", "22:00"),
                            "quiet_hours_end": quiet_hours.get("end", "07:00"),
                            "quiet_hours_timezone": quiet_hours.get("timezone", "Asia/Singapore"),
                            "daily_attention_ceiling_minutes": ceiling_val,
                        },
                    )
                logger.info("notifications.preferences.persisted")
        except Exception as exc:
            logger.error("notifications.preferences.persist_failed", extra={"error": str(exc)})
            raise HTTPException(
                status_code=500, detail="Failed to persist notification preferences"
            )

        return {"status": "updated", "preferences": body}

    # Estimated average time per decision in seconds — used when
    # per-decision timestamps are not available.
    _AVG_SECONDS_PER_DECISION = 30

    async def get_attention_report(self) -> dict[str, Any]:
        """Compute attention report from decision and audit data.

        Computes:
        - decision_seconds_this_week: estimated from weekly decision count
        - decision_count: filtered to current week using created_at_day
        - override_rate: computed from outcome_json status field
        - notification_volume_by_tier: audit_log entries grouped by severity
        - fatigue_signal_present: True when weekly decision count exceeds
          daily ceiling * 7, or override_rate > 0.5
        """
        logger.info("notifications.attention_report.start")
        try:
            db = await _get_db()

            from datetime import date, timedelta

            today = date.today()
            week_start = (today - timedelta(days=today.weekday())).isoformat()

            all_decisions = await db.express.list("decisions")

            # Filter to current week
            week_decisions = [d for d in all_decisions if d.get("created_at_day", "") >= week_start]
            total_count = len(week_decisions)

            # Compute override_rate from outcome_json
            override_count = 0
            for d in week_decisions:
                outcome_str = d.get("outcome_json", "{}")
                try:
                    outcome = json.loads(outcome_str)
                    status = outcome.get("status", "")
                    # Approved = not an override; Declined/Modified = override
                    if status in ("declined", "modified"):
                        override_count += 1
                except (json.JSONDecodeError, TypeError):
                    pass

            override_rate = override_count / total_count if total_count > 0 else 0.0

            # Estimate decision time from count
            decision_seconds = total_count * self._AVG_SECONDS_PER_DECISION
            avg_time_to_decide = decision_seconds / total_count if total_count > 0 else 0.0

            # Notification volume by tier — count audit_log entries by severity
            tier_volume = {"calm": 0, "elevated": 0, "urgent": 0, "crisis": 0}
            try:
                all_audit = await db.express.list("audit_log")
                severity_to_tier = {
                    "info": "calm",
                    "warning": "elevated",
                    "warn": "elevated",
                    "error": "urgent",
                    "critical": "crisis",
                }
                for entry in all_audit:
                    severity = str(entry.get("severity", "info")).lower()
                    tier = severity_to_tier.get(severity, "calm")
                    tier_volume[tier] += 1
            except Exception:
                pass

            # Fatigue signal: volume overload OR override overload
            # Get daily attention ceiling (minutes), convert to decision count
            daily_ceiling_minutes = 30  # default
            try:
                settings_rows = await db.express.list(
                    "notification_settings", filter={"user_id": 0}
                )
                if settings_rows:
                    daily_ceiling_minutes = settings_rows[0].get(
                        "daily_attention_ceiling_minutes", 30
                    )
            except Exception:
                pass
            daily_ceiling_decisions = daily_ceiling_minutes * 60 / self._AVG_SECONDS_PER_DECISION
            weekly_ceiling = daily_ceiling_decisions * 7
            fatigue_signal = total_count > weekly_ceiling or override_rate > 0.5

            return {
                "decision_seconds_this_week": decision_seconds,
                "decision_count": total_count,
                "average_time_to_decide": round(avg_time_to_decide, 1),
                "notification_volume_by_tier": tier_volume,
                "fatigue_signal_present": fatigue_signal,
                "override_rate": round(override_rate, 4),
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

    async def _get_decisions_for_run(self, db, run_id: str) -> list[dict[str, Any]]:
        """Get all shadow decisions for a backtest run."""
        try:
            return await db.express.list("shadow_decisions")
        except Exception:
            return []

    def _compute_metrics(self, returns: list[float]) -> dict[str, float]:
        """Compute CAGR, Sharpe, max_drawdown, calmar, turnover, win_rate."""
        import numpy as np

        if not returns:
            return {
                "cagr": 0.0,
                "sharpe": 0.0,
                "max_drawdown": 0.0,
                "calmar": 0.0,
                "turnover": 0.0,
                "win_rate": 0.0,
            }

        rets = np.array(returns)
        n = len(returns)

        # CAGR
        total_return = float(np.prod(1 + rets))
        years = n / 252.0
        cagr = (total_return ** (1 / years) - 1) if years > 0 and total_return > 0 else 0.0

        # Sharpe
        std_ret = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
        mean_ret = float(np.mean(rets))
        sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 1e-10 else 0.0

        # Max drawdown
        cumulative = np.cumprod(1 + rets)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / np.maximum(running_max, 1e-10)
        max_drawdown = abs(float(np.min(drawdown))) if len(drawdown) > 0 else 0.0

        # Calmar
        calmar = abs(cagr / max_drawdown) if max_drawdown > 1e-10 else 0.0

        # Turnover (avg absolute daily return)
        turnover = float(np.mean(np.abs(rets)))

        # Win rate
        win_rate = float(np.sum(rets > 0) / n) if n > 0 else 0.0

        return {
            "cagr": round(cagr, 4),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_drawdown, 4),
            "calmar": round(calmar, 4),
            "turnover": round(turnover, 4),
            "win_rate": round(win_rate, 4),
        }

    async def get_scorecard(self, run_id: str) -> dict[str, Any]:
        """Compute backtest scorecard metrics from decisions and prices."""
        logger.info("backtest.scorecard.start", extra={"run_id": run_id})
        db = await _get_db()
        await self._get_run(db, run_id)
        decisions = await self._get_decisions_for_run(db, run_id)
        returns = await self._compute_returns_from_decisions(db, decisions)
        metrics = self._compute_metrics(returns)
        return {"run_id": run_id, **metrics}

    async def _compute_returns_from_decisions(
        self, db, decisions: list[dict[str, Any]]
    ) -> list[float]:
        """Build daily return series from decisions and price data."""
        import numpy as np

        if not decisions:
            return []

        # Group by day
        by_day: dict[str, list[dict]] = {}
        for d in decisions:
            day = str(d.get("created_at_day", ""))[:10]
            if day:
                by_day.setdefault(day, []).append(d)

        if not by_day:
            return []

        sorted_days = sorted(by_day.keys())
        if len(sorted_days) < 2:
            return []

        # Collect unique tickers
        all_tickers: set[str] = set()
        for d in decisions:
            for t in str(d.get("instruments", "")).split(","):
                t = t.strip()
                if t:
                    all_tickers.add(t)

        if not all_tickers:
            return []

        # Fetch prices
        price_map: dict[str, list[tuple[str, float]]] = {}
        try:
            all_prices = await db.express.list("prices")
            for p in all_prices:
                ticker = p.get("ticker", "")
                if ticker in all_tickers:
                    day = str(p.get("period_end", ""))[:10]
                    close = float(p.get("close", 0) or 0)
                    if day and close > 0:
                        price_map.setdefault(ticker, []).append((day, close))
        except Exception:
            return []

        for ticker in price_map:
            price_map[ticker].sort(key=lambda x: x[0])

        # Build daily returns
        daily_returns: list[float] = []
        prev_value = 1.0

        for i, day in enumerate(sorted_days):
            positions: dict[str, float] = {}
            for d in by_day[day]:
                action = str(d.get("action", "")).lower()
                for ticker in str(d.get("instruments", "")).split(","):
                    ticker = ticker.strip()
                    if not ticker:
                        continue
                    if action == "buy":
                        positions[ticker] = positions.get(ticker, 0) + 0.1
                    elif action == "sell":
                        positions[ticker] = positions.get(ticker, 0) - 0.1

            current_value = prev_value
            for ticker, weight in positions.items():
                prices = price_map.get(ticker, [])
                if len(prices) > i:
                    idx = min(i, len(prices) - 1)
                    curr_p = prices[idx][1]
                    prev_p = prices[max(0, idx - 1)][1] if idx > 0 else curr_p
                    if prev_p > 0:
                        ret = (curr_p - prev_p) / prev_p
                        current_value += weight * ret * prev_value

            daily_ret = (current_value - prev_value) / prev_value if prev_value > 0 else 0.0
            daily_returns.append(daily_ret)
            prev_value = current_value

        return daily_returns

    # z_scale band thresholds from latent_state — maps posterior width
    # proxy to attention regimes used throughout Midas.
    _Z_SCALE_BANDS = [
        ("calm", lambda z: z < 0.3),
        ("elevated", lambda z: 0.3 <= z < 0.7),
        ("urgent", lambda z: 0.7 <= z < 0.9),
        ("crisis", lambda z: z >= 0.9),
    ]

    def _classify_z_scale(self, z: float) -> str:
        """Return the regime name for a given z_scale value."""
        for name, predicate in self._Z_SCALE_BANDS:
            if predicate(z):
                return name
        return "crisis"  # fallback for edge cases

    async def _get_latent_states(self, db) -> list[dict[str, Any]]:
        """Fetch latent_state rows from fabric."""
        try:
            return await db.express.list("latent_state")
        except Exception:
            return []

    async def get_regime_breakdown(self, run_id: str) -> dict[str, Any]:
        """Compute per-regime performance breakdown using z_scale bands from latent_state.

        Groups returns by the z_scale of the corresponding latent_state entry:
        - Calm: z_scale < 0.3
        - Elevated: 0.3 <= z_scale < 0.7
        - Urgent: 0.7 <= z_scale < 0.9
        - Crisis: z_scale >= 0.9

        Falls back to absolute-return percentile thresholds when latent_state
        data is unavailable.
        """
        logger.info("backtest.regime_breakdown.start", extra={"run_id": run_id})
        db = await _get_db()
        await self._get_run(db, run_id)
        decisions = await self._get_decisions_for_run(db, run_id)
        returns = await self._compute_returns_from_decisions(db, decisions)

        if not returns:
            return {
                "run_id": run_id,
                "regimes": [
                    {"name": "calm", "return_pct": 0.0, "sharpe": None, "time_pct": 0.0},
                    {"name": "elevated", "return_pct": 0.0, "sharpe": None, "time_pct": 0.0},
                    {"name": "urgent", "return_pct": 0.0, "sharpe": None, "time_pct": 0.0},
                    {"name": "crisis", "return_pct": 0.0, "sharpe": None, "time_pct": 0.0},
                ],
            }

        import numpy as np

        rets = np.array(returns)
        n = len(rets)

        # Attempt to use z_scale from latent_state
        latent_states = await self._get_latent_states(db)
        if latent_states:
            # Pair each return with a z_scale, cycling through available states
            z_scales = []
            for state in latent_states:
                z = float(state.get("z_scale", 0.0) or 0.0)
                z_scales.append(z)

            regime_rets = {"calm": [], "elevated": [], "urgent": [], "crisis": []}
            for i, r in enumerate(rets):
                # Map return index to z_scale — if we have fewer z_scale
                # entries than returns, cycle through them
                z = z_scales[i % len(z_scales)] if z_scales else 0.0
                regime = self._classify_z_scale(z)
                regime_rets[regime].append(float(r))
        else:
            # Fallback: absolute-return percentile thresholds
            abs_rets = np.abs(rets)
            p33 = float(np.percentile(abs_rets, 33))
            p66 = float(np.percentile(abs_rets, 66))

            regime_rets = {"calm": [], "elevated": [], "urgent": [], "crisis": []}
            for r in rets:
                ar = abs(float(r))
                if ar <= p33:
                    regime_rets["calm"].append(float(r))
                elif ar <= p66:
                    regime_rets["elevated"].append(float(r))
                elif ar <= p66 * 2:
                    regime_rets["urgent"].append(float(r))
                else:
                    regime_rets["crisis"].append(float(r))

        result_regimes = []
        for name in ["calm", "elevated", "urgent", "crisis"]:
            vals = regime_rets[name]
            cnt = len(vals)
            if cnt > 0:
                vals_arr = np.array(vals)
                mean_ret = float(np.mean(vals_arr))
                std = float(np.std(vals_arr, ddof=1)) if len(vals_arr) > 1 else 0.0
                ret_pct = mean_ret * 100
                sh = (mean_ret / std * np.sqrt(252)) if std > 1e-10 else 0.0
            else:
                ret_pct = 0.0
                sh = None
            result_regimes.append(
                {
                    "name": name,
                    "return_pct": round(ret_pct, 4),
                    "sharpe": round(sh, 4) if sh is not None else None,
                    "time_pct": round(cnt / n, 4) if n > 0 else 0.0,
                }
            )

        return {"run_id": run_id, "regimes": result_regimes}

    async def get_consistency(self, run_id: str) -> dict[str, Any]:
        """Compute monthly and quarterly positive-period fractions."""
        logger.info("backtest.consistency.start", extra={"run_id": run_id})
        db = await _get_db()
        await self._get_run(db, run_id)
        decisions = await self._get_decisions_for_run(db, run_id)
        returns = await self._compute_returns_from_decisions(db, decisions)

        if not returns:
            return {
                "run_id": run_id,
                "monthly": {"positive_periods": 0, "total_periods": 0, "positive_fraction": 0.0},
                "quarterly": {"positive_periods": 0, "total_periods": 0, "positive_fraction": 0.0},
            }

        import numpy as np

        rets = np.array(returns)
        n = len(rets)

        # Monthly: ~21 trading days
        monthly_periods = max(1, n // 21)
        m_positive = 0
        for i in range(monthly_periods):
            start = i * 21
            end = min((i + 1) * 21, n)
            if end > start:
                period_ret = float(np.prod(1 + rets[start:end]) - 1)
                if period_ret > 0:
                    m_positive += 1

        # Quarterly: ~63 trading days
        quarterly_periods = max(1, n // 63)
        q_positive = 0
        for i in range(quarterly_periods):
            start = i * 63
            end = min((i + 1) * 63, n)
            if end > start:
                period_ret = float(np.prod(1 + rets[start:end]) - 1)
                if period_ret > 0:
                    q_positive += 1

        return {
            "run_id": run_id,
            "monthly": {
                "positive_periods": m_positive,
                "total_periods": monthly_periods,
                "positive_fraction": (
                    round(m_positive / monthly_periods, 4) if monthly_periods > 0 else 0.0
                ),
            },
            "quarterly": {
                "positive_periods": q_positive,
                "total_periods": quarterly_periods,
                "positive_fraction": (
                    round(q_positive / quarterly_periods, 4) if quarterly_periods > 0 else 0.0
                ),
            },
        }

    async def get_cost_sensitivity(self, run_id: str) -> dict[str, Any]:
        """Compute CAGR/Sharpe under 4 cost scenarios."""
        logger.info("backtest.cost_sensitivity.start", extra={"run_id": run_id})
        db = await _get_db()
        await self._get_run(db, run_id)
        decisions = await self._get_decisions_for_run(db, run_id)
        returns = await self._compute_returns_from_decisions(db, decisions)

        import numpy as np

        scenarios = []
        for mult, label in [(1.0, "current"), (2.0, "double"), (0.5, "half"), (0.0, "zero_cost")]:
            if returns:
                rets = np.array(returns) * (1 - mult * 0.001)
                n = len(rets)
                total_ret = float(np.prod(1 + rets))
                years = n / 252.0
                cagr = (total_ret ** (1 / years) - 1) if years > 0 and total_ret > 0 else 0.0
                std = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
                sharpe = (float(np.mean(rets)) / std * np.sqrt(252)) if std > 1e-10 else 0.0
            else:
                cagr = 0.0
                sharpe = 0.0
            scenarios.append(
                {
                    "label": label,
                    "cost_multiplier": mult,
                    "cagr": round(float(cagr), 4),
                    "sharpe": round(float(sharpe), 4),
                }
            )

        return {"run_id": run_id, "scenarios": scenarios}


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

        # SC-C1: Subsystem health check — generate paper trading report and verify
        # all subsystems pass before allowing transition to live.
        from midas.paper_trading.report import PaperTradingReport

        report = PaperTradingReport(db)
        subsystem_report = await report.generate_report()
        if subsystem_report["overall_status"] != "pass":
            failing = [
                s["subsystem"] for s in subsystem_report["subsystems"] if s["status"] != "pass"
            ]
            logger.warning(
                "paper_live.transition.subsystem_health_failed",
                extra={"failing_subsystems": failing},
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Subsystem health check failed: {', '.join(failing)} "
                    f"did not pass. Resolve before transitioning to live."
                ),
            )

        # SC-C2: Report review gate — user must confirm report was reviewed before live
        report_reviewed = body.get("report_reviewed", False)
        if not report_reviewed:
            raise HTTPException(
                status_code=400,
                detail="report_reviewed must be true — paper trading report must be reviewed before live transition",
            )

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
                            "report_reviewed",
                        ],
                    }
                ),
                "severity": "info",
            },
        )

        logger.info("paper_live.transition.ok")
        # SC-H7: Use spec-compliant level name from LEVEL_NAMES
        from midas.autonomy.ladder import LEVEL_NAMES

        return {
            "status": "live",
            "previous_mode": "paper",
            "autonomy_level": LEVEL_NAMES[1],  # L1 Co-Pilot — post-transition default
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
