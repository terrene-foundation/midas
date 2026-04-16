# Test Coverage Audit Report

**Date**: 2026-04-16
**Branch**: zai
**Auditor**: testing-specialist (Step 4, audit mode)
**Method**: Re-derived from scratch via grep-based import tracing. No reliance on `.test-results` or prior self-reports.

---

## 1. Summary

| Metric                                   | Value                                 |
| ---------------------------------------- | ------------------------------------- |
| Source modules (excluding `__init__.py`) | 85                                    |
| Modules with test coverage               | 72                                    |
| Zero-coverage modules                    | 13                                    |
| Total test files                         | 44                                    |
| Total tests collected                    | 1,184                                 |
| `@pytest.mark.regression` tests          | 0                                     |
| `@pytest.mark.integration` tests         | 0                                     |
| Security-specific tests                  | 3 (credentials only, in IBKR adapter) |

---

## 2. Complete Module-to-Test Mapping

### COVERED modules (72)

| Source Module                                  | Test File(s)                                                                                        |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `agents.analyst`                               | `tests/test_agents_brief.py`                                                                        |
| `agents.debate`                                | `tests/test_agents_brief.py`                                                                        |
| `agents.orchestrator`                          | `tests/test_agents_brief.py`                                                                        |
| `agents.provider`                              | `tests/test_agents_brief.py`                                                                        |
| `agents.research`                              | `tests/test_agents_brief.py`                                                                        |
| `agents.tools`                                 | `tests/test_agents_brief.py`                                                                        |
| `api.app`                                      | `tests/test_api.py`                                                                                 |
| `api.routes` (indirect via `api.app`)          | `tests/test_api.py` (91 tests via TestClient)                                                       |
| `attribution.brinson`                          | `tests/unit/test_infrastructure.py`                                                                 |
| `attribution.counterfactual`                   | `tests/test_attribution.py`, `tests/unit/test_infrastructure.py`                                    |
| `attribution.metrics`                          | `tests/unit/test_infrastructure.py`                                                                 |
| `attribution.nav`                              | `tests/test_attribution.py`, `tests/unit/test_infrastructure.py`                                    |
| `attribution.track_record`                     | `tests/unit/test_infrastructure.py`                                                                 |
| `autonomy.envelope`                            | `tests/test_autonomy_compliance.py`                                                                 |
| `autonomy.ladder`                              | `tests/test_autonomy_compliance.py`                                                                 |
| `autonomy.triggers`                            | `tests/test_autonomy_compliance.py`                                                                 |
| `brief.composer`                               | `tests/test_agents_brief.py`                                                                        |
| `brief.density_matrix`                         | `tests/test_agents_brief.py`                                                                        |
| `brief.templates`                              | `tests/test_agents_brief.py`                                                                        |
| `brief.top_of_fold`                            | `tests/test_agents_brief.py`                                                                        |
| `compliance.blocking_rules`                    | `tests/test_autonomy_compliance.py`                                                                 |
| `compliance.escalation_rules`                  | `tests/test_autonomy_compliance.py`                                                                 |
| `compliance.kill_switch`                       | `tests/test_autonomy_compliance.py`                                                                 |
| `compliance.rules_engine`                      | `tests/test_autonomy_compliance.py`                                                                 |
| `compliance.warning_rules`                     | `tests/test_autonomy_compliance.py`                                                                 |
| `evaluation.probes.calibration_protocol`       | `tests/evaluation/probes/test_calibration_protocol.py`                                              |
| `evaluation.probes.debate_concession_rules`    | `tests/evaluation/probes/test_debate_concession_rules.py`                                           |
| `evaluation.probes.envelope_widening_protocol` | `tests/evaluation/probes/test_envelope_widening_protocol.py`                                        |
| `evaluation.probes.kill_switch_process_lock`   | `tests/evaluation/probes/test_kill_switch_process_lock.py`                                          |
| `evaluation.probes.latent_learnability`        | `tests/evaluation/probes/test_latent_learnability.py`                                               |
| `evaluation.probes.quote_moved_protocol`       | `tests/evaluation/probes/test_quote_moved_protocol.py`                                              |
| `evaluation.probes.router_overfitting`         | `tests/evaluation/probes/test_router_overfitting.py`                                                |
| `evaluation.probes.shadow_lane_isolation`      | `tests/evaluation/probes/test_shadow_lane_isolation.py`                                             |
| `evaluation.probes.top_of_fold_card`           | `tests/evaluation/probes/test_top_of_fold_card.py`                                                  |
| `execution.execution_agent`                    | `tests/unit/test_infrastructure.py`                                                                 |
| `execution.order_state`                        | `tests/unit/test_infrastructure.py`, `tests/test_execution.py`                                      |
| `execution.rate_limiter`                       | `tests/unit/test_infrastructure.py`                                                                 |
| `execution.reconciliation`                     | `tests/unit/test_infrastructure.py`, `tests/test_execution.py`                                      |
| `fabric.adapters.alt_macro`                    | `tests/fabric/test_adapter_alt_macro.py`                                                            |
| `fabric.adapters.base`                         | `tests/fabric/test_adapter_base.py`, `tests/fabric/test_adapter_ibkr.py`                            |
| `fabric.adapters.fred`                         | `tests/fabric/test_adapter_fred.py`                                                                 |
| `fabric.adapters.ibkr`                         | `tests/fabric/test_adapter_ibkr.py`                                                                 |
| `fabric.adapters.perplexity`                   | `tests/fabric/test_adapter_perplexity.py`                                                           |
| `fabric.adapters.sec_edgar`                    | `tests/fabric/test_adapter_sec_edgar.py`                                                            |
| `fabric.adapters.universe`                     | `tests/fabric/test_adapter_universe.py`, `tests/test_universe.py`                                   |
| `fabric.cache`                                 | `tests/fabric/test_fabric_cache.py`, `tests/fabric/test_fabric_freshness.py`                        |
| `fabric.embeddings`                            | `tests/fabric/test_fabric_embeddings.py`                                                            |
| `fabric.engine`                                | `tests/unit/test_infrastructure.py`, `tests/test_router_shadow.py`, `tests/test_state_inference.py` |
| `fabric.features`                              | `tests/fabric/test_fabric_features.py`                                                              |
| `fabric.freshness`                             | `tests/fabric/test_fabric_freshness.py`                                                             |
| `fabric.health`                                | `tests/fabric/test_fabric_health.py`                                                                |
| `fabric.models`                                | `tests/fabric/test_fabric_models.py`, `tests/regression/test_pit_protocol_no_future_leak.py`        |
| `heads.allocation`                             | `tests/test_model_heads.py` (via `midas.heads` package import)                                      |
| `heads.cross_sectional`                        | `tests/test_model_heads.py` (via `midas.heads` package import)                                      |
| `heads.execution`                              | `tests/test_execution.py`, `tests/test_model_heads.py`                                              |
| `heads.return_ts`                              | `tests/test_model_heads.py` (via `midas.heads` package import)                                      |
| `heads.score_tail`                             | `tests/test_model_heads.py` (via `midas.heads` package import)                                      |
| `heads.tail_risk`                              | `tests/test_model_heads.py` (via `midas.heads` package import)                                      |
| `heads.volatility`                             | `tests/test_model_heads.py` (via `midas.heads` package import)                                      |
| `ml.models.representation`                     | `tests/test_ml_online_inference.py`                                                                 |
| `ml.online_inference`                          | `tests/test_ml_online_inference.py`                                                                 |
| `ml.training`                                  | `tests/test_ml_training.py`                                                                         |
| `regime` (`__init__.py`)                       | `tests/test_regime.py` (57 tests)                                                                   |
| `release.changelog`                            | `tests/test_release.py`                                                                             |
| `release.version`                              | `tests/test_release.py`                                                                             |
| `router.calibration`                           | `tests/test_router_shadow.py` (via `midas.router` package import)                                   |
| `router.contextual_router`                     | `tests/test_router_shadow.py` (via `midas.router` package import)                                   |
| `router.pbt_harness`                           | `tests/test_router_shadow.py` (via `midas.router` package import)                                   |
| `router.promotion`                             | `tests/test_router_shadow.py` (via `midas.router` package import)                                   |
| `scheduler.jobs`                               | `tests/unit/test_infrastructure.py`                                                                 |
| `scheduler.scheduler`                          | `tests/unit/test_infrastructure.py`                                                                 |
| `shadow.shadow_lane`                           | `tests/test_router_shadow.py` (via `midas.shadow` package import)                                   |
| `shadow.shadow_monitor`                        | `tests/test_router_shadow.py` (via `midas.shadow` package import)                                   |
| `state_inference.bayesian_filter`              | `tests/test_state_inference.py`                                                                     |
| `state_inference.changepoint`                  | `tests/test_state_inference.py`                                                                     |
| `state_inference.ood_detector`                 | `tests/test_state_inference.py`                                                                     |
| `state_inference.posterior_combination`        | `tests/test_state_inference.py`                                                                     |
| `state_inference.posterior_service`            | `tests/test_state_inference.py`                                                                     |
| `testing.assertions`                           | `tests/test_testing_framework.py`                                                                   |
| `testing.fixtures`                             | `tests/test_testing_framework.py`                                                                   |
| `universe.changelog`                           | `tests/test_universe.py`                                                                            |
| `universe.constraints`                         | `tests/test_universe.py`                                                                            |
| `universe.etf_selection`                       | `tests/test_universe.py`                                                                            |
| `universe.factor_gap`                          | `tests/test_universe.py`                                                                            |
| `universe.overlap`                             | `tests/test_universe.py`                                                                            |
| `universe.scheduler`                           | `tests/test_universe.py`                                                                            |
| `paper_trading.paper_manager`                  | `tests/test_paper_trading.py`                                                                       |
| `paper_trading.report`                         | `tests/test_paper_trading.py`                                                                       |

### ZERO-COVERAGE modules (13) -- HIGH findings

| #   | Source Module                      | Severity   | Rationale                                                                                                                                                                 |
| --- | ---------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `config`                           | **MEDIUM** | Simple env-var config (76 LOC). No logic beyond `os.environ.get()`. Low risk but no test verifies defaults or missing-key behavior.                                       |
| 2   | `fabric.adapters.dataflow_adapter` | **HIGH**   | 260+ LOC with full DataFlow reader/writer implementing PIT discipline. This is the fabric substrate -- zero test coverage is a critical gap.                              |
| 3   | `fabric.adapters.eodhd`            | **HIGH**   | 500+ LOC primary data source adapter. Handles prices, fundamentals, news, corporate actions. Zero test coverage for auth failure handling, pagination, and audit logging. |
| 4   | `fabric.adapters.yahoo`            | **HIGH**   | 400+ LOC fallback adapter and cross-check mechanism. Zero test coverage for the cross-check price discrepancy logic and Yahoo-specific error handling.                    |
| 5   | `fabric.credentials`               | **HIGH**   | Credential management module. Zero test coverage despite security relevance.                                                                                              |
| 6   | `utils.url_credentials`            | **HIGH**   | Security-critical null-byte rejection helper mandated by `rules/security.md`. Zero test coverage for the exact credential decode helper that the security rules require.  |
| 7   | `universe.filters`                 | **MEDIUM** | S&P 1500 filter pipeline (80 LOC). Imports from `universe_adapter` but builds candidates with placeholder values. Functionally incomplete but structurally testable.      |

**Note**: `api.routes` is covered _indirectly_ -- `test_api.py` imports `create_app()` from `api.app`, which imports all router classes from `api.routes`. The 91 API tests exercise route endpoints through FastAPI's `TestClient`. This is acceptable indirect coverage but should be documented.

---

## 3. Test Count Summary

### By test file (top-level, sorted by count)

| Test File                                                    | Tests | Tier                            |
| ------------------------------------------------------------ | ----- | ------------------------------- |
| `tests/test_api.py`                                          | 91    | Tier 1 (TestClient, in-process) |
| `tests/test_attribution.py`                                  | 86    | Tier 1                          |
| `tests/fabric/test_adapter_ibkr.py`                          | 86    | Tier 1 (mocked HTTP)            |
| `tests/test_execution.py`                                    | 75    | Tier 1                          |
| `tests/test_autonomy_compliance.py`                          | 73    | Tier 1                          |
| `tests/unit/test_infrastructure.py`                          | 64    | Tier 1                          |
| `tests/test_testing_framework.py`                            | 61    | Tier 1                          |
| `tests/test_scheduler.py`                                    | 58    | Tier 1                          |
| `tests/test_regime.py`                                       | 57    | Tier 1                          |
| `tests/test_model_heads.py`                                  | 57    | Tier 1                          |
| `tests/test_release.py`                                      | 54    | Tier 1                          |
| `tests/test_agents_brief.py`                                 | 46    | Tier 1                          |
| `tests/test_paper_trading.py`                                | 33    | Tier 1                          |
| `tests/test_state_inference.py`                              | 27    | Tier 1                          |
| `tests/test_universe.py`                                     | 22    | Tier 1                          |
| `tests/test_ml_online_inference.py`                          | 21    | Tier 1                          |
| `tests/test_router_shadow.py`                                | 19    | Tier 1                          |
| `tests/evaluation/probes/test_calibration_protocol.py`       | 18    | Tier 1                          |
| `tests/fabric/test_fabric_freshness.py`                      | 15    | Tier 1                          |
| `tests/evaluation/probes/test_top_of_fold_card.py`           | 15    | Tier 1                          |
| `tests/fabric/test_fabric_models.py`                         | 14    | Tier 1                          |
| `tests/evaluation/probes/test_kill_switch_process_lock.py`   | 14    | Tier 1                          |
| `tests/regression/test_pit_protocol_no_future_leak.py`       | 13    | Regression                      |
| `tests/evaluation/probes/test_shadow_lane_isolation.py`      | 13    | Tier 1                          |
| `tests/evaluation/probes/test_quote_moved_protocol.py`       | 13    | Tier 1                          |
| `tests/fabric/test_fabric_cache.py`                          | 12    | Tier 1                          |
| `tests/test_ml_model_registry.py`                            | 11    | Tier 1                          |
| `tests/evaluation/probes/test_envelope_widening_protocol.py` | 11    | Tier 1                          |
| `tests/evaluation/probes/test_debate_concession_rules.py`    | 11    | Tier 1                          |
| `tests/fabric/test_fabric_health.py`                         | 9     | Tier 1                          |
| `tests/fabric/test_fabric_features.py`                       | 8     | Tier 1                          |
| `tests/fabric/test_fabric_embeddings.py`                     | 8     | Tier 1                          |
| `tests/evaluation/probes/test_router_overfitting.py`         | 8     | Tier 1                          |
| `tests/evaluation/probes/test_track_record_protocol.py`      | 7     | Tier 1                          |
| `tests/test_ml_training.py`                                  | 6     | Tier 1                          |
| `tests/fabric/test_adapter_base.py`                          | 6     | Tier 1                          |
| `tests/fabric/test_adapter_perplexity.py`                    | 5     | Tier 1                          |
| `tests/fabric/test_adapter_alt_macro.py`                     | 5     | Tier 1                          |
| `tests/fabric/test_adapter_universe.py`                      | 4     | Tier 1                          |
| `tests/fabric/test_adapter_fred.py`                          | 4     | Tier 1                          |
| `tests/evaluation/probes/test_latent_learnability.py`        | 4     | Tier 1                          |
| `tests/fabric/test_adapter_sec_edgar.py`                     | 3     | Tier 1                          |

**Total: 1,184 tests across 42 Python test files**

### Tier distribution

| Tier                 | Count | Notes                                                                                         |
| -------------------- | ----- | --------------------------------------------------------------------------------------------- |
| Tier 1 (Unit)        | 1,171 | All tests currently in `tests/` root and subdirectories                                       |
| Tier 2 (Integration) | 0     | No `@pytest.mark.integration` markers found                                                   |
| Tier 3 (E2E)         | 0     | No E2E tests found                                                                            |
| Regression           | 13    | `tests/regression/test_pit_protocol_no_future_leak.py` (unmarked but in regression directory) |

---

## 4. Fake Test Patterns

### MOCK/FAKE/DUMMY/SAMPLE constants in tests

**Finding: NONE.** No `MOCK_*`, `FAKE_*`, `DUMMY_*`, or `SAMPLE_*` constants found in test files.

### Stub response patterns

**Finding: NONE.** No `return {"status": "ok"}` or similar stub patterns found in test assertions.

### Source code TODOs (potential stubs)

Three TODO markers found in source code:

1. `src/midas/evaluation/probes/latent_learnability.py:189` -- `TODO (T-00-02): wire fabric price read -- placeholder returns NaN`
2. `src/midas/evaluation/probes/latent_learnability.py:267` -- `TODO (T-00-01): wire fabric price read once adapters are live`
3. `src/midas/fabric/adapters/dataflow_adapter.py:56` -- `TODO (T-00-01): implement lookback window`

