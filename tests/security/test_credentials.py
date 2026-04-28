"""Security regression tests for CredentialStore.

Tests that Fernet keys are validated for weak patterns (e.g., 'example',
'changeme') and that the store/retrieve round-trip works correctly.

Ref: round-N-redteam security findings on credential storage.

Note: These tests verify the weak key detection feature. If the feature
is not implemented, tests will fail, signaling the security gap.
"""

import base64
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

import pytest
from cryptography.fernet import Fernet

from midas.fabric.credentials import CredentialStore

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_valid_fernet_key_with_pattern(pattern: str) -> str:
    """Create a valid Fernet key that contains the given pattern when decoded.

    A Fernet key is 32 url-safe base64-encoded bytes.
    We create 32 bytes that include the pattern, then base64 encode it.
    """
    # Create 32 bytes with the pattern embedded
    pattern_bytes = pattern.encode("ascii")
    # Fill the rest with random bytes
    key_material = bytearray(32)
    # Embed the pattern at the start
    for i, b in enumerate(pattern_bytes[:32]):
        key_material[i] = b
    # Ensure the key is exactly 32 bytes
    key_bytes = bytes(key_material[:32])
    return base64.urlsafe_b64encode(key_bytes).decode("ascii")


@pytest.fixture
def real_fernet_key() -> str:
    """Generate a real Fernet key for valid key tests."""
    return Fernet.generate_key().decode()


@pytest.fixture
def mock_db() -> MagicMock:
    """DataFlow mock with async express methods."""
    db = MagicMock()
    db.express = MagicMock()
    db.express.create = AsyncMock()
    db.express.list = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Weak key detection
# ---------------------------------------------------------------------------

class TestCredentialStoreWeakKeyDetection:
    """Fernet key weak pattern detection — keys with 'example' or 'changeme' should warn."""

    def test_key_with_example_pattern_triggers_warning(
        self, mock_db: MagicMock, caplog
    ):
        """Fernet key containing 'example' should trigger a warning log.

        Weak keys (example patterns, default values, test placeholders) must
        not be silently accepted in production — they indicate misconfiguration
        or accidental substitution of a real key.
        """
        # Create a valid Fernet key that contains "example" in its decoded form
        weak_key = _make_valid_fernet_key_with_pattern("example")

        # Verify the key is valid Fernet format
        try:
            Fernet(weak_key.encode())
        except Exception:
            pytest.fail(f"Generated key is not valid Fernet format: {weak_key}")

        with caplog.at_level("WARNING"):
            # If weak key detection exists, it should warn when the key is used
            store = CredentialStore(mock_db, weak_key)

            # Trigger encryption which should trigger weak key detection
            try:
                store._encrypt("test_value")
            except Exception:
                pass  # Encryption may fail with weak key; we care about the warning

        # Check that a warning was emitted about the weak key pattern
        warning_emitted = any(
            "example" in record.message.lower() or "weak" in record.message.lower()
            for record in caplog.records
        )
        # This test documents the security gap: weak key detection is missing
        assert (
            warning_emitted
        ), "Weak key containing 'example' did not trigger warning (weak key detection may be missing)"

    def test_key_with_changeme_pattern_triggers_warning(
        self, mock_db: MagicMock, caplog
    ):
        """Fernet key containing 'changeme' should trigger a warning log."""
        weak_key = _make_valid_fernet_key_with_pattern("changeme")

        # Verify the key is valid Fernet format
        try:
            Fernet(weak_key.encode())
        except Exception:
            pytest.fail(f"Generated key is not valid Fernet format: {weak_key}")

        with caplog.at_level("WARNING"):
            store = CredentialStore(mock_db, weak_key)
            try:
                store._encrypt("test_value")
            except Exception:
                pass

        warning_emitted = any(
            "changeme" in record.message.lower() or "weak" in record.message.lower()
            for record in caplog.records
        )
        assert (
            warning_emitted
        ), "Weak key containing 'changeme' did not trigger warning (weak key detection may be missing)"

    def test_valid_key_does_not_warn(self, mock_db: MagicMock, caplog):
        """A valid Fernet key (from Fernet.generate_key) should not trigger weak key warning."""
        valid_key = Fernet.generate_key().decode()

        with caplog.at_level("WARNING"):
            store = CredentialStore(mock_db, valid_key)
            # Encrypt something to ensure the store is fully initialized
            try:
                encrypted = store._encrypt("test_value")
                # Verify encryption actually worked
                assert encrypted != "test_value"
            except Exception as exc:
                pytest.fail(f"Encryption with valid key failed: {exc}")

        # No weak key warnings should be emitted for a valid generated key
        weak_warnings = [
            record
            for record in caplog.records
            if "weak" in record.message.lower()
            or ("example" in record.message.lower() and "fernet" in record.message.lower())
            or ("changeme" in record.message.lower())
        ]
        assert (
            len(weak_warnings) == 0
        ), f"Valid key triggered unexpected warning: {[r.message for r in weak_warnings]}"


