"""
Credential store with Fernet encryption for API keys and tokens.

All credentials are encrypted at rest using a Fernet key from .env.
Token values are NEVER logged.

Ref: T-13-01
"""

import structlog
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet
from dataflow import DataFlow

logger = structlog.get_logger(__name__)


class CredentialStore:
    """Encrypted credential storage backed by DataFlow."""

    def __init__(self, db: DataFlow, fernet_key: str) -> None:
        self._db = db
        self._fernet = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def _decrypt(self, encrypted: str) -> str:
        return self._fernet.decrypt(encrypted.encode()).decode()

    async def store(
        self,
        service: str,
        key_name: str,
        value: str,
        expires_at: str = "",
    ) -> dict[str, Any]:
        """Store an encrypted credential."""
        encrypted_value = self._encrypt(value)
        row = {
            "service": service,
            "key_name": key_name,
            "encrypted_value": encrypted_value,
            "expires_at": expires_at,
            "last_rotated_at": datetime.now(timezone.utc).isoformat(),
            "active": True,
        }
        try:
            result = await self._db.express.create("credentials", row)
            logger.info("credential.stored", service=service, key_name=key_name)
            return result
        except Exception as exc:
            logger.error("credential.store_failed", service=service, error=str(exc))
            return {}

    async def retrieve(self, service: str, key_name: str) -> str | None:
        """Retrieve and decrypt a credential. Returns None if not found."""
        try:
            rows = await self._db.express.list(
                "credentials", filter={"service": service, "key_name": key_name}
            )
            if not rows:
                return None
            # Get the most recent active credential
            active = [r for r in rows if r.get("active")]
            if not active:
                return None
            latest = active[-1]
            encrypted = latest.get("encrypted_value", "")
            return self._decrypt(encrypted)
        except Exception as exc:
            logger.error("credential.retrieve_failed", service=service, error=str(exc))
            return None

    async def rotate(self, service: str, key_name: str, new_value: str) -> dict[str, Any]:
        """Rotate a credential — store new encrypted value."""
        return await self.store(service, key_name, new_value)

    async def list_services(self) -> list[dict[str, Any]]:
        """List all stored credentials (metadata only, no values)."""
        try:
            rows = await self._db.express.list("credentials")
            return [
                {
                    "service": r.get("service"),
                    "key_name": r.get("key_name"),
                    "expires_at": r.get("expires_at"),
                    "active": r.get("active"),
                    "last_rotated_at": r.get("last_rotated_at"),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("credential.list_services_failed", error=str(exc))
            return []

    async def is_expired(self, service: str, key_name: str) -> bool:
        """Check if a credential has expired."""
        try:
            rows = await self._db.express.list(
                "credentials", filter={"service": service, "key_name": key_name}
            )
            if not rows:
                return True
            expires = rows[-1].get("expires_at", "")
            if not expires:
                return False
            exp_dt = datetime.fromisoformat(expires)
            return datetime.now(timezone.utc) > exp_dt
        except Exception as exc:
            logger.error("credential.is_expired_failed", service=service, error=str(exc))
            return True
