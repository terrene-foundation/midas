# Security Audit Report -- Midas Project, Round 9

**Date:** 2026-04-20
**Auditor:** Security Review Agent (Round 9 Convergence)
**Scope:** `src/midas/` (API, auth, compliance, kill switch, scheduler, agents, execution), `apps/web/` (frontend)
**Baseline:** Round 3 security audit (2026-04-18)

---

## Executive Summary

| Category                           | Status       | Findings         |
| ---------------------------------- | ------------ | ---------------- |
| Secrets / Credential Handling      | PASSED       | 0                |
| SQL Injection                      | PASSED       | 0                |
| Code Execution (eval/exec)         | PASSED       | 0                |
| XSS (Frontend)                     | PASSED       | 0                |
| JWT Auth Implementation            | PASSED       | 0                |
| Kill Switch Security               | PASSED       | 0                |
| Compliance Rules Coverage          | PASSED       | 0                |
| Rate Limiting                      | PASSED       | 0                |
| WebSocket Auth                     | PASSED       | 0                |
| LLM Agent Tools                    | **1 HIGH**   | H-01             |
| Auth Bypass on Sensitive Endpoints | **1 HIGH**   | H-02             |
| Batch Review Missing Auth          | **1 MEDIUM** | M-01             |
| Rate Limiter Memory Growth         | **1 MEDIUM** | M-02             |
| Error Messages Leak Internals      | **3 LOW**    | L-01, L-02, L-03 |

**Verdict:** 2 HIGH, 2 MEDIUM, 3 LOW. No CRITICAL findings. The two HIGH findings are related to the previously identified auth bypass pattern, now expanded to cover additional endpoints and a new tool-level data access concern.

---

## HIGH Findings

### H-01: `query_fabric` Tool Allows Access to Sensitive Tables (users, sessions, credentials)

**File:** `src/midas/agents/tools.py:25-46`
**Severity:** HIGH
**Category:** Broken Access Control / Data Exposure

**Description:**
The `query_fabric` tool (Tool 1) accepts an arbitrary `table` parameter and passes it directly to `self._db.express.list(table, filter=filter)`. There is no allowlist or blocklist on which tables can be queried. Since the fabric database contains tables `users` (with `password_hash`), `sessions` (with `refresh_token_hash`), and `credentials` (with `encrypted_value`), the LLM agent or any caller of the debate `/tool-call` endpoint can read these tables and extract authentication secrets.

The tool is exposed via the `POST /api/v1/debate/threads/{thread_id}/tool-call` endpoint with `tool_name="query_fabric"`, which accepts `table` and `filter` from the request body and passes them through without validation.

**Attack vector:**

```json
POST /api/v1/debate/threads/1/tool-call
{
  "tool_name": "query_fabric",
  "table": "users",
  "filter": {}
}
```

Returns all rows from the `users` table, including `password_hash`.

**Fix:**
Add an explicit allowlist of tables that the `query_fabric` tool may access, excluding all authentication and credential tables:

```python
# In DebateTools.__init__:
FABRIC_ALLOWLIST = {
    "prices", "corporate_actions", "fundamentals", "filings", "news",
    "macro", "alt_data", "features", "embeddings", "latent_state",
    "positions", "orders", "decisions", "shadow_decisions", "model_registry",
    "universe_changelog", "audit_log", "quotes", "fills", "fills_synthetic",
    "fee_schedule", "cost_attribution", "sweep_history",
}

async def query_fabric(self, table: str, filter: dict) -> list[dict]:
    if table not in self.FABRIC_ALLOWLIST:
        raise ValueError(f"Table '{table}' is not queryable via this tool")
    ...
```

---

### H-02: Sensitive Endpoints Skippable When JWT_SECRET Not Set (Defense-in-Depth Failure)

**File:** `src/midas/api/routes.py:353-421` (approve), `src/midas/api/routes.py:423-468` (decline), `src/midas/api/routes_extended.py:172-234` (modify), `src/midas/api/routes_extended.py:249-320` (resolve)
**Severity:** HIGH
**Category:** Broken Access Control (Defense-in-Depth)

**Description:**
This is the same finding from Round 3 (previously MEDIUM), now escalated to HIGH because the pattern has propagated to additional endpoints since the prior audit. The pattern `auth_required = bool(os.environ.get("JWT_SECRET", ""))` appears in four separate endpoint handlers:

1. `DecisionsRouter.approve` (routes.py:357)
2. `DecisionsRouter.decline` (routes.py:427)
3. `DecisionModifyRouter.modify_decision` (routes_extended.py:177)
4. `DebateResolutionRouter.resolve` (routes_extended.py:254)

When `JWT_SECRET` is not set (misconfiguration, deployment error, or intentional dev-mode), all authentication and authorization checks on these sensitive endpoints are completely bypassed. Any unauthenticated requester can approve, decline, modify, or resolve any decision. The ownership (IDOR) checks are also skipped because `user` is `None`.

**Fix:**
Sensitive operations should require authentication unconditionally. The dev-mode bypass should only apply to read-only or non-destructive endpoints. Add a centralized function:

```python
# In auth.py:
def require_auth(request: Request) -> dict[str, Any]:
    """Require authentication for sensitive operations. Raises 401 if not authenticated."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
```

Then use `require_auth(request)` in all sensitive endpoints instead of the `auth_required` / `user` pattern.

---

## MEDIUM Findings

### M-01: Batch Review Endpoint Missing Auth and Compliance Checks

**File:** `src/midas/api/routes.py:528-554`
**Severity:** MEDIUM
**Category:** Broken Access Control / Missing Compliance Gate

**Description:**
The `batch_review` endpoint (`POST /api/v1/decisions/batch-review`) accepts a list of `{decision_id, verdict}` pairs and applies them in bulk. Unlike the individual `approve` and `decline` endpoints, `batch_review` has:

1. **No authentication check** -- does not check `request.state.user` or `auth_required` at all
2. **No ownership (IDOR) verification** -- does not check that the user owns the decisions
3. **No re-authentication gate** -- does not require `X-Reauth-Token`
4. **No pre-trade compliance check** -- skips the compliance engine that the individual `approve` endpoint runs (SC-C3)

The function signature is `async def batch_review(self, body: dict[str, Any])` with no `request: Request` parameter, so it cannot even access the JWT user state.

**Fix:**
Add `request: Request` parameter, enforce auth, verify ownership for each decision, and run compliance checks:

```python
async def batch_review(self, request: Request, body: dict[str, Any]) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    auth_required = bool(os.environ.get("JWT_SECRET", ""))
    if auth_required and not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    # ... add ownership checks and compliance per item
```

---

### M-02: Rate Limiter State Grows Unbounded Per Unique IP

**File:** `src/midas/api/app.py:47-51`
**Severity:** MEDIUM
**Category:** Denial of Service (Resource Exhaustion)

**Description:**
The per-IP rate limiter stores a `deque` for each unique client IP in the module-level `_ip_timestamps` dictionary. The dictionary uses `defaultdict(deque(maxlen=60))`, which limits each individual IP to 60 entries, but the dictionary itself grows without bound as new IPs appear. An attacker making requests from many different IPs (botnet, IP rotation) can cause unbounded memory growth.

This is a known pattern (auth middleware check A6 from the security checklist): rate limiter state must be bounded with periodic eviction.

**Fix:**
Add periodic eviction of stale IP entries:

```python
import time

_MAX_TRACKED_IPS = 10_000

def _evict_stale_ips():
    """Remove IPs with no recent activity."""
    if len(_ip_timestamps) > _MAX_TRACKED_IPS:
        now = time.monotonic()
        cutoff = now - _RATE_LIMIT_WINDOW_SECS
        stale = [ip for ip, ts in _ip_timestamps.items() if not ts or ts[-1] < cutoff]
        for ip in stale:
            del _ip_timestamps[ip]
```

Call `_evict_stale_ips()` periodically (e.g., every 100 requests or on a timer).

---

## LOW Findings

### L-01: Error Responses Expose Internal Exception Messages

**File:** `src/midas/api/routes_extended.py:383`, `src/midas/agents/tools.py:383`, and multiple locations
**Severity:** LOW
**Category:** Information Disclosure

**Description:**
Several error paths return `str(exc)` in error responses or log messages that could leak internal implementation details (database schema, connection strings, file paths) to API consumers. For example:

- `tools.py:383`: `return {"decision_id": decision_id, "status": "error", "error": str(exc)}`
- `routes_extended.py:383`: Returns `str(exc)` in 500 responses

Production error responses should use generic messages (PR5 from the production readiness checklist).

**Fix:** Replace `str(exc)` with generic error messages in API responses. Keep the detailed error in structured logs only.

