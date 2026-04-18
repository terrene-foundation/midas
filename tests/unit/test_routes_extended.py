"""Tests for extended API routes (T-23-03 through T-23-09).

Uses mocked DataFlow for persistence (Tier 1 unit tests).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from midas.api.routes_extended import (
    BacktestDetailRouter,
    DebateResolutionRouter,
    DecisionModifyRouter,
    NotificationRouter,
    OnboardingRouter,
    PaperLiveRouter,
    PositionHistoryRouter,
)


def _mock_db(audit_log=None, decisions=None, shadow_decisions=None, positions=None, orders=None):
    db = MagicMock()
    db.express = MagicMock()
    _audit = audit_log or []
    _decisions = decisions or []
    _shadow = shadow_decisions or []
    _positions = positions or []
    _orders = orders or []

    async def _list(model, filter=None):
        store = {
            "audit_log": _audit,
            "decisions": _decisions,
            "shadow_decisions": _shadow,
            "positions": _positions,
            "orders": _orders,
        }.get(model, [])
        if filter:
            return [r for r in store if all(r.get(k) == v for k, v in filter.items())]
        return store

    async def _create(model, data):
        row = dict(data)
        row["id"] = (
            len(_audit) + len(_decisions) + len(_shadow) + len(_positions) + len(_orders) + 1
        )
        {
            "audit_log": _audit,
            "decisions": _decisions,
            "shadow_decisions": _shadow,
            "positions": _positions,
            "orders": _orders,
        }.get(model, _audit).append(row)
        return row

    async def _read(model, pk):
        store = {
            "audit_log": _audit,
            "decisions": _decisions,
            "shadow_decisions": _shadow,
            "positions": _positions,
            "orders": _orders,
        }.get(model, [])
        for r in store:
            if str(r.get("id")) == str(pk):
                return r
        return None

    async def _update(model, pk, data):
        store = {
            "audit_log": _audit,
            "decisions": _decisions,
            "shadow_decisions": _shadow,
            "positions": _positions,
            "orders": _orders,
        }.get(model, [])
        for r in store:
            if str(r.get("id")) == str(pk):
                r.update(data)
                return r
        return None

    db.express.list = AsyncMock(side_effect=_list)
    db.express.create = AsyncMock(side_effect=_create)
    db.express.read = AsyncMock(side_effect=_read)
    db.express.update = AsyncMock(side_effect=_update)
    return db


async def _patch_get_db(db):
    import midas.api.routes as routes_mod

    original = routes_mod._get_db
    routes_mod._get_db = AsyncMock(return_value=db)
    return original, routes_mod


def _mock_request(user_id: str = "1"):
    """Create a mock Request with JWT user state."""
    req = MagicMock()
    req.state = MagicMock()
    req.state.user = {"sub": user_id, "email": f"user{user_id}@test.com"}
    return req


# ---------------------------------------------------------------------------
# T-23-03: Onboarding state machine
# ---------------------------------------------------------------------------


class TestOnboarding:
    @pytest.mark.asyncio
    async def test_connect_brokerage(self):
        db = _mock_db()
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = OnboardingRouter()
            result = await router.connect_brokerage(
                _mock_request(), {"user_id": "1", "connection_ref": "broker-abc"}
            )
            assert result["step"] == "connect_brokerage"
            assert result["status"] == "complete"
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_connect_brokerage_missing_ref(self):
        router = OnboardingRouter()
        with pytest.raises(Exception) as exc_info:
            await router.connect_brokerage(_mock_request(), {"user_id": "1"})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_risk_profile_requires_brokerage(self):
        db = _mock_db()
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = OnboardingRouter()
            with pytest.raises(Exception) as exc_info:
                await router.set_risk_profile(
                    _mock_request(),
                    {"user_id": "1", "vol_target_low": 0.1, "vol_target_high": 0.3},
                )
            assert exc_info.value.status_code == 409
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_risk_profile_validation(self):
        router = OnboardingRouter()
        with pytest.raises(Exception) as exc_info:
            await router.set_risk_profile(
                _mock_request(), {"user_id": "1", "vol_target_low": 0.5, "vol_target_high": 0.2}
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_full_onboarding_flow(self):
        db = _mock_db()
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = OnboardingRouter()
            req = _mock_request()
            await router.connect_brokerage(req, {"user_id": "1", "connection_ref": "brk"})
            await router.set_risk_profile(
                req,
                {
                    "user_id": "1",
                    "vol_target_low": 0.1,
                    "vol_target_high": 0.3,
                    "drawdown_ceiling": 0.15,
                    "concentration_cap": 0.20,
                },
            )
            await router.set_universe_constraints(req, {"user_id": "1", "sectors": ["tech"]})
            result = await router.activate(req, {"user_id": "1"})
            assert result["status"] == "active"
            assert result["mode"] == "paper"
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_activate_missing_steps(self):
        db = _mock_db()
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = OnboardingRouter()
            with pytest.raises(Exception) as exc_info:
                await router.activate(_mock_request(), {"user_id": "1"})
            assert exc_info.value.status_code == 409
            assert "connect_brokerage" in exc_info.value.detail
        finally:
            routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# T-23-04: Decision modify
# ---------------------------------------------------------------------------


class TestDecisionModify:
    @pytest.mark.asyncio
    async def test_modify_pending_decision(self):
        db = _mock_db(
            decisions=[
                {"id": "d1", "status": "pending", "rationale": "original", "autonomy_level": 0}
            ]
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = DecisionModifyRouter()
            result = await router.modify_decision(
                "d1",
                {
                    "parameter_overrides": {"stop_loss": 0.05},
                    "reason": "tighter stop",
                },
            )
            assert result["version"] == 1
            assert result["parameter_overrides"]["stop_loss"] == 0.05
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_modify_non_pending_rejected(self):
        db = _mock_db(
            decisions=[{"id": "d2", "status": "executed", "rationale": "", "autonomy_level": 0}]
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = DecisionModifyRouter()
            with pytest.raises(Exception) as exc_info:
                await router.modify_decision("d2", {"parameter_overrides": {"x": 1}})
            assert exc_info.value.status_code == 409
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_modify_nonexistent_decision(self):
        db = _mock_db()
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = DecisionModifyRouter()
            with pytest.raises(Exception) as exc_info:
                await router.modify_decision("missing", {"parameter_overrides": {"x": 1}})
            assert exc_info.value.status_code == 404
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_modify_no_overrides(self):
        router = DecisionModifyRouter()
        with pytest.raises(Exception) as exc_info:
            await router.modify_decision("d1", {"reason": "no overrides"})
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# T-23-05: Debate resolution
# ---------------------------------------------------------------------------


class TestDebateResolution:
    @pytest.mark.asyncio
    async def test_resolve_decision_updated(self):
        db = _mock_db(audit_log=[{"id": "t1", "action": "debate_thread"}])
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = DebateResolutionRouter()
            result = await router.resolve(
                "t1",
                {
                    "resolution_state": "decision_updated",
                    "updated_decision_id": "d1",
                },
            )
            assert result["resolution_state"] == "decision_updated"
            assert result["status"] == "resolved"
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_resolve_invalid_state(self):
        router = DebateResolutionRouter()
        with pytest.raises(Exception) as exc_info:
            await router.resolve("t1", {"resolution_state": "invalid_state"})
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_resolve_already_resolved(self):
        db = _mock_db(
            audit_log=[
                {"id": "t2", "action": "debate_thread"},
                {"action": "debate_resolved", "rule_name": "thread_t2", "details": "{}"},
            ]
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = DebateResolutionRouter()
            with pytest.raises(Exception) as exc_info:
                await router.resolve("t2", {"resolution_state": "decision_maintained"})
            assert exc_info.value.status_code == 409
            assert "immutable" in exc_info.value.detail
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_resolve_open_requires_note(self):
        db = _mock_db(audit_log=[{"id": "t3", "action": "debate_thread"}])
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = DebateResolutionRouter()
            with pytest.raises(Exception) as exc_info:
                await router.resolve("t3", {"resolution_state": "open"})
            assert exc_info.value.status_code == 422
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_resolve_envelope_change_requires_proposed_changes(self):
        db = _mock_db(audit_log=[{"id": "t4", "action": "debate_thread"}])
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = DebateResolutionRouter()
            with pytest.raises(Exception) as exc_info:
                await router.resolve("t4", {"resolution_state": "envelope_change_proposed"})
            assert exc_info.value.status_code == 422
        finally:
            routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# T-23-06: Notifications
# ---------------------------------------------------------------------------


class TestNotifications:
    @pytest.mark.asyncio
    async def test_get_preferences(self):
        router = NotificationRouter()
        result = await router.get_preferences()
        assert "tiers" in result
        assert result["tiers"]["calm"] == "silent_in_app"
        assert result["tiers"]["crisis"] == "emergency"
        assert "quiet_hours" in result

    @pytest.mark.asyncio
    async def test_update_preferences(self):
        router = NotificationRouter()
        result = await router.update_preferences(
            {
                "quiet_hours": {"start": "22:00", "end": "07:00"},
                "daily_attention_ceiling_minutes": 20,
            }
        )
        assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_update_invalid_quiet_hours(self):
        router = NotificationRouter()
        with pytest.raises(Exception) as exc_info:
            await router.update_preferences({"quiet_hours": {"start": "23:00", "end": "23:00"}})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_ceiling_out_of_range(self):
        router = NotificationRouter()
        with pytest.raises(Exception) as exc_info:
            await router.update_preferences({"daily_attention_ceiling_minutes": 200})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_attention_report(self):
        db = _mock_db()
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = NotificationRouter()
            result = await router.get_attention_report()
            assert "decision_seconds_this_week" in result
            assert "fatigue_signal_present" in result
        finally:
            routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# T-23-07: Backtest detail
# ---------------------------------------------------------------------------


class TestBacktestDetail:
    @pytest.mark.asyncio
    async def test_scorecard(self):
        db = _mock_db(shadow_decisions=[{"id": "run1"}])
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = BacktestDetailRouter()
            result = await router.get_scorecard("run1")
            assert result["run_id"] == "run1"
            assert "cagr" in result
            assert "sharpe" in result
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_scorecard_not_found(self):
        db = _mock_db()
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = BacktestDetailRouter()
            with pytest.raises(Exception) as exc_info:
                await router.get_scorecard("missing")
            assert exc_info.value.status_code == 404
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_regime_breakdown(self):
        db = _mock_db(shadow_decisions=[{"id": "run1"}])
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = BacktestDetailRouter()
            result = await router.get_regime_breakdown("run1")
            assert len(result["regimes"]) == 4
            assert result["regimes"][0]["name"] == "calm"
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_consistency(self):
        db = _mock_db(shadow_decisions=[{"id": "run1"}])
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = BacktestDetailRouter()
            result = await router.get_consistency("run1")
            assert "monthly" in result
            assert "quarterly" in result
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_cost_sensitivity(self):
        db = _mock_db(shadow_decisions=[{"id": "run1"}])
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = BacktestDetailRouter()
            result = await router.get_cost_sensitivity("run1")
            assert len(result["scenarios"]) == 4
            assert result["scenarios"][0]["label"] == "current"
        finally:
            routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# T-23-08: Paper-to-live transition
# ---------------------------------------------------------------------------


class TestPaperLive:
    @pytest.mark.asyncio
    async def test_transition_requires_confirmation(self):
        router = PaperLiveRouter()
        with pytest.raises(Exception) as exc_info:
            await router.transition({"user_confirmed": True, "biometric_confirmed": False})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_transition_already_live(self):
        db = _mock_db(
            audit_log=[
                {
                    "action": "paper_live_transition",
                    "details": json.dumps({"status": "live"}),
                }
            ]
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = PaperLiveRouter()
            with pytest.raises(Exception) as exc_info:
                await router.transition({"user_confirmed": True, "biometric_confirmed": True})
            assert exc_info.value.status_code == 409
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_transition_kill_switch_blocks(self):
        from datetime import datetime, timedelta, timezone

        paper_start = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        db = _mock_db(
            audit_log=[
                {
                    "action": "paper_live_transition",
                    "details": json.dumps({"status": "paper"}),
                    "filed_at": paper_start,
                },
                {"action": "kill_switch_activated", "details": json.dumps({"active": True})},
            ]
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = PaperLiveRouter()
            with pytest.raises(Exception) as exc_info:
                await router.transition({"user_confirmed": True, "biometric_confirmed": True})
            assert exc_info.value.status_code == 403
            assert "kill switch" in exc_info.value.detail
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_transition_paper_period_incomplete(self):
        from datetime import datetime, timedelta, timezone

        paper_start = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        db = _mock_db(
            audit_log=[
                {
                    "action": "paper_live_transition",
                    "details": json.dumps({"status": "paper"}),
                    "filed_at": paper_start,
                },
            ]
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = PaperLiveRouter()
            with pytest.raises(Exception) as exc_info:
                await router.transition({"user_confirmed": True, "biometric_confirmed": True})
            assert exc_info.value.status_code == 403
            assert "days remaining" in exc_info.value.detail
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_transition_success(self):
        from datetime import datetime, timedelta, timezone

        paper_start = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        db = _mock_db(
            audit_log=[
                {
                    "action": "paper_live_transition",
                    "details": json.dumps({"status": "paper"}),
                    "filed_at": paper_start,
                },
            ]
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = PaperLiveRouter()
            result = await router.transition({"user_confirmed": True, "biometric_confirmed": True})
            assert result["status"] == "live"
            assert result["autonomy_level"] == "L1_CoPilot"
        finally:
            routes_mod._get_db = orig


# ---------------------------------------------------------------------------
# T-23-09: Position history
# ---------------------------------------------------------------------------


class TestPositionHistory:
    @pytest.mark.asyncio
    async def test_position_history(self):
        db = _mock_db(
            positions=[{"ticker": "AAPL", "quantity": 100}],
            orders=[
                {
                    "ticker": "AAPL",
                    "side": "buy",
                    "filled_qty": 100,
                    "filled_price": 150.0,
                    "submitted_at": "2025-01-01",
                    "parent_decision_id": "d1",
                },
            ],
            audit_log=[],
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = PositionHistoryRouter()
            result = await router.get_position_history("AAPL")
            assert result["ticker"] == "AAPL"
            assert result["current_quantity"] == 100
            assert len(result["history"]) == 1
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_position_history_not_found(self):
        db = _mock_db()
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = PositionHistoryRouter()
            with pytest.raises(Exception) as exc_info:
                await router.get_position_history("NOPE")
            assert exc_info.value.status_code == 404
        finally:
            routes_mod._get_db = orig

    @pytest.mark.asyncio
    async def test_position_history_limit_validation(self):
        router = PositionHistoryRouter()
        with pytest.raises(Exception) as exc_info:
            await router.get_position_history("AAPL", limit=0)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_position_history_date_filtering(self):
        db = _mock_db(
            positions=[{"ticker": "AAPL", "quantity": 100}],
            orders=[
                {
                    "ticker": "AAPL",
                    "side": "buy",
                    "filled_qty": 50,
                    "filled_price": 150.0,
                    "submitted_at": "2025-01-01",
                },
                {
                    "ticker": "AAPL",
                    "side": "buy",
                    "filled_qty": 50,
                    "filled_price": 160.0,
                    "submitted_at": "2025-03-01",
                },
            ],
            audit_log=[],
        )
        orig, routes_mod = await _patch_get_db(db)
        try:
            router = PositionHistoryRouter()
            result = await router.get_position_history("AAPL", from_date="2025-02-01")
            assert len(result["history"]) == 1
            assert result["history"][0]["date"] == "2025-03-01"
        finally:
            routes_mod._get_db = orig
