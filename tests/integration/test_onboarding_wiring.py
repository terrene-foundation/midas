"""Tier 2 integration tests for OnboardingRouter state machine.

Tests the 4-step onboarding state machine logic:
  connect_brokerage → set_risk_profile → set_universe_constraints → activate

Validates: step ordering, validation rules, idempotency, and error paths.
Uses an in-memory state store to isolate from DataFlow caching issues
(the DataFlow express query cache doesn't invalidate on writes — see
journal entry for details).

Ref: specs/08-onboarding.md S2.1, specs/10-risk-controls.md S3
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from midas.api.routes_extended import OnboardingRouter


class _FakeExpress:
    """In-memory substitute for db.express create/list."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    async def create(self, table: str, row: dict) -> dict:
        key = f"{row.get('action')}:{row.get('rule_name')}"
        self._store[key] = row
        return {**row, "rows_affected": 1}

    async def list(self, table: str, **kwargs) -> list[dict]:
        return list(self._store.values())


class _FakeDB:
    """Minimal fake DB with .express attribute."""

    def __init__(self):
        self.express = _FakeExpress()


def _uid() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def router():
    """OnboardingRouter with _get_db, _resolve_user, and state storage patched."""
    r = OnboardingRouter()
    fake_db = _FakeDB()

    async def _fake_get_db():
        return fake_db

    @staticmethod
    def _fake_resolve_user(request, body):
        return str(body.get("user_id") or "default")

    with patch("midas.api.routes_extended._get_db", _fake_get_db):
        with patch.object(OnboardingRouter, "_resolve_user", _fake_resolve_user):
            yield r


class TestOnboardingConnectBrokerage:

    @pytest.mark.asyncio
    async def test_connect_succeeds_with_ref(self, router):
        uid = _uid()
        result = await router.connect_brokerage(
            None, {"connection_ref": "ibkr-account-12345", "user_id": uid}
        )
        assert result["step"] == "connect_brokerage"
        assert result["status"] == "complete"

    @pytest.mark.asyncio
    async def test_connect_rejects_empty_ref(self, router):
        uid = _uid()
        with pytest.raises(HTTPException) as exc_info:
            await router.connect_brokerage(None, {"connection_ref": "", "user_id": uid})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_connect_rejects_missing_ref(self, router):
        uid = _uid()
        with pytest.raises(HTTPException) as exc_info:
            await router.connect_brokerage(None, {"user_id": uid})
        assert exc_info.value.status_code == 400


class TestOnboardingRiskProfile:

    @pytest.mark.asyncio
    async def test_risk_profile_succeeds_after_connect(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        result = await router.set_risk_profile(
            None,
            {
                "user_id": uid,
                "vol_target_low": 0.10,
                "vol_target_high": 0.20,
                "drawdown_ceiling": 0.10,
                "concentration_cap": 0.10,
            },
        )
        assert result["step"] == "risk_profile"
        assert result["status"] == "complete"

    @pytest.mark.asyncio
    async def test_risk_profile_rejects_inverted_vol(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        with pytest.raises(HTTPException) as exc_info:
            await router.set_risk_profile(
                None,
                {"user_id": uid, "vol_target_low": 0.30, "vol_target_high": 0.10},
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_risk_profile_rejects_without_brokerage(self, router):
        uid = _uid()
        with pytest.raises(HTTPException) as exc_info:
            await router.set_risk_profile(
                None,
                {"user_id": uid, "vol_target_low": 0.10, "vol_target_high": 0.20},
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_risk_profile_rejects_out_of_range_dd(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        with pytest.raises(HTTPException) as exc_info:
            await router.set_risk_profile(
                None,
                {
                    "user_id": uid,
                    "vol_target_low": 0.10,
                    "vol_target_high": 0.20,
                    "drawdown_ceiling": 0.50,
                },
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_risk_profile_rejects_missing_vol(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        with pytest.raises(HTTPException) as exc_info:
            await router.set_risk_profile(None, {"user_id": uid, "drawdown_ceiling": 0.10})
        assert exc_info.value.status_code == 400


class TestOnboardingUniverseConstraints:

    @pytest.mark.asyncio
    async def test_universe_succeeds_with_exclusions(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        await router.set_risk_profile(
            None,
            {"user_id": uid, "vol_target_low": 0.10, "vol_target_high": 0.20},
        )
        result = await router.set_universe_constraints(
            None, {"user_id": uid, "universe_exclusions": ["TSLA", "COIN"]}
        )
        assert result["step"] == "universe_constraints"

    @pytest.mark.asyncio
    async def test_universe_succeeds_with_empty_exclusions(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        await router.set_risk_profile(
            None,
            {"user_id": uid, "vol_target_low": 0.10, "vol_target_high": 0.20},
        )
        result = await router.set_universe_constraints(
            None, {"user_id": uid, "universe_exclusions": []}
        )
        assert result["status"] == "complete"

    @pytest.mark.asyncio
    async def test_universe_rejects_without_risk_profile(self, router):
        uid = _uid()
        with pytest.raises(HTTPException) as exc_info:
            await router.set_universe_constraints(None, {"user_id": uid, "universe_exclusions": []})
        assert exc_info.value.status_code == 409


class TestOnboardingActivate:

    @pytest.mark.asyncio
    async def test_activate_succeeds(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        await router.set_risk_profile(
            None,
            {"user_id": uid, "vol_target_low": 0.10, "vol_target_high": 0.20},
        )
        await router.set_universe_constraints(None, {"user_id": uid, "universe_exclusions": []})
        result = await router.activate(None, {"user_id": uid})
        assert result["status"] == "active"
        assert result["mode"] == "paper"

    @pytest.mark.asyncio
    async def test_activate_rejects_when_steps_missing(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        with pytest.raises(HTTPException) as exc_info:
            await router.activate(None, {"user_id": uid})
        assert exc_info.value.status_code == 409
        assert "risk_profile" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_activate_idempotent(self, router):
        uid = _uid()
        await router.connect_brokerage(None, {"connection_ref": "ibkr-test", "user_id": uid})
        await router.set_risk_profile(
            None,
            {"user_id": uid, "vol_target_low": 0.10, "vol_target_high": 0.20},
        )
        await router.set_universe_constraints(None, {"user_id": uid, "universe_exclusions": []})
        await router.activate(None, {"user_id": uid})
        result = await router.activate(None, {"user_id": uid})
        assert result["status"] == "already_active"


class TestOnboardingFullFlow:

    @pytest.mark.asyncio
    async def test_complete_flow(self, router):
        uid = _uid()

        # Step 1
        r = await router.connect_brokerage(None, {"connection_ref": "ibkr-U123456", "user_id": uid})
        assert r["status"] == "complete"

        # Step 2
        r = await router.set_risk_profile(
            None,
            {
                "user_id": uid,
                "vol_target_low": 0.08,
                "vol_target_high": 0.15,
                "drawdown_ceiling": 0.10,
                "concentration_cap": 0.12,
            },
        )
        assert r["status"] == "complete"

        # Step 3
        r = await router.set_universe_constraints(
            None, {"user_id": uid, "universe_exclusions": ["MSTR", "COIN"]}
        )
        assert r["status"] == "complete"

        # Step 4
        r = await router.activate(None, {"user_id": uid})
        assert r["mode"] == "paper"

        # Idempotent re-activation
        r = await router.activate(None, {"user_id": uid})
        assert r["status"] == "already_active"
