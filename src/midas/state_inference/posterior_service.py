"""Posterior maintenance service.

Consumes representation-learner outputs and maintains p(z_t | x_{1:t})
per pool member in the latent_state fabric table.

Ref: specs/04 §5

NOTE: Uses in-memory cache to work around DataFlow SQLite read-after-write
consistency. All writes still go to DataFlow for durability.
"""

import json
from datetime import date
from typing import Any

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.state_inference.posterior_service")


class PosteriorMaintenanceService:
    """Continuous service for maintaining posteriors in the latent_state fabric table."""

    def __init__(self, db: DataFlow) -> None:
        self._db = db
        self._cache: list[dict[str, Any]] = []

    async def update_posterior(
        self,
        model_family: str,
        model_version: str,
        z_t_vector: str,
        posterior_variance: str,
        log_likelihood: float,
        as_of_date: str,
        is_champion: bool = False,
    ) -> dict[str, Any]:
        """Write a new posterior update to the latent_state table."""
        as_of_str = str(as_of_date) if isinstance(as_of_date, date) else as_of_date
        row = {
            "model_family": model_family,
            "model_version": model_version,
            "as_of_date": as_of_str,
            "z_vector": json.dumps(z_t_vector) if not isinstance(z_t_vector, str) else z_t_vector,
            "z_covariance": (
                json.dumps(posterior_variance)
                if not isinstance(posterior_variance, str)
                else posterior_variance
            ),
            "log_likelihood": log_likelihood,
            "is_champion": is_champion,
            "learner_role": "champion" if is_champion else "challenger",
            "period_end": as_of_str,
            "filed_at": f"{as_of_str}T00:00:00",
        }
        try:
            result = await self._db.express.create("latent_state", row)
            self._cache.append(row)
            logger.info(
                "posterior.updated",
                family=model_family,
                version=model_version,
                as_of_date=as_of_date,
                champion=is_champion,
            )
            return result
        except Exception as exc:
            logger.error(
                "posterior.update_failed",
                family=model_family,
                error=str(exc),
            )
            return {}

    async def get_latest_posterior(
        self, model_family: str, model_version: str
    ) -> dict[str, Any] | None:
        """Get the latest posterior for a specific model version."""
        matches = [
            r
            for r in self._cache
            if r.get("model_family") == model_family and r.get("model_version") == model_version
        ]
        return matches[-1] if matches else None

    async def get_posterior_history(
        self,
        model_family: str,
        model_version: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Get posterior history for a date range."""
        start_str = str(start_date) if isinstance(start_date, date) else start_date
        end_str = str(end_date) if isinstance(end_date, date) else end_date
        matches = [
            r
            for r in self._cache
            if r.get("model_family") == model_family
            and r.get("model_version") == model_version
            and start_str <= r.get("as_of_date", "") <= end_str
        ]
        return matches

    async def list_active_posteriors(self) -> list[dict[str, Any]]:
        """List all current posteriors (latest per model family/version)."""
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        for row in self._cache:
            key = (row.get("model_family", ""), row.get("model_version", ""))
            if key not in seen or row.get("as_of_date", "") > seen[key].get("as_of_date", ""):
                seen[key] = row
        return list(seen.values())

    async def get_champion_posterior(self) -> dict[str, Any] | None:
        """Get the current champion's posterior."""
        champions = [r for r in self._cache if r.get("is_champion")]
        return champions[-1] if champions else None
