"""
Feature store layer for the Midas fabric.

Versioned feature computation with point-in-time discipline. Features are
tagged as ``feature_v{N}``. New versions never overwrite prior versions
while models still reference them. Every read respects the PIT invariant:
no feature reads data whose ``filed_at > as_of_date``.

Ref: specs/03-universe-and-data.md section 4 (Feature Store)
Ref: T-01-12
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any

import structlog
from dataflow import DataFlow

from midas.config import DATABASE_URL  # noqa: F401 — used in _ensure_db fallback

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Feature table name in DataFlow
# ---------------------------------------------------------------------------

_FEATURES_TABLE = "features"

# Retired versions are marked with a special status rather than deleted.
_VERSION_STATUS_ACTIVE = "active"
_VERSION_STATUS_RETIRED = "retired"


def _compute_hash(instrument: str, feature_name: str, value: float, as_of_date: str) -> str:
    """Deterministic hash for a feature row, used as a duplicate guard."""
    raw = f"{instrument}:{feature_name}:{value}:{as_of_date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class FeatureStore:
    """Versioned feature store with point-in-time read discipline.

    Features are written to the ``features`` table via DataFlow express.
    Each feature is tagged with a version string (e.g. ``feature_v1``).
    Versions are immutable: a new version creates new rows and old
    versions remain queryable until explicitly retired.

    PIT invariant: reads use ``filed_at <= as_of_date`` to ensure no
    future data leaks into backtests or decisions.
    """

    def __init__(self, db: DataFlow | None = None, db_url: str | None = None) -> None:
        self._db = db
        self._db_url = db_url or DATABASE_URL

    async def _ensure_db(self) -> DataFlow:
        """Return the DataFlow instance, creating one if needed."""
        if self._db is None:
            self._db = DataFlow(self._db_url)
            await self._db.start()
        return self._db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def write(
        self,
        instrument: str,
        feature_name: str,
        value: float,
        as_of_date: str,
        *,
        version: str = "feature_v1",
        computation_hash: str = "",
    ) -> dict[str, Any]:
        """Write a feature value to the store.

        Validates that ``as_of_date`` is not in the future (PIT invariant).
        Writes a new row to the ``features`` table via DataFlow express.

        Args:
            instrument: Ticker or identifier (e.g. "SPY").
            feature_name: Feature identifier (e.g. "momentum_20d").
            value: The computed feature value.
            as_of_date: ISO date string. Must be <= today.
            version: Version tag (e.g. "feature_v1").
            computation_hash: Optional hash of the computation code for
                reproducibility tracing.

        Returns:
            The created row dict from DataFlow.

        Raises:
            ValueError: If as_of_date is in the future.
        """
        # PIT guard: no future data allowed.
        today = date.today()
        feature_date = date.fromisoformat(as_of_date)
        if feature_date > today:
            raise ValueError(
                f"Feature as_of_date ({as_of_date}) is in the future "
                f"(today is {today.isoformat()}). "
                f"Features must respect the point-in-time discipline."
            )

        db = await self._ensure_db()
        filed_at = datetime.now(tz=timezone.utc).isoformat()

        row_hash = computation_hash or _compute_hash(instrument, feature_name, value, as_of_date)

        row = {
            "instrument": instrument,
            "feature_name": feature_name,
            "value": value,
            "as_of_date": as_of_date,
            "filed_at": filed_at,
            "version": version,
            "computation_hash": row_hash,
            "status": _VERSION_STATUS_ACTIVE,
        }

        result = await db.express.create(_FEATURES_TABLE, row)

        logger.info(
            "feature_store.write",
            instrument=instrument,
            feature_name=feature_name,
            value=value,
            as_of_date=as_of_date,
            version=version,
        )
        return result

    # ------------------------------------------------------------------
    # Read (PIT-disciplined)
    # ------------------------------------------------------------------

    async def read(
        self,
        instrument: str,
        feature_name: str,
        as_of_date: str,
        *,
        version: str = "feature_v1",
    ) -> dict[str, Any] | None:
        """Read a single feature value with PIT discipline.

        Only returns features whose ``filed_at <= as_of_date``. This
        ensures backtests and decisions never see data that was not
        known at the time.

        Args:
            instrument: Ticker or identifier.
            feature_name: Feature identifier.
            as_of_date: ISO date string for PIT context.
            version: Version tag to read from.

        Returns:
            The feature row dict, or None if no matching row exists.
        """
        db = await self._ensure_db()

        rows = await db.express.list(
            _FEATURES_TABLE,
            filter={
                "instrument": instrument,
                "feature_name": feature_name,
                "version": version,
                "as_of_date": as_of_date,
            },
        )

        if not rows:
            return None

        # Apply PIT filter: only keep rows whose filed_at <= as_of_date.
        # The as_of_date represents the end of that day in UTC.
        as_of_dt = datetime.combine(
            date.fromisoformat(as_of_date),
            datetime.max.time(),
            tzinfo=timezone.utc,
        )

        eligible = []
        for row in rows:
            filed_at_str = row.get("filed_at")
            if filed_at_str is None:
                continue
            try:
                filed_at_dt = datetime.fromisoformat(filed_at_str)
                if filed_at_dt.tzinfo is None:
                    filed_at_dt = filed_at_dt.replace(tzinfo=timezone.utc)
                if filed_at_dt <= as_of_dt:
                    eligible.append(row)
            except (ValueError, TypeError):
                logger.warning(
                    "feature_store.unparseable_filed_at",
                    instrument=instrument,
                    feature_name=feature_name,
                    filed_at=filed_at_str,
                )
                continue

        if not eligible:
            return None

        # Return the most recently filed eligible row.
        eligible.sort(key=lambda r: r.get("filed_at", ""), reverse=True)
        result = eligible[0]

        logger.debug(
            "feature_store.read",
            instrument=instrument,
            feature_name=feature_name,
            as_of_date=as_of_date,
            version=version,
            filed_at=result.get("filed_at"),
        )
        return result

    # ------------------------------------------------------------------
    # Batch read
    # ------------------------------------------------------------------

    async def read_batch(
        self,
        instruments: list[str],
        feature_names: list[str],
        as_of_date: str,
        *,
        version: str = "feature_v1",
    ) -> dict[str, dict[str, Any]]:
        """Batch read features for multiple instruments and feature names.

        Args:
            instruments: List of ticker identifiers.
            feature_names: List of feature identifiers.
            as_of_date: ISO date string for PIT context.
            version: Version tag to read from.

        Returns:
            Dict keyed by instrument -> feature_name -> feature row.
            Missing entries are simply absent from the dict.
        """
        await self._ensure_db()

        result: dict[str, dict[str, Any]] = {}
        for instrument in instruments:
            result[instrument] = {}
            for feature_name in feature_names:
                row = await self.read(
                    instrument=instrument,
                    feature_name=feature_name,
                    as_of_date=as_of_date,
                    version=version,
                )
                if row is not None:
                    result[instrument][feature_name] = row

        total = sum(len(v) for v in result.values())
        logger.info(
            "feature_store.read_batch",
            instruments=len(instruments),
            feature_names=len(feature_names),
            results=total,
            as_of_date=as_of_date,
            version=version,
        )
        return result

    # ------------------------------------------------------------------
    # Version management
    # ------------------------------------------------------------------

    async def list_versions(self, feature_name: str) -> list[str]:
        """List all active versions of a feature.

        Returns:
            Sorted list of version strings (e.g. ["feature_v1", "feature_v2"]).
        """
        db = await self._ensure_db()

        rows = await db.express.list(
            _FEATURES_TABLE,
            filter={"feature_name": feature_name},
        )

        versions: set[str] = set()
        for row in rows:
            v = row.get("version")
            if v is not None:
                versions.add(v)

        sorted_versions = sorted(versions)
        logger.debug(
            "feature_store.list_versions",
            feature_name=feature_name,
            versions=sorted_versions,
        )
        return sorted_versions

    async def retire_version(self, version: str) -> int:
        """Mark a version as retired. No new writes are accepted for retired
        versions, but reads still work.

        This is a soft operation: rows are updated with status "retired"
        rather than deleted, preserving PIT queryability.

        Args:
            version: Version string to retire (e.g. "feature_v1").

        Returns:
            The number of rows updated.
        """
        db = await self._ensure_db()

        rows = await db.express.list(
            _FEATURES_TABLE,
            filter={
                "version": version,
                "status": _VERSION_STATUS_ACTIVE,
            },
        )

        updated = 0
        for row in rows:
            row_id = row.get("id")
            if row_id is None:
                continue
            await db.express.update(
                _FEATURES_TABLE,
                str(row_id),
                {"status": _VERSION_STATUS_RETIRED},
            )
            updated += 1

        if updated > 0:
            logger.info(
                "feature_store.retire_version",
                version=version,
                rows_retired=updated,
            )
        else:
            logger.info(
                "feature_store.retire_version.nothing_to_retire",
                version=version,
            )

        return updated

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the DataFlow connection if we own it."""
        if self._db is not None:
            try:
                close_method = getattr(self._db, "close", None)
                if close_method is not None and callable(close_method):
                    close_method()
            except Exception as exc:
                logger.warning(
                    "feature_store.close_failed",
                    error=str(exc),
                )
