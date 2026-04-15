"""
Redis hot cache layer for the Midas fabric.

Wraps Redis with typed methods for prices, latent state, and session data.
TTLs follow specs/03-universe-and-data.md section 3.4:
  - Active (user in app): 1-minute polling
  - Inactive (background): 15-minute polling

Graceful degradation: if Redis is unavailable, logs WARN and returns None.
No caller crashes when Redis is down.

Ref: T-01-10
"""

from __future__ import annotations

import json
import time
from typing import Any

import redis.asyncio as aioredis
import structlog

from midas.config import REDIS_URL

logger = structlog.get_logger(__name__)

# Namespace prefix for all Midas cache keys.
_KEY_PREFIX = "midas:v1"

# TTL constants (seconds).
_TTL_ACTIVE = 60  # 1 minute
_TTL_INACTIVE = 900  # 15 minutes
_TTL_LATENT_STATE = 3600  # 1 hour
_TTL_SESSION = 7200  # 2 hours


def _make_key(*parts: str) -> str:
    """Build a namespaced cache key from parts."""
    return f"{_KEY_PREFIX}:{':'.join(parts)}"


def _mask_url(url: str) -> str:
    """Mask credentials in a Redis URL for safe logging."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            return "<unparseable redis url>"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://***@{parsed.hostname}{port}{parsed.path}"
    except Exception:
        return "<unparseable redis url>"


class FabricCache:
    """Redis-backed hot cache for the Midas data fabric.

    Provides typed get/set methods for prices, latent state, and sessions.
    All keys are prefixed with ``midas:v1:`` for namespace isolation.
    Degrades gracefully when Redis is unavailable: every method returns
    None (or an empty dict for health_check) instead of crashing.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._url = redis_url or REDIS_URL
        self._client: aioredis.Redis | None = None
        self._available: bool = False

    async def _ensure_client(self) -> aioredis.Redis | None:
        """Lazily create the Redis client. Returns None on failure."""
        if self._client is not None:
            return self._client

        try:
            self._client = aioredis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Verify connectivity immediately.
            await self._client.ping()
            self._available = True
            logger.info(
                "cache.redis.connected",
                url=_mask_url(self._url),
            )
            return self._client
        except Exception as exc:
            self._available = False
            logger.warning(
                "cache.redis.unavailable",
                url=_mask_url(self._url),
                error=str(exc),
            )
            self._client = None
            return None

    @property
    def is_available(self) -> bool:
        """Return True if the Redis connection is healthy."""
        return self._available

    async def _get_json(self, key: str) -> dict | None:
        """Retrieve and deserialize a JSON value from Redis."""
        client = await self._ensure_client()
        if client is None:
            return None
        try:
            raw = await client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning(
                "cache.redis.get_failed",
                key=key,
                error=str(exc),
            )
            return None

    async def _set_json(self, key: str, data: dict, ttl: int) -> bool:
        """Serialize and store a JSON value in Redis with TTL."""
        client = await self._ensure_client()
        if client is None:
            return False
        try:
            payload = json.dumps(data, default=str)
            await client.setex(key, ttl, payload)
            return True
        except Exception as exc:
            logger.warning(
                "cache.redis.set_failed",
                key=key,
                ttl=ttl,
                error=str(exc),
            )
            return False

    # ------------------------------------------------------------------
    # Price cache
    # ------------------------------------------------------------------

    async def get_price(self, ticker: str) -> dict | None:
        """Get the latest cached price data for a ticker.

        Returns None if Redis is unavailable or the key does not exist.
        """
        key = _make_key("price", ticker)
        result = await self._get_json(key)
        if result is not None:
            logger.debug(
                "cache.price.hit",
                ticker=ticker,
            )
        return result

    async def set_price(
        self,
        ticker: str,
        data: dict[str, Any],
        active: bool = True,
    ) -> bool:
        """Cache price data for a ticker.

        TTL follows specs/03 section 3.4:
          - active=True (user in app): 1 minute
          - active=False (background): 15 minutes
        """
        ttl = _TTL_ACTIVE if active else _TTL_INACTIVE
        key = _make_key("price", ticker)
        enriched = {**data, "_cached_at": time.time()}
        ok = await self._set_json(key, enriched, ttl)
        if ok:
            logger.debug(
                "cache.price.set",
                ticker=ticker,
                active=active,
                ttl=ttl,
            )
        return ok

    # ------------------------------------------------------------------
    # Latent state cache
    # ------------------------------------------------------------------

    async def get_latent_state(self, model_family: str) -> dict | None:
        """Get the cached latent state (z_t posterior) for a model family."""
        key = _make_key("latent", model_family)
        return await self._get_json(key)

    async def set_latent_state(self, model_family: str, data: dict[str, Any]) -> bool:
        """Cache the latent state for a model family.

        TTL: 1 hour (latent state updates on the learner cadence).
        """
        key = _make_key("latent", model_family)
        enriched = {**data, "_cached_at": time.time()}
        return await self._set_json(key, enriched, _TTL_LATENT_STATE)

    # ------------------------------------------------------------------
    # Session cache
    # ------------------------------------------------------------------

    async def get_session(self, session_id: str) -> dict | None:
        """Get cached session data."""
        key = _make_key("session", session_id)
        return await self._get_json(key)

    async def set_session(self, session_id: str, data: dict[str, Any]) -> bool:
        """Cache session data.

        TTL: 2 hours (covers a typical user session).
        """
        key = _make_key("session", session_id)
        enriched = {**data, "_cached_at": time.time()}
        return await self._set_json(key, enriched, _TTL_SESSION)

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    async def invalidate(self, ticker: str) -> int:
        """Invalidate all cache entries matching a ticker pattern.

        Deletes keys matching ``midas:v1:price:<ticker>`` and any
        feature-related keys for the same ticker. Returns the number
        of keys deleted.
        """
        client = await self._ensure_client()
        if client is None:
            return 0

        patterns = [
            _make_key("price", ticker),
            _make_key("features", ticker, "*"),
        ]
        total_deleted = 0
        try:
            for pattern in patterns:
                if "*" in pattern:
                    # Scan and delete for glob patterns.
                    keys = []
                    async for key in client.scan_iter(match=pattern):
                        keys.append(key)
                    if keys:
                        deleted = await client.delete(*keys)
                        total_deleted += deleted
                else:
                    deleted = await client.delete(pattern)
                    total_deleted += deleted

            if total_deleted > 0:
                logger.info(
                    "cache.invalidated",
                    ticker=ticker,
                    keys_deleted=total_deleted,
                )
            return total_deleted
        except Exception as exc:
            logger.warning(
                "cache.invalidate.failed",
                ticker=ticker,
                error=str(exc),
            )
            return 0

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Ping Redis and return a status dict.

        Returns a dict with ``status``, ``latency_ms``, and ``available``
        fields. Never raises; failures are reported in the dict.
        """
        client = await self._ensure_client()
        if client is None:
            return {
                "status": "unavailable",
                "latency_ms": None,
                "available": False,
                "error": "Redis client not initialized",
            }

        try:
            t0 = time.monotonic()
            await client.ping()
            latency_ms = (time.monotonic() - t0) * 1000
            self._available = True
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "available": True,
            }
        except Exception as exc:
            self._available = False
            logger.warning(
                "cache.health_check.failed",
                error=str(exc),
            )
            return {
                "status": "unhealthy",
                "latency_ms": None,
                "available": False,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.warning(
                    "cache.redis.close_failed",
                    error=str(exc),
                )
            finally:
                self._client = None
                self._available = False
