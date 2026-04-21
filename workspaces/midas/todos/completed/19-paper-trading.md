# M19 — Paper Trading Flow & Report

**Spec anchors:** 08 §6, 10 §3, FP-7.
**Depends on:** M15, M16, M17, M18.
**Blocks:** live trading; T-00-11 trader redteam must also complete.

## T-19-01 — Paper-mode feature flag wiring

**Objective:** `state.paper_trading` rule enforced in compliance; IBKR adapter routes to paper account when flag is on.
**Acceptance:** Tier 2 confirms no live orders when paper is on.

## T-19-02 — Paper-mode banner (web + mobile)

**Objective:** persistent, unmissable banner across all surfaces per `10- §3.1` + T-18-15.

## T-19-03 — Two-week timer enforcement

**Objective:** compliance rule blocks `paper_to_live_transition` until ≥14 operating days elapsed from paper start.
**Acceptance:** timer-based block test.

## T-19-04 — Paper-trading report generator

**Objective:** scheduled job (T-14-02) at end of paper period producing the full subsystem pass/fail per `specs/08- §6.2`.
**Acceptance:** report renders; every subsystem evaluated.

## T-19-05 — Report review surface

**Objective:** dedicated UI where the user reviews the report; "Go Live" button appears only after review + all pass.
**Depends on:** M17, M18.

## T-19-06 — Go Live action

**Objective:** biometric-gated explicit action; first seven days forced L1 per T-11-06.
**Acceptance:** T-00-09-style test confirms enforcement.

## T-19-07 — Paper-trading anomaly detector

**Objective:** flags any subsystem degradation, compliance veto, or error class during paper; blocks Go Live if unresolved.

## T-19-08 — Paper-vs-backtest consistency check

**Objective:** comparison of live paper behavior to backtest expectation; significant divergence blocks Go Live.

**Gate out:** report generates with all subsystems green; Go Live works end-to-end; first live week operates at L1.
