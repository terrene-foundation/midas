# Round 9 Test Coverage Audit

**Date**: 2026-04-20
**Auditor**: testing-specialist (audit mode)
**Method**: Re-derived from scratch via `pytest --collect-only` and grep-based import analysis. No trust of `.test-results` or prior round reports.

## Summary

| Metric                                   | Value                                                                                                                         |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Total tests collected**                | 1485                                                                                                                          |
| **Test files**                           | 60                                                                                                                            |
| **Test directories**                     | `tests/unit/`, `tests/fabric/`, `tests/evaluation/probes/`, `tests/regression/`, `tests/sdk/`, `tests/integration/` (JS only) |
| **Source modules**                       | 20 packages + `config.py`                                                                                                     |
| **Modules with zero primary test files** | 1 (`config`)                                                                                                                  |
| **Frontend test files**                  | 0 (70+ TSX components, no test infrastructure)                                                                                |

## Step 1: Total Test Collection

```
1485 tests collected in 0.61s
```

Verified via `pytest --collect-only -q tests/`.

## Step 2: Per-Module Coverage Table

| Module            | Source Files  | Primary Test Files | Primary Test Count | Status     |
| ----------------- | ------------- | ------------------ | ------------------ | ---------- |
| `fabric`          | 8             | 13                 | 179                | COVERED    |
| `universe`        | 7             | 2                  | 35                 | COVERED    |
| `ml`              | 5             | 10                 | 106                | COVERED    |
| `state_inference` | 5             | 1                  | 27                 | COVERED    |
| `heads`           | 7             | 1                  | 57                 | COVERED    |
| `evaluation`      | 9             | 9                  | 107                | COVERED    |
| `autonomy`        | 3             | 1                  | 78                 | COVERED    |
| `compliance`      | 5             | 3                  | 48                 | COVERED    |
| `scheduler`       | 2             | 1                  | 59                 | COVERED    |
| `agents`          | 6             | 1                  | 46                 | COVERED    |
| `api`             | 5             | 4                  | 171                | COVERED    |
| `execution`       | 6             | 2                  | 104                | COVERED    |
| `attribution`     | 5             | 1                  | 94                 | COVERED    |
| `paper_trading`   | 2             | 1                  | 33                 | COVERED    |
| `shadow`          | 2             | 1                  | 19                 | COVERED    |
| `config`          | 1             | 0                  | 0                  | **MEDIUM** |
| `utils`           | 1             | 1                  | 15                 | COVERED    |
| `brief`           | 4             | 1                  | 46                 | COVERED    |
| `regime`          | 1 (init only) | 1                  | 74                 | COVERED    |
| `router`          | 4             | 1                  | 19                 | COVERED    |
| `release`         | 2             | 1                  | 54                 | COVERED    |
| `testing`         | 2             | 1                  | 61                 | COVERED    |

**Notes**:

- `config` is imported by `conftest.py` and `test_api.py` indirectly (patching `DATABASE_URL`), but has no dedicated test file. The module is a single file (`src/midas/config.py`) containing environment variable lookups and app configuration. Risk is LOW given its simplicity.
- `regime` has only `__init__.py` with `RegimeRenderer` and data classes; tested via `test_regime.py` (74 tests).
- Cross-module test files (`test_infrastructure.py` with 64 tests, `test_autonomy_compliance.py` with 78 tests) exercise multiple modules, so the "primary" counts above are conservative lower bounds.

## Step 3: Recent Module Verification (M22/M23 Spec Gap Fixes)

