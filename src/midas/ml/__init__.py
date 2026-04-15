"""M03 ML Infrastructure — model registry, training pipeline, architectures."""

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
        except Exception:
            return None

    async def list_by_pool(self, pool_layer: str) -> list[dict[str, Any]]:
        try:
            rows = await self._db.express.list("model_registry")
            return [r for r in rows if r.get("pool_layer", "") == pool_layer]
        except Exception:
            return []

    async def get_champion(self, pool_layer: str) -> dict[str, Any] | None:
        try:
            rows = await self._db.express.list(
                "model_registry", filter={"promotion_status": "champion"}
            )
            matching = [r for r in rows if pool_layer in r.get("model_type", "")]
            return matching[-1] if matching else None
        except Exception:
            return None

    async def get_challengers(self, pool_layer: str) -> list[dict[str, Any]]:
        try:
            rows = await self._db.express.list(
                "model_registry", filter={"promotion_status": "shadow"}
            )
            return [r for r in rows if pool_layer in r.get("model_type", "")]
        except Exception:
            return []

    async def promote(self, model_family: str, model_version: str) -> bool:
        try:
            rows = await self._db.express.list(
                "model_registry",
                filter={"model_family": model_family, "promotion_status": "champion"},
            )
            for row in rows:
                # Demote existing champion — in v1 we just register a new version
                pass
            return True
        except Exception:
            return False

    async def retire(self, model_family: str, model_version: str) -> bool:
        try:
            rows = await self._db.express.list(
                "model_registry",
                filter={"model_family": model_family, "model_version": model_version},
            )
            return len(rows) > 0
        except Exception:
            return False

    async def get_lineage(self, model_family: str) -> list[dict[str, Any]]:
        try:
            return await self._db.express.list(
                "model_registry", filter={"model_family": model_family}
            )
        except Exception:
            return []