---

### L-02: Compliance Engine Uses In-Memory Database for Pre-Trade Checks

**File:** `src/midas/api/routes.py:35`
**Severity:** LOW
**Category:** Reliability / Logic Error

**Description:**
The compliance engine is initialized with `DataFlow(":memory:")`:

```python
_compliance_engine = RulesEngine(DataFlow(":memory:"))
```

Pre-trade compliance checks on the `approve` endpoint query this in-memory database, which is separate from the production fabric database. This means compliance rules are not reading from the persisted compliance_rules table -- they are using whatever was registered at startup via `create_blocking_rules()`. Runtime updates to compliance rules via the `ComplianceRouter.create_rule` and `ComplianceRouter.update_rule` endpoints will NOT be reflected in pre-trade checks.

**Fix:** Either (a) construct the compliance engine with the real fabric database, or (b) document that compliance rule changes require a server restart to take effect in pre-trade checks.

---

### L-03: WebSocket JWT Token in Query Parameter

**File:** `src/midas/api/websocket.py:76`
**Severity:** LOW
**Category:** Credentials in URL (auth middleware check A4)

**Description:**
The WebSocket authentication reads the JWT token from the query parameter `?token=xxx`:

```python
token = ws.query_params.get("token", "")
```

Query parameters appear in server logs, proxy logs, and browser history. This is a known pattern (A4 from the auth middleware checklist): API keys/tokens in query params leak to logs.

**Mitigation note:** This is largely unavoidable for WebSocket connections since browsers cannot set custom headers during the WebSocket handshake. The risk is low for short-lived JWT tokens (24h expiry) but should be documented as accepted.

---

## PASSED Checks

### 1. Secrets / Credential Handling

| Check                                    | Status | Detail                                             |
| ---------------------------------------- | ------ | -------------------------------------------------- |
| No hardcoded API keys or passwords       | PASS   | All secrets from `os.environ.get()`                |
| `.env` in `.gitignore`                   | PASS   | Line 26: `.env`                                    |
| `.env` is a template (no real keys)      | PASS   | All values commented out with placeholder text     |
| Secrets not logged                       | PASS   | `structlog` usage never logs password/token values |
| Fernet encryption for stored credentials | PASS   | `credentials.py` uses `cryptography.fernet.Fernet` |
| Credential metadata-only listing         | PASS   | `list_services()` returns no encrypted values      |

### 2. SQL Injection Prevention

| Check                                | Status | Detail                                     |
| ------------------------------------ | ------ | ------------------------------------------ |
| All DB access through DataFlow ORM   | PASS   | No raw SQL in application code             |
| No f-string SQL construction         | PASS   | Grep confirmed no `f"SELECT` etc.          |
| `subprocess` only in release tooling | PASS   | `release/changelog.py` only                |
| No `eval()` / `exec()` in app code   | PASS   | `model.eval()` is PyTorch, not Python eval |

### 3. Authentication / JWT

| Check                                      | Status | Detail                             |
| ------------------------------------------ | ------ | ---------------------------------- |
| JWT secret from environment                | PASS   | `os.environ.get("JWT_SECRET")`     |
| bcrypt password hashing (primary)          | PASS   | Lines 52-58 in auth.py             |
| PBKDF2 fallback uses `hmac.compare_digest` | PASS   | Line 76 in auth.py                 |
| Refresh token rotation                     | PASS   | Old token revoked, new pair issued |
| Concurrent session detection               | PASS   | Suspicious session revokes all     |
| Re-auth token with 5-min expiry            | PASS   | Separate `type: "reauth"` claim    |
| JWT expiry enforcement                     | PASS   | `jwt.ExpiredSignatureError` caught |

### 4. Kill Switch Security

| Check                                    | Status | Detail                                            |
| ---------------------------------------- | ------ | ------------------------------------------------- |
| Confirmation code with SHA-256 hash      | PASS   | `hashlib.sha256` + `hmac.compare_digest`          |
| Confirmation code persisted in audit_log | PASS   | Cross-worker validation supported                 |
| Process lock enforcement                 | PASS   | `KillSwitchProcessLock` with brief acknowledgment |
| Auto-trip wired in scheduler             | PASS   | `kill_switch_auto_trip` job every 5 minutes       |
| Auto-trip conditions from spec           | PASS   | Drawdown, OOD+NAV, IBKR error, PACT breach        |
| Clear reverts to L1 autonomy             | PASS   | `revert_level: 1` in clear response               |