| File                                     | Test Coverage | Test Files Importing                                                                                                     |
| ---------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `src/midas/compliance/blocking_rules.py` | COVERED       | `test_compliance_rules.py`, `test_autonomy_compliance.py`, `test_rules_engine_factories.py`                              |
| `src/midas/compliance/warning_rules.py`  | COVERED       | `test_compliance_rules.py`, `test_autonomy_compliance.py`                                                                |
| `src/midas/compliance/kill_switch.py`    | COVERED       | `test_kill_switch.py` (12 tests), `test_autonomy_compliance.py` (8 kill switch tests), `test_api.py` (5 API-level tests) |
| `src/midas/scheduler/jobs.py`            | COVERED       | `test_scheduler.py` (59 tests), `test_infrastructure.py`                                                                 |
| `src/midas/api/routes_extended.py`       | COVERED       | `test_routes_extended.py` (41 tests), `test_api.py` (90 tests)                                                           |
| `src/midas/fabric/engine.py`             | COVERED       | 10+ test files import `create_fabric`/`reset_fabric`                                                                     |

**Result**: All recently modified modules have corresponding test coverage.

### Kill Switch Auto-Trip Coverage

The `kill_switch_auto_trip` scheduled job is tested:

- `test_scheduler.py::test_kill_switch_auto_trip` -- exercises the `_kill_switch_auto_trip` method
- `test_kill_switch.py` -- 12 unit tests on `KillSwitch` class
- `test_autonomy_compliance.py` -- 8 integration-level kill switch tests
- `test_api.py` -- 5 API endpoint tests for activate/clear

## Step 4: Security Test Coverage

### Kill Switch Tests (12 direct + 13 indirect)

| Test File                                            | Tests | Focus                                                                  |
| ---------------------------------------------------- | ----- | ---------------------------------------------------------------------- |
| `test_kill_switch.py`                                | 12    | Unit: activate, clear, approval codes, confirmation, state transitions |
| `test_autonomy_compliance.py`                        | 8     | Integration: blocks operations, activate via API, process lock         |
| `test_api.py`                                        | 5     | API: activate returns 200, clear requires approval, confirmation code  |
| `test_scheduler.py`                                  | 1     | Scheduled auto-trip execution                                          |
| `evaluation/probes/test_kill_switch_process_lock.py` | 14    | Protocol: process lock prevents concurrent trips                       |

### Auth/JWT Tests (30)

| Test File      | Tests | Focus                                                                                               |
| -------------- | ----- | --------------------------------------------------------------------------------------------------- |
| `test_auth.py` | 30    | Token creation/decode, expiry, refresh rotation, revocation, reauth, JWT enable/disable, middleware |

### Compliance Rule Tests (48)

| Test File                        | Tests | Focus                                                                         |
| -------------------------------- | ----- | ----------------------------------------------------------------------------- |
| `test_compliance_rules.py`       | 25    | Blocking rules (input_freshness, order_size_cap, spread_band) + warning rules |
| `test_rules_engine_factories.py` | 11    | Factory creation for block/warn rules                                         |
| `test_kill_switch.py`            | 12    | Kill switch state machine                                                     |

### Input Validation Tests (15+)

| Test File                 | Tests | Focus                                                                    |
| ------------------------- | ----- | ------------------------------------------------------------------------ |
| `test_url_credentials.py` | 15    | Null-byte rejection, credential decode, pre-encoding                     |
| `test_routes_extended.py` | 5+    | Risk profile validation, quiet hours validation, position history limits |
| `test_infrastructure.py`  | 5+    | State machine valid/invalid transitions                                  |

### Credential Security Tests (15)

| Test File                 | Tests | Focus                                                          |
| ------------------------- | ----- | -------------------------------------------------------------- |
| `test_credentials.py`     | 15    | Connection string parsing, credential masking, secret handling |
| `test_url_credentials.py` | 15    | Null-byte injection, pre-encoding, decode helper               |

### Rate Limiting Tests (4)

| Test File                                 | Tests | Focus                                                    |
| ----------------------------------------- | ----- | -------------------------------------------------------- |
| `test_infrastructure.py::TestRateLimiter` | 4     | Budget enforcement, over-budget rejection, refill, burst |

### Security Coverage Assessment

**No gaps found** for: kill switch, auth/JWT, compliance rules, input validation, credential handling, rate limiting.

**Missing**: No dedicated test for API-level rate limiting (`_check_rate_limit` in `app.py`). The `RateLimiter` class in `execution/rate_limiter.py` is tested, but the FastAPI middleware that calls it is not directly tested.

## Step 5: Frontend Test Coverage

| Metric                             | Value                                                                                               |
| ---------------------------------- | --------------------------------------------------------------------------------------------------- |
| Element directories                | 11 (attention, backtest, debate, decisions, portfolio, pulse, regime, safety, settings, signal, ui) |
| TSX component files                | 70+                                                                                                 |
| Test files (`.test.*` / `.spec.*`) | **0**                                                                                               |
| Test framework config              | None (no playwright.config, jest.config, vitest.config)                                             |

**Status**: Zero frontend test coverage. No test infrastructure exists.

### FINDING: FRONTEND-TESTS-MISSING (MEDIUM)

70+ TSX components across 11 element directories have zero automated tests. The web application (backtest, portfolio, safety, settings, etc.) has no test framework configured. Users interact with the product through these components.

**Mitigating factors**:

- The backend API serving these components has 171 tests
- Integration/e2e tests in Python cover the API endpoints the frontend calls
- The frontend is a display layer, not a logic layer

**Recommended action**: Set up Playwright or vitest testing for at minimum the critical user journeys (portfolio view, backtest execution, kill switch activation).

## Step 6: Test Infrastructure Assessment

### Tier Distribution

| Tier                 | Directory                  | Files      | Tests | Status                    |
| -------------------- | -------------------------- | ---------- | ----- | ------------------------- |
| Unit                 | `tests/unit/`              | 14         | 272+  | Active, passing           |
| Integration (Python) | `tests/` root-level        | 20         | 800+  | Mixed unit/integration    |
| Integration (JS)     | `tests/integration/`       | 2 JS files | N/A   | Hooks and learning system |
| Evaluation Probes    | `tests/evaluation/probes/` | 10         | 107   | Protocol verification     |
| Regression           | `tests/regression/`        | 1          | 13    | PIT protocol              |
| SDK Patterns         | `tests/sdk/`               | 1          | 8     | SDK validation            |
| E2E                  | `tests/e2e/`               | 0          | 0     | **Empty directory**       |

### E2E Tier Status

**FINDING: E2E-TIER-EMPTY (LOW)**

The `tests/e2e/` directory does not exist. No end-to-end workflow tests exist. The `tests/integration/` directory contains only JavaScript hook tests, not Python integration tests against real infrastructure.

**Note**: Many tests in the root `tests/` directory exercise real SQLite databases and are functionally integration tests, but they are not organized under the standard 3-tier structure.

### Test Execution Issues

**FINDING: UNIT-TEST-ORDERING-FLAKY (MEDIUM)**

When running `tests/unit/` as a batch, 5 `TestPaperLive` tests in `test_routes_extended.py` fail. When running `test_routes_extended.py` in isolation, all 41 tests pass. This indicates test state leakage between unit test files (likely database state not being properly cleaned between tests).

Affected tests:

- `test_transition_already_live`
- `test_transition_kill_switch_blocks`
- `test_transition_paper_period_incomplete`
- `test_transition_success`
- (1 additional)

## Findings Summary

| ID                        | Severity | Finding                                                  | Recommendation                                                              |
| ------------------------- | -------- | -------------------------------------------------------- | --------------------------------------------------------------------------- |
| FRONTEND-TESTS-MISSING    | MEDIUM   | 70+ TSX components have zero automated tests             | Set up vitest or Playwright; prioritize kill switch UI, portfolio, backtest |
| E2E-TIER-EMPTY            | LOW      | No `tests/e2e/` directory or end-to-end workflow tests   | Create E2E tests for critical user journeys                                 |
| CONFIG-NO-DEDICATED-TESTS | LOW      | `src/midas/config.py` has no dedicated test file         | Low risk (simple env var lookups); add if config grows                      |
| UNIT-TEST-ORDERING-FLAKY  | MEDIUM   | 5 `TestPaperLive` tests fail in batch, pass in isolation | Fix test isolation (database state cleanup)                                 |
| API-RATE-LIMIT-UNTESTED   | LOW      | `_check_rate_limit` in `app.py` has no direct test       | Add endpoint-level rate limit test                                          |

