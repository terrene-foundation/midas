"""
JWT authentication system for the Midas API.

Provides login, token refresh, logout, and re-authentication endpoints.
Uses bcrypt for password hashing and PyJWT for token management.

Ref: specs/11 S6.2 (JWT auth), specs/08 S1 (trust boundary)
"""

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, Request

import midas.api.routes as _routes_module

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_JWT_SECRET: str | None = None
_JWT_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRY_MINUTES = 60 * 24  # 24 hours
_REFRESH_TOKEN_EXPIY_DAYS = 30


def _get_jwt_secret() -> str:
    global _JWT_SECRET
    if _JWT_SECRET is None:
        _JWT_SECRET = os.environ.get("JWT_SECRET", "")
        if not _JWT_SECRET:
            raise RuntimeError(
                "JWT_SECRET environment variable is not set. "
                "Set it to a cryptographically random string (min 32 chars)."
            )
    return _JWT_SECRET


# ---------------------------------------------------------------------------
# Password hashing (bcrypt when available, sha256 fallback for test envs)
# ---------------------------------------------------------------------------

try:
    import bcrypt

    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def _verify_password(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())

except ImportError:
    logger.warning("auth.bcrypt_unavailable_using_pbkdf2_fallback")
    _PBKDF2_ITERATIONS = 600_000

    def _hash_password(password: str) -> str:
        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
        ).hex()
        return f"{salt}${h}"

    def _verify_password(password: str, hashed: str) -> bool:
        salt, h = hashed.split("$", 1)
        computed = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
        ).hex()
        return hmac.compare_digest(computed, h)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def create_access_token(user_id: str, email: str) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=_ACCESS_TOKEN_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=_JWT_ALGORITHM)


def create_refresh_token() -> str:
    """Create a cryptographically random refresh token."""
    return secrets.token_urlsafe(64)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token. Raises on invalid/expired."""
    return jwt.decode(token, _get_jwt_secret(), algorithms=[_JWT_ALGORITHM])


_REAUTH_TOKEN_EXPIRY_MINUTES = 5


def create_reauth_token(user_id: str, email: str) -> str:
    """Create a short-lived JWT for re-authentication of sensitive operations."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "reauth",
        "iat": now,
        "exp": now + timedelta(minutes=_REAUTH_TOKEN_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=_JWT_ALGORITHM)


