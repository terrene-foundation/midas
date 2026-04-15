"""
Shadow lane monitor -- tracks all active shadow lanes and verifies isolation.

The monitor reads from model_registry and shadow_decisions to report on
shadow lane status. The isolation check verifies that no shadow model
family appears in the production decisions table, which would indicate
a leak from shadow to live trading.

Ref: specs/06-meta-router.md
"""

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)


class ShadowMonitor:
    """Monitors all shadow lanes and verifies shadow/production isolation."""

    def __init__(self, db: DataFlow) -> None:
        self._db = db

    async def list_active_lanes(self) -> list[dict]:
        """List all active shadow lanes with status.

        Reads from model_registry for models with promotion_status='shadow'.
        Each lane entry includes the model family, version, and registration
        metadata.
        """
        registry_rows = await self._db.express.list("model_registry")
        shadow_rows = [r for r in registry_rows if r.get("promotion_status") == "shadow"]

        lanes: list[dict] = []
        for row in shadow_rows:
            lanes.append(
                {
                    "model_family": row.get("model_family", ""),
                    "model_version": row.get("model_version", ""),
                    "model_type": row.get("model_type", ""),
                    "pool_layer": row.get("pool_layer", ""),
                    "trained_at": row.get("trained_at", ""),
                }
            )

        logger.debug(
            "shadow_monitor.listed_lanes",
            n_lanes=len(lanes),
        )
        return lanes

    async def get_lane_status(self, model_family: str) -> dict:
        """Get detailed status of a shadow lane.

        Returns registration metadata and the count of shadow decisions
        recorded for this lane.
        """
        # Find the model in registry
        registry_rows = await self._db.express.list("model_registry")
        matching = [r for r in registry_rows if r.get("model_family") == model_family]

        if not matching:
            return {
                "model_family": model_family,
                "model_version": "",
                "decision_count": 0,
                "status": "not_found",
            }

        model = matching[-1]
        model_version = model.get("model_version", "")

        # Count shadow decisions
        shadow_rows = await self._db.express.list("shadow_decisions")
        decision_count = len([r for r in shadow_rows if r.get("model_family") == model_family])

        return {
            "model_family": model_family,
            "model_version": model_version,
            "decision_count": decision_count,
            "status": "active",
        }

    async def check_isolation(self, model_family: str) -> bool:
        """Verify shadow lane has no production call sites.

        Returns True if the shadow model family does NOT appear in the
        production decisions table. Returns False if a leak is detected
        (i.e. the model family appears in a production decision).

        This is a critical safety check: shadow decisions must never
        reach the live trading pipeline.
        """
        decisions = await self._db.express.list("decisions")

        # Check if any production decision references this shadow model
        for row in decisions:
            model_version = row.get("model_version", "")
            if model_family in model_version:
                logger.warning(
                    "shadow_monitor.isolation_violation",
                    model_family=model_family,
                    leaked_decision_id=row.get("id"),
                )
                return False

        return True
