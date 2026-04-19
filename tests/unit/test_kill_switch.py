"""Tier 1 tests for KillSwitch compliance integration.

Ref: specs/08-autonomy-and-trust.md S5
Ref: src/midas/compliance/kill_switch.py
"""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from midas.compliance.kill_switch import KillSwitch


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.express = MagicMock()
    db.express.create = AsyncMock(return_value={"id": 1})
    db.express.list = AsyncMock(return_value=[])
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

    async def test_activate_writes_audit_with_hash(self, ks, mock_db):
        result = await ks.activate("reason")
        mock_db.express.create.assert_called_once()
        call_args = mock_db.express.create.call_args
        assert call_args[0][0] == "audit_log"
        details = json.loads(call_args[0][1]["details"])
        assert "confirmation_code_hash" in details
        # Verify the hash matches the confirmation code
        code = result["confirmation_code"]
        expected_hash = hashlib.sha256(code.encode()).hexdigest()
        assert details["confirmation_code_hash"] == expected_hash

    async def test_activate_sets_active(self, ks):
        await ks.activate("test")
        assert await ks.is_active() is True


class TestClear:
    def _stub_activation_record(self, mock_db, confirmation_code: str) -> None:
        """Configure mock_db.express.list to return the activation audit record."""
        code_hash = hashlib.sha256(confirmation_code.encode()).hexdigest()
        mock_db.express.list = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "action": "kill_switch_activate",
                    "details": json.dumps({"reason": "test", "confirmation_code_hash": code_hash}),
                }
            ]
        )

    async def test_clear_rejected_when_not_active(self, ks):
        result = await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code="abc",
        )
        assert result["cleared"] is False

    async def test_clear_rejected_without_approval(self, ks, mock_db):
        activate_result = await ks.activate("test")
        self._stub_activation_record(mock_db, activate_result["confirmation_code"])
        result = await ks.clear(
            user_approved=False,
            state_brief={"z_t_posterior": "test"},
            confirmation_code="abc",
        )
        assert result["cleared"] is False

    async def test_clear_rejected_with_wrong_code(self, ks, mock_db):
        activate_result = await ks.activate("test")
        self._stub_activation_record(mock_db, activate_result["confirmation_code"])
        result = await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code="wrong-code",
        )
        assert result["cleared"] is False

    async def test_clear_succeeds_with_correct_code(self, ks, mock_db):
        activate_result = await ks.activate("test")
        code = activate_result["confirmation_code"]
        self._stub_activation_record(mock_db, code)
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
        self._stub_activation_record(mock_db, code)
        mock_db.express.create.reset_mock()
        await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code=code,
        )
        mock_db.express.create.assert_called_once()

    async def test_clear_resets_active(self, ks, mock_db):
        activate_result = await ks.activate("test")
        code = activate_result["confirmation_code"]
        self._stub_activation_record(mock_db, code)
        await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code=code,
        )
        assert await ks.is_active() is False


class TestConfirmationCodeSecurity:
    def _stub_activation_record(self, mock_db, confirmation_code: str) -> None:
        """Configure mock_db.express.list to return the activation audit record."""
        code_hash = hashlib.sha256(confirmation_code.encode()).hexdigest()
        mock_db.express.list = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "action": "kill_switch_activate",
                    "details": json.dumps({"reason": "test", "confirmation_code_hash": code_hash}),
                }
            ]
        )

    async def test_empty_code_rejected(self, ks):
        await ks.activate("test")
        result = await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test"},
            confirmation_code="",
        )
        assert result["cleared"] is False

    async def test_code_cleared_after_use(self, ks, mock_db):
        activate_result = await ks.activate("test")
        code = activate_result["confirmation_code"]
        self._stub_activation_record(mock_db, code)
        await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test", "drawdown_state": "10%"},
            confirmation_code=code,
        )
        # Replay attack: same code should fail because the second activation
        # generates a different hash. Stub with the new activation's hash.
        activate_result2 = await ks.activate("test2")
        new_code_hash = hashlib.sha256(activate_result2["confirmation_code"].encode()).hexdigest()
        mock_db.express.list = AsyncMock(
            return_value=[
                {
                    "id": 2,
                    "action": "kill_switch_activate",
                    "details": json.dumps(
                        {"reason": "test2", "confirmation_code_hash": new_code_hash}
                    ),
                }
            ]
        )
        result = await ks.clear(
            user_approved=True,
            state_brief={"z_t_posterior": "test"},
            confirmation_code=code,
        )
        assert result["cleared"] is False
