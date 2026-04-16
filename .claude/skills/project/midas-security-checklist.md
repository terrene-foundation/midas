# Midas Security Checklist

Ten specific security and quality patterns found during red team validation (commits 04b1125 through ee8fe28). These are the patterns this codebase already exhibited — check every new module against this list before commit.

---

## Kill Switch

- **MUST require confirmation_code + user_approved** — a body boolean alone is spoofable
- **MUST NOT auto-clear** — only user action clears it
- Test: verify rejection when `confirmation_code` is missing

## Credential Leaks

- **MUST NOT include response bodies in error messages** — OAuth tokens may be present
- Applies to all HTTP adapters, not just IBKR
- Search: `grep -n "response.text\|response.content" src/midas/fabric/adapters/`

## Financial Calculations

- **MUST guard NaN/Inf with `math.isfinite()`** — applies to every float that reaches a brief, API response, or decision
- Applies to: Brinson decomposition, NAV computation, Sharpe ratio, returns, spread calculations
- **MUST guard division by near-zero** — use `if denominator > 1e-10` not `if denominator`

## API Authentication

- **MUST authenticate all non-health endpoints** — Bearer or ApiKey tokens
- Health endpoints (`/api/v1/health/*`, `/docs`, `/openapi.json`) are public
- Dev mode (no `MIDAS_API_KEY` env var) passes all requests through

## Health Endpoints

- **MUST check real infrastructure** — database URL, broker connectivity, data source keys
- MUST NOT return `{"status": "healthy"}` unconditionally

## Debate Agent

- **MUST return honest failure signal on parse error** — `{"recommendation": "parse_failed", "parse_error": true}`
- MUST NOT fabricate steel_man or red_team text when JSON parsing fails

## Tool Outputs

- **MUST use lazy imports for optional modules** — `try: from midas.X import Y; except ImportError: ...`
- **MUST NOT use placeholder strings** like `"computed_from_z_t"` as fake outputs

## Silent Exceptions

- **MUST log before falling back** — `except Exception: return []` without logging is BLOCKED
- Acceptable: cleanup/teardown paths (db.close, os.unlink, CancelledError)
- Search: `grep -A3 "except.*:" src/midas/ | grep -B3 "pass\|return None\|return \[\]"`

## Kill Switch Confirmation

```python
# DO
async def clear_kill_switch(self, body):
    confirmation_code = body.get("confirmation_code", "")
    user_approved = body.get("user_approved", False)
    if not user_approved:
        raise HTTPException(400, "User approval required")
    if not confirmation_code:
        raise HTTPException(400, "Confirmation code required")

# DO NOT
async def clear_kill_switch(self, body):
    if body.get("user_approved"):
        return {"status": "cleared"}  # spoofable
```

## NaN Guard Pattern

```python
# DO
import math
nav = positions_value + cash - unsettled
if not math.isfinite(nav):
    logger.warning("nav.non_finite", nav=nav, positions_value=positions_value)
    nav = 0.0

# DO NOT
nav = positions_value + cash - unsettled  # NaN propagates silently
```
