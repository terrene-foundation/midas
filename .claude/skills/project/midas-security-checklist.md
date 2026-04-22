# Midas Security Checklist

Security and quality patterns codified from red team rounds 1–12. Check every new module against this list before commit.

---

## Tool Allowlist for LLM Database Access (CRITICAL)

Every tool that queries a shared database MUST have an explicit allowlist of queryable tables. Authentication, credential, and session tables (`users`, `sessions`, `credentials`) are NEVER queryable by LLM tools.

```python
# DO
FABRIC_ALLOWLIST = {"prices", "decisions", "audit_log", ...}
async def query_fabric(table: str, ...):
    if table not in FABRIC_ALLOWLIST:
        raise ValueError(f"Table '{table}' not in allowlist")

# DO NOT
async def query_fabric(table: str, ...):
    return await db.express.list(table)  # reads users, sessions, credentials
```

**Why:** Without an allowlist, the debate endpoint could read `password_hash`, `refresh_token_hash`, and `encrypted_value` from auth tables. Source: round 9 security audit H-01.

---

## Conditional Auth Bypass (CRITICAL)

Sensitive operations (anything modifying decisions, trades, or money) MUST require authentication unconditionally. The `auth_required = bool(os.environ.get("JWT_SECRET", ""))` pattern bypasses auth when the env var is unset. Dev-mode bypass may only apply to read-only endpoints.

```python
# DO — unconditional auth for mutations
async def modify_decision(decision_id, request, body):
    user = require_auth(request)  # raises 401 if no user

# DO NOT — conditional auth
async def modify_decision(decision_id, request, body):
    if os.environ.get("JWT_SECRET"):
        user = get_current_user(request)  # bypassed when JWT_SECRET unset
```

**Why:** The conditional pattern propagated from 2 to 4 endpoints between rounds. Source: round 9 security audit H-02.

---

## Batch Endpoints Skip Auth (HIGH)

Every batch mutation endpoint MUST accept `request`, enforce auth, verify ownership per item, and run compliance checks. Batch endpoints amplify a single auth gap into bulk data modification.

```python
# DO
async def batch_review(body: BatchReviewRequest, request: Request):
    user = require_auth(request)
    for item in body.items:
        verify_ownership(user, item)

# DO NOT
async def batch_review(body: BatchReviewRequest):
    # no request param = no auth possible
    for item in body.items:
        process(item)  # no auth, no IDOR, no compliance
```

**Why:** `batch_review` had no `request` parameter and could not even access JWT state. Source: round 9 security audit M-01.

---

## Rate Limiter Bounded State (MEDIUM)

Rate limiter `defaultdict(deque(maxlen=60))` limits per-IP entries but the dictionary grows without bound. MUST add periodic eviction of stale IPs.

```python
# DO
_MAX_TRACKED_IPS = 10_000
if len(self._requests) > _MAX_TRACKED_IPS:
    self._evict_stale()

# DO NOT
self._requests = defaultdict(deque(maxlen=60))  # unbounded dict
```

**Why:** Memory exhaustion under IP spray attacks. Source: round 9 security audit M-02.

---

## Error Response Sanitization (MEDIUM)

Production error responses MUST use generic messages. `str(exc)` in responses leaks database schema, connection strings, or file paths. Detailed errors belong in structured logs only.

```python
# DO
except Exception as exc:
    logger.error("route.failed", error=str(exc))
    raise HTTPException(500, "Internal error")

# DO NOT
except Exception as exc:
    raise HTTPException(500, str(exc))  # leaks internals
```

**Why:** Error paths leaked database schema and connection info in API responses. Source: round 9 security audit L-01.

---

## Frontend Mock Data Detection (CRITICAL)

Frontend mock patterns are invisible to Python-side detection but are zero-tolerance Rule 2 violations. Grep frontend code for:

- `MOCK_*`, `FAKE_*`, `PLACEHOLDER_*`, `DUMMY_*`, `SAMPLE_*` constants
- `Math.random()` used for display data
- Hardcoded `met: true` in safety gate conditions
- Static "will appear here" / "coming soon" text in production components

