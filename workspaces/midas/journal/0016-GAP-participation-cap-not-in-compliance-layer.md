---
name: participation-cap-not-in-compliance-layer
description: exec.participation_cap check exists in cost_model.py but is not wired as a compliance-layer blocking rule — execution bypasses it
type: GAP
---

# GAP: participation_cap not wired as compliance blocking rule

## Finding

`check_participation_cap()` exists in `src/midas/execution/cost_model.py` (line 108) and is verified present, but it is not registered as a `ComplianceRule` in `src/midas/compliance/blocking_rules.py`.

```bash
$ grep "participation_cap" src/midas/compliance/blocking_rules.py
# (empty)
```

The compliance engine does not call `check_participation_cap` at execution time.

## Why it matters

Spec/13 §4.3 defines `exec.participation_cap` as a blocking rule: "order size > tier-adjusted ADV cap → block." If this is not in the compliance layer, order sizing can bypass the participation cap regardless of the cost model's check.

## Fix required

Add `exec.participation_cap` as a `ComplianceRule` in `blocking_rules.py` that calls `check_participation_cap()` from the cost model. The existing method can remain in cost_model.py; the compliance rule should delegate to it.

## Spec reference

`specs/13-execution-cost-and-microstructure.md` §4.3; `specs/11-compliance-and-risk.md` blocking rules table row: `exec.participation_cap`
