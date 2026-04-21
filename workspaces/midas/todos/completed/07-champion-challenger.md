# M07 — Champion / Challenger Shadow Infrastructure

**Spec anchors:** 05 §5.
**Depends on:** M00 (T-00-05), M05, M06.

## T-07-01 — Shadow lane namespace

**Objective:** dedicated `features_shadow_v{N}` namespace, `shadow_decisions` table, shadow inference services.
**Invariants:** namespace isolation enforced in fabric schema; no shared pointers with champion namespaces.
**Acceptance:** T-00-05 isolation test passes.

## T-07-02 — Shadow execution: no orders

**Objective:** shadow pipeline writes hypothetical decisions + hypothetical fills but never calls IBKR adapter.
**Invariants:** PACT compliance layer enforces; assertion is structural, not a comment.
**Acceptance:** T-00-05 `test_shadow_decision_does_not_reach_order_manager.py` passes.

## T-07-03 — Shadow P&L and attribution

**Objective:** compute hypothetical P&L and Brinson attribution for shadow-lane decisions.
**Depends on:** M16.

## T-07-04 — Shadow override simulation

**Objective:** estimate what the user would likely have done for each shadow decision (based on their override history) and factor that into shadow performance.
**Acceptance:** Tier 2 against a simulated user profile.

## T-07-05 — Shadow monitoring dashboard

**Objective:** operator view of all currently-running shadow lanes, their P&L, calibration, and contract-evaluation status.
**Depends on:** M17.

## T-07-06 — Orphan-detection audit cron

**Objective:** scheduled job that walks the shadow-lane call graph monthly and asserts no production call sites; surfaces violations to audit log.
**Invariants:** runs monthly; violations escalate.
**Depends on:** M14.

**Gate out:** shadow lanes run in parallel with champion, P&L diverges as expected, isolation audits clean.
