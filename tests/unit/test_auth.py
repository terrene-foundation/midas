"""Tests for JWT auth system — T-23-01.

Covers: login, refresh, logout, reauth, token validation, password hashing.
Uses mocked DataFlow for persistence (Tier 1 unit tests).
"""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-must-be-32-bytes-long")

from midas.api.auth import (
    AuthRouter,
    create_access_token,
    decode_access_token,
    seed_default_user,
    _hash_password,
    _verify_password,
    jwt_auth_enabled,
    verify_jwt_or_pass,
)


def _mock_db(users=None, sessions=None):
    """Create a mock DataFlow with async express methods."""
    db = MagicMock()
    db.express = MagicMock()
    _users = users or []
    _sessions = sessions or []

    async def _list(model, filter=None):
        if model == "users":
            if filter:
                return [u for u in _users if all(u.get(k) == v for k, v in filter.items())]
            return _users
        if model == "sessions":
            if filter:
                return [s for s in _sessions if all(s.get(k) == v for k, v in filter.items())]
            return _sessions
        return []

    async def _create(model, data):
        row = dict(data)
        row["id"] = len(_users) + len(_sessions) + 1
        if model == "users":
            _users.append(row)
        elif model == "sessions":
            _sessions.append(row)
        return row

    async def _read(model, pk):
        if model == "users":
            for u in _users:
                if str(u.get("id")) == str(pk):
                    return u
        if model == "sessions":
            for s in _sessions:
                if str(s.get("id")) == str(pk):
                    return s
        return None

    async def _update(model, pk, data):
        store = _users if model == "users" else _sessions
        for row in store:
            if str(row.get("id")) == str(pk):
                row.update(data)
                return row
        return None

    db.express.list = AsyncMock(side_effect=_list)
    db.express.create = AsyncMock(side_effect=_create)
    db.express.read = AsyncMock(side_effect=_read)
    db.express.update = AsyncMock(side_effect=_update)
    return db


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        pw = "secure_password_123"
        hashed = _hash_password(pw)
        assert hashed != pw
        assert _verify_password(pw, hashed) is True

    def test_wrong_password_fails(self):
        hashed = _hash_password("correct")
        assert _verify_password("wrong", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = _hash_password("same")
        h2 = _hash_password("same")
        assert h1 != h2  # different salt


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------


class TestJWTTokens:
    def test_create_and_decode_access_token(self):
        token = create_access_token("42", "test@example.com")
        payload = decode_access_token(token)
        assert payload["sub"] == "42"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_expired_token_raises(self):
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": "1",
            "email": "x@y.com",
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = pyjwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_invalid_token_raises(self):
        import jwt as pyjwt

        with pytest.raises(pyjwt.InvalidTokenError):
            decode_access_token("this.is.not.valid")


# ---------------------------------------------------------------------------
# Seed default user
# ---------------------------------------------------------------------------


class TestSeedDefaultUser:
    @pytest.mark.asyncio
    async def test_seeds_when_no_users(self):
        db = _mock_db()
        await seed_default_user(db, email="admin@test.local", password="strong-test-password")
        db.express.list.assert_called()
        db.express.create.assert_called_once()
        call_args = db.express.create.call_args[0]
        assert call_args[0] == "users"
        assert call_args[1]["email"] == "admin@test.local"

    @pytest.mark.asyncio
    async def test_does_not_seed_if_users_exist(self):
        db = _mock_db(users=[{"id": 1, "email": "existing@x.com", "password_hash": "x"}])
        await seed_default_user(db, email="admin@test.local", password="strong-test-password")
        db.express.create.assert_not_called()


# ---------------------------------------------------------------------------
# Auth router endpoints
# ---------------------------------------------------------------------------


class TestAuthLogin:
    @pytest.mark.asyncio
    async def test_login_valid_credentials(self):
        hashed = _hash_password("testpass")
        db = _mock_db(users=[{"id": 1, "email": "user@test.com", "password_hash": hashed}])

        router = AuthRouter()
        from midas.api import routes as routes_mod

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.json = AsyncMock(
                return_value={"email": "user@test.com", "password": "testpass"}
            )
            result = await router.login(request)
            assert "access_token" in result
            assert "refresh_token" in result
            assert result["user"]["email"] == "user@test.com"
        finally:
            routes_mod._get_db = original_get_db

    @pytest.mark.asyncio
    async def test_login_invalid_password(self):
        hashed = _hash_password("correct")
        db = _mock_db(users=[{"id": 1, "email": "user@test.com", "password_hash": hashed}])

        router = AuthRouter()
        from midas.api import routes as routes_mod
        from fastapi import HTTPException

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.json = AsyncMock(return_value={"email": "user@test.com", "password": "wrong"})
            with pytest.raises(HTTPException) as exc_info:
                await router.login(request)
            assert exc_info.value.status_code == 401
            assert "Invalid credentials" in str(exc_info.value.detail)
        finally:
            routes_mod._get_db = original_get_db

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self):
        db = _mock_db()

        router = AuthRouter()
        from midas.api import routes as routes_mod
        from fastapi import HTTPException

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.json = AsyncMock(return_value={"email": "noone@test.com", "password": "x"})
            with pytest.raises(HTTPException) as exc_info:
                await router.login(request)
            assert exc_info.value.status_code == 401
        finally:
            routes_mod._get_db = original_get_db

    @pytest.mark.asyncio
    async def test_login_empty_fields(self):
        db = _mock_db()
        router = AuthRouter()
        from midas.api import routes as routes_mod
        from fastapi import HTTPException

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.json = AsyncMock(return_value={"email": "", "password": ""})
            with pytest.raises(HTTPException) as exc_info:
                await router.login(request)
            assert exc_info.value.status_code == 400
        finally:
            routes_mod._get_db = original_get_db

    @pytest.mark.asyncio
    async def test_login_no_email_enumeration(self):
        """Invalid password for existing user and nonexistent user return same error."""
        hashed = _hash_password("correct")
        db = _mock_db(users=[{"id": 1, "email": "exists@test.com", "password_hash": hashed}])

        router = AuthRouter()
        from midas.api import routes as routes_mod
        from fastapi import HTTPException

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            # Wrong password for existing user
            request = AsyncMock()
            request.json = AsyncMock(return_value={"email": "exists@test.com", "password": "wrong"})
            with pytest.raises(HTTPException) as exc1:
                await router.login(request)

            # Nonexistent user
            request.json = AsyncMock(return_value={"email": "ghost@test.com", "password": "wrong"})
            with pytest.raises(HTTPException) as exc2:
                await router.login(request)

            assert exc1.value.status_code == exc2.value.status_code == 401
            assert exc1.value.detail == exc2.value.detail
        finally:
            routes_mod._get_db = original_get_db


