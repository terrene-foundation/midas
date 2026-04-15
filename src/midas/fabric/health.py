"""
Health check orchestrator for all data source adapters.

Aggregates health status from every registered adapter and provides
a single health endpoint for monitoring and compliance.

Ref: T-01-14
"""

from typing import Any

import structlog

logger = structlog.get_logger("midas.fabric.health")


class HealthCheckOrchestrator:
    """Orchestrates health checks across all data source adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}

    def register(self, name: str, adapter: Any) -> None:
        """Register an adapter for health checking."""
        self._adapters[name] = adapter

    def unregister(self, name: str) -> None:
        """Remove an adapter from health checking."""
        self._adapters.pop(name, None)

    async def check_all(self) -> dict[str, dict[str, Any]]:
        """Run health checks on all registered adapters.

        Returns dict mapping adapter name to health status.
        """
        results: dict[str, dict[str, Any]] = {}
        for name, adapter in self._adapters.items():
            try:
                results[name] = await adapter.health_check()
            except Exception as exc:
                results[name] = {
                    "source": name,
                    "healthy": False,
                    "detail": f"health check raised: {exc}",
                }

        healthy_count = sum(1 for r in results.values() if r.get("healthy"))
        logger.info(
            "health.check_all",
            total=len(results),
            healthy=healthy_count,
            unhealthy=len(results) - healthy_count,
        )
        return results

    async def check_source(self, name: str) -> dict[str, Any]:
        """Run health check on a single adapter."""
        adapter = self._adapters.get(name)
        if adapter is None:
            return {"source": name, "healthy": False, "detail": "adapter not registered"}
        try:
            return await adapter.health_check()
        except Exception as exc:
            return {"source": name, "healthy": False, "detail": str(exc)}

    def list_sources(self) -> list[str]:
        """List all registered adapter names."""
        return list(self._adapters.keys())