```bash
# Detection command
grep -rn 'MOCK_\|FAKE_\|PLACEHOLDER_\|DUMMY_\|met: true\|will appear' apps/web/
```

**Why:** `PLACEHOLDER_DATA` (zero-filled constant) was used as sole data source for the weekly attention report. Hardcoded `met: true` made safety gates always pass. Source: round 9 frontend audit CRITICAL-1, CRITICAL-2, HIGH-1.

---

## Tool Output Honesty (CRITICAL)

Tool outputs MUST NOT fabricate results. If data is unavailable, return `status: "no_data"` or `None`. Never return zeros with a success status when computation did not occur.

```python
# DO
if not prices:
    return {"status": "no_data", "scenario": scenario}

# DO NOT
return {"returns": 0.0, "status": "computed"}  # fake data as real
```

**Why:** `backtest_scenario` tool discarded real price data and returned hardcoded zeros as "computed". `query_head` returned literal string `"computed_from_z_t"` as prediction value. Source: code quality review C-2, I-7.

---

## Parse Failure Honesty (HIGH)

When LLM returns non-parseable JSON, the result MUST be marked `status: "parse_failed"`. Do NOT fabricate fallback data and present it as a real outcome.

```python
# DO
except json.JSONDecodeError:
    return {"status": "parse_failed", "recommendation": None}

# DO NOT
except json.JSONDecodeError:
    return {"recommendation": "hold", "concession_count": 0}  # fabricated
```

**Why:** Debate agent fabricated fallback with `concession_count: 0` and copied brief confidence, presented as real debate outcome. Source: code quality review I-6.

---

## Silent Exception Swallowing in Data Pipelines (HIGH)

Every `except Exception` in a data pipeline MUST log at WARNING level with context (series name, date, error). Three alt_macro adapters silently swallowed row-level failures.

```python
# DO
except Exception as exc:
    logger.warning("ingest.row_failed", series=series_id, date=date, error=str(exc))
    continue

# DO NOT
except Exception:
    pass  # entire datasets silently lost
```

**Why:** Silent catches in alt_macro and universe adapters lost data with zero signal. Source: code quality review C-3, C-4.

---

## ModelRegistry Exception Logging (HIGH)

`except Exception: return None/[]/False` without logging is equivalent to `except: pass`. Add `logger.error` in all catch blocks.

**Why:** All 7 `except Exception` blocks in ModelRegistry returned empty values without logging. Source: code quality review I-3.

---

## Compliance Rule Completeness (HIGH)

Every rule listed in the compliance spec MUST be present in the rules files. When a spec defines rules, grep the rules files for every rule ID.

Missing from v1: `warn.wide_spread` (microstructure warning), `data.stale_cost_inputs` (blocking), `exec.participation_cap` (blocking).

**Why:** Three spec-required rules were absent from implementation. Source: round 8 red team SC-H9/H10/H11.

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

---

## Frontend Catch Blocks

Frontend `catch` blocks MUST surface an error state to the user (toast, error message). Empty results on error mislead the user into thinking there genuinely are no results.

```typescript
// DO
catch (err) {
  setError("Search failed. Please try again.");
  setResults([]);
}

// DO NOT
catch { setResults([]); }  // user thinks "no results" when actually "request failed"
```

**Why:** `ResearchSearch.tsx` and `ThreadView.tsx` silently swallowed errors with empty results. Source: round 9 frontend audit MINOR-1, MINOR-2.

---

## Security Middleware Wiring

Importing a security library is NOT the same as using it. Every security middleware MUST have a test that verifies it actually blocks requests (not just that the import exists).

**Why:** slowapi `Limiter` was imported for 6+ months but the middleware body was `return await call_next(request)` — a no-op pass-through. Source: journal 0017-DISCOVERY.

---

## TODO Markers in Production Code

TODO markers are zero-tolerance violations. Either implement the feature or raise a typed error when the stub path is hit. A parameter that is accepted and silently ignored gives callers false confidence.

**Why:** Three TODO markers: `lookback_days` accepted but ignored, `_realised_return_for_state` returning NaN, placeholder method body. Source: code quality review C-1.