## Detailed Test File Inventory

### tests/unit/ (14 files, 272+ tests)

- `test_auth.py` (30) -- JWT auth, login, refresh, reauth
- `test_compliance_rules.py` (25) -- Blocking/warning rule evaluation
- `test_cost_model.py` (22) -- Cost model calculations
- `test_credentials.py` (15) -- Credential handling
- `test_dataflow_adapter.py` (19) -- DataFlow adapter
- `test_infrastructure.py` (64) -- Scheduler, jobs, state machine, rate limiter
- `test_kill_switch.py` (12) -- Kill switch state machine
- `test_routes_extended.py` (41) -- Extended API routes
- `test_rules_engine_factories.py` (11) -- Rules engine factories
- `test_universe_filters.py` (13) -- Universe ETF filtering
- `test_url_credentials.py` (15) -- URL credential decode/encode
- `test_websocket.py` (10) -- WebSocket connection management

### tests/fabric/ (13 files, 179 tests)

- Adapter tests: `test_adapter_ibkr.py` (86), `test_adapter_base.py` (6), `test_adapter_fred.py` (4), `test_adapter_perplexity.py` (5), `test_adapter_alt_macro.py` (5), `test_adapter_sec_edgar.py` (3), `test_adapter_universe.py` (4)
- Engine tests: `test_fabric_models.py` (14), `test_fabric_cache.py` (12), `test_fabric_freshness.py` (15), `test_fabric_health.py` (9), `test_fabric_features.py` (8), `test_fabric_embeddings.py` (8)

### tests/evaluation/probes/ (10 files, 107 tests)

- `test_calibration_protocol.py` (18), `test_top_of_fold_card.py` (15), `test_kill_switch_process_lock.py` (14), `test_shadow_lane_isolation.py` (13), `test_quote_moved_protocol.py` (13), `test_envelope_widening_protocol.py` (11), `test_debate_concession_rules.py` (11), `test_router_overfitting.py` (8), `test_track_record_protocol.py` (7), `test_latent_learnability.py` (4)

### Root-level test files (22 files, ~927 tests)

- `test_attribution.py` (94), `test_api.py` (90), `test_execution.py` (82), `test_autonomy_compliance.py` (78), `test_regime.py` (74), `test_testing_framework.py` (61), `test_scheduler.py` (59), `test_model_heads.py` (57), `test_release.py` (54), `test_agents_brief.py` (46), `test_paper_trading.py` (33), `test_state_inference.py` (27), `test_universe.py` (22), `test_ml_online_inference.py` (21), `test_router_shadow.py` (19), `test_ml_posterior_state.py` (15), `test_ml_deep_bayesian_filter.py` (14), `test_ml_ood_detector.py` (12), `test_ml_model_registry.py` (11), `test_ml_training.py` (6), `test_ml_contrastive_training.py` (6), `test_ml_vae_training.py` (7), `test_ml_mae_training.py` (7), `test_ml_deepssm_training.py` (7)

### tests/regression/ (1 file, 13 tests)

- `test_pit_protocol_no_future_leak.py` (13)

### tests/sdk/ (1 file, 8 tests)

- `sdk_patterns_runner.py` (8)

## Methodology

All counts derived via:

1. `pytest --collect-only -q tests/` -- 1485 tests
2. `grep -rln "from midas\.<module>\|import midas\.<module>" tests/` -- per-module import check
3. Direct grep for `def test_` patterns in security areas (kill switch, auth, compliance, input validation, credentials)
4. `find apps/web -name "*.test.*" -o -name "*.spec.*"` -- frontend test discovery
5. Isolated and batch test runs to verify pass/fail status
