# Midas Todos — Master Index

**Status:** Planning Wave 1-4 (7 open gaps from red team rounds 8-12). Awaiting human approval.
**Previous:** M00-M21 HUMAN-APPROVED 2026-04-14, implemented sessions 1-3, codified in `14c6a28`.
**Spec set:** `specs/_index.md` v1 (14 governing files). Red team converged round 12 (0 CRITICAL/0 HIGH on existing code).
**Execution model:** Autonomous. Effort in sessions (1 session ≈ 3-5 human-days equivalent per the 10x multiplier).

---

## Sessions 1-3: COMPLETE

All M00-M21 milestones implemented. See prior index content in git history (`14c6a28`). Spec coverage 15/15. Red team converged round 12.

---

## Remaining Gaps: Wave Plan

7 architecturally-significant gaps identified in rounds 8-12. Organized into 4 waves ordered by value-chain dependency: what unblocks the next.

```
WAVE 1 — Make It Usable (1 session)
  GAP-1: Onboarding frontend (CRITICAL)
  Adapter test coverage: EODHD + Yahoo edge cases
  Backtest engine + weight fix
       │
       ▼
WAVE 2 — Make It Valuable (2 sessions)
  GAP-3: Brief composer grounding (HIGH)
  GAP-4: Debate multi-turn + tools (HIGH)
  GAP-6: ModelRegistry promote/retire (HIGH)
       │
       ▼
WAVE 3 — Make It Trustworthy (1-2 sessions)
  GAP-2: IBKR order states + rejection taxonomy (CRITICAL)
       │
       ▼
WAVE 4 — Make It Complete (1 session)
  GAP-5: Notification system (MEDIUM)
```

**Total: 5-6 sessions** from first gap to complete v1.

---

## Wave Summary

| Wave | Scope                       | Gaps                             | Sessions | Unblock Criteria                                              |
| ---- | --------------------------- | -------------------------------- | -------- | ------------------------------------------------------------- |
| 1    | User gate + data foundation | GAP-1 + adapter tests + backtest | 1        | New user completes onboarding, backtest panels show real data |
| 2    | Decision quality            | GAP-3 + GAP-4 + GAP-6            | 2        | Briefs grounded, debate multi-turn, model lifecycle works     |
| 3    | Execution trust             | GAP-2                            | 1-2      | IBKR order states complete, rejection taxonomy full           |
| 4    | Polish                      | GAP-5                            | 1        | Notifications fire on real events                             |

---

## Dependency Graph (Cross-Wave)

```
Wave 1:
  B1 (query hooks) → B2 (wizard) → B8 (page refactor)
                    → B3-B6 (steps, parallel) → W2 (wire steps)
                    → B7 (skeleton) → W1 (guard)
  W1 + W2 → W3 (shell integration)

  T1-T5 (EODHD tests) — independent
  T6-T10 (Yahoo tests) — independent
  F11 (BacktestEngine) → F12 (API wire) → T14 (API tests)
  T13 (engine tests) alongside F11

Wave 2:
  3A (validators) ─┐
  3B (enricher) ────┼→ W3A (wire composer) → W3C (decision audit) → R5 (regression)
  4A (multi-turn) → 4B (session + tools) → W4A+W4B (wire orchestrator)
  6A (fix promote) → 6B (fix retire) → W6A+W6B (wire audit + router)

Wave 3:
  2A (state machine) → 2B (rejection codes) → 2C (order manager)
  W2A (adapter wire) → W2B (rejection dispatch) + W2C (facade exposure) → R8 (regression)

Wave 4:
  B10-BE (notification backend) → B10 (types/hooks) → B13 (weekly summary) → W7
  B11 + B12 (permission + toast, parallel) → W5, W6
  W4 (preferences wire) → W8 (settings page)
  Wave 3 W2B dispatch interface → Wave 4 wires actual delivery
```

---

## Per-Session Capacity Discipline

Every todo conforms to the budget (`rules/autonomous-execution.md`):

- ≤ 500 LOC load-bearing logic per todo
- ≤ 5-10 simultaneous invariants per todo
- ≤ 3-4 call-graph hops
- Describable in ≤ 3 sentences

---

## File Index

| File                                 | Wave | Contents                                         |
| ------------------------------------ | ---- | ------------------------------------------------ |
| `wave1-onboarding-tests-backtest.md` | 1    | GAP-1 onboarding, adapter tests, backtest engine |
| `wave2-decision-quality.md`          | 2    | GAP-3 brief, GAP-4 debate, GAP-6 ModelRegistry   |
| `wave3-ibkr-execution.md`            | 3    | GAP-2 IBKR order states + rejection taxonomy     |
| `wave4-notifications.md`             | 4    | GAP-5 notification system + backend              |

---

## Red Team Review — Addressed

Post-compilation review found 3 legitimate gaps, all patched into wave files:

| Finding                                      | Resolution                                                                        |
| -------------------------------------------- | --------------------------------------------------------------------------------- |
| No backend notification endpoints (CRITICAL) | Added B10-BE to Wave 4                                                            |
| W2B cross-wave dependency (HIGH)             | Changed to dispatch interface pattern — Wave 3 logs+audits, Wave 4 wires delivery |
| OrderManager facade exposure (MEDIUM)        | Added W2C to Wave 3 with Tier 2 wiring test                                       |
| Decision audit composition (HIGH)            | Added W3C to Wave 2 Group D                                                       |
| Sidebar/navigation (HIGH)                    | Already implemented at `elements/Sidebar.tsx` — not a gap                         |
| Compliance rules for quote-moved (HIGH)      | Already in `blocking_rules.py:221-274` — not a gap                                |

---

## Approval Gate — PENDING

| Question                                                        | Answer  |
| --------------------------------------------------------------- | ------- |
| Q1 — Wave 1 scope correct (onboarding + tests + backtest)?      | PENDING |
| Q2 — Wave 2-4 ordering correct (value → trust → polish)?        | PENDING |
| Q3 — Start with Wave 1, defer remaining to subsequent sessions? | PENDING |