# ---------------------------------------------------------------------------
# Round-trip store and retrieve
# ---------------------------------------------------------------------------

class TestCredentialStoreRoundTrip:
    """store/retrieve round-trip works correctly with valid keys."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_round_trip(self, mock_db: MagicMock, real_fernet_key: str):
        """Store a credential and retrieve it — decrypted value matches original."""
        secret = "sk-live-api-key-abc123xyz"
        encrypted_value = Fernet(real_fernet_key.encode()).encrypt(secret.encode()).decode()

        mock_db.express.create.return_value = {"id": 1, "service": "test_service"}
        mock_db.express.list.return_value = [
            {
                "service": "test_service",
                "key_name": "api_key",
                "encrypted_value": encrypted_value,
                "active": True,
                "expires_at": "",
                "last_rotated_at": "2026-04-01T00:00:00+00:00",
            }
        ]

        store = CredentialStore(mock_db, real_fernet_key)
        await store.store("test_service", "api_key", secret)
        result = await store.retrieve("test_service", "api_key")

        assert result == secret

    @pytest.mark.asyncio
    async def test_encrypted_value_is_not_plaintext(
        self, mock_db: MagicMock, real_fernet_key: str
    ):
        """Store operation must encrypt the value — encrypted_value != plaintext."""
        mock_db.express.create.return_value = {"id": 1}

        store = CredentialStore(mock_db, real_fernet_key)
        await store.store("svc", "key", "super_secret_value")

        call_args = mock_db.express.create.call_args
        row = call_args[0][1]
        assert row["encrypted_value"] != "super_secret_value"
        assert len(row["encrypted_value"]) > 0

    @pytest.mark.asyncio
    async def test_retrieve_returns_none_for_missing_credential(
        self, mock_db: MagicMock, real_fernet_key: str
    ):
        """retrieve() returns None when no matching credential exists."""
        mock_db.express.list.return_value = []

        store = CredentialStore(mock_db, real_fernet_key)
        result = await store.retrieve("nonexistent", "key")

        assert result is None

    @pytest.mark.asyncio
    async def test_store_and_retrieve_with_expiry(
        self, mock_db: MagicMock, real_fernet_key: str
    ):
        """Store and retrieve a credential with an expiry date."""
        secret = "temp_token_xyz"
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        encrypted_value = Fernet(real_fernet_key.encode()).encrypt(secret.encode()).decode()

        mock_db.express.create.return_value = {"id": 1}
        mock_db.express.list.return_value = [
            {
                "service": "temp_svc",
                "key_name": "token",
                "encrypted_value": encrypted_value,
                "active": True,
                "expires_at": future,
                "last_rotated_at": "2026-04-01T00:00:00+00:00",
            }
        ]

        store = CredentialStore(mock_db, real_fernet_key)
        await store.store("temp_svc", "token", secret, expires_at=future)
        result = await store.retrieve("temp_svc", "token")

        assert result == secret
