"""Background job scheduler using APScheduler-style cron triggers.

Provides SchedulerService for registering, triggering, and managing
scheduled jobs, and JobFailureRecovery for exponential-backoff retry.

Ref: M14 — T-01-14
"""

import asyncio
import time
import uuid

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.scheduler")


class SchedulerService:
    """Background job scheduler using APScheduler-style cron triggers."""

    def __init__(self, db: DataFlow):
        self._db = db
        self._jobs: dict[str, dict] = {}
        self._running = False
        self._log = structlog.get_logger("midas.scheduler")

    def register_job(
        self,
        job_id: str,
        cron_expr: str,
        handler,
        description: str = "",
        max_retries: int = 3,
    ) -> None:
        """Register a scheduled job."""
        self._jobs[job_id] = {
            "job_id": job_id,
            "cron_expr": cron_expr,
            "handler": handler,
            "description": description,
            "max_retries": max_retries,
            "status": "idle",
            "last_run": None,
            "last_result": None,
        }
        self._log.info(
            "scheduler.register_job",
            job_id=job_id,
            cron_expr=cron_expr,
            description=description,
        )

    async def start(self) -> None:
        """Start the scheduler."""
        self._running = True
        self._log.info("scheduler.started", jobs=len(self._jobs))

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        self._log.info("scheduler.stopped")

    async def trigger_job(self, job_id: str, context: dict | None = None) -> dict:
        """Manually trigger a job. Returns {success, result, duration_ms}."""
        if job_id not in self._jobs:
            raise KeyError(f"Job '{job_id}' is not registered")

        job = self._jobs[job_id]
        handler = job["handler"]
        ctx = context or {}

        job["status"] = "running"
        t0 = time.monotonic()

        try:
            result = await handler(ctx)
            duration_ms = (time.monotonic() - t0) * 1000
            job["status"] = "idle"
            job["last_run"] = time.time()
            job["last_result"] = result
            self._log.info(
                "scheduler.trigger_job.ok",
                job_id=job_id,
                duration_ms=round(duration_ms, 2),
            )
            return {
                "success": True,
                "result": result,
                "duration_ms": round(duration_ms, 2),
            }
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            job["status"] = "idle"
            job["last_run"] = time.time()
            self._log.error(
                "scheduler.trigger_job.error",
                job_id=job_id,
                error=str(exc),
                duration_ms=round(duration_ms, 2),
            )
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": round(duration_ms, 2),
            }

    async def get_job_status(self, job_id: str) -> dict:
        """Get status of a job."""
        if job_id not in self._jobs:
            raise KeyError(f"Job '{job_id}' is not registered")
        job = self._jobs[job_id]
        return {
            "job_id": job["job_id"],
            "cron_expr": job["cron_expr"],
            "description": job["description"],
            "status": job["status"],
            "last_run": job["last_run"],
            "last_result": job["last_result"],
        }

    async def list_jobs(self) -> list[dict]:
        """List all registered jobs with status."""
        return [
            {
                "job_id": j["job_id"],
                "cron_expr": j["cron_expr"],
                "description": j["description"],
                "status": j["status"],
                "last_run": j["last_run"],
            }
            for j in self._jobs.values()
        ]


class JobFailureRecovery:
    """Handles job failure with exponential backoff."""

    def __init__(self, max_retries: int = 3, base_delay: float = 60.0):
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._log = structlog.get_logger("midas.scheduler.recovery")

    async def execute_with_retry(self, job_id: str, handler, context: dict = None) -> dict:
        """Execute handler with retry logic.

        Returns {success, result, error, attempts}.
        """
        ctx = context or {}
        delay = self._base_delay
        last_error = None

        for attempt in range(1, self._max_retries + 1):
            try:
                result = await handler(ctx)
                self._log.info(
                    "recovery.success",
                    job_id=job_id,
                    attempt=attempt,
                )
                return {
                    "success": True,
                    "result": result,
                    "attempts": attempt,
                }
            except Exception as exc:
                last_error = exc
                if attempt < self._max_retries:
                    self._log.warning(
                        "recovery.retry",
                        job_id=job_id,
                        attempt=attempt,
                        delay_s=round(delay, 2),
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 300.0)

        self._log.error(
            "recovery.exhausted",
            job_id=job_id,
            max_retries=self._max_retries,
            error=str(last_error),
        )
        return {
            "success": False,
            "error": str(last_error),
            "attempts": self._max_retries,
        }
