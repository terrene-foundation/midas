# M15 — IBKR Integration

**Spec anchors:** 02 §5.2, 11 §6.1.
**Depends on:** M01 (adapters), M12 (compliance), M13 (credentials).

## T-15-01 — IBKR Web API v1.0 OAuth handshake

**Objective:** OAuth 2.0 flow; token storage in encrypted `credentials`; refresh handled by T-13-02.
**Acceptance:** end-to-end OAuth against IBKR paper; token stored; positions queryable.

## T-15-02 — Order state machine

**Objective:** state machine pending → submitted → partial → filled → reconciled → attributed; durable in `orders` table.
**Invariants:** every state transition audited; terminal states are immutable.
**Acceptance:** Tier 2 walks all transitions.

## T-15-03 — Execution agent (order router)

**Objective:** service that consumes approved decisions, applies execution-head output (T-05-14), routes to IBKR with the priority queue (trades > monitoring > data).
**Invariants:** fresh price pulled at execution, `exec.freshness_at_execution` rule evaluated.
**Acceptance:** end-to-end against IBKR paper; fills reconcile.

## T-15-04 — Partial-fill handler

**Objective:** handle partial fills, reroute / cancel per policy; never leaves orders in indeterminate state.
**Acceptance:** Tier 2 simulated partial-fill test.

## T-15-05 — Rejected-order handler

**Objective:** IBKR rejections logged, surfaced to Pulse; compliance decides whether to retry or abandon.
**Acceptance:** Tier 2 injected rejection handled gracefully.

## T-15-06 — Rate-limit back-pressure

**Objective:** 50 req/min budget managed with priority queue; exponential backoff on 429; rebalance batches sized to stay under limits (Phase 01 A-H4).
**Acceptance:** synthetic batch hitting limit back-pressures correctly.

## T-15-07 — TWS fallback path

**Objective:** when Web API is unavailable, fall back to `ib_async` via TWS adapter; identical order state machine.
**Acceptance:** Tier 2 confirms fallback.

## T-15-08 — Post-execution reconciliation

**Objective:** compare filled quantities × prices to pre-trade brief; flag discrepancies.
**Acceptance:** reconciliation matches on synthetic fills.

## T-15-09 — Kill-switch order cancellation

**Objective:** on kill-switch trip, cancel all pending IBKR orders; confirm cancellations.
**Acceptance:** Tier 2 trip → all orders cancelled.

**Gate out:** end-to-end paper trade executes, reconciles, shows in brief; rate-limit tests pass; fallback tested.
