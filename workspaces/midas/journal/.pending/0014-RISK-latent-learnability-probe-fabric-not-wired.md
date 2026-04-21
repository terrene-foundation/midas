# RISK: Latent Learnability Probe Fabric Price Read Not Wired — FIXED

**Date:** 2026-04-16
**Found during:** /redteam spec compliance audit
**Fixed during:** /redteam round 2 — fix applied immediately

## Finding (original)

`src/midas/evaluation/probes/latent_learnability.py:256-268` — `_realised_return_for_state()` returned `float("nan")` with a TODO. The mutual information probe worked with synthetic data but the real fabric price read was stubbed.

## Fix Applied

`_realised_return_for_state` is now `async` and wires the `FabricReader.read_price()`:

1. Queries market proxy ticker (default: SPY) at entry and exit dates
2. Uses PIT discipline: `as_of = period_end + 1 day`, `lookback_days = horizon + 5`
3. Returns forward return as `(end_close - start_close) / start_close`
4. Returns NaN for missing data, zero-closes, or fabric errors (probe continues)

## Verification

```
tests/evaluation/probes/test_latent_learnability.py ....  4 passed
tests/evaluation/probes/                                  114 passed
```

## Disposition

**FIXED** — committed to zai branch.
