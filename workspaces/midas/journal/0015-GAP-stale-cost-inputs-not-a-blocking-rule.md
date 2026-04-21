---
name: stale-cost-inputs-not-blocking-rule
description: data.stale_cost_inputs missing from compliance blocking rules — cost model inputs can go stale without tripping execution block
type: GAP
---

# GAP: data.stale_cost_inputs not wired as blocking rule

## Finding

`specs/13-execution-cost-and-microstructure.md` § Cost Model Inputs states:

> "Missing inputs → stale-data gate trips (rule `data.stale_cost_inputs`, added)"

This rule is not in `src/midas/compliance/blocking_rules.py`:

```bash
$ grep "stale_cost" src/midas/compliance/blocking_rules.py
# (empty)
```

`data.stale_price` and `data.stale_fundamental` exist, but `data.stale_cost_inputs` does not.

## Why it matters

The cost model (Almgren-Chriss) uses volatility, ADV, and spread estimates as inputs. If these go stale (e.g., market microstructure changed after a halt, or ADV is from a thin-volume period), execution could be sized incorrectly — too large in illiquid conditions, or too small and ineffective in trending conditions.

## Fix required

Add `data.stale_cost_inputs` to `blocking_rules.py` following the same pattern as `data.stale_price`:

- Check age of each cost-model input (volatility, ADV, spread estimates)
- Block if any input exceeds the staleness threshold
- Write audit record on block

## Spec reference

`specs/13-execution-cost-and-microstructure.md` — § "Cost Model Inputs" and § Blocking Rules table row: `data.stale_cost_inputs`
