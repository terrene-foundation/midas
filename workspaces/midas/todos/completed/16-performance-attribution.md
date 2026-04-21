# M16 — Performance Attribution & Track Record

**Spec anchors:** 12.
**Depends on:** M01, M11, M15.

## T-16-01 — Daily NAV computation

**Objective:** daily NAV pipeline from positions × marks; EODHD marks with IBKR cross-check.
**Acceptance:** NAV matches IBKR reported value within tolerance.

## T-16-02 — Brinson-Fachler decomposition engine

**Objective:** allocation + selection + interaction effect per bucket (asset class, sector, duration, style) per period (1w/1m/3m/12m/inception).
**Acceptance:** Tier 2 against synthetic portfolio with known allocation/selection split reproduces the split.

## T-16-03 — Risk-adjusted metrics (Sharpe, Sortino, Calmar, vol, drawdown, recovery, tracking error, turnover, cost ratio)

**Objective:** rolling-window computation of all Section 2 metrics in `specs/12-`.
**Acceptance:** metrics match reference library implementation on same inputs.

## T-16-04 — Information Ratio, Jensen's Alpha, M², Treynor

**Objective:** IR, alpha, M², Treynor vs SAA baseline + 60/40 + S&P 500 per `specs/12- §2.1` (added in latest revision).
**Invariants:** bootstrap confidence intervals reported; Deflated Sharpe + PBO on promotion gate per T-00-04.
**Acceptance:** metrics + CIs match reference library.

## T-16-05 — Counterfactual computation (1d/1w/1m)

**Objective:** daily batch computing counterfactual returns for every decision (executed, rejected, modified) at three horizons.
**Acceptance:** Tier 2 replays a week; counterfactuals populated.

## T-16-06 — Track-record composite score

**Objective:** composite score per `specs/12- §6.1` for the autonomy ladder to read.
**Acceptance:** composite moves in expected direction on synthetic scenarios.

## T-16-07 — Calibration-curve tracker (links to T-05-16)

**Objective:** per-head + aggregate calibration curves computed rolling; queryable by UI and by the Debate agent.
**Acceptance:** UI surface renders curves per T-10-07 provenance rules.

## T-16-08 — Reporting surface backend (weekly summary + monthly statement)

**Objective:** data endpoints for the three reporting cadences in `specs/12- §7`.
**Depends on:** M17, M18.

**Gate out:** Brinson reconciles, metrics populate, composite score trustworthy on synthetic, counterfactuals flow into the evidence store.
