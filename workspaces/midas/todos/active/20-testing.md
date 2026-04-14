# M20 — Testing (3-Tier + Regression + Redteam Tests)

**Spec anchors:** all.
**Rules:** `rules/testing.md`, `rules/zero-tolerance.md`.

## T-20-01 — Tier 1 unit test scaffold

**Objective:** pytest scaffold per `rules/testing.md`; mocking allowed; <1s/test.
**Acceptance:** `pytest -m unit` runs green.

## T-20-02 — Tier 2 integration tests (real infrastructure recommended)

**Objective:** DataFlow against real PostgreSQL, Redis, IBKR paper, EODHD sandbox; no mocking.
**Acceptance:** suite runs green against real infrastructure.

## T-20-03 — Tier 3 E2E tests (Playwright for web, Flutter integration tests for mobile)

**Objective:** real browser flows; real backend; state persistence verified via read-back.
**Acceptance:** suite runs green.

## T-20-04 — Regression test bank

**Objective:** `tests/regression/` with reproduction tests for every bug + every critical redteam finding.
**Invariants:** behavioral (not source-grep) per `rules/testing.md`; regression tests never deleted.
**Acceptance:** all 12 M00 fixes have regression tests.

## T-20-05 — Redteam test rig (quant findings)

**Objective:** tests for each of: point-in-time protocol (T-00-01), latent learnability probe (T-00-02), router leakage (T-00-03), calibration multiple-comparison (T-00-04), shadow lane isolation (T-00-05).
**Acceptance:** all pass.

## T-20-06 — Redteam test rig (PM findings)

**Objective:** tests for: track-record window extension (T-00-06), envelope-widening lockout (T-00-07), top-of-fold usability gate (T-00-08), kill-switch process lock (T-00-09), Debate concession rule (T-00-10).
**Acceptance:** all pass.

## T-20-07 — Leakage / survivorship bias test harness

**Objective:** synthetic scenarios that inject leakage; assert the system catches them.

## T-20-08 — Backtest reproducibility test

**Objective:** given seed + config + as-of-date, backtest output is deterministic.

## T-20-09 — Multi-horizon consistency test

**Objective:** every model head validated at 1/3/6 month horizons per `rules/specs-authority`.

## T-20-10 — Adversarial backtest suite

**Objective:** injected tail regimes (2008, 2020, 2022) + synthetic adverse states from the generative challengers.

## T-20-11 — Security regression tests

**Objective:** null-byte credential decode, auth on endpoints, log-redaction checks, no hardcoded secrets.
**Acceptance:** `security-reviewer` agent runs clean.

## T-20-12 — Attention-budget test harness

**Objective:** synthetic user profiles; system behavior under fatigue signals.

## T-20-13 — Value-audit harness

**Objective:** run `value-auditor` agent over full user flows periodically.

## T-20-14 — Orphan-detection test

**Objective:** `rules/orphan-detection.md` protocol automated as a Tier 2 test per PR.

## T-20-15 — Coverage gates

**Objective:** 80% general + 100% for financial / auth / security-critical code per `rules/testing.md`.
**Acceptance:** CI enforces coverage thresholds.

**Gate out:** all three tiers green; redteam test rigs pass; coverage gates enforced; orphan audit automated.
