# Security Audit Report -- Midas Autonomous Investment Assistant

**Branch:** `zai`
**Date:** 2026-04-16
**Scope:** `src/midas/` (full codebase)
**Reviewer:** security-reviewer

---

## CRITICAL (Must fix before commit)

### C1. No Authentication or Authorization on Any API Endpoint

**Files:**

- `/Users/esperie/repos/training/midas/src/midas/api/routes.py` (all routers, all endpoints)
- `/Users/esperie/repos/training/midas/src/midas/api/app.py` (no auth middleware)

**Description:** Every endpoint across all 10 routers (Health, Pulse, Decisions, Debate, Portfolio, Backtest, Signal, Settings, Compliance, Audit) is completely unauthenticated. The `create_app()` factory in `app.py` adds CORS middleware but no auth middleware. Most critically:

- `POST /api/v1/decisions/{id}/approve` -- approves a financial decision with zero auth
- `POST /api/v1/settings/kill-switch` -- activates the kill switch without auth
- `POST /api/v1/settings/kill-switch/clear` -- clears the kill switch (only checks `body.user_approved`, a trivially spoofable boolean)
- `PUT /api/v1/settings/envelope` -- modifies investment envelope parameters (drawdown ceiling, vol targets, concentration limits) without auth
- `POST /api/v1/debate/threads/{id}/tool-call` -- invokes tools without auth
- `POST /api/v1/backtest/run` -- runs backtests without auth

In a financial application, this is a critical vulnerability. Any network-reachable client can approve trades, modify risk parameters, and clear kill switches.

**Remediation:**

1. Add JWT or API key authentication middleware to the FastAPI app.
2. Require authentication on all non-health endpoints (health/liveness/readiness are the only exceptions).
3. The `clear_kill_switch` endpoint must require re-authentication (not just a boolean in the request body).
4. Add rate limiting on all endpoints.
5. Consider RBAC for sensitive operations (kill switch, envelope changes, trade approval).

---

### C2. Kill Switch Clear Endpoint Accepts Spoofable Approval

**File:** `/Users/esperie/repos/training/midas/src/midas/api/routes.py:337-342`

**Description:**

```python
async def clear_kill_switch(self, body: dict[str, Any]) -> dict[str, Any]:
    user_approved = body.get("user_approved", False)
    if not user_approved:
        raise HTTPException(status_code=400, detail="User approval required")
    return {"status": "cleared", "revert_level": 1}
```

The "user approval" is just a boolean field in the request body. Any attacker can send `{"user_approved": true}` to clear the kill switch. Combined with C1 (no auth), this means an unauthenticated attacker can disable the emergency stop on a live trading system.

**Remediation:** Clearing the kill switch MUST require authenticated user action with re-authentication (e.g., password re-entry or 2FA), not a body parameter.

---

### C3. IBKR OAuth Client Secret Can Be Logged in Error Messages

**File:** `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/ibkr.py:289-292`

**Description:** When the IBKR initial token request fails with a client error (4xx), the response text is included in the error message:

```python
raise AdapterError(
    self.SOURCE_NAME, "oauth2_initial",
    f"client error: HTTP {response.status_code}: {response.text[:200]}",
)
```

IBKR may include the client_id or request parameters in error responses. The same pattern exists at lines 345, 416. These errors are then audited (e.g., `_write_audit` at line 506) and logged, potentially persisting sensitive credential fragments.

**Remediation:** Truncate or sanitize error detail messages before logging/auditing. Do not include raw response bodies in audit records. Use a generic error message for external storage and log the full detail at DEBUG level only.

---

## HIGH (Should fix before merge)

### H1. Silent Error Swallowing in Data Adapters (`except Exception: pass`)

**Files:**

- `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/alt_macro.py:113` -- row write failures silently dropped
- `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/alt_macro.py:222` -- same pattern
- `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/alt_macro.py:373` -- same pattern
- `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/universe.py:256` -- universe member write failures silently dropped

**Description:** These are `except Exception: pass` blocks with zero logging inside data write loops. In a financial application, silently losing macro data or universe membership records can lead to stale or incorrect signals driving trading decisions.

**Remediation:** Add at minimum a `logger.warning(...)` call inside each catch block. Consider accumulating failed row counts and logging a summary after the loop.

---

### H2. Silent Error Swallowing in ML Model Registry

**File:** `/Users/esperie/repos/training/midas/src/midas/ml/__init__.py:73-131`

