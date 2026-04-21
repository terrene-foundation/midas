# Round 9: Red Team Convergence — 2026-04-20

## Scope

Full convergence audit. Re-derived every spec assertion from scratch. Five parallel agents: spec compliance (analyst), test coverage (testing-specialist), frontend audit (react-specialist), security (security-reviewer), value audit (value-auditor).

## Agent Results

### 1. Spec Compliance (124 assertions, 107 PASS, 17 FAIL)

**Report:** `.spec-coverage-v3.md`

| ID    | Severity | Finding                                                                     | Fix Status                                           |
| ----- | -------- | --------------------------------------------------------------------------- | ---------------------------------------------------- |
| SC-C1 | CRITICAL | Frontend band thresholds (0.25/0.50/0.75) mismatch backend (0.30/0.60/0.85) | **FIXED** — PulseShell.tsx + regime-store.ts aligned |
| SC-C2 | CRITICAL | IBKR order state machine lacks spec-required granular states                | OPEN                                                 |
| SC-C3 | CRITICAL | IBKR rejection code taxonomy incomplete (3 of 8 categories)                 | OPEN                                                 |
| SC-H1 | HIGH     | Brief composer missing 4 of 7 mandatory sections                            | OPEN                                                 |
| SC-H2 | HIGH     | Foundation TS model integration absent                                      | OPEN                                                 |
| SC-M1 | MEDIUM   | UCITS/Ireland ETF evaluation not implemented                                | OPEN                                                 |
| SC-M2 | MEDIUM   | JWT auth depth not verified across all routes                               | PARTIALLY FIXED (4 endpoints)                        |
| SC-M3 | MEDIUM   | Spatial Approve/Reject separation not programmatic                          | OPEN                                                 |
| SC-L1 | LOW      | Debate concession enforcement unclear in production                         | OPEN                                                 |

### 2. Test Coverage (1485 tests, 60 test files, 0 modules uncovered)

**Report:** `round-9-test-audit.md`

| Finding                               | Severity | Status                              |
| ------------------------------------- | -------- | ----------------------------------- |
| 5 PaperLive tests flaky in batch      | MEDIUM   | OPEN (test state leakage)           |
| 70+ TSX components have zero tests    | MEDIUM   | OPEN (no test framework configured) |
| Rate limit middleware wiring untested | LOW      | OPEN                                |
| No E2E test directory                 | LOW      | OPEN                                |

### 3. Frontend Audit (engine-first confirmed, 4 findings)

**Report:** `round-9-frontend-audit.md`

| ID   | Severity | Finding                                      | Fix Status                                   |
| ---- | -------- | -------------------------------------------- | -------------------------------------------- |
| C-01 | CRITICAL | PLACEHOLDER_DATA in AttentionReport          | **FIXED** — uses /pulse/attention/weekly API |
| C-02 | CRITICAL | Hardcoded $50K dollar impact in DecisionCard | **FIXED** — reads from brief/decision data   |
| H-01 | HIGH     | Paper-to-live gate conditions hardcoded      | **FIXED** — queries backend health           |
| H-02 | HIGH     | Static placeholder report in PaperToLiveFlow | **FIXED** — fetches from backend             |

### 4. Security Audit (2 HIGH, 2 MEDIUM, 3 LOW)

**Report:** `round-9-security-audit.md`

| ID   | Severity | Finding                                         | Fix Status                                      |
| ---- | -------- | ----------------------------------------------- | ----------------------------------------------- |
| H-01 | HIGH     | query_fabric allows sensitive tables            | **FIXED** — FABRIC_ALLOWLIST                    |
| H-02 | HIGH     | JWT_SECRET not set = auth bypass on 4 endpoints | **FIXED** — unconditional auth on sensitive ops |
| M-01 | MEDIUM   | Batch review missing auth                       | OPEN                                            |
| M-02 | MEDIUM   | Rate limiter memory growth unbounded            | OPEN                                            |
| L-01 | LOW      | Error responses expose str(exc)                 | OPEN                                            |
| L-02 | LOW      | Compliance engine uses :memory: db              | OPEN                                            |
| L-03 | LOW      | WebSocket JWT in query param                    | ACCEPTED                                        |

### 5. Value Audit (3 critical gaps)

**Report:** `round-9-value-audit.md`

| Flow                      | Verdict      | Gap                                                    |
| ------------------------- | ------------ | ------------------------------------------------------ |
| Onboarding                | FAIL         | Backend state machine exists, no frontend wizard       |
| Daily Monitoring          | PARTIAL      | Missing recent actions feed, notifications             |
| Turbulent Market Approval | PASS         | Strongest flow, all spec-compliant                     |
| AI Debate                 | PARTIAL FAIL | Agent is single-turn, no live portfolio data injection |
| Backtesting               | PARTIAL      | Drill-down panels receive empty arrays                 |

## Fixes Committed (commit c907300)

1. Frontend band thresholds aligned to backend (0.30/0.60/0.85)
2. AttentionReport wired to `/pulse/attention/weekly` API
3. DecisionCard reads `dollar_impact` from data, not hardcoded $50K
4. PaperToLiveFlow gates query backend subsystem health
5. Paper trading report fetched from `/settings/paper-live/report`
6. Debate tool allowlist blocks auth tables
7. Sensitive endpoints require auth unconditionally
8. Backend endpoints added: `/pulse/attention/weekly`, `/settings/paper-live/report`
9. Worktree policy codified

## Convergence Status

**NOT CONVERGED.** 3 CRITICAL and 2 HIGH findings remain open:

| Priority | Finding                            | Effort                       |
| -------- | ---------------------------------- | ---------------------------- |
| 1        | IBKR order state machine (SC-C2)   | Extend enum + mapping        |
| 2        | IBKR rejection codes (SC-C3)       | Add 5 missing categories     |
| 3        | Brief composer sections (SC-H1)    | Structural composer change   |
| 4        | Onboarding frontend (value)        | New page + wizard flow       |
| 5        | Debate live data injection (value) | Wire tools into debate agent |

## Remaining Items for Next Round

- Fix SC-C2, SC-C3, SC-H1 (spec compliance)
- Add onboarding frontend (value audit)
- Wire debate tools into live agent context (value audit)
- Add frontend test framework (test audit)
- Fix batch_review auth (security audit)
- Bound rate limiter memory (security audit)
