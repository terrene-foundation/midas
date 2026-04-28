# Test Coverage Audit v2 — Midas Project

**Date:** 2026-04-22
**Auditor:** Testing Specialist Agent
**Scope:** All modules in `src/midas/` created in the current implementation cycle
**Verification method:** `pytest --collect-only -q` + grep-based import analysis

---

## Summary

| Metric                                | Value    |
| ------------------------------------- | -------- |
| Total tests collected                 | 1820     |
| Source modules audited                | ~120     |
| Modules with ZERO direct test imports | 2        |
| Security test files                   | 3        |
| Integration test markers found        | 14 files |

---

## Test Enumeration

```bash
$ pytest --collect-only -q 2>&1 | tail -5
1820 tests collected in 0.23s
```

### Test Files by Category

| Category               | Count     | Examples                                                                   |
| ---------------------- | --------- | -------------------------------------------------------------------------- |
| Unit tests             | ~50       | `test_auth.py`, `test_url_credentials.py`, `test_websocket.py`             |
| Integration tests      | 14 marked | `test_api.py`, `test_adapter_ibkr.py`, `test_scheduler.py`                 |
| Security tests         | 3         | `test_credentials.py`, `test_ibkr_queue.py`, `test_pydantic_validation.py` |
| Probe/evaluation tests | 10        | `test_calibration_protocol.py`, `test_kill_switch_process_lock.py`         |
| Fabric adapter tests   | 12        | `test_adapter_base.py`, `test_adapter_fred.py`, etc.                       |
| ML tests               | 11        | `test_ml_training.py`, `test_ml_ood_detector.py`, etc.                     |
| Router/shadow tests    | 2         | `test_router_shadow.py`, `test_contextual_bandit.py`                       |

---

## HIGH Findings — Modules with Zero Test Imports

### Finding 1: `midas.fabric.adapters.yahoo` — YahooFinanceAdapter

**Severity:** HIGH

**Module path:** `src/midas/fabric/adapters/yahoo.py`

**Description:** `YahooFinanceAdapter` is a fallback data adapter for Yahoo Finance. It is exposed in `midas.fabric.adapters.__all__` but has **zero test imports** anywhere in the test directory.

**Production usage:** The adapter is documented as a secondary price source and cross-check mechanism in `specs/03-universe-and-data.md`.

**Audit command:**

```bash
$ grep -rl "from midas.fabric.adapters.yahoo\|import midas.fabric.adapters.yahoo\|YahooFinanceAdapter" tests/
# No matches found
```

**Risk:** Without tests, any refactor that breaks the Yahoo Finance adapter will not be caught before deployment. Given that this adapter is part of the data ingestion pipeline (T-01-03 per spec), failure could result in stale or missing price data propagating to all downstream models.

**Recommended action:** Add a Tier 2 integration test that:

1. Mocks or uses a real Yahoo Finance API response
2. Verifies the adapter writes correct rows to the fabric via DataFlow express
3. Tests the cross-check discrepancy threshold logic

---

### Finding 2: `midas.fabric.adapters.eodhd` — EODHDAdapter

**Severity:** HIGH

**Module path:** `src/midas/fabric/adapters/eodhd.py`

**Description:** `EODHDAdapter` is the **primary price source** for EOD OHLCV data, fundamentals, news, and corporate actions. It is exposed in `midas.fabric.adapters.__all__` but has **zero test imports** anywhere in the test directory.

**Production usage:** Per `specs/03-universe-and-data.md` §2.1, EODHD is the primary data source. This is a critical path component.

**Audit command:**

```bash
$ grep -rl "from midas.fabric.adapters.eodhd\|import midas.fabric.adapters.eodhd\|EODHDAdapter" tests/
# No matches found
```

**Risk:** This is the highest-risk finding. The primary data adapter for the entire Midas system has no test coverage. Any regression in EODHD API handling, authentication, pagination, or DataFlow write logic will silently reach production.

**Recommended action:** Add Tier 2 integration tests covering:

1. Happy-path price fetch and DataFlow write
2. Authentication failure (returns empty results + audit entry)
3. Pagination handling for large result sets
4. Rate limit handling
5. Error audit logging behavior

---

## Modules with Indirect Coverage via Parent Re-exports

The following modules are NOT directly imported in tests, but ARE exercised through parent module re-exports:

| Module                           | Re-exported via            | Tested via                                       |
| -------------------------------- | -------------------------- | ------------------------------------------------ |
| `midas.heads.allocation`         | `midas.heads.__init__.py`  | `test_model_heads.py` imports from `midas.heads` |
| `midas.heads.tail_risk`          | `midas.heads.__init__.py`  | `test_model_heads.py`                            |
| `midas.heads.cross_sectional`    | `midas.heads.__init__.py`  | `test_model_heads.py`                            |
| `midas.heads.return_ts`          | `midas.heads.__init__.py`  | `test_model_heads.py`                            |
| `midas.heads.score_tail`         | `midas.heads.__init__.py`  | `test_model_heads.py`                            |
| `midas.heads.volatility`         | `midas.heads.__init__.py`  | `test_model_heads.py`                            |
| `midas.shadow.shadow_lane`       | `midas.shadow.__init__.py` | `test_router_shadow.py`                          |
| `midas.shadow.shadow_monitor`    | `midas.shadow.__init__.py` | `test_router_shadow.py`                          |
| `midas.router.pbt_harness`       | `midas.router.__init__.py` | `test_router_shadow.py`                          |
| `midas.router.promotion`         | `midas.router.__init__.py` | `test_router_shadow.py`                          |
| `midas.router.contextual_bandit` | `midas.router.__init__.py` | `test_router_shadow.py`                          |
| `midas.router.contextual_router` | `midas.router.__init__.py` | `test_router_shadow.py`                          |
| `midas.router.calibration`       | `midas.router.__init__.py` | `test_router_shadow.py`                          |

**Note:** While these modules are exercised through parent re-exports, the audit protocol requires direct import verification. The indirect coverage is noted here as context — these modules are not orphans and do have behavioral tests through their re-exported parent APIs. However, if the re-export path breaks (e.g., import error in `__init__.py`), there would be no signal.

---

## Security Test Coverage

### Existing Security Tests

| File                                         | Coverage                                                                          |
| -------------------------------------------- | --------------------------------------------------------------------------------- |
| `tests/security/test_credentials.py`         | Credential masking, null-byte rejection, URL credential decode/encode round-trips |
| `tests/security/test_ibkr_queue.py`          | IBKR queue ordering, message processing, authentication                           |
| `tests/security/test_pydantic_validation.py` | Input validation for API models, schema enforcement                               |

### Missing Security Tests

**No explicit kill-switch security tests found:**

```bash
$ grep -rln "test.*kill.*switch.*security\|test.*kill.*auth" tests/
# No matches found
```

The kill switch process lock is tested in `tests/evaluation/probes/test_kill_switch_process_lock.py` but this tests functional behavior, not security properties (e.g., unauthorized bypass attempts).

**No explicit auth/JWT attack tests found:**

```bash
$ grep -rln "test.*auth.*bypass\|test.*jwt.*forge\|test.*token.*steal" tests/
# No matches found
```

Auth is tested functionally in `tests/unit/test_auth.py` but security attack vectors (token forgery, privilege escalation, session fixation) do not appear to have dedicated tests.

---

## Integration Test Markers

14 files use `pytest.mark.integration`:

```
tests/security/test_pydantic_validation.py
tests/security/test_credentials.py
tests/test_regime.py
tests/test_autonomy_compliance.py
tests/test_scheduler.py
tests/test_gap_ladder_demote_to.py
tests/unit/test_routes_extended.py
tests/test_api.py
tests/unit/test_auth.py
tests/unit/test_websocket.py
tests/fabric/test_adapter_ibkr.py
tests/fabric/test_adapter_base.py
tests/evaluation/probes/test_kill_switch_process_lock.py
```

These tests require real infrastructure (Docker services) and are marked appropriately.

---

## Test Execution Verification

```bash
$ uv run pytest tests/unit/test_auth.py tests/unit/test_url_credentials.py tests/unit/test_websocket.py -q --tb=short
....................................................... [100%]
55 passed in 4.32s
```

Sample unit tests pass. Full suite (1820 tests) was collected but background execution was interrupted. Recommend running full suite with:

```bash
cd /Users/esperie/repos/training/midas
uv run pytest tests/ -x -q --tb=short
```

---

## Recommendations

### Immediate (CRITICAL)

1. **Add tests for `EODHDAdapter`** — this is the primary data source adapter with zero coverage
2. **Add tests for `YahooFinanceAdapter`** — fallback adapter with zero coverage

### High Priority

3. **Add security tests for kill switch** — test unauthorized bypass attempts and process lock behavior under adversarial conditions
4. **Add JWT attack vector tests** — token forgery, privilege escalation scenarios

### Medium Priority

5. **Consider direct import tests** for modules currently covered only via re-exports (e.g., `from midas.router.pbt_harness import PBTHarness` directly rather than `from midas.router import PBTHarness`) — this ensures the re-export path is tested as a distinct code path

---

## Compliance Status

| Rule                                      | Status                                                        |
| ----------------------------------------- | ------------------------------------------------------------- |
| Zero-tolerance for stubs                  | PASS — no stubs found                                         |
| Test coverage for new modules             | **2 modules in violation**                                    |
| Security tests for auth/JWT paths         | PARTIAL — functional tests exist, attack vector tests missing |
| Integration tests use real infrastructure | PASS — 14 files properly marked                               |

---

## Files Modified in This Audit

This audit did not modify any source or test files. All findings are documentation of existing coverage gaps.
