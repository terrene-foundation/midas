# Wave 1 — Make It Usable

GAP-1 (Onboarding Frontend, CRITICAL) + Adapter Test Coverage + Backtest Engine Fix

**Session estimate:** 1 session (parallelizable across 3 agents)
**Spec anchors:** 02 (value chain), 03 (data fabric), 09 (surfaces), 12 (performance), 14 (IBKR)

---

## GROUP A: Onboarding Frontend (GAP-1)

### BUILD Todos

**B1. Build OnboardingStatus query hooks**

- Create `apps/web/lib/queries/useOnboarding.ts` with typed hooks: `useOnboardingStatus()` (GET), `useConnectBrokerage()` (mutation), `useSetRiskProfile()` (mutation), `useSetUniverseConstraints()` (mutation), `useActivate()` (mutation).
- Add `OnboardingStatus`, `OnboardingStep` types to `apps/web/lib/types.ts`.
- Each mutation invalidates `["onboarding"]` query key on success.
- **Spec:** 09 S2 (onboarding wizard), backend `OnboardingRouter` API contract
- **LOC:** ~60 load-bearing
- **Invariants:** (1) Every mutation invalidates `["onboarding"]` on success. (2) Types match backend shapes (`"connect" | "risk" | "universe" | "activate" | "done"`). (3) Errors are `ApiError` from `api-client.ts`.
- **Dependencies:** None — foundational

**B2. Build OnboardingWizard multi-step component**

- Create `apps/web/elements/onboarding/OnboardingWizard.tsx` as client component. Owns step state machine, renders correct step, handles transitions. Uses `useOnboardingStatus()` to init from server state (resume on refresh). Includes progress bar. Forward-only transitions matching backend.
- **Spec:** 09 S2, 02 (front office onboarding)
- **LOC:** ~80 load-bearing
- **Invariants:** (1) Mount reads server step from `useOnboardingStatus()`. (2) Forward transitions only on successful mutation. (3) "done" triggers `router.replace("/pulse")` after 3s. (4) No back button — matches backend state machine.
- **Dependencies:** B1

**B3. Build ConnectBrokerageStep element**

- Create `apps/web/elements/onboarding/ConnectBrokerageStep.tsx`. Uses `useConnectBrokerage()` mutation. IBKR auth explanatory copy, connection reference input (text field), validation (non-empty), loading state, error display. 44px primary gold button.
- **Spec:** 14 (brokerage connection), 09
- **LOC:** ~50 load-bearing
- **Invariants:** (1) Button disabled when empty or in-flight. (2) Error from API displayed in red banner with exact message. (3) Touch target ≥ 48px.
- **Dependencies:** B1

**B4. Build RiskProfileStep element**

- Create `apps/web/elements/onboarding/RiskProfileStep.tsx`. Uses `useSetRiskProfile()` mutation. Four numeric inputs: vol_target_low, vol_target_high, drawdown_ceiling, concentration_cap. Client validation mirrors backend: vol_low > 0, vol_high > vol_low, dd in [0.05, 0.30], cap in [0.01, 0.50]. Inline errors. Mono numerals for financial figures.
- **Spec:** 11 (risk parameters), backend `set_risk_profile` validation
- **LOC:** ~70 load-bearing
- **Invariants:** (1) vol_low positive and < vol_high. (2) dd_ceiling [0.05, 0.30]. (3) conc_cap [0.01, 0.50]. (4) All valid before submit enables. (5) Display percentages ×100, submit decimals.
- **Dependencies:** B1

**B5. Build UniverseConstraintsStep element**

- Create `apps/web/elements/onboarding/UniverseConstraintsStep.tsx`. Uses `useSetUniverseConstraints()` mutation. Comma-separated ticker input, optional. Parse: split, trim, filter empty, uppercase, deduplicate.
- **Spec:** 03 (universe constraints), backend `set_universe_constraints`
- **LOC:** ~40 load-bearing
- **Invariants:** (1) Empty input valid (no exclusions). (2) All tickers uppercased. (3) Duplicates removed.
- **Dependencies:** B1

**B6. Build ActivateStep element**

- Create `apps/web/elements/onboarding/ActivateStep.tsx`. Uses `useActivate()` mutation. Summary of configured items. 3-second dwell on activate button (matches kill-switch pattern). On success: "done" state showing paper mode + link to `/pulse`.
- **Spec:** 08 S2.1 (activation gate), 10 S3 (confirm before act)
- **LOC:** ~70 load-bearing
- **Invariants:** (1) Button disabled 3s after render. (2) Response `{ mode: "paper" }` displayed. (3) Auto-redirect to `/pulse` after 3s.
- **Dependencies:** B1

**B7. Build OnboardingLoadingSkeleton**

- Create `apps/web/elements/onboarding/OnboardingLoadingSkeleton.tsx`. Shimmer skeleton matching wizard layout: progress bar, card body, button. Used while `useOnboardingStatus()` loads.
- **LOC:** ~20 presentational
- **Dependencies:** None

