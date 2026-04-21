# Round 8: Red Team — 2026-04-20

## Scope

Post-merge verification on `main` (zai merged). Re-derive all spec assertions via grep/AST. Verify test suite status.

## Tests

**90/90 test_api.py tests pass** (verified 2026-04-20, 21 min run).

Full suite: 1459 tests collected.

## Spec Compliance — Fresh Re-Derivation

Re-derived every spec assertion from scratch. Prior coverage files (v2/v3) were from `zai` branch — audited as-is on `main`.

**Result: 5 new HIGH/MEDIUM gaps** in the compliance/safety layer. All prior CRITICAL/HIGH findings from round 7 remain verified.

### New Findings

| ID     | Severity | Finding                                                                      | Spec Reference            |
| ------ | -------- | ---------------------------------------------------------------------------- | ------------------------- |
| SC-H9  | HIGH     | `warn.wide_spread` missing from `warning_rules.py`                           | spec/13 § Warning Rules   |
| SC-H10 | HIGH     | `data.stale_cost_inputs` missing from `blocking_rules.py`                    | spec/13 § Blocking Rules  |
| SC-H11 | HIGH     | `exec.participation_cap` not wired as compliance blocking rule               | spec/13 §4.3              |
| SC-C3  | HIGH     | Kill switch auto-trip not wired (drawdown, OOD+NAV, IBKR error, PACT breach) | spec/08 § Kill Switch     |
| SC-M2  | MEDIUM   | Paper→live "user opened report" not persisted to backend                     | spec/08 § Paper→Live Gate |

### Previously-Failed Items Now Fixed

| Item                                   | Status                                                     |
| -------------------------------------- | ---------------------------------------------------------- |
| [00-1] Hardcoded tickers in `tools.py` | **FIXED** — now imports `FACTOR_MAP` from `midas.universe` |

### All Prior Round 7 CRITICAL/HIGH Still Verified

| Item                                      | Status                                            |
| ----------------------------------------- | ------------------------------------------------- |
| CRIT-1 KillSwitch process lock            | **PASS**                                          |
| CRIT-2 Confirmation code validation       | **PASS**                                          |
| HIGH-1 evaluate_no_bypass() bypass checks | **PASS**                                          |
| SPEC-1 Almgren-Chriss cost model          | **PASS**                                          |
| SPEC-2 Participation cap check            | **PASS** (in cost_model.py, not compliance layer) |
| SPEC-3 Liquidity tiering                  | **PASS**                                          |
| SPEC-11-7 JWT auth middleware             | **PASS**                                          |

## Fixes Implemented (Round 8 Fix Pass)

All 5 gaps resolved this session:

| ID     | Status    | Fix                                                                                     |
| ------ | --------- | --------------------------------------------------------------------------------------- |
| SC-H9  | **FIXED** | `warn.wide_spread` added to `warning_rules.py` (rule #8)                                |
| SC-H10 | **FIXED** | `data.stale_cost_inputs` added to `blocking_rules.py` (rule #9)                         |
| SC-H11 | **FIXED** | `exec.participation_cap` added to `blocking_rules.py` (rule #21)                        |
| SC-C3  | **FIXED** | `KillSwitch.auto_evaluate()` added; `kill_switch_auto_trip` job registered in scheduler |
| SC-M2  | **FIXED** | `paper_live_settings` model added; `POST /acknowledge` endpoint in `PaperLiveRouter`    |

**Tests:**

- `tests/unit/test_compliance_rules.py`: 25 new tests — 25 passed
- `tests/unit/test_infrastructure.py`: `test_get_all_jobs_returns_14` (was 13) — 6 passed
- **277 unit tests total passed**
- **90/90 API tests passing** (prior run)

## Journal Entries Created

- `0015-GAP-stale-cost-inputs-not-a-blocking-rule.md`
- `0016-GAP-participation-cap-not-in-compliance-layer.md`
- `0017-GAP-wide-spread-warning-missing.md`
- `0018-RISK-kill-switch-auto-trip-not-wired.md`
- `0019-GAP-paper-live-report-acknowledgment-not-persisted.md`