**Description:** The `ModelRegistry` class has 7 methods that catch `except Exception:` with no logging and return `None`, `[]`, or `False`:

- `get()` returns `None` on failure
- `list_by_pool()` returns `[]`
- `get_champion()` returns `None`
- `get_challengers()` returns `[]`
- `promote()` returns `False`
- `retire()` returns `False`
- `get_lineage()` returns `[]`

In a financial system, silently failing to look up the champion model or failing to promote a new model version could lead to stale models making live trading decisions with no signal to operators.

**Remediation:** Log each failure with `logger.error()` including the exception detail. For `promote()` and `retire()`, consider raising or at least returning a typed error instead of silently returning `False`.

---

### H3. Silent Error Swallowing in NAV Computation

**File:** `/Users/esperie/repos/training/midas/src/midas/attribution/nav.py:34`

**Description:**

```python
except Exception:
    positions = []
```

If the positions query fails, NAV is computed as 0.0 (cash - unsettled). A zero NAV could trigger false drawdown breach alerts, cause the compliance engine to block all trades, or trigger an autonomous demotion. There is no logging of the failure.

**Remediation:** Log the error with `logger.error()`. Consider raising instead of returning a zero-valued NAV, or at minimum record the failure in the audit log.

---

### H4. Silent Error Swallowing in Daily Reconciliation

**File:** `/Users/esperie/repos/training/midas/src/midas/execution/reconciliation.py:85`

**Description:**

```python
except Exception:
    orders = []
```

If the order query fails during daily reconciliation, the reconciliation reports zero orders and zero discrepancies -- a false "all matched" result. This is a serious gap in a financial system where reconciliation is the last line of defense against incorrect fills or missing trades.

**Remediation:** Log the failure and either raise or return a reconciliation result with a clear error status flag (e.g., `{"status": "error", "error": str(exc)}`).

---

### H5. Credential Store Returns Empty on Store Failure

**File:** `/Users/esperie/repos/training/midas/src/midas/fabric/credentials.py:54-56`

**Description:** `CredentialStore.store()` catches exceptions and returns `{}` on failure. The caller cannot distinguish between a successful store that returned an empty dict and a complete failure. The error is logged but the empty return makes it easy for callers to silently continue as if the credential was stored.

Similarly, `retrieve()` returns `None` on failure (line 75), which is indistinguishable from "credential not found". If the database is down, the system may proceed as if no credentials exist.

**Remediation:** Raise a typed exception on store failure. For `retrieve()`, distinguish between "not found" and "database error".

---

### H6. Credential Store `is_expired()` Defaults to `True` on Failure

**File:** `/Users/esperie/repos/training/midas/src/midas/fabric/credentials.py:111`

**Description:** `is_expired()` returns `True` when an exception occurs. This is fail-closed (safe), which is the correct default. However, it does so silently with no logging. Operators have no signal that the expiry check is failing.

**Remediation:** Add `logger.error("credential.expiry_check_failed", ...)` before returning `True`.

---

### H7. No NaN/Inf Checks on Financial Calculations

**Files:**

- `/Users/esperie/repos/training/midas/src/midas/attribution/metrics.py` (multiple methods)
- `/Users/esperie/repos/training/midas/src/midas/attribution/brinson.py:59-68`
- `/Users/esperie/repos/training/midas/src/midas/heads/allocation.py:57-59`

**Description:** The `RiskMetrics` methods can return `float("inf")` (Sortino at line 82, Calmar at line 115) and `float("nan")` (Information Ratio at line 227). The `MVOBaseline.optimize()` at `allocation.py:59` performs `raw_weights / raw_weights.sum()` which produces `nan` or `inf` when weights sum to 0. The `BrinsonDecomposition` accepts numpy arrays without checking for NaN/Inf inputs.

In a financial system, NaN or Inf values flowing into the compliance engine, decision pipeline, or order execution can cause silent corruption or unexpected behavior (NaN comparisons always return False, so compliance checks like `current_drawdown > ceiling` would silently pass when the drawdown is NaN).

**Remediation:**

1. Add `math.isfinite()` checks at the entry points of all financial calculation functions.
2. Return a sensible default (e.g., 0.0 for Sharpe when std is 0) instead of `inf` or `nan`.
3. Validate numpy array inputs for NaN/Inf before computation.
4. Add output validation: if any computed metric is NaN/Inf, log a warning and return a safe default.

