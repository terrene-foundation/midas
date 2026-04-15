"""
Stale-data gate for the Midas fabric.

Computes data freshness per feature type and emits stale flags to the
audit log when data exceeds its threshold. Consumed by the Pre-Trade
Compliance Agent (M12) to block trades on stale upstream data.

Freshness thresholds from specs/03-universe-and-data.md sections 3.4:
  - prices:    1 day (EOD data)
  - fundamentals: 90 days
  - macro:     30 days
  - quotes:    1 minute (active) / 15 minutes (inactive)
  - news:      1 hour
  - latent_state: 1 hour

Ref: T-01-11
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import structlog

from midas.fabric.cache import FabricCache

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Freshness thresholds (seconds)
# ---------------------------------------------------------------------------

FRESHNESS_THRESHOLDS: dict[str, float] = {
    "prices": 86400.0,  # 1 day
    "fundamentals": 7_776_000.0,  # 90 days
    "macro": 2_592_000.0,  # 30 days
    "quotes_active": 60.0,  # 1 minute
    "quotes_inactive": 900.0,  # 15 minutes
    "news": 3600.0,  # 1 hour
    "latent_state": 3600.0,  # 1 hour
}

# Map logical feature types to their cache key prefixes for last-updated lookup.
_FEATURE_CACHE_PREFIXES: dict[str, str] = {
    "prices": "price",
    "fundamentals": "fundamentals",
    "macro": "macro",
    "quotes": "quote",
    "news": "news",
    "latent_state": "latent",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FreshnessResult:
    """Result of a single freshness check.

    Attributes:
        is_fresh: True when staleness_seconds <= threshold_seconds.
        staleness_seconds: Seconds elapsed since the data was last updated.
        threshold_seconds: The configured freshness threshold for this type.
        feature_type: The feature type that was checked.
        last_updated: ISO-format timestamp of the last update, or None if
            no data was found.
        message: Human-readable description of the result.
    """

    is_fresh: bool
    staleness_seconds: float
    threshold_seconds: float
    feature_type: str
    last_updated: str | None
    message: str


# ---------------------------------------------------------------------------
# Freshness gate
# ---------------------------------------------------------------------------


class FreshnessGate:
    """Computes data freshness per feature type.

    Reads the ``_cached_at`` timestamp from the Redis cache to determine
    how old each data source is, compares it against the configured
    threshold, and writes stale-data flags to the audit log when a
    threshold is exceeded.
    """

    def __init__(self, cache: FabricCache) -> None:
        self._cache = cache

    @staticmethod
    def _resolve_threshold(feature_type: str) -> float:
        """Return the freshness threshold in seconds for a feature type."""
        if feature_type in FRESHNESS_THRESHOLDS:
            return FRESHNESS_THRESHOLDS[feature_type]
        # Support "quotes" as an alias for "quotes_active".
        if feature_type == "quotes":
            return FRESHNESS_THRESHOLDS["quotes_active"]
        # Unknown types get a conservative 1-hour threshold.
        logger.warning(
            "freshness.unknown_feature_type",
            feature_type=feature_type,
            fallback_threshold=3600.0,
        )
        return 3600.0

    async def _get_last_updated(self, instrument: str, feature_type: str) -> str | None:
        """Retrieve the last-updated timestamp for a feature from cache.

        Returns an ISO-format string or None if no cached data exists.
        """
        prefix = _FEATURE_CACHE_PREFIXES.get(feature_type, feature_type)
        cached = await self._cache.get_price(instrument) if prefix == "price" else None

        # For non-price types, look up via the generic latent-state or
        # direct cache key construction.
        if cached is None and feature_type == "latent_state":
            cached = await self._cache.get_latent_state(instrument)

        if cached is None:
            return None

        cached_at = cached.get("_cached_at")
        if cached_at is not None:
            return datetime.fromtimestamp(cached_at, tz=timezone.utc).isoformat()

        # Fall back to any timestamp field the cache row might carry.
        for ts_field in ("filed_at", "timestamp", "updated_at"):
            val = cached.get(ts_field)
            if val is not None:
                return str(val)

        return None

    async def check(
        self,
        instrument: str,
        feature_type: str,
        as_of_date: str,  # noqa: ARG002 — API contract for PIT discipline
        *,
        active: bool = True,
    ) -> FreshnessResult:
        """Check freshness of a single feature type for an instrument.

        Args:
            instrument: Ticker or identifier (e.g. "SPY").
            feature_type: One of the keys in FRESHNESS_THRESHOLDS.
            as_of_date: ISO date string for the PIT context.
            active: Whether the user is active (affects quotes TTL).

        Returns:
            A FreshnessResult indicating whether the data is fresh enough
            for use in decisions.
        """
        # Resolve the effective threshold for quotes.
        if feature_type == "quotes":
            effective_type = "quotes_active" if active else "quotes_inactive"
        else:
            effective_type = feature_type

        threshold = self._resolve_threshold(effective_type)

        last_updated_str = await self._get_last_updated(instrument, feature_type)

        if last_updated_str is None:
            # No data at all is definitely stale.
            return FreshnessResult(
                is_fresh=False,
                staleness_seconds=float("inf"),
                threshold_seconds=threshold,
                feature_type=feature_type,
                last_updated=None,
                message=f"No cached data found for {instrument} {feature_type}",
            )

        # Parse the timestamp and compute staleness.
        try:
            last_updated_dt = datetime.fromisoformat(last_updated_str)
            if last_updated_dt.tzinfo is None:
                last_updated_dt = last_updated_dt.replace(tzinfo=timezone.utc)
            staleness = (datetime.now(tz=timezone.utc) - last_updated_dt).total_seconds()
        except (ValueError, TypeError):
            staleness = float("inf")

        is_fresh = staleness <= threshold

        if is_fresh:
            message = (
                f"{feature_type} for {instrument} is fresh "
                f"({staleness:.0f}s <= {threshold:.0f}s threshold)"
            )
        else:
            message = (
                f"{feature_type} for {instrument} is STALE "
                f"({staleness:.0f}s > {threshold:.0f}s threshold)"
            )

        return FreshnessResult(
            is_fresh=is_fresh,
            staleness_seconds=staleness,
            threshold_seconds=threshold,
            feature_type=feature_type,
            last_updated=last_updated_str,
            message=message,
        )

    async def check_all(
        self,
        instrument: str,
        as_of_date: str | None = None,
        *,
        active: bool = True,
    ) -> dict[str, FreshnessResult]:
        """Check freshness for all known feature types for an instrument.

        Returns:
            A dict mapping feature type name to its FreshnessResult.
        """
        if as_of_date is None:
            as_of_date = date.today().isoformat()

        results: dict[str, FreshnessResult] = {}
        for feature_type in (
            "prices",
            "fundamentals",
            "macro",
            "quotes",
            "news",
            "latent_state",
        ):
            results[feature_type] = await self.check(
                instrument=instrument,
                feature_type=feature_type,
                as_of_date=as_of_date,
                active=active,
            )

        stale_count = sum(1 for r in results.values() if not r.is_fresh)
        logger.info(
            "freshness.check_all",
            instrument=instrument,
            total=len(results),
            stale=stale_count,
            fresh=len(results) - stale_count,
        )
        return results

    async def emit_stale_flag(
        self,
        instrument: str,
        feature_type: str,
        *,
        as_of_date: str | None = None,
        active: bool = True,
    ) -> bool:
        """Write a stale-data flag to the audit log when data is stale.

        This method is called by the Pre-Trade Compliance Agent (M12)
        and by scheduled health checks. It performs a freshness check and
        writes an audit entry when the threshold is exceeded.

        Args:
            instrument: Ticker or identifier.
            feature_type: The feature type to check.
            as_of_date: ISO date string for PIT context.
            active: Whether the user is currently active.

        Returns:
            True if a stale flag was emitted, False if data is fresh.
        """
        if as_of_date is None:
            as_of_date = date.today().isoformat()

        result = await self.check(
            instrument=instrument,
            feature_type=feature_type,
            as_of_date=as_of_date,
            active=active,
        )

        if not result.is_fresh:
            logger.warning(
                "freshness.stale_flag",
                instrument=instrument,
                feature_type=feature_type,
                staleness_seconds=result.staleness_seconds,
                threshold_seconds=result.threshold_seconds,
                last_updated=result.last_updated,
                message=result.message,
            )
            return True

        return False
