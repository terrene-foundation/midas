"""Tier 1 tests for FreshnessGate (src/midas/fabric/freshness.py)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from midas.fabric.cache import FabricCache
from midas.fabric.freshness import FreshnessGate, FRESHNESS_THRESHOLDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_fake_cache(get_price_result=None, get_latent_state_result=None) -> FabricCache:
    """Build a FabricCache with controlled async return values."""
    cache = FabricCache(redis_url="redis://fake:6379/0")
    cache.get_price = AsyncMock(return_value=get_price_result)
    cache.get_latent_state = AsyncMock(return_value=get_latent_state_result)
    return cache


# ---------------------------------------------------------------------------
# FreshnessGate._resolve_threshold
# ---------------------------------------------------------------------------


class TestResolveThreshold:
    def test_prices_threshold(self):
        assert FreshnessGate._resolve_threshold("prices") == FRESHNESS_THRESHOLDS["prices"]

    def test_fundamentals_threshold(self):
        assert (
            FreshnessGate._resolve_threshold("fundamentals") == FRESHNESS_THRESHOLDS["fundamentals"]
        )

    def test_macro_threshold(self):
        assert FreshnessGate._resolve_threshold("macro") == FRESHNESS_THRESHOLDS["macro"]

    def test_quotes_active_threshold(self):
        assert (
            FreshnessGate._resolve_threshold("quotes_active")
            == FRESHNESS_THRESHOLDS["quotes_active"]
        )

    def test_quotes_inactive_threshold(self):
        assert (
            FreshnessGate._resolve_threshold("quotes_inactive")
            == FRESHNESS_THRESHOLDS["quotes_inactive"]
        )

    def test_news_threshold(self):
        assert FreshnessGate._resolve_threshold("news") == FRESHNESS_THRESHOLDS["news"]

    def test_latent_state_threshold(self):
        assert (
            FreshnessGate._resolve_threshold("latent_state") == FRESHNESS_THRESHOLDS["latent_state"]
        )

    def test_resolve_threshold_unknown_type_defaults_to_3600(self):
        """Unknown feature types fall back to 3600 seconds (1 hour)."""
        assert FreshnessGate._resolve_threshold("unknown_type_xyz") == 3600.0
        assert FreshnessGate._resolve_threshold("foobar") == 3600.0


# ---------------------------------------------------------------------------
# FreshnessGate.check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_returns_fresh_when_within_threshold():
    """Cache hit with recent _cached_at returns is_fresh=True."""
    now = datetime.now(tz=timezone.utc)
    recent_ts = now.timestamp() - 10  # 10 seconds ago — well within 60s quotes threshold
    recent_iso = datetime.fromtimestamp(recent_ts, tz=timezone.utc).isoformat()

    cache = make_fake_cache()
    gate = FreshnessGate(cache)
    gate._get_last_updated = AsyncMock(return_value=recent_iso)

    result = await gate.check(
        instrument="SPY",
        feature_type="quotes",
        as_of_date="2024-01-15",
        active=True,
    )

    assert result.is_fresh is True
    assert result.feature_type == "quotes"
    assert result.last_updated is not None
    assert "fresh" in result.message.lower()


@pytest.mark.asyncio
async def test_check_returns_stale_when_exceeds_threshold():
    """Cache hit with _cached_at older than threshold returns is_fresh=False."""
    old_ts = datetime.now(tz=timezone.utc).timestamp() - 7200  # 2 hours ago — way past 60s
    old_iso = datetime.fromtimestamp(old_ts, tz=timezone.utc).isoformat()

    cache = make_fake_cache()
    gate = FreshnessGate(cache)
    gate._get_last_updated = AsyncMock(return_value=old_iso)

    result = await gate.check(
        instrument="SPY",
        feature_type="quotes",
        as_of_date="2024-01-15",
        active=True,
    )

    assert result.is_fresh is False
    assert result.staleness_seconds > FRESHNESS_THRESHOLDS["quotes_active"]
    assert "stale" in result.message.lower()


@pytest.mark.asyncio
async def test_check_all_returns_result_per_feature_type():
    """check_all returns one FreshnessResult per known feature type."""
    cache = make_fake_cache(get_price_result=None)  # no data — everything stale
    gate = FreshnessGate(cache)

    results = await gate.check_all(instrument="SPY", as_of_date="2024-01-15", active=True)

    expected_types = {
        "prices",
        "fundamentals",
        "macro",
        "quotes",
        "news",
        "latent_state",
    }
    assert set(results.keys()) == expected_types
    for r in results.values():
        assert r.is_fresh is False  # no data cached → stale
        assert r.staleness_seconds == float("inf")


# ---------------------------------------------------------------------------
# FreshnessGate.emit_stale_flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_stale_flag_writes_audit_on_stale():
    """emit_stale_flag returns True when data is stale (no data cached)."""
    cache = make_fake_cache(get_price_result=None)  # no data
    gate = FreshnessGate(cache)

    emitted = await gate.emit_stale_flag(
        instrument="SPY",
        feature_type="prices",
        as_of_date="2024-01-15",
    )

    assert emitted is True


@pytest.mark.asyncio
async def test_emit_stale_flag_returns_false_when_fresh():
    """emit_stale_flag returns False when data is within threshold."""
    now = datetime.now(tz=timezone.utc)
    recent_ts = now.timestamp() - 5  # 5 seconds ago — within quotes threshold
    recent_iso = datetime.fromtimestamp(recent_ts, tz=timezone.utc).isoformat()

    cache = make_fake_cache()
    gate = FreshnessGate(cache)
    gate._get_last_updated = AsyncMock(return_value=recent_iso)

    emitted = await gate.emit_stale_flag(
        instrument="SPY",
        feature_type="quotes",
        as_of_date="2024-01-15",
        active=True,
    )

    assert emitted is False


# ---------------------------------------------------------------------------
# FreshnessGate quotes thresholds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quotes_uses_active_threshold_when_active():
    """'quotes' with active=True resolves to quotes_active (60s)."""
    # Data is 120 seconds old — stale for active (60s), fresh for inactive (900s)
    old_ts = datetime.now(tz=timezone.utc).timestamp() - 120

    cache = make_fake_cache(
        get_price_result={
            "_cached_at": old_ts,
            "close": 474.0,
        }
    )
    gate = FreshnessGate(cache)

    result = await gate.check(
        instrument="SPY",
        feature_type="quotes",
        as_of_date="2024-01-15",
        active=True,
    )

    assert result.is_fresh is False
    assert result.threshold_seconds == FRESHNESS_THRESHOLDS["quotes_active"]


@pytest.mark.asyncio
async def test_quotes_uses_inactive_threshold_when_inactive():
    """'quotes' with active=False resolves to quotes_inactive (900s)."""
    # Data is 120 seconds old — fresh for inactive (900s)
    recent_ts = datetime.now(tz=timezone.utc).timestamp() - 120
    recent_iso = datetime.fromtimestamp(recent_ts, tz=timezone.utc).isoformat()

    cache = make_fake_cache()
    gate = FreshnessGate(cache)
    gate._get_last_updated = AsyncMock(return_value=recent_iso)

    result = await gate.check(
        instrument="SPY",
        feature_type="quotes",
        as_of_date="2024-01-15",
        active=False,
    )

    assert result.is_fresh is True
    assert result.threshold_seconds == FRESHNESS_THRESHOLDS["quotes_inactive"]
