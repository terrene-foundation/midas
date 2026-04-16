"""Tier 1 unit tests for CredentialStore.

Tests encryption, retrieval, rotation, expiration, and error handling
using MagicMock for DataFlow. Uses a real Fernet key for deterministic
encryption/decryption verification.

Ref: T-13-01
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from midas.fabric.credentials import CredentialStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fernet_key() -> str:
    """Generate a real Fernet key for deterministic encrypt/decrypt tests."""
    return Fernet.generate_key().decode()


@pytest.fixture
def mock_db() -> MagicMock:
    """DataFlow mock with async express.create and express.list."""
    db = MagicMock()
    db.express = MagicMock()
    db.express.create = AsyncMock()
    db.express.list = AsyncMock()
    return db


@pytest.fixture
def store(mock_db: MagicMock, fernet_key: str) -> CredentialStore:
    """CredentialStore backed by a mock DataFlow."""
    return CredentialStore(mock_db, fernet_key)


# ---------------------------------------------------------------------------
# Store and Retrieve
# ---------------------------------------------------------------------------


class TestCredentialStore:
    """CredentialStore: encrypt, store, retrieve, rotate, expire."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_returns_value(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """Store a credential then retrieve it; decrypted value matches original."""
        secret = "sk-test-api-key-12345"
        mock_db.express.create.return_value = {"id": 1, "service": "eodhd"}
        mock_db.express.list.return_value = [
            {
                "service": "eodhd",
                "key_name": "api_key",
                "encrypted_value": store._encrypt(secret),
                "active": True,
                "expires_at": "",
                "last_rotated_at": "2026-04-16T00:00:00+00:00",
            }
        ]

        await store.store("eodhd", "api_key", secret)
        result = await store.retrieve("eodhd", "api_key")

        assert result == secret

    @pytest.mark.asyncio
    async def test_store_calls_express_create(self, store: CredentialStore, mock_db: MagicMock):
        """store() calls db.express.create with the correct fields."""
        mock_db.express.create.return_value = {"id": 1}

        await store.store("fred", "api_key", "abc123", expires_at="2026-12-31")

        mock_db.express.create.assert_awaited_once()
        call_args = mock_db.express.create.call_args
        assert call_args[0][0] == "credentials"
        row = call_args[0][1]
        assert row["service"] == "fred"
        assert row["key_name"] == "api_key"
        assert row["expires_at"] == "2026-12-31"
        assert row["active"] is True
        # encrypted_value must be different from the plaintext
        assert row["encrypted_value"] != "abc123"

    @pytest.mark.asyncio
    async def test_retrieve_returns_none_when_no_rows(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """retrieve() returns None when no matching rows exist."""
        mock_db.express.list.return_value = []

        result = await store.retrieve("missing", "key")

        assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_returns_none_when_no_active(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """retrieve() returns None when rows exist but none are active."""
        mock_db.express.list.return_value = [
            {
                "service": "eodhd",
                "key_name": "api_key",
                "encrypted_value": store._encrypt("old"),
                "active": False,
            }
        ]

        result = await store.retrieve("eodhd", "api_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_picks_latest_active(self, store: CredentialStore, mock_db: MagicMock):
        """retrieve() returns the decrypted value of the last active credential."""
        old_encrypted = store._encrypt("old-key")
        new_encrypted = store._encrypt("new-key")
        mock_db.express.list.return_value = [
            {
                "service": "svc",
                "key_name": "k",
                "encrypted_value": old_encrypted,
                "active": True,
            },
            {
                "service": "svc",
                "key_name": "k",
                "encrypted_value": new_encrypted,
                "active": True,
            },
        ]

        result = await store.retrieve("svc", "k")

        assert result == "new-key"

    # ---------------------------------------------------------------------------
    # Rotate
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_rotate_stores_new_value(self, store: CredentialStore, mock_db: MagicMock):
        """rotate() delegates to store() with the new value."""
        mock_db.express.create.return_value = {"id": 2}

        result = await store.rotate("svc", "key", "rotated-secret")

        mock_db.express.create.assert_awaited_once()
        row = mock_db.express.create.call_args[0][1]
        assert row["service"] == "svc"
        assert row["key_name"] == "key"
        # The encrypted value should decrypt to the rotated secret
        assert store._decrypt(row["encrypted_value"]) == "rotated-secret"

    # ---------------------------------------------------------------------------
    # list_services
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_services_returns_metadata_without_values(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """list_services() returns rows with metadata fields but no encrypted_value."""
        mock_db.express.list.return_value = [
            {
                "service": "eodhd",
                "key_name": "api_key",
                "encrypted_value": "should_not_appear",
                "expires_at": "2026-12-31",
                "active": True,
                "last_rotated_at": "2026-04-16T00:00:00+00:00",
            },
            {
                "service": "fred",
                "key_name": "token",
                "encrypted_value": "also_hidden",
                "expires_at": "",
                "active": True,
                "last_rotated_at": "2026-04-15T00:00:00+00:00",
            },
        ]

        services = await store.list_services()

        assert len(services) == 2
        for svc in services:
            assert "encrypted_value" not in svc
            assert "service" in svc
            assert "key_name" in svc
            assert "expires_at" in svc
            assert "active" in svc
            assert "last_rotated_at" in svc

    # ---------------------------------------------------------------------------
    # is_expired
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_is_expired_returns_true_when_no_rows(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """is_expired() returns True when no credential rows exist."""
        mock_db.express.list.return_value = []

        result = await store.is_expired("missing", "key")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_expired_returns_false_when_no_expires_at(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """is_expired() returns False when expires_at is empty (never expires)."""
        mock_db.express.list.return_value = [
            {
                "service": "svc",
                "key_name": "k",
                "expires_at": "",
                "active": True,
            }
        ]

        result = await store.is_expired("svc", "k")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_expired_returns_true_when_past_expiration(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """is_expired() returns True when expires_at is in the past."""
        past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        mock_db.express.list.return_value = [
            {
                "service": "svc",
                "key_name": "k",
                "expires_at": past,
                "active": True,
            }
        ]

        result = await store.is_expired("svc", "k")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_expired_returns_false_when_future_expiration(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """is_expired() returns False when expires_at is in the future."""
        future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        mock_db.express.list.return_value = [
            {
                "service": "svc",
                "key_name": "k",
                "expires_at": future,
                "active": True,
            }
        ]

        result = await store.is_expired("svc", "k")

        assert result is False

    # ---------------------------------------------------------------------------
    # Error handling
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_failed_store_returns_empty_dict_with_error_log(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """store() returns empty dict when db.express.create raises."""
        mock_db.express.create.side_effect = RuntimeError("db connection lost")

        with patch("midas.fabric.credentials.logger") as mock_logger:
            result = await store.store("svc", "k", "val")

        assert result == {}
        mock_logger.error.assert_called_once()
        log_call = mock_logger.error.call_args
        assert log_call[0][0] == "credential.store_failed"

    @pytest.mark.asyncio
    async def test_failed_retrieve_returns_none_with_error_log(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """retrieve() returns None when db.express.list raises."""
        mock_db.express.list.side_effect = RuntimeError("timeout")

        with patch("midas.fabric.credentials.logger") as mock_logger:
            result = await store.retrieve("svc", "k")

        assert result is None
        mock_logger.error.assert_called_once()
        log_call = mock_logger.error.call_args
        assert log_call[0][0] == "credential.retrieve_failed"

    @pytest.mark.asyncio
    async def test_failed_list_services_returns_empty_list_with_error_log(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """list_services() returns empty list when db.express.list raises."""
        mock_db.express.list.side_effect = RuntimeError("unavailable")

        with patch("midas.fabric.credentials.logger") as mock_logger:
            result = await store.list_services()

        assert result == []
        mock_logger.error.assert_called_once()
        log_call = mock_logger.error.call_args
        assert log_call[0][0] == "credential.list_services_failed"

    @pytest.mark.asyncio
    async def test_failed_is_expired_returns_true_with_error_log(
        self, store: CredentialStore, mock_db: MagicMock
    ):
        """is_expired() returns True (fail-closed) when db.express.list raises."""
        mock_db.express.list.side_effect = RuntimeError("connection error")

        with patch("midas.fabric.credentials.logger") as mock_logger:
            result = await store.is_expired("svc", "k")

        assert result is True
        mock_logger.error.assert_called_once()
        log_call = mock_logger.error.call_args
        assert log_call[0][0] == "credential.is_expired_failed"
