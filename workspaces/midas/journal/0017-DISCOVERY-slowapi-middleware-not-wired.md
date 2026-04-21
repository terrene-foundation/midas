# DISCOVERY: slowapi Already Imported But Not Wired

**Date:** 2026-04-19
**Type:** DISCOVERY
**Slug:** slowapi-middleware-not-wired

## Finding

The original `app.py` had `slowapi` imported at lines 17-19 (`Limiter`, `get_remote_address`, `RateLimitExceeded`) but the middleware was a no-op pass-through:

```python
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting before auth."""
    return await call_next(request)  # ← literally does nothing
```

## Implication

The `Limiter` was imported but never instantiated or used. The rate limiting was cosmetic (imported but not functional). My fix replaced the no-op with a proper sliding-window implementation using `time.monotonic()` and `deque`.

## Lesson

Presence of an import ≠ presence of functionality. The decorator imports were in the file for 6+ months without being connected to the middleware chain.
