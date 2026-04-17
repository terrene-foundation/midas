"""Rate limiter for IBKR API calls.

Enforces a configurable requests-per-minute budget with a sliding window.
Priority levels are accepted but share the same budget pool.

Ref: M15 — Rate limiter
"""

import time
from collections import deque

import structlog

logger = structlog.get_logger("midas.execution.rate_limiter")


class RateLimiter:
    """50 req/min budget with priority queue."""

    def __init__(self, budget_per_minute: int = 50):
        self._budget = budget_per_minute
        # deque with maxlen provides hard cap on memory regardless of call pattern
        self._timestamps: deque[float] = deque(maxlen=budget_per_minute)
        self._log = structlog.get_logger("midas.execution.rate_limiter")

    def _prune_old_timestamps(self) -> None:
        """Remove timestamps older than 60 seconds (outside the window).

        With deque(maxlen=budget), old entries are auto-evicted on insert when
        the deque is full. This method handles the case where the deque is not
        full but entries have aged out (quiet period between calls).
        """
        cutoff = time.monotonic() - 60.0
        # Rebuild deque keeping only recent entries (deque doesn't support in-place filter)
        self._timestamps = deque(
            (t for t in self._timestamps if t > cutoff),
            maxlen=self._budget,
        )

    async def acquire(self, priority: str = "normal") -> bool:
        """Acquire rate limit slot. Returns True if allowed."""
        self._prune_old_timestamps()

        if len(self._timestamps) >= self._budget:
            self._log.debug(
                "rate_limiter.rejected",
                budget=self._budget,
                current=len(self._timestamps),
                priority=priority,
            )
            return False

        now = time.monotonic()
        self._timestamps.append(now)

        self._log.debug(
            "rate_limiter.acquired",
            remaining=self._budget - len(self._timestamps),
            priority=priority,
        )
        return True

    def get_remaining_budget(self) -> int:
        """Get remaining requests in current window."""
        self._prune_old_timestamps()
        return max(0, self._budget - len(self._timestamps))
