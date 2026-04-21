# /redteam Round 4 — Post-Merge Audit

**Date:** 2026-04-17
**Branch:** main (merged from zai, commit d9374cc)
**Previous round:** round-3-convergence-2026-04-17

---

## Executive Summary

Post-merge audit found **2 CRITICAL + 1 HIGH security findings** that existed before the d9374cc commit and remain unfixed. These are distinct from the spec compliance failures.

---

## CRITICAL FINDINGS

### CRIT-1: KillSwitch.clear() — Biometric/Process-Lock Unenforced

**File:** `src/midas/compliance/kill_switch.py:88-156`

**Spec:** `specs/08-autonomy-and-trust.md §5.4` — kill switch clear requires: biometric + explicit acknowledgment + 60-second dwell + state-of-the-world brief

**Finding:** `KillSwitch.clear()` accepts `user_approved: bool` and `state_brief: dict` as parameters. The docstring describes biometric verification and multi-step process, but the implementation only checks the boolean:

```python
if not user_approved:
    return {"cleared": False, "revert_level": 0, "conditions": []}
```

`user_approved` is a bare boolean from the caller — no biometric verification, no dwell timer, no brief-content validation.

**KillSwitchProcessLock** exists in `evaluation/probes/kill_switch_process_lock.py` with proper step tracking (BRIEF_READ, BRIEF_ACKNOWLEDGED, COMPLETE) and dwell enforcement — but it is **never instantiated or used** by `KillSwitch`.

**Fix:** Wire `KillSwitchProcessLock` into `KillSwitch.clear()`.

---

### CRIT-2: clear_kill_switch API — Confirmation Code Never Validated

**File:** `src/midas/api/routes.py:374-387`

**Spec:** `specs/08-autonomy-and-trust.md §5.4` — requires "valid confirmation code that matches the one issued when the kill switch was activated"

**Finding:**

1. `activate_kill_switch` (line ~362) never generates or stores a confirmation code
2. `clear_kill_switch` accepts **any non-empty string** as `confirmation_code` — no validation against stored value

```python
confirmation_code = body.get("confirmation_code", "")
if not confirmation_code:
    raise HTTPException(status_code=400, detail="Confirmation code required to clear kill switch")
# ↑ Any non-empty string passes
```

**Impact:** Anyone who can call `clear_kill_switch` with `{"user_approved": true, "confirmation_code": "anything"}` can clear the kill switch.

**Fix:** Generate and store confirmation code in `activate()`, validate in `clear()`.

---

## HIGH FINDINGS

### HIGH-1: KillSwitchProcessLock.evaluate_no_bypass() Always Returns True

**File:** `src/midas/evaluation/probes/kill_switch_process_lock.py:245-255`

```python
def evaluate_no_bypass(self) -> bool:
    """Assert that the clear flow cannot be bypassed."""
    return True  # ← always returns True, no actual checks
```

Even if wired into `KillSwitch`, this method provides no actual bypass detection.

**Fix:** Implement actual bypass checks or remove the method.

---

## SPEC COMPLIANCE FAILURES

### SPEC-1: Almgren-Chriss Cost Model Not Implemented

**Spec:** `specs/13-execution-cost-and-microstructure.md §2.2`

`grep -rn "Almgren\|Chriss" src/midas/` returns empty.

The `cost_attribution` model has placeholder fields but not the functional form:
`C_impact = γ × σ × (q / ADV)^0.5 + η × σ × (q / V_schedule)`

---

### SPEC-2: Participation Cap Rule Missing

**Spec:** `specs/13-execution-cost-and-microstructure.md §4.3`

`grep -rn "participation_cap" src/midas/` returns empty.

`exec.participation_cap` blocking rule not implemented.

---

### SPEC-3: Liquidity Tiering Not Implemented

**Spec:** `specs/13-execution-cost-and-microstructure.md §5`

`grep -rn "LIQUIDITY_TIER\|liquidity_tier" src/midas/` returns empty.

L1/L2/L3/L4 liquidity tiers not defined.

---

## MEDIUM FINDING

### MED-1: RulesEngine Unknown Operators Bypass Default-Deny

**File:** `src/midas/compliance/rules_engine.py:300`

```python
elif op == "contains":
    return lambda ctx, f=field, v=value: str(v) in str(ctx.get(f, ""))
return lambda ctx: False  # ← unknown operator PASSES, not blocked
```

Unknown operators pass rather than block, defeating default-deny for DB-loaded rules.

---

## ITEMS FROM PRIOR ROUND STILL OPEN

| Item                              | Status       | Notes                                     |
| --------------------------------- | ------------ | ----------------------------------------- |
| RateLimiter unbounded list        | **RESOLVED** | d9374cc uses deque(maxlen=)               |
| Latent learnability fabric wiring | **RESOLVED** | d9374cc wires \_realised_return_for_state |
| Attention budget tracking         | PARTIAL      | Density matrix exists, UI not implemented |
| User-owned enforcement            | PARTIAL      | Structure exists, explicit guard missing  |

---

## Convergence Status

| Criterion                  | Status                                   |
| -------------------------- | ---------------------------------------- |
| 0 CRITICAL                 | **FAIL** — 2 CRITICAL findings           |
| 0 HIGH                     | **FAIL** — 1 HIGH + 3 SPEC-HIGH findings |
| 2 consecutive clean rounds | No                                       |
| 100% spec compliance       | **FAIL** — 3 spec compliance failures    |

**Not converged.**
