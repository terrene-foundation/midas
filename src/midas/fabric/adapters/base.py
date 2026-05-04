"""
Base adapter class for all data source adapters.

Provides common retry logic with exponential backoff, rate-limit enforcement,
and audit logging to the fabric. Every adapter inherits from BaseAdapter and
implements its own fetch methods on top of this shared infrastructure.

Ref: specs/03-universe-and-data.md §3.2 — adapter layer is the only place
that makes outbound calls.
Ref: T-01-02, T-01-03
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import structlog
from dataflow import DataFlow

from midas.config import DATABASE_URL

logger = structlog.get_logger("midas.fabric.adapters")

# ---------------------------------------------------------------------------
# Retry defaults
# ---------------------------------------------------------------------------

DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BASE_DELAY_S: float = 1.0
DEFAULT_MAX_DELAY_S: float = 30.0
DEFAULT_BACKOFF_MULTIPLIER: float = 2.0

# ---------------------------------------------------------------------------
# Rate-limit defaults
# ---------------------------------------------------------------------------

DEFAULT_MIN_CALL_INTERVAL_S: float = 0.1  # 100ms between calls


class AdapterError(Exception):
    """Typed error for adapter-level failures.

    These are written to the audit_log rather than raised to callers.
    """

    def __init__(self, source: str, operation: str, detail: str) -> None:
        self.source = source
        self.operation = operation
        self.detail = detail
        super().__init__(f"[{source}:{operation}] {detail}")


class RateLimitExceeded(AdapterError):
    """The adapter has hit its configured rate limit."""

    def __init__(self, source: str, operation: str, retry_after_s: float | None = None) -> None:
        detail = (
            f"rate limit exceeded, retry_after={retry_after_s}s"
            if retry_after_s is not None
            else "rate limit exceeded"
        )
        super().__init__(source, operation, detail)
        self.retry_after_s = retry_after_s


class AuthenticationError(AdapterError):
    """The adapter could not authenticate with the source."""

    def __init__(self, source: str, operation: str, status_code: int | None = None) -> None:
        detail = (
            f"authentication failed (status={status_code})"
            if status_code is not None
            else "authentication failed"
        )
        super().__init__(source, operation, detail)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# BaseAdapter
# ---------------------------------------------------------------------------


class BaseAdapter(ABC):
    """Abstract base for every external data source adapter.

    Subclasses implement domain-specific fetch methods. The base provides:

    - Exponential-backoff retry via ``_retry()``.
    - Rate-limit enforcement via ``_enforce_rate_limit()``.
    - Structured audit logging to the ``audit_log`` fabric table via
      ``_write_audit()``.
    - A single shared ``DataFlow`` instance for fabric writes.
    """

    # Subclasses override these
    SOURCE_NAME: str = "base"

    def __init__(
        self,
        db: DataFlow | None = None,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay_s: float = DEFAULT_BASE_DELAY_S,
        max_delay_s: float = DEFAULT_MAX_DELAY_S,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        min_call_interval_s: float = DEFAULT_MIN_CALL_INTERVAL_S,
    ) -> None:
        self._db = db
        self._max_retries = max_retries
        self._base_delay_s = base_delay_s
        self._max_delay_s = max_delay_s
        self._backoff_multiplier = backoff_multiplier
        self._min_call_interval_s = min_call_interval_s

        # Rate-limit tracking
        self._last_call_time: float = 0.0

        # Adapter-scoped logger bound with source name
        self._log = logger.bind(adapter=self.SOURCE_NAME)

    # ------------------------------------------------------------------
    # DataFlow access
    # ------------------------------------------------------------------

    def _get_db(self) -> DataFlow:
        """Return the DataFlow instance, creating one lazily if needed."""
        if self._db is None:
            self._db = DataFlow(DATABASE_URL)
        return self._db

    # ------------------------------------------------------------------
    # Health check — subclasses MUST implement
    # ------------------------------------------------------------------

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return a health-status dict for this adapter.

        The dict always includes at least:

        - ``source``: the adapter's SOURCE_NAME
        - ``healthy``: bool
        - ``detail``: human-readable status
        """
        ...

    # ------------------------------------------------------------------
    # Rate-limit enforcement
    # ------------------------------------------------------------------

    async def _enforce_rate_limit(self) -> None:
        """Sleep if the last call was too recent.

        This is a simple time-based gate. Subclasses that negotiate
        rate-limit headers (e.g. Retry-After) should override
        ``_handle_rate_limit_headers()`` instead.
        """
        now = time.monotonic()
        elapsed = now - self._last_call_time
        if elapsed < self._min_call_interval_s:
            sleep_time = self._min_call_interval_s - elapsed
            self._log.debug(
                "rate_limit.sleep",
                sleep_s=round(sleep_time, 3),
            )
            await asyncio.sleep(sleep_time)
        self._last_call_time = time.monotonic()

    def _handle_rate_limit_headers(self, headers: dict[str, str]) -> None:
        """Inspect response headers for rate-limit signals.

        Subclasses can override to extract ``Retry-After`` or similar
        headers and adjust ``_min_call_interval_s`` dynamically.
        """
        retry_after = (
            headers.get("Retry-After")
            or headers.get("retry-after")
            or headers.get("X-RateLimit-Reset")
            or headers.get("x-ratelimit-reset")
        )
        if retry_after is not None:
            try:
                self._min_call_interval_s = max(float(retry_after), self._min_call_interval_s)
                self._log.debug(
                    "rate_limit.adjusted",
                    new_interval_s=self._min_call_interval_s,
                )
            except (ValueError, TypeError):
                pass

    # ------------------------------------------------------------------
    # Exponential-backoff retry
    # ------------------------------------------------------------------

    async def _retry(self, operation: str, fn, *args, **kwargs):
        """Call ``fn`` with exponential-backoff retry.

        Parameters
        ----------
        operation:
            Human-readable label for log lines (e.g. ``"fetch_prices"``).
        fn:
            The async callable to retry.
        *args, **kwargs:
            Forwarded to ``fn`` on every attempt.

        Returns
        -------
        Whatever ``fn`` returns on success.

        Raises
        ------
        AdapterError
            After exhausting all retries.
        """
        last_exc: Exception | None = None
        delay = self._base_delay_s

        for attempt in range(1, self._max_retries + 1):
            try:
                await self._enforce_rate_limit()
                result = await fn(*args, **kwargs)
                if attempt > 1:
                    self._log.info(
                        "retry.success",
                        operation=operation,
                        attempt=attempt,
                    )
                return result
            except AuthenticationError:
                # Auth failures are not retriable — propagate immediately
                raise
            except (RateLimitExceeded, AdapterError) as exc:
                last_exc = exc
            except Exception as exc:
                last_exc = exc

            if attempt < self._max_retries:
                self._log.warning(
                    "retry.attempt_failed",
                    operation=operation,
                    attempt=attempt,
                    max_retries=self._max_retries,
                    delay_s=round(delay, 2),
                    error=str(last_exc),
                )
                await asyncio.sleep(delay)
                delay = min(delay * self._backoff_multiplier, self._max_delay_s)

        # Exhausted retries
        self._log.error(
            "retry.exhausted",
            operation=operation,
            max_retries=self._max_retries,
            error=str(last_exc),
        )
        raise AdapterError(
            source=self.SOURCE_NAME,
            operation=operation,
            detail=f"exhausted {self._max_retries} retries: {last_exc}",
        )

    # ------------------------------------------------------------------
    # Audit logging to fabric
    # ------------------------------------------------------------------

    async def _write_audit(
        self,
        *,
        operation: str,
        success: bool,
        detail: str,
        instrument: str | None = None,
        rows_written: int = 0,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Write a structured audit entry to the ``audit_log`` fabric table.

        This never raises — failures are logged locally so they don't
        mask the original operation's outcome.
        """
        now = datetime.now(timezone.utc)
        audit_id = f"adapter:{self.SOURCE_NAME}:{operation}:{uuid.uuid4().hex[:8]}"

        details_payload: dict[str, Any] = {
            "source": self.SOURCE_NAME,
            "operation": operation,
            "success": success,
            "detail": detail,
            "rows_written": rows_written,
        }
        if instrument is not None:
            details_payload["instrument"] = instrument
        if extra:
            details_payload.update(extra)

        try:
            import json

            db = self._get_db()
            await db.express.create(
                "audit_log",
                {
                    "audit_id": audit_id,
                    "period_end": now.date().isoformat(),
                    "filed_at": now.isoformat(),
                    "agent": f"adapter:{self.SOURCE_NAME}",
                    "rule_name": operation,
                    "action": "SUCCESS" if success else "FAILURE",
                    "details": json.dumps(details_payload),
                    "z_t_snapshot": None,
                },
            )
            self._log.debug(
                "audit.written",
                audit_id=audit_id,
                operation=operation,
                success=success,
            )
        except Exception as exc:
            # Audit write failure must not mask the original operation result.
            self._log.error(
                "audit.write_failed",
                operation=operation,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Clean up resources. Subclasses override to close HTTP clients etc."""
        pass