---

### H8. Division by Zero in Spread Calculation

**File:** `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/ibkr.py:522`

**Description:**

```python
spread_bps = ((ask - bid) / mid * 10000) if mid else 0.0
```

This is guarded against `mid == 0`, but `mid` could be very close to zero (e.g., a penny stock) producing an enormous spread_bps value that could distort downstream calculations.

**Remediation:** Add a minimum mid threshold (e.g., `if mid < 0.01: spread_bps = 0.0`).

---

### H9. subprocess.run in Changelog Generator

**File:** `/Users/esperie/repos/training/midas/src/midas/release/changelog.py:102-103`

**Description:**

```python
result = subprocess.run(
    ["git", "log", "--oneline", f"{from_ref}..{to_ref}"],
    ...
)
```

The `from_ref` and `to_ref` parameters are passed directly to git as command arguments. If these values come from user input (API call, CLI argument), they could inject arbitrary git arguments. While `subprocess.run` with a list (not `shell=True`) prevents shell injection, a crafted ref like `--exec=malicious_command` could still be interpreted as a git flag.

**Remediation:** Validate `from_ref` and `to_ref` against a strict regex (e.g., `^[a-zA-Z0-9_./-]+$`) before passing to subprocess. Reject any value starting with `-`.

---

### H10. CORS Allows Credentials with Wildcard-Methods

**File:** `/Users/esperie/repos/training/midas/src/midas/api/app.py:64-70`

**Description:**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_credentials=True` combined with `allow_methods=["*"]` and `allow_headers=["*"]` is overly permissive. While the origins are restricted to localhost in development, this configuration must not ship to production. In production, the wildcard methods and headers would allow any cross-origin request with credentials.

**Remediation:**

1. Restrict `allow_methods` to only the methods used (`GET`, `POST`, `PUT`).
2. Restrict `allow_headers` to only the headers needed (e.g., `Authorization`, `Content-Type`).
3. Ensure `cors_origins` is configured per-environment and never includes `*` in production.

---

## MEDIUM (Fix in next iteration)

### M1. Unbounded Rate Limiter Timestamps List

**File:** `/Users/esperie/repos/training/midas/src/midas/execution/rate_limiter.py:21-27`

**Description:**

```python
self._timestamps: list[float] = []
...
self._timestamps = [t for t in self._timestamps if t > cutoff]
```

The timestamps list is pruned on each `acquire()` call but uses a plain `list` rather than `deque(maxlen=N)`. Under high-frequency usage, this list could grow large between prunes. More importantly, `self._timestamps.append(now)` at line 43 happens after the budget check but before any concurrency control, so concurrent calls could exceed the budget.

**Remediation:** Use `collections.deque(maxlen=60)` to bound the collection. Add an asyncio Lock for concurrent safety.

---

### M2. Debug Flag Defaults to True

**File:** `/Users/esperie/repos/training/midas/src/midas/config.py:32`

**Description:**

```python
DEBUG: bool = os.environ.get("DEBUG", "true").lower() in ("true", "1", "yes")
```

The default is `DEBUG=true`. If deployed without setting the environment variable, the application runs in debug mode, which may expose stack traces, disable security features, or enable verbose error messages.

**Remediation:** Default to `false` and require explicit opt-in for debug mode.

---

### M3. Default SQLite Database URL with No Encryption

**File:** `/Users/esperie/repos/training/midas/src/midas/config.py:11`

**Description:**

```python
DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///midas.db")
```

The default database is an unencrypted SQLite file. For a financial application storing credentials, positions, orders, and audit logs, this is a risk if the file is accessible on the host.

**Remediation:** Document that the SQLite default is for development only. Production deployments MUST use PostgreSQL with TLS and proper access controls.

---

### M4. Fernet Key Not Validated Before Use

**File:** `/Users/esperie/repos/training/midas/src/midas/fabric/credentials.py:25`

**Description:** `CredentialStore.__init__` accepts a `fernet_key` string and immediately uses it to construct a `Fernet` instance. While Fernet will raise `ValueError` on an invalid key, the key is not checked for minimum length or entropy. A weak key (or the example key from `.env.example`) would provide no real encryption.

**Remediation:** Add validation that the Fernet key was generated (not hardcoded) and warn if it matches common test/example patterns.

---

### M5. Priority Queue Drain Does Not Propagate Exceptions Correctly

**File:** `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/ibkr.py:218-229`

**Description:** The `_drain_queue` method catches exceptions and stores them in `result`, then calls `event.set()`. But the caller (`_enqueue`) awaits `event.wait()` and then returns... nothing from the result. The exception is silently lost. The caller never sees the stored exception.

**Remediation:** Store the exception in a shared container (e.g., `Future`) and re-raise it in the caller after `event.wait()` returns.

---

### M6. No Request Body Validation on API Endpoints

**File:** `/Users/esperie/repos/training/midas/src/midas/api/routes.py` (multiple endpoints)

**Description:** Multiple endpoints accept `body: dict[str, Any]` without Pydantic model validation:

- `batch_review` (line 142): `body.get("actions", [])` -- no type or length validation
- `create_thread` (line 170): `body.get("decision_id", "")` -- no validation
- `add_message` (line 179): `body.get("content", "")` -- no length limit
- `invoke_tool` (line 184): `body.get("tool_name", "")` -- no allowlist
- `update_envelope` (line 318): `body` passed directly to logger and returned
- `run_backtest` (line 252): `body` accepted with no validation

In a financial application, unvalidated inputs could contain unexpected types, extremely long strings, or malicious payloads that flow into database queries or log entries.

**Remediation:** Define Pydantic models for all request bodies with field types, validators, and length constraints. Add an allowlist for `tool_name` values.

---

### M7. Debate Tool `query_fabric` Allows Arbitrary Table Access

**File:** `/Users/esperie/repos/training/midas/src/midas/agents/tools.py:25-46`

**Description:** `query_fabric(table, filter)` passes an arbitrary `table` string directly to `db.express.list()`. While DataFlow may provide some protection, an LLM agent (or attacker controlling agent input) could query any table in the database, potentially including the `credentials` table.

**Remediation:** Add an allowlist of permitted fabric tables for the debate tools. Reject any table name not in the allowlist.

---

### M8. `update_decision` Tool Allows Arbitrary Field Updates

**File:** `/Users/esperie/repos/training/midas/src/midas/agents/tools.py:300-328`

**Description:** `update_decision(decision_id, updates)` passes an arbitrary `updates` dict directly to `db.express.update()`. This allows modifying any field on a decision record, including potentially sensitive fields like `status`, `approved_by`, or compliance-related fields.

**Remediation:** Define an allowlist of fields that can be updated through this tool. Reject any field not in the allowlist.

---

## LOW (Consider fixing)

### L1. Error Response Bodies May Contain Internal Details

**Files:**

- `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/ibkr.py:289` -- includes response text in error
- `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/ibkr.py:453` -- `str(exc)` in health check response

**Description:** Error responses include internal details that could help an attacker understand the system's internals.

**Remediation:** Return generic error messages to external consumers. Log detailed errors at DEBUG level.

---

### L2. No Security Tests Exist

**Finding:** There are zero test files matching `*security*`, `*injection*`, `*sanitiz*`, or `*auth*` in the `tests/` directory. No dedicated security test coverage exists for:

- Authentication bypass
- Authorization checks
- SQL injection (even though DataFlow is used, defense-in-depth testing is warranted)
- Credential handling
- Input validation
- Kill switch integrity

**Remediation:** Create a `tests/security/` directory with tests covering:

- Auth middleware behavior (unauthenticated request rejection)
- Kill switch clear requires valid auth
- Input validation on all body-accepting endpoints
- Credential store encryption round-trip
- NaN/Inf rejection in financial calculations
- Table name allowlist in debate tools

---

### L3. `preencode_password_special_chars` Does Not Round-Trip with `decode_userinfo_or_raise`

**File:** `/Users/esperie/repos/training/midas/src/midas/utils/url_credentials.py:44-68`

**Description:** The `preencode_password_special_chars` function operates on the already-parsed password (which URL-parsing has already decoded). If the password was `%40` in the raw URL, `urlparse` decodes it to `@`, then `preencode_password_special_chars` re-encodes it to `%40`. This is correct for a fresh URL but could double-encode if called on an already-encoded URL. There is no round-trip test.

**Remediation:** Add a round-trip test: `preencode -> parse -> decode` should be idempotent.

---

### L4. Shadow Lane P&L Uses Placeholder Heuristic

**File:** `/Users/esperie/repos/training/midas/src/midas/shadow/shadow_lane.py:99-107`

**Description:** `get_shadow_pnl` uses `confidence * 0.01` as a placeholder P&L. While this is documented as a heuristic, it could mislead users into believing the shadow performance is real.

**Remediation:** Return a clear `"status": "placeholder"` field and emit a WARN log when this method is called in production.

---

## PASSED CHECKS

### 1. Hardcoded Secrets -- PASS

All API keys, tokens, and secrets are read from `os.environ.get()` via `config.py`. No hardcoded credentials found in any source file. The `.env.example` file uses placeholder values (`sk-your-key-here`, `pplx-your-key-here`). The `.gitignore` correctly excludes `.env`.

### 2. SQL Injection -- PASS

No raw SQL queries found anywhere in the codebase. All database access goes through DataFlow's `db.express` API (`create`, `read`, `list`, `update`, `delete`), which uses parameterized queries internally. No `f"SELECT..."` or string-concatenated SQL patterns detected.

### 3. Command Injection -- PASS

The only `subprocess` usage is in `release/changelog.py` for `git log`, using a list (not `shell=True`). No `os.system`, `os.popen`, `eval()`, or `exec()` on user input. The `eval()` calls in ML code are PyTorch model evaluations (safe).

### 4. Secrets in Logs -- PASS

No passwords, tokens, or API keys are logged. The `CredentialStore` explicitly logs only `service` and `key_name` (metadata), never values. The `FabricCache` uses `_mask_url()` to mask Redis URLs before logging. The mask helper returns `<unparseable redis url>` on failure, which is a distinct sentinel.

### 5. Credential Decode Safety -- PASS

The `url_credentials.py` helper properly rejects null bytes after percent-decoding, following the pattern from `rules/security.md`. All credential decode sites should route through this shared helper.

### 6. URL Credential Masking -- PASS

The `_mask_url()` function in `fabric/cache.py` uses the canonical `scheme://***@host[:port]/path` form and returns `<unparseable redis url>` on failure (distinct from masked output).

### 7. Fernet Encryption at Rest -- PASS

`CredentialStore` uses Fernet symmetric encryption for all stored credentials. Values are encrypted before storage and decrypted on retrieval.

### 8. Compliance Default-Deny -- PASS

The `RulesEngine._evaluate_single()` method treats evaluation exceptions as violations (default-deny). Unknown rules also default to blocked. This is the correct posture for a financial compliance engine.

### 9. Order State Machine Transitions -- PASS

The `OrderStateMachine` uses a strict transition table with terminal states. Invalid transitions raise `ValueError`. Every transition is audited to the `audit_log` table.

### 10. Shadow Lane Isolation -- PASS

`ShadowLane` writes exclusively to the `shadow_decisions` table and never to `decisions` or `orders`. This isolation is enforced at the code level.

### 11. OOD Detection Always On -- PASS

The `OODDetector` produces bounded [0, 1] scores with proper input validation. The `OODResult` dataclass is `frozen=True`.

---

## Summary of Overall Security Posture

**Overall Rating: NEEDS HARDENING before production**

The codebase demonstrates good foundational security practices in several areas:

- All secrets from environment variables (no hardcoded credentials)
- All database access through DataFlow (no raw SQL)
- Fernet encryption for stored credentials
- Compliance engine with default-deny posture
- Audit logging on order state transitions
- Shadow lane isolation

However, there are critical gaps that must be addressed before this system can safely handle real money:

| Category                     | Critical | High  | Medium | Low   | Passed |
| ---------------------------- | -------- | ----- | ------ | ----- | ------ |
| Authentication/Authorization | 2        | 0     | 0      | 0     | 0      |
| Error Handling               | 0        | 6     | 0      | 1     | 2      |
| Input Validation             | 0        | 0     | 3      | 1     | 2      |
| Data Integrity               | 0        | 2     | 1      | 0     | 1      |
| Credential Safety            | 1        | 0     | 1      | 0     | 3      |
| Observability                | 0        | 0     | 0      | 0     | 2      |
| **Total**                    | **3**    | **8** | **5**  | **2** | **10** |

**Priority order for remediation:**

1. Add authentication middleware to all API endpoints (C1, C2)
2. Sanitize error messages before logging/auditing (C3)
3. Fix all silent `except Exception: pass` blocks (H1-H4)
4. Add NaN/Inf guards to financial calculations (H7)
5. Add Pydantic request body validation (M6)
6. Add table and field allowlists to debate tools (M7, M8)
7. Create security test suite (L2)