**B8. Refactor onboarding page.tsx**

- Replace current monolithic `apps/web/app/(shell)/onboarding/page.tsx` with thin shell (< 15 lines) importing `OnboardingWizard`. Ensure React Query provider available.
- **LOC:** ~15
- **Dependencies:** B2, B3, B4, B5, B6, B7

**B9. Build onboarding elements index.tsx**

- Create `apps/web/elements/onboarding/index.tsx` barrel export for all onboarding elements.
- **LOC:** ~10
- **Dependencies:** B3-B7

### WIRE Todos

**W1. Wire OnboardingGuard to React Query status**

- Replace raw `api.get()` in `OnboardingGuard.tsx` with `useOnboardingStatus()`. Show full-page loading skeleton while checking. On `activated: true` render children; on `false` redirect to `/onboarding`; on 401 let auth middleware handle.
- **Verification:** (1) No onboarding → redirect to `/onboarding`. (2) Completed → access to `/pulse`. (3) Refresh after onboarding → no flash (cached query). (4) 401 → auth middleware takes over.
- **Dependencies:** B1, B7

**W2. Wire OnboardingWizard steps to real API**

- Each step calls mutation hook on submit. `onSuccess` advances wizard AND invalidates `["onboarding"]`. Error responses (400 validation, 409 ordering) display exact `detail` message.
- **Verification:** (1) Empty connection_ref → error. (2) vol_low ≥ vol_high → validation error. (3) Risk before connect → 409. (4) All 4 steps complete → status `activated: true`. (5) Visit `/pulse` → no redirect.
- **Dependencies:** B1-B6

**W3. Wire onboarding completion into PulseShell**

- After onboarding, verify PulseShell renders with real data. Confirm OnboardingGuard in shell layout works with new React Query approach. Verify regime layout transitions work for new user.
- **Verification:** (1) Complete onboarding → land on `/pulse`. (2) PulseShell Calm layout renders. (3) Sidebar navigable. (4) AttentionBudgetGauge renders.
- **Dependencies:** W1, W2, B8

---

## GROUP B: Adapter Test Coverage

**Note:** Existing tests at `tests/fabric/test_adapter_eodhd.py` (12 tests) and `tests/fabric/test_adapter_yahoo.py` (10 tests) use mock HTTP responses with real SQLite DataFlow. These are Tier 1. The journals claimed "zero test imports" but tests exist — the gap is missing edge cases and Tier 2 coverage.

### EODHD Adapter Tests

**T1. Build EODHD rate-limit and retry tests**

- Test `_retry` under 429 and 500 responses. `RateLimitExceeded` handling, `Retry-After` header, retry exhaustion raising `AdapterError`, success on second attempt, auth failures propagating immediately.
- **File:** `tests/fabric/test_adapter_eodhd.py` (extend)
- **Tier:** 1
- **Dependencies:** Existing `started_db` fixture

**T2. Build EODHD fetch_news pagination test**

- Test pagination with limit=150 and 100-item pages: two requests, offset incrementing, final result capped at limit, stops on partial page.
- **File:** `tests/fabric/test_adapter_eodhd.py` (extend)
- **Tier:** 1

**T3. Build EODHD fetch_fundamentals multi-period test**

- Test 3 annual periods → 3 rows in fundamentals table, most recent period returned as result dict, ROE computation correct.
- **File:** `tests/fabric/test_adapter_eodhd.py` (extend)
- **Tier:** 1

**T4. Build EODHD observability contract tests**

- Verify structured log output: `fetch_prices.start`, `fetch_prices.complete`, `fetch_prices.failed`, `audit.written`. Use `caplog`.
- **File:** `tests/fabric/test_adapter_eodhd.py` (extend)
- **Tier:** 1

**T5. Build EODHD corporate_actions edge cases test**

- Decimal split ratio, missing splitRatio field, zero-value dividends, empty actions DataFrame.
- **File:** `tests/fabric/test_adapter_eodhd.py` (extend)
- **Tier:** 1

### Yahoo Adapter Tests

**T6. Build Yahoo cross-check missing data test**

- Test cross_check when Yahoo empty but EODHD present, vice versa, both empty. `discrepancy_pct` None, `flagged` False. `cross_check.incomplete` log emitted.
- **File:** `tests/fabric/test_adapter_yahoo.py` (extend)
- **Tier:** 1

**T7. Build Yahoo fundamentals computed fields test**

- Test `de_ratio` and `roe` computation. Edge cases: zero bookValue (no ZeroDivisionError), missing fields, correct computation with valid inputs.
- **File:** `tests/fabric/test_adapter_yahoo.py` (extend)
- **Tier:** 1

**T8. Build Yahoo fetch_news no-ticker test**

