# HIGH: Yahoo Finance Adapter Zero Test Coverage

**Date:** 2026-04-22
**Round:** Round 10 red team
**Severity:** HIGH

## Finding

`midas.fabric.adapters.yahoo.YahooFinanceAdapter` is the fallback/cross-check data adapter but has zero test imports anywhere in the test directory.

## Impact

The Yahoo Finance adapter is part of the data ingestion pipeline (T-01-03 per spec). Without tests, any refactor that breaks it will not be caught. As the cross-check mechanism for data quality validation, this gap could allow bad data to propagate undetected.

## Audit Command

```bash
grep -rl "from midas.fabric.adapters.yahoo\|import midas.fabric.adapters.yahoo\|YahooFinanceAdapter" tests/
# No matches found
```

## Resolution Path

Add a Tier 2 integration test that verifies the adapter fetches and writes correct price data, including the cross-check discrepancy threshold logic.

## Status

OPEN