class TestAuthRefresh:
    @pytest.mark.asyncio
    async def test_refresh_rotates_tokens(self):
        hashed = _hash_password("testpass")
        db = _mock_db(
            users=[{"id": 1, "email": "user@test.com", "password_hash": hashed}],
            sessions=[],
        )

        router = AuthRouter()
        from midas.api import routes as routes_mod

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            # Login
            request = AsyncMock()
            request.json = AsyncMock(
                return_value={"email": "user@test.com", "password": "testpass"}
            )
            login_result = await router.login(request)
            old_refresh = login_result["refresh_token"]

            # Refresh
            request.json = AsyncMock(return_value={"refresh_token": old_refresh})
            result = await router.refresh(request)
            assert "access_token" in result
            assert "refresh_token" in result
            assert result["refresh_token"] != old_refresh
        finally:
            routes_mod._get_db = original_get_db

    @pytest.mark.asyncio
    async def test_refresh_revoked_token_rejected(self):
        import hashlib
        from datetime import datetime, timedelta, timezone

        old_token = "old_refresh_token"
        old_hash = hashlib.sha256(old_token.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        db = _mock_db(
            users=[{"id": 1, "email": "user@test.com", "password_hash": "x"}],
            sessions=[
                {
                    "id": 1,
                    "user_id": 1,
                    "refresh_token_hash": old_hash,
                    "expires_at": (now + timedelta(days=30)).isoformat(),
                    "revoked_at": now.isoformat(),
                }
            ],
        )

        router = AuthRouter()
        from midas.api import routes as routes_mod
        from fastapi import HTTPException

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.json = AsyncMock(return_value={"refresh_token": old_token})
            with pytest.raises(HTTPException) as exc_info:
                await router.refresh(request)
            assert exc_info.value.status_code == 401
        finally:
            routes_mod._get_db = original_get_db

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_rejected(self):
        db = _mock_db()
        router = AuthRouter()
        from midas.api import routes as routes_mod
        from fastapi import HTTPException

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.json = AsyncMock(return_value={"refresh_token": "nonexistent"})
            with pytest.raises(HTTPException) as exc_info:
                await router.refresh(request)
            assert exc_info.value.status_code == 401
        finally:
            routes_mod._get_db = original_get_db


class TestAuthLogout:
    @pytest.mark.asyncio
    async def test_logout_revokes_token(self):
        hashed = _hash_password("testpass")
        db = _mock_db(
            users=[{"id": 1, "email": "user@test.com", "password_hash": hashed}],
            sessions=[],
        )

        router = AuthRouter()
        from midas.api import routes as routes_mod

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.json = AsyncMock(
                return_value={"email": "user@test.com", "password": "testpass"}
            )
            login_result = await router.login(request)

            request.json = AsyncMock(return_value={"refresh_token": login_result["refresh_token"]})
            result = await router.logout(request)
            assert result["status"] == "logged_out"
        finally:
            routes_mod._get_db = original_get_db


class TestAuthReauth:
    @pytest.mark.asyncio
    async def test_reauth_valid_password(self):
        hashed = _hash_password("testpass")
        db = _mock_db(
            users=[{"id": 1, "email": "user@test.com", "password_hash": hashed}],
        )
        token = create_access_token("1", "user@test.com")

        router = AuthRouter()
        from midas.api import routes as routes_mod

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.headers = {"Authorization": f"Bearer {token}"}
            request.json = AsyncMock(return_value={"password": "testpass"})

            result = await router.reauth(request)
            assert "access_token" in result
            assert result["expires_in"] == 86400
        finally:
            routes_mod._get_db = original_get_db

    @pytest.mark.asyncio
    async def test_reauth_wrong_password(self):
        hashed = _hash_password("correct")
        db = _mock_db(
            users=[{"id": 1, "email": "user@test.com", "password_hash": hashed}],
        )
        token = create_access_token("1", "user@test.com")

        router = AuthRouter()
        from midas.api import routes as routes_mod
        from fastapi import HTTPException

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.headers = {"Authorization": f"Bearer {token}"}
            request.json = AsyncMock(return_value={"password": "wrong"})

            with pytest.raises(HTTPException) as exc_info:
                await router.reauth(request)
            assert exc_info.value.status_code == 401
        finally:
            routes_mod._get_db = original_get_db

    @pytest.mark.asyncio
    async def test_reauth_missing_token(self):
        db = _mock_db()
        router = AuthRouter()
        from midas.api import routes as routes_mod
        from fastapi import HTTPException

        original_get_db = routes_mod._get_db
        routes_mod._get_db = AsyncMock(return_value=db)
        try:
            request = AsyncMock()
            request.headers = {}
            request.json = AsyncMock(return_value={"password": "test"})

            with pytest.raises(HTTPException) as exc_info:
                await router.reauth(request)
            assert exc_info.value.status_code == 401
        finally:
            routes_mod._get_db = original_get_db


# ---------------------------------------------------------------------------
# JWT middleware and helpers
# ---------------------------------------------------------------------------


class TestJWTMiddleware:
    def test_jwt_auth_enabled_when_secret_set(self):
        assert jwt_auth_enabled() is True

    def test_jwt_auth_disabled_when_secret_empty(self):
        original = os.environ.pop("JWT_SECRET", None)
        try:
            assert jwt_auth_enabled() is False
        finally:
            if original:
                os.environ["JWT_SECRET"] = original

    @pytest.mark.asyncio
    async def test_exempt_path_returns_none(self):
        request = AsyncMock()
        request.url = MagicMock()
        request.url.path = "/api/v1/health"
        result = await verify_jwt_or_pass(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_exempt_path_login(self):
        request = AsyncMock()
        request.url = MagicMock()
        request.url.path = "/api/v1/auth/login"
        result = await verify_jwt_or_pass(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_health_subpath_exempt(self):
        request = AsyncMock()
        request.url = MagicMock()
        request.url.path = "/api/v1/health/deep"
        result = await verify_jwt_or_pass(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_dev_mode_no_secret_passes(self):
        original = os.environ.pop("JWT_SECRET", None)
        try:
            request = AsyncMock()
            request.url = MagicMock()
            request.url.path = "/api/v1/decisions"
            result = await verify_jwt_or_pass(request)
            assert result is None
        finally:
            if original:
                os.environ["JWT_SECRET"] = original

    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self):
        token = create_access_token("42", "user@test.com")
        request = AsyncMock()
        request.url = MagicMock()
        request.url.path = "/api/v1/decisions"
        request.headers = {"Authorization": f"Bearer {token}"}
        result = await verify_jwt_or_pass(request)
        assert result["sub"] == "42"
        assert result["email"] == "user@test.com"

    @pytest.mark.asyncio
    async def test_missing_bearer_raises_401(self):
        request = AsyncMock()
        request.url = MagicMock()
        request.url.path = "/api/v1/decisions"
        request.headers = {"Authorization": "Basic abc"}
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_or_pass(request)
        assert exc_info.value.status_code == 401
        assert "Missing or invalid" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": "1",
            "email": "x@y.com",
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = pyjwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")
        request = AsyncMock()
        request.url = MagicMock()
        request.url.path = "/api/v1/decisions"
        request.headers = {"Authorization": f"Bearer {token}"}
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_or_pass(request)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        request = AsyncMock()
        request.url = MagicMock()
        request.url.path = "/api/v1/decisions"
        request.headers = {"Authorization": "Bearer garbage.token.here"}
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_or_pass(request)
        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail
