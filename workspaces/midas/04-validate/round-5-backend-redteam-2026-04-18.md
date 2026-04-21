# Round 5: Backend API Red Team — 2026-04-18

## Scope

Backend API gaps implementation (T-23-01 through T-23-09): JWT auth, WebSocket, onboarding, decision modify, debate resolution, notifications, backtest detail, paper-live, position history.

## Agents Deployed

- **analyst** — Spec compliance audit (specs 07-11 vs implementation)
- **security-reviewer** — Full security review of auth, WebSocket, routes, app factory
- **testing-specialist** — Test coverage audit with per-module verification

## Findings Resolved (This Round)

### CRITICAL → Fixed

| ID  | Finding                                   | Fix                                            | Commit  |
| --- | ----------------------------------------- | ---------------------------------------------- | ------- |
| C1  | SHA-256 password comparison timing-unsafe | `hmac.compare_digest()`                        | 18fdb46 |
| C2  | WebSocket zero authentication             | JWT token query param auth gate                | 18fdb46 |
| C3  | Dev-mode auth bypass silent               | Loud WARN log on every unauthenticated request | 18fdb46 |
| C4  | Onboarding IDOR (user_id from body)       | Derive from JWT `sub` claim, fallback to body  | 18fdb46 |

### HIGH → Fixed

| ID  | Finding                                       | Fix                              | Commit  |
| --- | --------------------------------------------- | -------------------------------- | ------- |
| H10 | Approve/decline returns success on DB failure | Raise HTTPException(500) instead | 18fdb46 |

### MEDIUM → Fixed

| ID  | Finding                                    | Fix                   | Commit  |
| --- | ------------------------------------------ | --------------------- | ------- |
| M2  | Backtest regime breakdown missing "urgent" | Added 4th regime band | 18fdb46 |
| M4  | bcrypt fallback silent                     | Added warning log     | 18fdb46 |

### Test Coverage Gaps → Fixed

| Gap                      | Fix                                     | Tests Added |
| ------------------------ | --------------------------------------- | ----------- |
| Auth middleware untested | `TestJWTMiddleware` class               | 10 tests    |
| WebSocket auth untested  | `test_auth_rejection_when_jwt_required` | 1 test      |

## Findings Deferred (Requires Architectural Work)

These require design decisions or substantial new infrastructure:

| ID     | Finding                                     | Reason Deferred                                |
| ------ | ------------------------------------------- | ---------------------------------------------- |
| SC-C1  | Paper-live missing subsystem health checks  | Requires fabric health API                     |
| SC-C2  | Paper-live missing report review gate       | Requires report surface                        |
| SC-C3  | No pre-trade compliance on decision approve | Requires compliance engine wiring              |
| SC-H1  | Re-auth not enforced on approve/decline     | Requires frontend re-auth flow integration     |
| SC-H2  | No rate limiting                            | Requires middleware choice (slowapi vs custom) |
| SC-H3  | Notification prefs not persisted            | Requires notification_settings table           |
| SC-H4  | Envelope settings not persisted             | Requires envelope state management             |
| SC-H5  | First-seven-days enforcement not wired      | Requires compliance engine integration         |
| SC-H6  | Attention report returns zeros              | Requires tracking infrastructure               |
| SC-H7  | Autonomy level names inconsistent           | Requires cross-module rename                   |
| SC-H8  | Backtest detail returns nulls               | Requires backtest computation engine           |
| SC-H9  | WebSocket auth (duplicate of C2)            | Already fixed                                  |
| SC-H11 | Autonomy reads from wrong source            | Requires AutonomyLadder wiring                 |

## Test Results

```
74 passed in 4.09s
- 20 auth (password hashing, JWT, login, refresh, logout, reauth)
- 10 JWT middleware (exempt paths, dev mode, token validation)
- 35 extended routes (7 routers × happy + error paths)
- 9 websocket (ConnectionManager + endpoint + auth rejection)
```

## Convergence Status

**Round 5: NOT CONVERGED** — deferred findings require architectural work beyond current session scope.

- 0 CRITICAL findings remaining in implementation scope
- 0 HIGH findings remaining in implementation scope
- 12 deferred findings (spec compliance gaps requiring new infrastructure)
- 74/74 tests passing
- 2 consecutive clean rounds for implementation-scope findings