Finding #1 and #2 are placeholder code in the latent learnability probe that returns NaN instead of real fabric data. This violates `rules/zero-tolerance.md` Rule 2 (no stubs, placeholders, or deferred implementation).

Finding #3 is an unimplemented lookback window in the dataflow adapter -- a missing feature, not a stub.

---

## 5. Critical Pattern Verification

### Regression markers

**Finding: ZERO `@pytest.mark.regression` markers in the entire test suite.** The regression test in `tests/regression/test_pit_protocol_no_future_leak.py` has 13 tests but none carry the `@pytest.mark.regression` decorator. This makes it impossible to filter and run regression tests selectively.

### Integration markers

**Finding: ZERO `@pytest.mark.integration` markers.** No Tier 2 tests exist. All 1,184 tests are Tier 1 (unit). The 3-tier testing strategy from `rules/testing.md` is not implemented.

### Security tests

Only 3 credential-related tests found, all in `tests/fabric/test_adapter_ibkr.py`:

- `test_client_credentials_stored`
- `test_health_check_unhealthy_without_credentials`
- `test_fetch_initial_token_raises_without_credentials`

**Missing security tests** (per `rules/security.md` requirements):

- No tests for `utils.url_credentials.py` null-byte rejection (`decode_userinfo_or_raise`)
- No tests for `utils/url_credentials.py` pre-encoder (`preencode_password_special_chars`)
- No injection tests for dynamic identifiers
- No input validation tests for API endpoints
- No XSS/output encoding tests

---

## 6. Recommendations

### HIGH priority (security and critical-path gaps)

1. **Add tests for `utils/url_credentials.py`** -- This module implements the exact security control mandated by `rules/security.md` (null-byte rejection at credential decode sites). Without tests, a refactor could silently break the protection. Minimum tests needed:
   - `test_decode_userinfo_rejects_null_byte_in_username`
   - `test_decode_userinfo_rejects_null_byte_in_password`
   - `test_decode_userinfo_handles_percent_encoded_credentials`
   - `test_preencode_password_special_chars_round_trip`

2. **Add tests for `fabric.adapters.dataflow_adapter.py`** -- This is the fabric substrate implementing the PIT discipline. It has 260+ LOC of row-to-record conversion logic and is the primary interface between the fabric and DataFlow. Zero coverage here means PIT enforcement could silently break.

3. **Add tests for `fabric.adapters.eodhd.py`** -- Primary data source adapter. Auth failure handling, pagination, and audit logging paths are untested. The `fetch_prices`, `fetch_fundamentals`, `fetch_news`, and `fetch_corporate_actions` methods all have error paths that return empty lists on auth failures -- these should be verified.

4. **Add tests for `fabric.adapters.yahoo.py`** -- Fallback adapter and cross-check mechanism. The `cross_check_prices` method is the only price validation mechanism and has zero coverage.

5. **Add tests for `fabric.credentials.py`** -- Credential management is security-sensitive and has zero test coverage.

### MEDIUM priority (test infrastructure and markers)

6. **Add `@pytest.mark.regression` to regression tests** -- The 13 tests in `tests/regression/test_pit_protocol_no_future_leak.py` should carry the marker for selective filtering.

7. **Add `@pytest.mark.integration` markers** -- At minimum, tests that use `create_fabric()` (which creates real SQLite DataFlow instances) should be marked as integration tests. This includes tests in `test_router_shadow.py`, `test_state_inference.py`, `test_universe.py`, and many fabric tests.

8. **Remove TODO stubs from `latent_learnability.py`** -- Two placeholder `NaN` returns violate `rules/zero-tolerance.md` Rule 2. Either wire the fabric reads or implement a fallback with a test.

### LOW priority (nice-to-have)

9. **Add config tests** -- `config.py` is simple but testing default values and env-var loading prevents silent regressions.

10. **Add `universe.filters` tests** -- The S&P 1500 filter pipeline has placeholder values but the filtering logic itself is testable.

11. **Consider Tier 2 directory structure** -- Currently all tests live in `tests/` root or `tests/unit/`. The 3-tier strategy (`tests/unit/`, `tests/integration/`, `tests/e2e/`) is not in effect. Restructuring would enable tier-based test execution.
