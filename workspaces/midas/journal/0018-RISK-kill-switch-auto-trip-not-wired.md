---
name: kill-switch-auto-trip-not-wired
description: Kill switch activate() requires manual action for all 4 conditions — spec requires automatic tripping on drawdown circuit breaker, OOD+NAV, IBKR severe error, and PACT breach
type: RISK
---

# RISK: Kill switch auto-trip not wired for spec-required conditions

## Finding

`specs/08-autonomy-and-trust.md` § Kill Switch states Midas trips the switch automatically when:

1. Drawdown crosses hard circuit-breaker threshold
2. OOD `z_t` state coincides with rapid NAV move
3. IBKR integration reports a severe error class
4. PACT policy breach detected

Current `kill_switch.py` `activate()` is manual-only. The `evaluate_no_bypass()` probe and `begin_clear_flow()` require user action. No automatic tripping is wired.

```bash
$ grep -n "auto.*trip\|drawdown_state\|nav_move\|ood_state" src/midas/compliance/kill_switch.py
189:            drawdown_state=state_brief.get("drawdown_state", ""),
# (read for state brief display only — not used to auto-trip)
```

## Why it matters

The spec gives users the assurance that Midas cannot continue trading through a crisis even if they are unavailable. If the kill switch requires manual action during a drawdown event or OOD state, Midas could continue generating orders through conditions it should have automatically halted.

## Fix required

Wire auto-trip conditions into `kill_switch.py`:

1. Monitor `drawdown_state` and `envelope_drawdown_pct` — trip if hard ceiling breached
2. Monitor `z_t` OOD score + NAV move rate simultaneously — trip if both exceed threshold
3. Subscribe to IBKR error events — trip on severe error class
4. Subscribe to PACT policy breach events — trip on any breach

Each condition should set `activation_reason` and persist to audit_log.

## Spec reference

`specs/08-autonomy-and-trust.md` § Kill Switch — "Midas trips the switch automatically when..."