def verify_reauth_token(token: str) -> dict[str, Any]:
    """Verify a re-auth token. Raises on invalid/expired or wrong type."""
    payload = decode_access_token(token)
    if payload.get("type") != "reauth":
        raise HTTPException(status_code=401, detail="Invalid re-auth token")
    return payload


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class AuthRouter:
    """Authentication endpoints: login, refresh, logout, reauth.

    Ref: specs/11 S6.2
    """

    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route("/login", self.login, methods=["POST"])
        self.router.add_api_route("/refresh", self.refresh, methods=["POST"])
        self.router.add_api_route("/logout", self.logout, methods=["POST"])
        self.router.add_api_route("/reauth", self.reauth, methods=["POST"])

    async def login(self, request: Request) -> dict[str, Any]:
        """Authenticate with email + password, return JWT + refresh token."""
        body = await request.json()
        email = body.get("email", "").strip().lower()
        password = body.get("password", "")

        logger.info("auth.login.start", extra={"email": email})

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")

        db = await _routes_module._get_db()

        users = await db.express.list("users", filter={"email": email})
        if not users:
            logger.info("auth.login.failed", extra={"reason": "user_not_found"})
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user = users[0]
        stored_hash = user.get("password_hash", "")
        if not _verify_password(password, stored_hash):
            logger.info("auth.login.failed", extra={"reason": "wrong_password"})
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user_id = str(user["id"])
        access_token = create_access_token(user_id, email)
        refresh_token = create_refresh_token()

        refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        await db.express.create(
            "sessions",
            {
                "user_id": int(user_id),
                "refresh_token_hash": refresh_hash,
                "expires_at": (now + timedelta(days=_REFRESH_TOKEN_EXPIY_DAYS)).isoformat(),
                "revoked_at": "",
            },
        )

        logger.info("auth.login.ok", extra={"user_id": user_id})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": _ACCESS_TOKEN_EXPIRY_MINUTES * 60,
            "user": {"email": email, "id": user_id},
        }

    async def refresh(self, request: Request) -> dict[str, Any]:
        """Rotate refresh token: invalidate old, return new pair."""
        body = await request.json()
        old_refresh = body.get("refresh_token", "")

        logger.info("auth.refresh.start")

        if not old_refresh:
            raise HTTPException(status_code=400, detail="Refresh token required")

        db = await _routes_module._get_db()

        old_hash = hashlib.sha256(old_refresh.encode()).hexdigest()
        sessions = await db.express.list("sessions", filter={"refresh_token_hash": old_hash})

        if not sessions:
            logger.info("auth.refresh.failed", extra={"reason": "token_not_found"})
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        session = sessions[0]
        now = datetime.now(timezone.utc)

        revoked_at = session.get("revoked_at", "")
        if revoked_at:
            logger.info("auth.refresh.failed", extra={"reason": "token_revoked"})
            raise HTTPException(status_code=401, detail="Refresh token revoked")

        expires_at_str = session.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if now > expires_at:
                    logger.info("auth.refresh.failed", extra={"reason": "token_expired"})
                    raise HTTPException(status_code=401, detail="Refresh token expired")
            except (ValueError, TypeError):
                pass

        # Revoke old session
        await db.express.update("sessions", str(session["id"]), {"revoked_at": now.isoformat()})

        # Concurrent-use detection: if another non-revoked session exists for
        # this user that was created AFTER the old session, the refresh token
        # was likely stolen. Revoke ALL sessions for this user.
        user_id_int = session.get("user_id", 0)
        old_created = session.get("created_at", "") or session.get("expires_at", "")
        if user_id_int:
            all_sessions = await db.express.list("sessions", filter={"user_id": user_id_int})
            suspicious = [
                s
                for s in all_sessions
                if not s.get("revoked_at", "")
                and str(s.get("id")) != str(session["id"])
                and (s.get("created_at", "") or "") > old_created
            ]
            if suspicious:
                for s in all_sessions:
                    if not s.get("revoked_at", ""):
                        await db.express.update(
                            "sessions", str(s["id"]), {"revoked_at": now.isoformat()}
                        )
                logger.warning(
                    "auth.refresh.concurrent_use_detected",
                    extra={"user_id": str(user_id_int), "sessions_revoked": len(all_sessions)},
                )
                raise HTTPException(
                    status_code=401,
                    detail="Concurrent session detected. All sessions revoked.",
                )

        # Get user for new access token
        user_id = str(session.get("user_id", ""))
        users = []
        if user_id:
            try:
                user_row = await db.express.read("users", user_id)
                users = [user_row] if user_row else []
            except Exception as exc:
                logger.warning(
                    "auth.refresh.user_read_failed",
                    extra={"user_id": user_id, "error": str(exc)},
                )
        email = users[0].get("email", "") if users else ""

        new_access = create_access_token(user_id, email)
        new_refresh = create_refresh_token()
        new_hash = hashlib.sha256(new_refresh.encode()).hexdigest()

        await db.express.create(
            "sessions",
            {
                "user_id": int(user_id) if user_id else 0,
                "refresh_token_hash": new_hash,
                "expires_at": (now + timedelta(days=_REFRESH_TOKEN_EXPIY_DAYS)).isoformat(),
                "revoked_at": "",
            },
        )

        logger.info("auth.refresh.ok", extra={"user_id": user_id})

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "expires_in": _ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        }

    async def logout(self, request: Request) -> dict[str, Any]:
        """Revoke the refresh token."""
        body = await request.json()
        refresh_token = body.get("refresh_token", "")

        logger.info("auth.logout.start")

        db = await _routes_module._get_db()

        if refresh_token:
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            sessions = await db.express.list("sessions", filter={"refresh_token_hash": token_hash})
            for s in sessions:
                now = datetime.now(timezone.utc).isoformat()
                await db.express.update("sessions", str(s["id"]), {"revoked_at": now})
                logger.info(
                    "auth.logout.revoked",
                    extra={"session_id": str(s["id"]), "user_id": str(s.get("user_id", ""))},
                )

        return {"status": "logged_out"}

    async def reauth(self, request: Request) -> dict[str, Any]:
        """Re-authenticate for sensitive operations (approve, kill switch).

        Verifies password for the currently authenticated user.
        The Authorization header must contain a valid access token.
        """
        body = await request.json()
        password = body.get("password", "")

        logger.info("auth.reauth.start")

        if not password:
            raise HTTPException(status_code=400, detail="Password required")

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")

        try:
            payload = decode_access_token(auth_header[7:])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

        user_id = payload.get("sub", "")
        email = payload.get("email", "")

        db = await _routes_module._get_db()

        users = await db.express.list("users", filter={"email": email})
        if not users:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        stored_hash = users[0].get("password_hash", "")
        if not _verify_password(password, stored_hash):
            logger.info("auth.reauth.failed", extra={"user_id": user_id})
            raise HTTPException(status_code=401, detail="Invalid credentials")

        reauth_token = create_reauth_token(user_id, email)

        logger.info("auth.reauth.ok", extra={"user_id": user_id})

        return {
            "reauth_token": reauth_token,
            "expires_in": _REAUTH_TOKEN_EXPIRY_MINUTES * 60,
        }


# ---------------------------------------------------------------------------
# JWT middleware (replaces API key middleware)
# ---------------------------------------------------------------------------

# Paths that bypass JWT auth
AUTH_EXEMPT_PATHS = {
    "/api/v1/health",
    "/api/v1/health/",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def jwt_auth_enabled() -> bool:
    """Check if JWT auth is configured (JWT_SECRET is set and non-empty)."""
    secret = os.environ.get("JWT_SECRET", "")
    return bool(secret)


async def verify_jwt_or_pass(request: Request) -> dict[str, Any] | None:
    """Verify JWT token on the request. Returns payload or None for dev mode.

    Raises HTTPException(401) for invalid tokens.
    """
    path = request.url.path

    # Exempt paths
    if path in AUTH_EXEMPT_PATHS:
        return None
    if path.startswith("/api/v1/health/"):
        return None

    # Dev mode: no JWT_SECRET means no auth
    if not jwt_auth_enabled():
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    try:
        payload = decode_access_token(auth_header[7:])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# User seeding helper
# ---------------------------------------------------------------------------


async def seed_default_user(db, email: str, password: str) -> None:
    """Create the default admin user if no users exist.

    Args:
        db: DataFlow instance
        email: Admin user email (required - no default)
        password: Admin password (required - no default; use strong password)
    """
    users = await db.express.list("users")
    if users:
        return
    hashed = _hash_password(password)
    await db.express.create("users", {"email": email, "password_hash": hashed})
    logger.info("auth.seed_default_user", extra={"email": email})
