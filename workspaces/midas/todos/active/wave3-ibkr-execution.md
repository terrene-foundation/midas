# Wave 3 — Make It Trustworthy

GAP-2 (IBKR Order States + Rejection Taxonomy, CRITICAL)

**Session estimate:** 1-2 sessions
**Spec anchors:** 14 (IBKR integration)

---

## GROUP G: IBKR Order State Machine (GAP-2)

**Current state:** `OrderState` enum in `fabric/models.py:313-367` defines all 9 values with `from_ibkr()` classmethod. `OrderStateTransition` model exists. But there is no state machine enforcing legal transitions, no rejection taxonomy beyond catch-all `REJECTED`, and no `OrderManager` class. The execution module handles only decomposition, not lifecycle.

### BUILD Todos

**2A. Build OrderStateMachine with legal transition graph**

- Create `src/midas/execution/state_machine.py`. Enforces legal IBKR state transitions per spec 14 S6. Accepts `OrderState` + trigger, validates legality, produces new state + `OrderStateTransition` record. All 8 non-rejected states reachable. `inactive_flagged` trap state handled with explicit user surfacing.
- **Spec:** 14 S6 (order state table, terminal flags, inactive_flagged trap)
- **LOC:** ~250 load-bearing
- **Invariants:** (1) Only legal transitions permitted; illegal raise `IllegalTransitionError` with from/to/reason. (2) Terminal states (filled, cancelled, cancelled_api) accept no further transitions. (3) `inactive_flagged` is trap state triggering user notification, no auto-transition. (4) Every transition produces immutable `OrderStateTransition` with audit fields. (5) Initial state always `SUBMITTED_PENDING`.
- **Dependencies:** None (uses existing `OrderState` + `OrderStateTransition` models)
- **3 sentences:** Enforces 8-state IBKR order lifecycle so illegal transitions are caught at the state machine layer. Produces audit-grade transition records for every state change. Handles the `inactive_flagged` trap state with explicit user surfacing per spec.

**2B. Build RejectionCode taxonomy and classification**

- Create `src/midas/execution/rejection.py` with `RejectionCode` enum for all 8 spec 14 S7 codes (risk, cancelled.risk, info, margin, halted, no_data, price_band, contract). Each code carries handling strategy, severity, user-surfacing requirement. `classify_rejection(ibkr_code, ibkr_message)` maps raw responses to typed codes.
- **Spec:** 14 S7 (rejection code taxonomy table)
- **LOC:** ~180 load-bearing
- **Invariants:** (1) Every IBKR rejection code maps to exactly one `RejectionCode`. (2) All `rejected.*` codes write to orders table with full IBKR message. (3) Unknown codes fall to `RejectionCode.UNKNOWN` with audit + surfacing. (4) `rejected.risk` and `rejected.margin` never auto-retry. (5) `rejected.halted` kills all outstanding for instrument.
- **Dependencies:** 2A (rejection feeds into state machine transition)
- **3 sentences:** Maps 8 IBKR rejection codes into typed Python enums with per-code handling strategies. Unknown codes caught by typed fallback, not silently swallowed. Every rejection writes full IBKR message to orders table for compliance rule aggregation.

**2C. Build OrderManager with state machine + audit integration**

- Create `src/midas/execution/order_manager.py`. Takes DataFlow instance + IBKR adapter. Methods: `submit_order()`, `cancel_order()`, `process_ibkr_status_update()`, `get_order_state()`. Each drives state machine, writes `OrderStateTransition` to fabric, surfaces rejections/inactive to notification layer. Follows manager-shape pattern from `rules/facade-manager-detection.md`.
- **Spec:** 14 S6-S7
- **LOC:** ~300 load-bearing
- **Invariants:** (1) Every state change through state machine (no direct `OrderState` mutation). (2) Every transition persisted to fabric before returning. (3) Constructor receives DataFlow explicitly (no global lookup). (4) `process_ibkr_status_update()` is single entry point for IBKR-driven transitions. (5) Rejection codes classified and persisted alongside transition. (6) Partial fills update `fill_quantity` without terminal state change.
- **Dependencies:** 2A, 2B
- **3 sentences:** Orchestrates order lifecycle from submission through terminal state, persisting every transition for audit. Classifies IBKR rejections into typed taxonomy and surfaces user-actionable states. Follows manager-shape pattern for facade exposure.

### WIRE Todos

**W2A. Wire IBKR adapter status updates through OrderManager**

- Wire IBKR adapter poll results through `OrderManager.process_ibkr_status_update()` so every IBKR status change drives state machine + writes `OrderStateTransition` to fabric. Replace direct `OrderState` construction in adapter.
- **Spec:** 14 S6
- **Verification:** Submit test order via IBKR paper adapter → poll status → `OrderStateTransition` rows in fabric with correct from/to/reason/ibkr_message.

**W2B. Wire rejection notifications to dispatch interface**

- When `OrderManager` processes rejection or inactive state, call lightweight `NotificationDispatch.dispatch(event_type, payload)` — thin abstraction that Wave 4 later wires to actual delivery. For now: logs at INFO + writes to `audit_log` fabric table so rejection events are never lost.
- **Spec:** 14 S7 (default handling requires user alert for margin/risk/halted)
- **Verification:** Simulate margin rejection → `audit_log` row with event_type="order_rejected" + rejection code + instrument.

**W2C. Wire OrderManager to execution facade**

- Expose `OrderManager` on a public facade (e.g., `execution.order_manager`). Add Tier 2 wiring test `tests/integration/test_order_manager_wiring.py` importing through facade, triggering state transition, verifying `OrderStateTransition` in fabric. Per `rules/facade-manager-detection.md`.
- **Spec:** 14 S6-S7, `rules/facade-manager-detection.md`
- **Verification:** Tier 2 test: import through facade, process status update, read back transition from fabric.

### Regression Tests

**R8. Regression: Order state machine**

- File: `tests/regression/test_order_state_machine.py`
- Tests: all non-terminal states reachable from SUBMITTED_PENDING, terminal states block transitions, inactive_flagged is trap, all 8 rejection codes classified, unknown IBKR code falls to UNKNOWN, risk rejection never auto-retries, halted kills outstanding, partial fill updates quantity not state.
- **Marker:** `@pytest.mark.regression`

---

## Execution Order

Sequential chain: 2A → 2B → 2C → W2A + W2B → R8

Can be completed in 1 session (total ~730 LOC load-bearing across 3 build todos, within capacity with the feedback loop from TDD).

If pairing with Wave 2's GROUP F (ModelRegistry, ~200 LOC), both fit in a single session with 2 agents.
