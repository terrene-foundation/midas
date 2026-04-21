# M11 — Autonomy Ladder & Trust Boundary

**Spec anchors:** 08.
**Depends on:** M12, M16.

## T-11-01 — Envelope data model + enforcement read

**Objective:** envelope parameters (drawdown ceiling, vol target band, concentration caps, universe exclusions, cost budget ceiling) as first-class fabric rows; exposed read-only to compliance.
**Acceptance:** envelope mutation audited; read-back match.

## T-11-02 — Autonomy-level state machine

**Objective:** L0 → L1 → L2 → L3 → L4 state machine with typed transitions; promotions always user-approved, demotions automatic.
**Invariants:** no silent promotion; first-seven-live-days always L1 regardless.
**Acceptance:** state machine unit-tested; invariant violations rejected.

## T-11-03 — Upgrade contract evaluator

**Objective:** evaluates L0→L1, L1→L2, L2→L3, L3→L4 contracts per `specs/08- §7` + T-00-06 (12-month primary window).
**Invariants:** 12-month Brinson bootstrap CI lower bound above floor; pool-consistency gate; minimum-activity gate.
**Acceptance:** synthetic lucky-streak test confirms no false promotions.

## T-11-04 — Promotion-proposal surface

**Objective:** when upgrade contract passes, write a `autonomy_upgrade` decision to `decisions`; user reviews evidence + approves/declines.
**Depends on:** M10, M17.

## T-11-05 — Demotion triggers

**Objective:** automatic demotion on drawdown breach, model-champion demoted, override-rate threshold, calibration drift, stale-data, Crisis band, OOD `z_t`, kill switch.
**Acceptance:** each trigger produces demotion event in Tier 2 test.

## T-11-06 — First-seven-days enforcement

**Objective:** compliance rule `escalate.first_seven_days` forces L1 behavior for 7 days post paper→live.
**Depends on:** M12.

## T-11-07 — Envelope-widening flow (T-00-07 enforcement)

**Objective:** drawdown-conditional lockout, 24h cooldown, 72h minimum from drawdown, mandatory Debate pushback.
**Depends on:** M12, M09.

**Gate out:** ladder traverses L0→L1 in paper→live; promotion+demotion tests pass; widening lockout tested.
