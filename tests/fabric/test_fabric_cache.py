"""Tier 1 tests for FabricCache (src/midas/fabric/cache.py)."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midas.fabric.cache import FabricCache, _make_key, _TTL_ACTIVE, _TTL_INACTIVE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_client(setex_result: bool = True, get_result: str | None = None) -> AsyncMock:
    """Build a fake async Redis client with controllable responses."""
    client = AsyncMock()
    client.setex = AsyncMock(return_value=setex_result)
    client.get = AsyncMock(return_value=get_result)
    client.ping = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.scan_iter = MagicMock(return_value=iter([]))
    client.aclose = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# _make_key
# ---------------------------------------------------------------------------


class TestMakeKey:
    def test_two_parts(self):
        assert _make_key("price", "SPY") == "midas:v1:price:SPY"

    def test_three_parts(self):
        assert _make_key("features", "SPY", "momentum") == "midas:v1:features:SPY:momentum"

    def test_single_part(self):
        assert _make_key("session") == "midas:v1:session"


# ---------------------------------------------------------------------------
# FabricCache.get_price / set_price
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_and_get_price():
    """Write a price, read it back — basic round-trip."""
    cache = FabricCache(redis_url="redis://fake:6379/0")

    stored_data = {}

    async def capture_setex(key: str, ttl: int, payload: str) -> bool:
        stored_data[key] = (ttl, payload)
        return True

    mock_client = AsyncMock()
    mock_client.setex = capture_setex
    mock_client.ping = AsyncMock(return_value=True)
    cache._client = mock_client
    cache._available = True

    ok = await cache.set_price("SPY", {"close": 474.0, "ticker": "SPY"}, active=True)
    assert ok is True

    # Simulate the stored value being retrieved
    cached_at = time.time()
    mock_client.get = AsyncMock(
        return_value=json.dumps({"close": 474.0, "ticker": "SPY", "_cached_at": cached_at})
    )

    result = await cache.get_price("SPY")
    assert result is not None
    assert result["close"] == 474.0
    assert "_cached_at" in result


@pytest.mark.asyncio
async def test_price_ttl_active_vs_inactive():
    """Active prices use 60s TTL; inactive use 900s TTL."""
    cache = FabricCache(redis_url="redis://fake:6379/0")

    recorded_ttls: list[int] = []

    async def capture_ttl(key: str, ttl: int, payload: str) -> bool:
        recorded_ttls.append(ttl)
        return True

    mock_client = AsyncMock()
    mock_client.setex = capture_ttl
    mock_client.ping = AsyncMock(return_value=True)
    cache._client = mock_client
    cache._available = True

    await cache.set_price("SPY", {"close": 474.0}, active=True)
    await cache.set_price("SPY", {"close": 475.0}, active=False)

    assert recorded_ttls[0] == _TTL_ACTIVE  # 60
    assert recorded_ttls[1] == _TTL_INACTIVE  # 900


# ---------------------------------------------------------------------------
# FabricCache.latent_state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_and_get_latent_state():
    """Write a latent state, read it back."""
    cache = FabricCache(redis_url="redis://fake:6379/0")

    stored: dict[str, tuple[int, str]] = {}

    async def capture_setex(key: str, ttl: int, payload: str) -> bool:
        stored[key] = (ttl, payload)
        return True

    mock_client = AsyncMock()
    mock_client.setex = capture_setex
    mock_client.ping = AsyncMock(return_value=True)
    cache._client = mock_client
    cache._available = True

    state_data = {"z_t": [0.1, -0.3, 0.8], "model": "ssl_v2"}
    ok = await cache.set_latent_state("ssl_v2", state_data)
    assert ok is True

    cached_at = time.time()
    mock_client.get = AsyncMock(return_value=json.dumps({**state_data, "_cached_at": cached_at}))

    result = await cache.get_latent_state("ssl_v2")
    assert result is not None
    assert result["z_t"] == [0.1, -0.3, 0.8]


# ---------------------------------------------------------------------------
# FabricCache.session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_and_get_session():
    """Write a session, read it back."""
    cache = FabricCache(redis_url="redis://fake:6379/0")

    stored_key: str | None = None

    async def capture_setex(key: str, ttl: int, payload: str) -> bool:
        nonlocal stored_key
        stored_key = key
        return True

    mock_client = AsyncMock()
    mock_client.setex = capture_setex
    mock_client.ping = AsyncMock(return_value=True)
    cache._client = mock_client
    cache._available = True

    session_data = {"user_id": "u123", "roles": ["analyst"]}
    ok = await cache.set_session("sess-abc", session_data)
    assert ok is True
    assert stored_key == "midas:v1:session:sess-abc"

    cached_at = time.time()
    mock_client.get = AsyncMock(return_value=json.dumps({**session_data, "_cached_at": cached_at}))

    result = await cache.get_session("sess-abc")
    assert result is not None
    assert result["user_id"] == "u123"


# ---------------------------------------------------------------------------
# FabricCache.invalidate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_removes_price_keys():
    """invalidate(ticker) deletes price and feature keys for that ticker."""
    cache = FabricCache(redis_url="redis://fake:6379/0")

    deleted_keys: list[str] = []

    async def mock_delete(*keys: str) -> int:
        deleted_keys.extend(keys)
        return len(keys)

    async def mock_scan_iter(match: str):
        if match == _make_key("features", "SPY", "*"):
            yield _make_key("features", "SPY", "momentum")
            yield _make_key("features", "SPY", "volatility")
        return
        yield  # make it an async generator

    mock_client = AsyncMock()
    mock_client.delete = mock_delete
    mock_client.scan_iter = mock_scan_iter
    mock_client.ping = AsyncMock(return_value=True)
    cache._client = mock_client
    cache._available = True

    deleted = await cache.invalidate("SPY")

    # Should have deleted the price key + 2 feature keys
    assert _make_key("price", "SPY") in deleted_keys
    assert deleted >= 1


# ---------------------------------------------------------------------------
# FabricCache.health_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_returns_healthy_dict():
    """health_check returns status=healthy when Redis responds to ping."""
    cache = FabricCache(redis_url="redis://fake:6379/0")

    mock_client = AsyncMock()
    mock_client.ping = AsyncMock()
    cache._client = mock_client
    cache._available = True

    result = await cache.health_check()

    assert result["status"] == "healthy"
    assert result["available"] is True
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_health_check_returns_unhealthy_when_redis_down():
    """health_check returns status=unhealthy when Redis ping raises."""
    cache = FabricCache(redis_url="redis://fake:6379/0")

    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=ConnectionError("connection refused"))
    cache._client = mock_client
    cache._available = False

    result = await cache.health_check()

    # ping raised → caught in except → status="unhealthy"
    assert result["status"] == "unhealthy"
    assert result["available"] is False
    assert result["latency_ms"] is None
    assert "connection refused" in result["error"]


# ---------------------------------------------------------------------------
# FabricCache graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graceful_degradation_on_redis_error():
    """get_price returns None when Redis is unavailable."""
    cache = FabricCache(redis_url="redis://fake:6379/0")

    # Simulate _ensure_client returning None (Redis down)
    cache._client = None
    cache._available = False

    result = await cache.get_price("SPY")
    assert result is None


@pytest.mark.asyncio
async def test_set_price_returns_false_when_redis_down():
    """set_price returns False when Redis client is unavailable."""
    cache = FabricCache(redis_url="redis://fake:6379/0")
    cache._client = None
    cache._available = False

    ok = await cache.set_price("SPY", {"close": 474.0}, active=True)
    assert ok is False