### 5. Compliance Rules

| Check                            | Status | Detail                                   |
| -------------------------------- | ------ | ---------------------------------------- |
| 21 blocking rules implemented    | PASS   | All spec-required rules present          |
| 9 warning rules implemented      | PASS   | All spec-required rules present          |
| Kill switch rule present         | PASS   | Rule 10: `state.kill_switch`             |
| Participation cap rule present   | PASS   | Rule 21: `exec.participation_cap`        |
| Paper trading block rule present | PASS   | Rule 11: `state.paper_trading`           |
| IBKR rules present               | PASS   | Rules 17-19: health, rate limit, session |

### 6. Rate Limiting

| Check                                  | Status | Detail                        |
| -------------------------------------- | ------ | ----------------------------- |
| Per-IP sliding window (60/min)         | PASS   | `app.py` middleware           |
| X-RateLimit-Remaining header           | PASS   | Set in response               |
| WebSocket connection cap (100/channel) | PASS   | `MAX_CONNECTIONS_PER_CHANNEL` |

### 7. CORS

| Check                          | Status | Detail                                               |
| ------------------------------ | ------ | ---------------------------------------------------- |
| Restricted origins             | PASS   | localhost only by default                            |
| Credentials allowed explicitly | PASS   | `allow_credentials=True`                             |
| Limited headers                | PASS   | `Authorization`, `Content-Type`, `X-Request-ID` only |

### 8. Frontend (XSS)

| Check                        | Status | Detail                     |
| ---------------------------- | ------ | -------------------------- |
| No `dangerouslySetInnerHTML` | PASS   | Grep returned zero matches |
| No `innerHTML`               | PASS   | Grep returned zero matches |

### 9. LLM Agent Tools

| Check                          | Status | Detail                     |
| ------------------------------ | ------ | -------------------------- |
| Tools are data-only operations | PASS   | No decision logic in tools |
| No `eval()` on tool outputs    | PASS   |                            |
| Tool name allowlist on invoke  | PASS   | 10-tool dispatch map       |

### 10. Paper-to-Live Transition

| Check                                  | Status | Detail                     |
| -------------------------------------- | ------ | -------------------------- |
| 14-day paper period enforced           | PASS   | Date comparison check      |
| User + biometric confirmation required | PASS   | Both must be `True`        |
| Kill switch blocks transition          | PASS   | Active kill switch checked |
| Subsystem health gate                  | PASS   | PaperTradingReport check   |
| Report review gate                     | PASS   | `report_reviewed` required |
| Autonomy resets to L1                  | PASS   | Uses `LEVEL_NAMES[1]`      |

---

## Comparison with Prior Rounds

| Finding                                              | Round 3 Status | Round 9 Status       | Change                                       |
| ---------------------------------------------------- | -------------- | -------------------- | -------------------------------------------- |
| Auth bypass on approve/decline when JWT_SECRET unset | MEDIUM         | **H-02 (escalated)** | Escalated: pattern now in 4 endpoints, not 2 |
| SQL injection                                        | PASSED         | PASSED               | Stable                                       |
| Hardcoded secrets                                    | PASSED         | PASSED               | Stable                                       |
| Kill switch security                                 | PASSED         | PASSED               | Stable                                       |
| CORS configuration                                   | PASSED         | PASSED               | Stable                                       |
| `query_fabric` table access                          | Not found      | **H-01 (new)**       | New: tool has no table allowlist             |
| `batch_review` auth                                  | Not found      | **M-01 (new)**       | New: endpoint missing auth entirely          |
| Rate limiter memory                                  | Not found      | **M-02 (new)**       | New: unbounded IP tracking                   |
| Error message leaking                                | Not found      | **L-01 (new)**       | New: `str(exc)` in API responses             |
| Compliance engine :memory:                           | Not found      | **L-02 (new)**       | New: stale compliance state                  |
| WebSocket query token                                | Not found      | **L-03 (new)**       | New: accepted risk documented                |

**Summary:** The Round 3 MEDIUM finding (auth bypass) has not been fixed and has expanded to two additional endpoints, warranting escalation to HIGH. Three new findings result from the expanded codebase (routes_extended.py was not present in Round 3). The core security infrastructure (JWT, kill switch, compliance, DataFlow) remains solid.
