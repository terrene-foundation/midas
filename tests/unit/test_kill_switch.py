"""Tier 1 tests for KillSwitch compliance integration.

Ref: specs/08-autonomy-and-trust.md S5
Ref: src/midas/compliance/kill_switch.py
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from midas.compliance.kill_switch import KillSwitch


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.express = MagicMock()
    db.express.create = AsyncMock(return_value={"id": 1})
    return db


@pytest.fixture
def ks(mock_db):
    return KillSwitch(mock_db)


class TestActivate:
    async def test_activate_returns_active(self, ks):
        result = await ks.activate("test reason")
        assert result["active"] is True
        assert "reason" in result
        assert "confirmation_code" in result

    async def test_activate_generates_confirmation_code(self, ks):
        result = await ks.activate("test")
        assert result["confirmation_code"] is not None
        assert len(result["confirmation_code"]) == 16  # token_hex(8)

    async def test_activate_writes_audit(self, ks, mock_db):
        await ks.activate("reason")
        mock_db.express.create.assert_called_once()
        call_args = mock_db.express.create.call_args
        assert call_args[0][0] == "audit_log"

    async def test_activate_sets_active(self, ks):
        await ks.activate("test")
        assert await ks.is_active() is True


class TestClear:
    async def test_clear_rejected_when_not_active(self, ks):
        result = await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code="abc",
        )
        assert result["cleared"] is False

    async def test_clear_rejected_without_approval(self, ks):
        await ks.activate("test")
        result = await ks.clear(
            user_approved=False,
            state_brief={"z_t_posterior": "test"},
            confirmation_code="abc",
        )
        assert result["cleared"] is False

    async def test_clear_rejected_with_wrong_code(self, ks):
        await ks.activate("test")
        result = await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code="wrong-code",
        )
        assert result["cleared"] is False

    async def test_clear_succeeds_with_correct_code(self, ks):
        activate_result = await ks.activate("test")
        code = activate_result["confirmation_code"]
        result = await ks.clear(
            user_approved=True,
            state_brief={
                "z_t_posterior": "Elevated band",
                "drawdown_state": "Drawdown 14%",
                "compliance_events": ["state.kill_switch"],
            },
            confirmation_code=code,
        )
        assert result["cleared"] is True
        assert result["revert_level"] == 1

    async def test_clear_writes_audit(self, ks, mock_db):
        activate_result = await ks.activate("test")
        code = activate_result["confirmation_code"]
        mock_db.express.create.reset_mock()
        await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code=code,
        )
        mock_db.express.create.assert_called_once()

    async def test_clear_resets_active(self, ks):
        activate_result = await ks.activate("test")
        code = activate_result["confirmation_code"]
        await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code=code,
        )
        assert await ks.is_active() is False


class TestConfirmationCodeSecurity:
    async def test_empty_code_rejected(self, ks):
        await ks.activate("test")
        result = await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test"},
            confirmation_code="",
        )
        assert result["cleared"] is False

    async def test_code_cleared_after_use(self, ks):
        activate_result = await ks.activate("test")
        code = activate_result["confirmation_code"]
        await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code=code,
        )
        # Replay attack: same code should fail
        await ks.activate("test2")
        result = await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test"},
            confirmation_code=code,
        )
        assert result["cleared"] is False
