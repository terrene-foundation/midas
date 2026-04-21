---
name: wide-spread-warning-missing
description: warn.wide_spread (spread exceeds rolling_mean + N×stdev) is missing from warning_rules.py — microstructure conditions not monitored
type: GAP
---

# GAP: warn.wide_spread missing from warning_rules

## Finding

`specs/13-execution-cost-and-microstructure.md` § Warning Rules table defines `warn.wide_spread`:

> "current spread > (rolling_mean + N×stdev)"

This rule is not in `src/midas/compliance/warning_rules.py`:

```bash
$ grep "wide_spread" src/midas/compliance/warning_rules.py
# (empty)
```

All 7 warning rules are present except `warn.wide_spread`.

## Why it matters

Wide spreads indicate adverse microstructure conditions — thin books, stressed markets, or impending moves. A trader should be warned before Midas orders execute at poor prices. Without this warning, Midas can move ahead in conditions where the cost impact exceeds expectations.

## Fix required

Add `warn.wide_spread` to `warning_rules.py` following the pattern of existing rules:

- Compute rolling mean and stdev of bid-ask spread for the instrument
- If current spread exceeds threshold, emit warning
- Log the warning with spread statistics

## Spec reference

`specs/13-execution-cost-and-microstructure.md` § Warning Rules — row: `warn.wide_spread`
