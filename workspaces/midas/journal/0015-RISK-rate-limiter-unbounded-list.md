# RISK: RateLimiter Unbounded List Growth

**Date:** 2026-04-16
**Found during:** /redteam security audit
**Source:** security-audit (security-reviewer agent)

## Finding

`src/midas/execution/rate_limiter.py:21` — `self._timestamps: list[float] = []` grows without a hard cap. While `_prune_old_timestamps()` removes entries older than 60 seconds, the list itself has no `maxlen` bound. Under high request volume, if `acquire()` is called rarely (quiet periods), the list could temporarily accumulate unbounded entries before pruning triggers.

**IBKR rate limit:** 50 req/min. RateLimiter enforces 50 req/min budget with 20% margin (IBKR_MIN_CALL_INTERVAL_S = 1.5). The pruning runs every `acquire()` call, so normal operation is safe.

## Risk

- Medium: List grows unbounded in pathological quiet-period-then-burst scenario
- Not exploitable for rate limit bypass (pruning still works, just inefficient)
- No security impact (timestamps are opaque numbers, not sensitive)

## Recommendation

Use `collections.deque(maxlen=...)` or add a `maxlen` check at `acquire()` entry to hard-cap at the maximum possible entries.

## Disposition

**RESOLVED (2026-04-17)** — commit `d9374cc` changes `_timestamps` from `list[float]` to `collections.deque(maxlen=budget_per_minute)`. Provides hard cap on memory regardless of call pattern. Time-based pruning still runs to handle quiet periods.
