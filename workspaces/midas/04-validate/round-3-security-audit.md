# Security Audit Report — Midas Project

**Date:** 2026-04-18
**Auditor:** Security Review Agent
**Scope:** `src/midas/` — API auth, CORS, kill switch, SQL injection, hardcoded secrets, code execution

---

## Executive Summary

| Category | Status |
|----------|--------|
| SQL Injection | PASSED |
| Hardcoded Secrets | PASSED |
| CORS Configuration | PASSED |
| Kill Switch | PASSED |
| Code Execution | PASSED |
| XSS | PASSED |
| Auth Middleware | **1 MEDIUM finding** |

---

## Findings

### MEDIUM — Auth Bypass on approve/decline When JWT_SECRET Not Set

**File:** `src/midas/api/routes.py` (lines 303–369)

**Description:**
The `approve` and `decline` endpoints check `auth_required = bool(os.environ.get("JWT_SECRET", ""))` before enforcing authentication. When `JWT_SECRET` is not set:

1. `verify_jwt_or_pass()` in `app.py` returns `None` (dev mode bypass)
2. `request.state.user` is never set
3. `user = getattr(request.state, "user", None)` returns `None`
4. `auth_required = False` (because `JWT_SECRET` is not set)
5. The condition `if auth_required and not user` evaluates to `False` and auth is skipped
6. The ownership check `if user:` on lines 320 and 354 is also skipped because `user` is `None`

**Result:** Any unauthenticated requester can approve or decline any decision when `JWT_SECRET` is not configured.

**Code path:**
```python
# routes.py:303-327
async def approve(self, decision_id: str, request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    auth_required = bool(os.environ.get("JWT_SECRET", ""))  # False if not set
    if auth_required and not user:  # skipped when JWT_SECRET absent
        raise HTTPException(status_code=401, detail="Authentication required")
    ...
    if user:  # skipped when user is None
        owner_id = decision.get("user_id", "")
        if owner_id and owner_id != user.get("sub"):
            raise HTTPException(status_code=403, ...)
```

**Remediation:**
Either enforce auth on these endpoints regardless of `JWT_SECRET`, or require an explicit "auth disabled" configuration flag that is never present in production:

```python
# Option A: Always require auth on approve/decline
auth_required = True  # Do not check JWT_SECRET for sensitive ops

# Option B: Explicit dev-only flag
dev_mode = bool(os.environ.get("MIDAS_DEV_MODE", ""))
if dev_mode:
    # Allow bypass only in dev, not in production
    pass
```

**Severity:** MEDIUM — Production exposure only if `JWT_SECRET` is accidentally unset. However, this is a defense-in-depth failure: sensitive operations should never be skippable based solely on an env-var check that could be forgotten.

---

## PASSED Checks

### 1. JWT Authentication (`src/midas/api/auth.py`)

| Check | Status |
|-------|--------|
| `hmac.compare_digest` for token comparison | PASS — Line 71 for SHA256 fallback |
| bcrypt used when available | PASS — Lines 52–58 |
| `decode_access_token` raises HTTPException on failure | PASS — Lines 366–372 |
| JWT secret from environment | PASS — Line 38 |
| No hardcoded secrets | PASS |

**Details:**
- bcrypt password hashing (primary path, lines 52–58)
- `hmac.compare_digest` used in SHA256 fallback (line 71)
- `jwt.ExpiredSignatureError` and `jwt.InvalidTokenError` caught and raised as HTTPException 401

### 2. IDOR Check in approve/decline

| Check | Status |
|-------|--------|
| Decision ownership verified before approve | PASS — routes.py:319–326 |
| Decision ownership verified before decline | PASS — routes.py:353–360 |

**Details:**
Both endpoints verify `owner_id != user.get("sub")` and return 403 if not authorized. However, these checks are bypassed when `user` is `None` (see MEDIUM finding above).

### 3. SQL Injection Prevention

| Check | Status |
|-------|--------|
| No raw SQL f-strings | PASS — 0 matches |
| All DB calls through DataFlow express | PASS — `db.express.list/create/update` used |
| No string concatenation in SQL | PASS |

### 4. Hardcoded Secrets

| Check | Status |
|-------|--------|
| No hardcoded passwords | PASS — 0 matches |
| No hardcoded API keys | PASS — 0 matches |
| Secrets from environment variables | PASS |

### 5. CORS Configuration (`src/midas/api/app.py`)

| Check | Status |
|-------|--------|
| No `allow_origins=["*"]` | PASS |
| Explicit origins configured | PASS — Lines 69–72 |
| `allow_credentials=True` with explicit origins | PASS |
| `allow_methods` limited | PASS — Line 84 |
| `allow_headers` limited | PASS — Line 85 |

**Details:**
CORS is configured with explicit localhost origins in development and allows credentials. The `allow_headers` list is restrictive (`Authorization`, `Content-Type`, `X-Request-ID`).

### 6. Kill Switch (`src/midas/compliance/kill_switch.py`)

| Check | Status |
|-------|--------|
| Requires user approval to clear | PASS — Line 138 |
| Uses `hmac.compare_digest` for confirmation code | PASS — Lines 143–144 |
| State-of-world brief required | PASS — Lines 154–162 |
| Process lock enforced | PASS — `KillSwitchProcessLock` |
| Audit logging on activate/clear | PASS — Lines 80–94, 175–190 |

**Details:**
The kill switch uses `hmac.compare_digest` for constant-time comparison of confirmation codes, requires explicit `user_approved=True`, and enforces process-lock acknowledgment of the state brief.

### 7. Code Execution — No eval/exec/shell=True

| Check | Status |
|-------|--------|
| No `eval()` | PASS — 0 matches |
| No `exec()` | PASS — 0 matches |
| No `shell=True` | PASS — 0 matches |

### 8. XSS Prevention

| Check | Status |
|-------|--------|
| No `innerHTML` usage | PASS — 0 matches |
| No `dangerouslySetInnerHTML` | PASS — 0 matches |

---

## Recommendations

1. **MEDIUM:** Add explicit auth enforcement for `approve`/`decline` endpoints — do not allow bypass when `JWT_SECRET` is unset. Consider requiring a separate `MIDAS_DEV_MODE=true` flag to explicitly enable dev-mode bypass, making it impossible to accidentally deploy without auth.

2. **LOW:** Add `httponly` and `secure` flags to session cookie handling if web UI is added in the future.

3. **LOW:** Consider adding rate limiting to the `/auth/login` endpoint to mitigate brute-force attacks (the framework supports this through Nexus middleware).

---

## Files Reviewed

| File | Key Security Checks |
|------|---------------------|
| `src/midas/api/auth.py` | JWT creation, decoding, password hashing, token comparison |
| `src/midas/api/app.py` | CORS, middleware auth flow, legacy API key fallback |
| `src/midas/api/routes.py` | approve/decline ownership, kill-switch endpoints |
| `src/midas/compliance/kill_switch.py` | Confirmation code, user approval, process lock |
| SQL injection grep | 0 raw SQL f-strings |
| Secrets grep | 0 hardcoded secrets |
| eval/exec grep | 0 dangerous patterns |