- Test `fetch_news(ticker="")` returns `[]` immediately, no API calls, no audit row. `fetch_news.no_ticker_skip` log emitted.
- **File:** `tests/fabric/test_adapter_yahoo.py` (extend)
- **Tier:** 1

**T9. Build Yahoo corporate actions same-date test**

- Test single date with both dividend and stock split → 2 separate rows (DIVIDEND + SPLIT), same `period_end`.
- **File:** `tests/fabric/test_adapter_yahoo.py` (extend)
- **Tier:** 1

**T10. Build Yahoo observability contract tests**

- Verify structured logs: start/complete for fetch_prices, discrepancy/consistent for cross_check, empty for empty download.
- **File:** `tests/fabric/test_adapter_yahoo.py` (extend)
- **Tier:** 1

### Adapter Regression Tests

**R1. Regression: EODHD auth failure writes audit row**

- Verify 401 on any adapter operation → `audit_log` table has row with `action="FAILURE"` and `rule_name`.
- **File:** `tests/regression/test_issue_eodhd_auth_audit.py` (new)

**R2. Regression: Yahoo cross-check flags above threshold**

- Verify prices differing > configured threshold → `result["flagged"] == True` + audit entry.
- **File:** `tests/regression/test_issue_yahoo_crosscheck_threshold.py` (new)

---

## GROUP C: Backtest Engine + Weight Fix

**Current state:** `BacktestRouter.get_results()` (routes.py:1012-1053) hardcodes `regime_breakdown: []` and `metrics: {}`. No `/backtest/{run_id}/regime-breakdown` or `/consistency` endpoints exist. No backtest engine computes real return series.

### BUILD Todos

**F11. Build BacktestEngine producing regime-segmented return series**

- Create `src/midas/backtest/engine.py` with `BacktestEngine` class. Takes weights, prices (fabric), regime labels (latent_state). Computes: daily portfolio returns `sum(w_i * r_i)`, regime-segmented metrics (return, Sharpe, max DD per segment), sub-horizon consistency (monthly/quarterly/annual positive fractions), headline metrics (CAGR, Sharpe, Calmar, max DD, turnover, win rate), equity curve.
- **Spec:** 09 S9.2 (drill-down panels), 12 (Brinson attribution)
- **LOC:** ~300 load-bearing
- **Invariants:** (1) Uses provided weights, never hardcoded constant. (2) Regime segments use latent_state timestamps. (3) All metrics match `RiskMetrics` computations. (4) Empty data → graceful empty results (no crash).
- **Dependencies:** None
- **3 sentences:** Produces real portfolio return series from actual weights and price data instead of fixed 0.1. Segments returns by regime period for the drill-down panels that currently show blank. Computes all headline metrics the spec requires (CAGR, Sharpe, Calmar, DD, turnover, win rate).

**F12. Wire BacktestRouter to BacktestEngine output**

- Modify `BacktestRouter.get_results()` to load prices + regime labels + weights, call `BacktestEngine.compute()`, return real data. Add `/backtest/{run_id}/regime-breakdown` and `/backtest/{run_id}/consistency` endpoints.
- **Spec:** 09 S9.2
- **LOC:** ~120 load-bearing
- **Dependencies:** F11

### TEST Todos

**T13. Build BacktestEngine unit tests**

- Tier 1: known prices + weights → correct returns, CAGR, Sharpe, max DD. Regime segmentation: all-one-regime, flips-every-bar, single-bar, missing labels. Weight sensitivity: different weights → different CAGR.
- **File:** `tests/unit/test_backtest_engine.py` (new)
- **Dependencies:** F11

**T14. Build BacktestRouter API integration tests**

- Tier 2: real FastAPI test client + real SQLite DataFlow. Seed data, call endpoints, verify non-empty metrics, regime_breakdown, sub_horizons, equity_curve. Verify new endpoints return correct shapes.
- **File:** `tests/integration/test_backtest_api.py` (new)
- **Dependencies:** F11, F12

### Regression Tests

**R3. Regression: BacktestRouter must not return empty regime_breakdown**

- With seeded price + regime data: `response["regime_breakdown"]` is non-empty list with correct keys.
- **File:** `tests/regression/test_issue_backtest_empty_panels.py` (new)

**R4. Regression: BacktestEngine uses provided weights not hardcoded**

- Two engines with [0.8, 0.2] vs [0.2, 0.8] on asymmetric returns → different CAGR.
- **File:** `tests/regression/test_issue_fixed_backtest_weight.py` (new)

---

## Execution Order

Group A (onboarding) and Group B (adapter tests) are fully independent — run in parallel.

Group C (backtest) is independent of both — can also run in parallel.

All three groups complete within Wave 1. Recommended agent assignment:

- Agent 1 (react-specialist): B1-B9, W1-W3
- Agent 2 (testing-specialist): T1-T10, R1-R2
- Agent 3 (pattern-expert): F11, F12, T13, T14, R3-R4
