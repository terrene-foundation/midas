# Red Team Round 10 Report — 2026-04-22

**Branch:** `worktree-mm-claude`
**Scope:** Full spec compliance + security + test coverage + value audit
**Previous Round:** Round 9 (2026-04-20)

---

## Convergence Status

| Criterion             | Result                                 |
| --------------------- | -------------------------------------- |
| 0 CRITICAL            | FAIL — 1 found                         |
| 0 HIGH                | FAIL — 4 found                         |
| 2 clean rounds        | NO — new findings this round           |
| Spec compliance       | PASS (minor docstring mismatch only)   |
| New code has tests    | PARTIAL — 2 adapter modules lack tests |
| Frontend: 0 mock data | PASS — no MOCK*/FAKE*/DUMMY\_ found    |

**Convergence: NO**

---

## CRITICAL Findings

### CR-1: No Onboarding Frontend

**Severity:** CRITICAL
**Category:** Value / UX
**Finding:** Backend `OnboardingRouter` exists (4-step state machine) but no frontend wizard drives it. Users land in empty shell.

**Impact:** New Singapore investor sees "No positions" / "No pending decisions" with no path to configure brokerage, risk profile, or paper trading.

**Spec:** Spec 02 (Value Chain front office), Spec 09 (7 surfaces — onboarding wizard)

**Resolution:** Build frontend onboarding wizard that sequences through OnboardingRouter states.

**Status:** OPEN

---

## HIGH Findings

### H-1: Backtest Panels Empty

**Severity:** HIGH
**Category:** Value
**Finding:** `RegimeBreakdown` and `SubHorizonConsistency` receive hardcoded empty arrays (`periods={}`, `horizons={}`). Headline metrics compute from real data but regime drill-down panels are blank.

**Impact:** Singapore investor cannot validate historical strategy performance across market regimes.

**Spec:** Spec 09 §9.2, Spec 11

**Resolution:** Wire panels with real regime segmentation data, or remove if out of v1 scope.

**Status:** OPEN

---

### H-2: Debate Agent Single-Turn

**Severity:** HIGH
**Category:** Value
**Finding:** `DebateAgent` runs one LLM call without live portfolio context injection. Frontend has polished multi-turn UI with InlineVisualization and 10 MCP tools, but backend doesn't inject positions, weights, or regime state.

**Impact:** "Why am I holding 15% NVDA?" gets generic LLM response, not portfolio-grounded analysis.

**Spec:** Spec 07 §3.5, Spec 07 §3.6

**Resolution:** Inject live portfolio positions, weights, and regime state into DebateAgent context before each turn.

**Status:** OPEN

---

### H-3: EODHD Adapter Zero Test Coverage

**Severity:** HIGH
**Category:** Testing
**Finding:** `EODHDAdapter` (primary price source per spec 03 §2.1) has zero test imports in entire test directory.

**Impact:** Any refactor breaking EODHD ingestion won't be caught. Stale/missing price data could propagate to all downstream models.

**Verification:**

```bash
grep -rl "from midas.fabric.adapters.eodhd\|EODHDAdapter" tests/
# No matches found
```

**Resolution:** Add Tier 2 integration test for EODHD adapter.

**Status:** OPEN

---

### H-4: Yahoo Finance Adapter Zero Test Coverage

**Severity:** HIGH
**Category:** Testing
**Finding:** `YahooFinanceAdapter` (fallback/cross-check per spec 03) has zero test imports in entire test directory.

**Impact:** Cross-check mechanism for data quality validation has no test coverage.

**Verification:**

```bash
grep -rl "from midas.fabric.adapters.yahoo\|YahooFinanceAdapter" tests/
# No matches found
```

**Resolution:** Add Tier 2 integration test for Yahoo adapter.

**Status:** OPEN

---

## Security Audit: PASS

Full security audit found **0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW** security vulnerabilities.

| Check                 | Result                                         |
| --------------------- | ---------------------------------------------- |
| Hardcoded secrets     | PASS — all from environment                    |
| Subprocess validation | PASS — git ref allowlist regex in changelog.py |
| eval/exec             | PASS — only PyTorch model.eval()               |
| Error message leakage | PASS — truncated to 200 chars                  |
| JWT auth              | PASS — wired in app.py with re-auth tokens     |
| Kill switch           | PASS — process-lock clear flow                 |
| Fernet encryption     | PASS — credentials.py                          |
| Rate limiter          | PASS — bounded deque                           |

---

## Spec Compliance: PASS

All 14 spec files verified. Minor docstring mismatch in `blocking_rules.py` (says "19 rules" on line 1, "21 rules" on line 14 — implementation is 21, correct).

Core systems verified:

- 22 fabric table models (all specified tables present)
- 37 compliance rules (21 blocking + 7 escalation + 9 warning)
- L0-L4 autonomy ladder with correct transitions
- RegimeRenderer with continuous `a_t` attention axis
- DebateAgent with non-sycophancy in system prompt
- QuoteMovedDialog with regime-adaptive thresholds (0.5/0.3/0.2/0.1%)
- KillSwitch with process-lock clear flow

---

## Test Coverage: PARTIAL

- 1820 tests collected
- 57 security tests pass (auth, kill switch, URL credentials)
- 80 cost model/credentials/PLAF tests pass
- 2 adapter modules lack ANY test coverage: EODHDAdapter, YahooFinanceAdapter

---

## What Improved Since Round 9

1. **PLACEHOLDER_DATA removed** — AttentionReport now queries `/pulse/attention/weekly` for real data
2. **$50,000 hardcoded multiplier removed** — DecisionCard uses `brief?.dollar_impact` from API
3. **Paper-to-live placeholder gates fixed** — Now queries subsystem health and fetches real paper trading reports
4. **blocking_rules docstring** — Minor mismatch flagged (doc only, not blocking)

---

## Journal Entries Created

| ID   | Type     | Topic                            |
| ---- | -------- | -------------------------------- |
| 0021 | CRITICAL | No onboarding frontend           |
| 0022 | HIGH     | Backtest panels empty            |
| 0023 | HIGH     | Debate agent single-turn         |
| 0024 | HIGH     | EODHD adapter zero test coverage |
| 0025 | HIGH     | Yahoo adapter zero test coverage |

---

## Recommendation

**NOT READY TO COMMIT.** The 4 HIGH findings (backtest empty, debate single-turn, 2 zero-coverage adapters) and 1 CRITICAL (no onboarding) are implementation gaps, not code quality regressions. They're also front-end heavy.

Two paths forward:

1. **Fix now** — onboard the frontend wizard + wire debate context + add adapter tests
2. **Ship backend only** — commit the backend (which is solid), track frontend gaps as v1.1

The backend is hard. The frontend is what a Singapore investor actually sees.
