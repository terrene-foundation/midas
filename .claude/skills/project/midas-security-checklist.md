# Midas Security Checklist

Security and quality patterns codified from red team rounds 1–7 (commits 04b1125 through ebfbad4). Check every new module against this list before commit.

---

## Kill Switch

- **MUST require confirmation_code + user_approved** — a body boolean alone is spoofable
- **MUST NOT auto-clear** — only user action clears it
- **Confirmation code hash persisted in audit_log** — instance vars lost on worker restart
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
- **Re-auth required for sensitive operations** — approve/decline decisions require X-Reauth-Token (5-min JWT with `type=reauth`)

## Rate Limiting

- **Per-IP sliding-window** — 60 requests/minute, custom implementation (no external deps)
- Returns `X-RateLimit-Remaining` header on every response
- Accounts for `X-Forwarded-For` proxy header
- Test: verify 429 response after exceeding limit

## IDOR Protection

- **Mutation endpoints MUST verify ownership** — extract JWT `sub` from `request.state.user`, compare to resource `user_id`
- Applies to: modify_decision, resolve debate, paper-live transition
- Raises 403 on mismatch

```python
# DO
async def modify_decision(self, decision_id, request, body):
    user = request.state.user
    decision = await db.express.read("Decision", decision_id)
    if decision.get("user_id") != user.get("sub"):
        raise HTTPException(403, "Not authorized")

# DO NOT
async def modify_decision(self, decision_id, body):
    # no auth check — any authenticated user can modify any decision
```

## Health Endpoints

- **MUST check real infrastructure** — adapter health status, not config key presence
- MUST NOT return `{"status": "healthy"}` unconditionally
- MUST NOT leak which env vars are set or which adapters are configured

## Database Access

- **`_get_db()` raises HTTPException(503)** — never returns None
- Callers MUST NOT check `if db is None` — the 503 is raised before return
- Use try/except HTTPException around `_get_db()` calls

## Password Hashing

- **bcrypt for primary** — `bcrypt.hashpw()` with salt
- **PBKDF2-HMAC-SHA256 fallback** — 600,000 iterations when bcrypt unavailable
- **SHA-256 fallback is BLOCKED** — insufficient for production

## Session Security

- **Concurrent refresh token detection** — if a refresh token is used while another session exists for the same user, revoke ALL sessions
- **Mass revocation on concurrent use** — prevents token theft from going undetected
- Log WARN on detection

## Silent Exceptions

- **MUST log before falling back** — `except Exception: return []` without logging is BLOCKED
- Acceptable: cleanup/teardown paths (db.close, os.unlink, CancelledError)
- Search: `grep -A3 "except.*:" src/midas/ | grep -B3 "pass\|return None\|return \[\]"`

## Debate Agent

- **MUST return honest failure signal on parse error** — `{"recommendation": "parse_failed", "parse_error": true}`
- MUST NOT fabricate steel_man or red_team text when JSON parsing fails

## Tool Outputs

- **MUST use lazy imports for optional modules** — `try: from midas.X import Y; except ImportError: ...`
- **MUST NOT use placeholder strings** like `"computed_from_z_t"` as fake outputs

## Kill Switch Confirmation

```python
# DO — hash persisted in audit_log, survives worker restart
async def activate(self, db):
    code = secrets.token_hex(8)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    await db.express.create("AuditLog", {
        "action": "kill_switch_activate",
        "details": {"confirmation_code_hash": code_hash},
    })
    return {"confirmation_code": code}

async def clear(self, db, body):
    log = await db.express.list("AuditLog", {"action": "kill_switch_activate"})
    stored_hash = log[-1]["details"]["confirmation_code_hash"]
    if not hmac.compare_digest(hashlib.sha256(body["code"].encode()).hexdigest(), stored_hash):
        raise HTTPException(400, "Invalid confirmation code")
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
