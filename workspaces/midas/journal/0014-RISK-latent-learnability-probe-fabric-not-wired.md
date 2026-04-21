# RISK: Latent Learnability Probe Fabric Price Read Not Wired

**Date:** 2026-04-16
**Found during:** /redteam spec compliance audit
**Source:** spec-compliance-audit-v2.md § HIGH-1

## Finding

`src/midas/evaluation/probes/latent_learnability.py:256-268` — the `_realised_return_for_state()` method returns `float("nan")` with a TODO. The mutual information probe works with synthetic data via `realized_returns_override`, but the real fabric price read path is not wired.

**Spec requirement (T-00-02):** "build `probe_latent_learnability.py` computing mutual information between `z_t` and realized forward returns vs a scrambled-target null; a family passes only if MI exceeds the null by a statistically significant margin"

**Current state:** Probe structure and statistical framework are complete and correct. Tests pass with synthetic data. Real fabric path is stubbed with TODO.

## Why This Is a Risk

The probe cannot be used to validate real representation learner families against live fabric data until the fabric price read is wired. This means:

- T-00-02 acceptance criteria cannot be fully satisfied in production
- Representation learner promotion decisions would rely on synthetic validation only
- The PIT price query (required for T-00-01) is also needed here

## Dependency

T-00-01 (Point-in-Time Data Protocol) — fabric price reads with `as_of_date` must land first

## Recommendation

Wire `fabric/adapters/dataflow_adapter.py` price read to `_realised_return_for_state()` after T-00-01 is implemented (PIT fabric queries available).

## Disposition

**RESOLVED (2026-04-17)** — commit `d9374cc` wires `_realised_return_for_state` to `FabricReader.read_price()` with PIT discipline. Uses `asyncio.gather` for parallel price fetches. Default market proxy: SPY (configurable).
