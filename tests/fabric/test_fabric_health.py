"""Tier 1 tests for HealthCheckOrchestrator (src/midas/fabric/health.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from midas.fabric.health import HealthCheckOrchestrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def orch():
    """Create a fresh HealthCheckOrchestrator."""
    return HealthCheckOrchestrator()


# ---------------------------------------------------------------------------
# HealthCheckOrchestrator.register / list_sources
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_and_list_sources(self, orch):
        """register() makes the adapter visible in list_sources()."""
        fake_adapter = AsyncMock()
        fake_adapter.health_check = AsyncMock(return_value={"healthy": True})

        orch.register("redis", fake_adapter)

        sources = orch.list_sources()
        assert "redis" in sources
        assert len(sources) == 1

    def test_register_multiple_sources(self, orch):
        """Multiple adapters can be registered simultaneously."""
        for name in ("redis", "postgres", "yfinance"):
            adapter = AsyncMock()
            adapter.health_check = AsyncMock(return_value={"healthy": True})
            orch.register(name, adapter)

        sources = orch.list_sources()
        assert set(sources) == {"redis", "postgres", "yfinance"}


# ---------------------------------------------------------------------------
# HealthCheckOrchestrator.check_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_all_runs_all_registered(orch):
    """check_all() calls health_check on every registered adapter."""
    healthy_adapter = AsyncMock()
    healthy_adapter.health_check = AsyncMock(
        return_value={"source": "redis", "healthy": True, "latency_ms": 0.5}
    )

    sick_adapter = AsyncMock()
    sick_adapter.health_check = AsyncMock(
        return_value={"source": "yfinance", "healthy": False, "detail": "rate limited"}
    )

    orch.register("redis", healthy_adapter)
    orch.register("yfinance", sick_adapter)

    results = await orch.check_all()

    assert "redis" in results
    assert "yfinance" in results
    assert results["redis"]["healthy"] is True
    assert results["yfinance"]["healthy"] is False


@pytest.mark.asyncio
async def test_check_all_catches_adapter_exception(orch):
    """check_all() catches exceptions from adapters and reports them."""
    broken_adapter = AsyncMock()
    broken_adapter.health_check = AsyncMock(side_effect=RuntimeError("connection refused"))

    orch.register("broken", broken_adapter)

    results = await orch.check_all()

    assert "broken" in results
    assert results["broken"]["healthy"] is False
    assert "connection refused" in results["broken"]["detail"]


# ---------------------------------------------------------------------------
# HealthCheckOrchestrator.check_source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_source_returns_not_registered_for_unknown(orch):
    """check_source() returns a not-registered response for unknown names."""
    result = await orch.check_source("nonexistent-adapter")

    assert result["healthy"] is False
    assert "not registered" in result["detail"]


@pytest.mark.asyncio
async def test_check_source_returns_adapter_result(orch):
    """check_source() returns the adapter's own health_check result."""
    adapter = AsyncMock()
    adapter.health_check = AsyncMock(
        return_value={"source": "redis", "healthy": True, "latency_ms": 1.2}
    )
    orch.register("redis", adapter)

    result = await orch.check_source("redis")

    assert result["healthy"] is True
    assert result["latency_ms"] == 1.2


@pytest.mark.asyncio
async def test_check_source_propagates_exception(orch):
    """check_source() catches exceptions and returns them in the detail field."""
    adapter = AsyncMock()
    adapter.health_check = AsyncMock(side_effect=OSError("timeout"))
    orch.register("redis", adapter)

    result = await orch.check_source("redis")

    assert result["healthy"] is False
    assert "timeout" in result["detail"]


# ---------------------------------------------------------------------------
# HealthCheckOrchestrator.unregister
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unregister_removes_adapter(orch):
    """unregister() removes the adapter from the registry."""
    adapter = AsyncMock()
    adapter.health_check = AsyncMock(return_value={"healthy": True})
    orch.register("redis", adapter)

    assert "redis" in orch.list_sources()

    orch.unregister("redis")

    assert "redis" not in orch.list_sources()


@pytest.mark.asyncio
async def test_unregister_idempotent(orch):
    """unregister() on a non-existent key does not raise."""
    orch.unregister("never-registered")  # must not raise
    assert orch.list_sources() == []
