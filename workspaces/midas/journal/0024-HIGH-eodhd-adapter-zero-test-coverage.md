# HIGH: EODHD Adapter Zero Test Coverage

**Date:** 2026-04-22
**Round:** Round 10 red team
**Severity:** HIGH

## Finding

`midas.fabric.adapters.eodhd.EODHDAdapter` is the primary price source (per spec 03 §2.1) but has zero test imports anywhere in the test directory.

## Impact

Any refactor that breaks the EODHD adapter will not be caught before deployment. Failure could result in stale or missing price data propagating to all downstream models.

## Audit Command

```bash
grep -rl "from midas.fabric.adapters.eodhd\|import midas.fabric.adapters.eodhd\|EODHDAdapter" tests/
# No matches found
```

## Resolution Path

Add a Tier 2 integration test that:

1. Mocks or uses a real EODHD API response
2. Verifies the adapter writes correct rows to the fabric via DataFlow express
3. Tests the OHLCV, fundamentals, news, and corporate actions ingestion paths

## Status

OPEN
