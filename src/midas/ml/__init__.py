"""M03 ML Infrastructure — model registry, training pipeline, architectures."""

from datetime import datetime, timezone

from dataclasses import dataclass
from typing import Any

import structlog
from dataflow import DataFlow

from midas.ml.online_inference import (
    InferenceInput,
    InferenceResult,
    POOL_MEMBERS,
    RepresentationInferenceService,
)

logger = structlog.get_logger(__name__)


class RegistryError(Exception):
    """Typed error for model registry operations."""


@dataclass
class ModelVersion:
    model_family: str
    model_version: str
    model_type: str
    training_window_start: str
    training_window_end: str
    calibration_json: str = ""
    promotion_status: str = "shadow"
    sample_count: int = 0
    parameter_count: int = 0
    trained_at: str = ""
    config_hash: str = ""
    parent_version: str = ""
    pool_layer: str = ""
    metrics_json: str = ""


class ModelRegistry:
    """Model registry backed by the model_registry fabric table."""

    def __init__(self, db: DataFlow) -> None:
        self._db = db

    async def register(self, mv: ModelVersion) -> dict[str, Any]:
        row = {
            "model_family": mv.model_family,
            "model_version": mv.model_version,
            "model_type": mv.model_type,
            "training_window_start": mv.training_window_start,
            "training_window_end": mv.training_window_end,
            "calibration_json": mv.calibration_json,
            "promotion_status": mv.promotion_status,
            "sample_count": mv.sample_count,
            "parameter_count": mv.parameter_count,
            "trained_at": mv.trained_at,
            "pool_layer": mv.pool_layer,
            "parent_version": mv.parent_version,
            "config_hash": mv.config_hash,
            "metrics_json": mv.metrics_json,
        }
        try:
            return await self._db.express.create("model_registry", row)
        except Exception as exc:
            logger.error("registry.register_failed", family=mv.model_family, error=str(exc))
            return {}

    async def get(self, model_family: str, model_version: str) -> dict[str, Any] | None:
        try:
            rows = await self._db.express.list(
                "model_registry",
                filter={"model_family": model_family, "model_version": model_version},
            )
            return rows[-1] if rows else None
        except Exception as exc:
            logger.error("registry.get_failed", error=str(exc))
            return None

    async def list_by_pool(self, pool_layer: str) -> list[dict[str, Any]]:
        try:
            rows = await self._db.express.list("model_registry")
            return [r for r in rows if r.get("pool_layer", "") == pool_layer]
        except Exception as exc:
            logger.error("registry.list_by_pool_failed", error=str(exc))
            return []

    async def get_champion(self, model_family: str) -> dict[str, Any] | None:
        """Return the champion model for a given family.

        Gets all rows for the family via express.list (cache bypassed), then
        individually reads each row via express.read to get the current committed
        status. This avoids express.list returning stale promotion_status after
        upsert operations due to SQLite transaction isolation.
        Returns the most recent verified champion (highest id).
        """
        try:
            rows = await self._db.express.list(
                "model_registry",
                filter={"model_family": model_family},
                cache_ttl=0,
            )
            champion = None
            for row in rows:
                # Read each row individually to get current committed state
                verified = await self._db.express.read("model_registry", row["id"])
                if verified and verified.get("promotion_status") == "champion":
                    if champion is None or row["id"] > champion["id"]:
                        champion = verified
            return champion
        except Exception as exc:
            logger.error("registry.get_champion_failed", family=model_family, error=str(exc))
            return None

    async def get_challengers(self, model_family: str) -> list[dict[str, Any]]:
        """Return all challenger (shadow) models for a given family.

        Filters by model_family AND promotion_status='shadow'.
        """
        try:
            rows = await self._db.express.list(
                "model_registry",
                filter={"model_family": model_family, "promotion_status": "shadow"},
                order_by="id DESC",
            )
            return list(rows)
        except Exception as exc:
            logger.error("registry.get_challengers_failed", family=model_family, error=str(exc))
            return []

    async def promote(self, model_family: str, model_version: str) -> bool:
        """Promote a model version to champion.

        Demotes all existing champions for the family, then promotes
        the specified model_version to champion. Writes audit log entry.
        """
        try:
            # Demote all existing champions for this family using upsert
            champion_rows = await self._db.express.list(
                "model_registry",
                filter={"model_family": model_family, "promotion_status": "champion"},
            )
            previous_champion_version = None
            for row in champion_rows:
                previous_champion_version = row.get("model_version")
                await self._db.express.upsert(
                    "model_registry",
                    {
                        "id": row["id"],
                        "model_family": row["model_family"],
                        "model_version": row["model_version"],
                        "model_type": row.get("model_type", ""),
                        "training_window_start": row.get("training_window_start", ""),
                        "training_window_end": row.get("training_window_end", ""),
                        "calibration_json": row.get("calibration_json", ""),
                        "promotion_status": "challenger",
                        "sample_count": row.get("sample_count", 0),
                        "parameter_count": row.get("parameter_count", 0),
                        "trained_at": row.get("trained_at", ""),
                        "config_hash": row.get("config_hash", ""),
                        "parent_version": row.get("parent_version", ""),
                        "pool_layer": row.get("pool_layer", ""),
                        "metrics_json": row.get("metrics_json", ""),
                    },
                )
            # Promote the target model version
            target_rows = await self._db.express.list(
                "model_registry",
                filter={"model_family": model_family, "model_version": model_version},
            )
            if not target_rows:
                raise RegistryError(
                    f"Cannot promote: model {model_family}/{model_version} not found"
                )
            target = target_rows[-1]
            await self._db.express.upsert(
                "model_registry",
                {
                    "id": target["id"],
                    "model_family": target["model_family"],
                    "model_version": target["model_version"],
                    "model_type": target.get("model_type", ""),
                    "training_window_start": target.get("training_window_start", ""),
                    "training_window_end": target.get("training_window_end", ""),
                    "calibration_json": target.get("calibration_json", ""),
                    "promotion_status": "champion",
                    "sample_count": target.get("sample_count", 0),
                    "parameter_count": target.get("parameter_count", 0),
                    "trained_at": target.get("trained_at", ""),
                    "config_hash": target.get("config_hash", ""),
                    "parent_version": target.get("parent_version", ""),
                    "pool_layer": target.get("pool_layer", ""),
                    "metrics_json": target.get("metrics_json", ""),
                },
            )
            await self._write_audit(
                "model_promoted",
                model_family,
                model_version,
                {
                    "previous_champion": previous_champion_version,
                    "new_champion": model_version,
                },
            )
            logger.info(
                "registry.promoted",
                family=model_family,
                version=model_version,
                previous_champion=previous_champion_version,
            )
            return True
        except RegistryError:
            raise
        except Exception as exc:
            logger.error("registry.promote_failed", family=model_family, error=str(exc))
            return False

    async def retire(self, model_family: str, model_version: str) -> bool:
        """Retire a model version.

        Marks the model as retired. If retiring the current champion,
        auto-promotes the best challenger. Prevents retiring the last
        active model in the family.
        """
        try:
            rows = await self._db.express.list("model_registry")
            family_rows = [r for r in rows if r["model_family"] == model_family]
            candidates = [r for r in family_rows if r["model_version"] == model_version]
            if not candidates:
                raise RegistryError(
                    f"Cannot retire: model {model_family}/{model_version} not found"
                )
            target = candidates[-1]

            # Guard: cannot retire the last active model in the family
            active_statuses = {"champion", "challenger", "shadow"}
            active_in_family = [r for r in family_rows if r["promotion_status"] in active_statuses]
            if len(active_in_family) <= 1 and target["promotion_status"] in active_statuses:
                raise RegistryError(
                    f"Cannot retire {model_version}: it is the last active model "
                    f"in family {model_family}"
                )

            is_champion = target["promotion_status"] == "champion"
            await self._db.express.update(
                "model_registry", target["id"], {"promotion_status": "retired"}
            )

            # Auto re-promote best challenger when retiring a champion
            promoted_successor = None
            if is_champion:
                challengers = [
                    r
                    for r in family_rows
                    if r["promotion_status"] in ("challenger", "shadow")
                    and r["model_version"] != model_version
                ]
                if challengers:
                    best = max(challengers, key=lambda r: r["id"])
                    await self.promote(model_family, best["model_version"])
                    promoted_successor = best["model_version"]

            await self._write_audit(
                "model_retired",
                model_family,
                model_version,
                {"was_champion": is_champion, "promoted_successor": promoted_successor},
            )
            logger.info(
                "registry.retired",
                family=model_family,
                version=model_version,
                was_champion=is_champion,
                promoted_successor=promoted_successor,
            )
            return True
        except RegistryError:
            raise
        except Exception as exc:
            logger.error("registry.retire_failed", family=model_family, error=str(exc))
            return False

    async def _write_audit(
        self,
        action: str,
        model_family: str,
        model_version: str,
        metadata: dict[str, Any],
    ) -> None:
        """Write a structured audit entry for a registry event."""
        import json

        try:
            await self._db.express.create(
                "audit_log",
                {
                    "action": action,
                    "rule_name": f"model_{model_family}",
                    "details": json.dumps(
                        {
                            "model_family": model_family,
                            "model_version": model_version,
                            **metadata,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                },
            )
        except Exception as exc:
            logger.warning("registry.audit_write_failed", action=action, error=str(exc))

    async def get_lineage(self, model_family: str) -> list[dict[str, Any]]:
        try:
            return await self._db.express.list(
                "model_registry", filter={"model_family": model_family}
            )
        except Exception as exc:
            logger.error("registry.get_lineage_failed", family=model_family, error=str(exc))
            return []
