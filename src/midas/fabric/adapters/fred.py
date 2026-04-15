"""
FRED (Federal Reserve Economic Data) adapter.

Ingests macro series with ALFRED-style vintage tracking. Every data point
carries a ``vintage`` field recording when the data was released, ensuring
the point-in-time discipline is preserved for backtesting.

The FRED API documentation: https://fred.stlouisfed.org/docs/api/fred/

Ref: specs/03-universe-and-data.md §2.4 — FRED yield curve, PMI, CPI, etc.
Ref: T-01-06
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import httpx
import structlog
from dataflow import DataFlow

from midas.config import FRED_API_KEY
from midas.fabric.adapters.base import (
    AdapterError,
    AuthenticationError,
    BaseAdapter,
    RateLimitExceeded,
)

logger = structlog.get_logger("midas.fabric.adapters.fred")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRED_BASE_URL = "https://api.stlouisfed.org/fred"
DEFAULT_PAGE_SIZE = 1000  # FRED max per page
HTTP_TIMEOUT_S = 30.0
# FRED rate limit: 120 requests per minute (as of 2024)
FRED_MIN_CALL_INTERVAL_S = 0.5


class FREDAdapter(BaseAdapter):
    """Adapter for FRED macro data with ALFRED-style vintage tracking.

    Every method:
    - Fetches data with vintage/release information
    - Writes rows to the ``macro`` fabric table
    - Includes ``source_vintage`` tracking when the data was published
    - Never raises to callers on data-source failure
    """

    SOURCE_NAME = "fred"

    def __init__(
        self,
        db: DataFlow | None = None,
        *,
        api_key: str | None = None,
        base_url: str = FRED_BASE_URL,
        http_timeout_s: float = HTTP_TIMEOUT_S,
        **kwargs,
    ) -> None:
        # Override the default min_call_interval for FRED's rate limit
        kwargs.setdefault("min_call_interval_s", FRED_MIN_CALL_INTERVAL_S)
        super().__init__(db, **kwargs)
        self._api_key = api_key or FRED_API_KEY
        self._base_url = base_url.rstrip("/")
        self._http_timeout_s = http_timeout_s
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Return (or lazily create) the httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._http_timeout_s),
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Check FRED connectivity by fetching a known series."""
        if not self._api_key:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": "FRED_API_KEY not configured",
            }

        try:
            rows = await self.fetch_series("DGS10", "2024-01-02", "2024-01-03")
            return {
                "source": self.SOURCE_NAME,
                "healthy": True,
                "detail": f"returned {len(rows)} rows for DGS10",
            }
        except Exception as exc:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": str(exc),
            }

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(
        self,
        path: str,
        params: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        """Make an authenticated GET to FRED, handling error codes."""
        if not self._api_key:
            raise AuthenticationError(self.SOURCE_NAME, operation)

        params_with_key = {
            **params,
            "api_key": self._api_key,
            "file_type": "json",
        }

        async def _do_request() -> dict[str, Any]:
            client = self._get_client()
            response = await client.get(path, params=params_with_key)

            if response.status_code == 400 and "api_key" in response.text.lower():
                raise AuthenticationError(
                    self.SOURCE_NAME, operation, status_code=response.status_code
                )

            if response.status_code == 401 or response.status_code == 403:
                raise AuthenticationError(
                    self.SOURCE_NAME, operation, status_code=response.status_code
                )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_after_s = float(retry_after) if retry_after else 60.0
                self._handle_rate_limit_headers(dict(response.headers))
                raise RateLimitExceeded(self.SOURCE_NAME, operation, retry_after_s)

            if response.status_code >= 500:
                raise AdapterError(
                    self.SOURCE_NAME,
                    operation,
                    f"server error: HTTP {response.status_code}",
                )

            if response.status_code >= 400:
                raise AdapterError(
                    self.SOURCE_NAME,
                    operation,
                    f"client error: HTTP {response.status_code}: {response.text[:200]}",
                )

            return response.json()

        return await self._retry(operation, _do_request)

    # ------------------------------------------------------------------
    # Series fetch (primary method)
    # ------------------------------------------------------------------

    async def fetch_series(
        self,
        series_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch a macro series with vintage tracking.

        Uses the ALFRED ``releases/dates`` endpoint to determine when each
        data point was published, enabling point-in-time backtesting. Falls
        back to the observation date when release-date information is
        unavailable.

        Parameters
        ----------
        series_id:
            FRED series identifier (e.g. ``"CPIAUCSL"``, ``"DGS10"``,
            ``"UNRATE"``).
        start_date, end_date:
            ISO date strings (``"YYYY-MM-DD"``).

        Returns
        -------
        List of fabric rows written to the ``macro`` table.
        """
        operation = "fetch_series"
        self._log.info(
            "fetch_series.start",
            series_id=series_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Step 1: Fetch the series observations
        observations = await self._fetch_observations(series_id, start_date, end_date, operation)
        if not observations:
            return []

        # Step 2: Attempt to fetch vintage/release information via ALFRED
        release_dates = await self._fetch_release_dates(series_id, start_date, end_date)

        # Step 3: Determine the series frequency from metadata
        series_info = await self._fetch_series_info(series_id)
        frequency = series_info.get("frequency_short", None)
        units = series_info.get("units", None)

        # Step 4: Write rows to the macro table
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for obs in observations:
            obs_date = obs.get("date", "")
            obs_value = obs.get("value")

            # Skip observations with no value (FRED uses "." for missing)
            if obs_value is None or obs_value == ".":
                continue

            try:
                value = float(obs_value)
            except (ValueError, TypeError):
                continue

            # Look up the release date (vintage) for this observation
            vintage_date = release_dates.get(obs_date)
            if vintage_date is None:
                # Fall back to the observation date itself as vintage
                vintage_date = obs_date

            filed_at = self._build_filed_at(vintage_date)

            row: dict[str, Any] = {
                "series_code": series_id,
                "period_end": obs_date,
                "filed_at": filed_at,
                "restated_at": None,
                "source_vintage": f"fred:{series_id}:{vintage_date}",
                "value": value,
                "unit": units,
                "frequency": frequency,
            }

            try:
                await db.express.create("macro", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_series.row_write_failed",
                    series_id=series_id,
                    date=obs_date,
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(observations)} observations, wrote {len(created_rows)}",
            instrument=series_id,
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_series.complete",
            series_id=series_id,
            rows_fetched=len(observations),
            rows_written=len(created_rows),
        )
        return created_rows

    # ------------------------------------------------------------------
    # Observation fetcher (handles pagination)
    # ------------------------------------------------------------------

    async def _fetch_observations(
        self,
        series_id: str,
        start_date: str,
        end_date: str,
        operation: str,
    ) -> list[dict[str, Any]]:
        """Fetch paginated observations from FRED."""
        all_obs: list[dict[str, Any]] = []
        offset = 0
        limit = DEFAULT_PAGE_SIZE

        while True:
            params: dict[str, Any] = {
                "series_id": series_id,
                "observation_start": start_date,
                "observation_end": end_date,
                "sort_order": "asc",
                "offset": offset,
                "limit": limit,
            }

            try:
                data = await self._request(
                    "/series/observations",
                    params,
                    f"{operation}:observations",
                )
            except AuthenticationError as exc:
                self._log.error(
                    "fetch_series.auth_failed",
                    series_id=series_id,
                    error=str(exc),
                )
                await self._write_audit(
                    operation=operation,
                    success=False,
                    detail=f"auth failed: {exc}",
                    instrument=series_id,
                )
                return []
            except AdapterError as exc:
                self._log.error(
                    "fetch_series.page_failed",
                    series_id=series_id,
                    offset=offset,
                    error=str(exc),
                )
                break

            observations = data.get("observations", [])
            if not observations:
                break

            all_obs.extend(observations)

            count = data.get("count", 0)
            if offset + limit >= count:
                break
            offset += limit

        return all_obs

    # ------------------------------------------------------------------
    # ALFRED vintage data
    # ------------------------------------------------------------------

    async def _fetch_release_dates(
        self,
        series_id: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, str]:
        """Fetch release dates for observations via ALFRED.

        Returns a mapping of ``{observation_date: release_date}``.
        Falls back to an empty dict on failure (non-critical).
        """
        try:
            data = await self._request(
                "/release/dates",
                {
                    "series_id": series_id,
                    "observation_start": start_date,
                    "observation_end": end_date,
                    "include_release_dates": "true",
                },
                "fetch_release_dates",
            )
            release_dates: dict[str, str] = {}
            for entry in data.get("observation_dates", data.get("release_dates", [])):
                obs_date = entry.get("date", entry.get("observation_date", ""))
                release_date = entry.get("release_date", entry.get("date", ""))
                if obs_date and release_date:
                    release_dates[obs_date] = release_date
            return release_dates
        except Exception as exc:
            self._log.warning(
                "release_dates.unavailable",
                series_id=series_id,
                error=str(exc),
            )
            return {}

    # ------------------------------------------------------------------
    # Series metadata
    # ------------------------------------------------------------------

    async def _fetch_series_info(self, series_id: str) -> dict[str, Any]:
        """Fetch series metadata (frequency, units, title).

        Returns the ``seriess`` entry from the FRED API, or an empty
        dict on failure (non-critical).
        """
        try:
            data = await self._request(
                "/series",
                {"series_id": series_id},
                "fetch_series_info",
            )
            series_list = data.get("seriess", [])
            if series_list:
                return series_list[0]
            return {}
        except Exception as exc:
            self._log.warning(
                "series_info.unavailable",
                series_id=series_id,
                error=str(exc),
            )
            return {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filed_at(date_str: str) -> str:
        """Build an ISO datetime from a date string, defaulting to end-of-day."""
        try:
            d = date.fromisoformat(date_str)
            return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()
        except (ValueError, TypeError):
            return datetime.now(timezone.utc).isoformat()
