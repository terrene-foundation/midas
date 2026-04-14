# IBKR Integration

**Status:** GOVERNING. Defines the IBKR-specific operational contract: rate limits, order states, rejection taxonomy, paper vs live endpoints, IBKR-SG entity specifics, partial-fill-during-approval protocol, and session management.

Created in response to Redteam Round 1 — Trader C-4. Phase 01 declared "IBKR Web API v1.0" four times without engaging with the operational detail. This spec closes that gap.

---

## 1. Principle

> **IBKR is the one piece of real-world infrastructure Midas does not own. Every IBKR-specific quirk, limit, and failure mode is captured here as an explicit contract.**

If IBKR changes behavior, this spec is the first thing that updates.

---

## 2. Transport And Endpoints

### 2.1 Primary: IBKR Web API v1.0

- OAuth 2.0 handshake per `11-` §6.1
- Endpoints versioned; Midas pins to v1.0 and tracks IBKR release notes
- Paper-trading endpoint is **separate** from live endpoint — hostname + account ID differ; enforced by `state.paper_trading` compliance rule
- Session keepalive: Midas maintains a long-lived session; reauthentication on expiry via refresh token (background job T-13-02)

### 2.2 Fallback: TWS via `ib_async`

- Used only when Web API is unavailable
- Requires local TWS / IB Gateway process; Midas detects its availability via port probe
- Order state machine (`15-` T-15-02) is identical across both transports — the adapter normalizes

### 2.3 Entity: IBKR Singapore

- Midas account is held at IBKR-SG (the owner is Singapore domicile, FP-6)
- SIPC coverage does **not** apply (US-only); Monetary Authority of Singapore regulations apply
- Settlement in SGD or USD per instrument; FX sweep policy captured in `03-` §2.1

---

## 3. Rate Limits

| Limit                     | Value                                        | Enforcement                                             |
| ------------------------- | -------------------------------------------- | ------------------------------------------------------- |
| Global request rate       | 50 req/min (IBKR documented)                 | Priority queue with 40/min soft cap (20% safety margin) |
| Concurrent orders         | Conservative default (10 open parent orders) | Child-order scheduler enforces                          |
| Pacing violation response | HTTP 429 + temporary suspension              | Exponential backoff, queue drain                        |
| Historical data request   | Per-instrument throttling                    | Batched at ingestion, not on demand                     |

### 3.1 Priority Queue

Requests are tiered. Higher tier drains first:

1. **Order submission / cancellation** (highest — money is at risk)
2. **Fresh quote pull for compliance `exec.freshness_at_execution`** (trade-adjacent)
3. **Position / balance reconciliation** (trade-adjacent)
4. **Pending order status polling**
5. **Monitoring quote polling**
6. **Bulk data ingestion** (lowest)

Tier 1-3 always drain before Tier 4-6. A compliance-gate check never starves.

---

## 4. Order Types (Allowed In v1)

| Order type | Usage                                          | Notes                                 |
| ---------- | ---------------------------------------------- | ------------------------------------- |
| LMT        | Default                                        | Limit price comes from execution head |
| MKT        | Emergency exit only, auction submission        | Blocked by default in Calm/Elevated   |
| MOC / LOC  | Closing auction participation                  | Scheduled, opt-in per order           |
| MOO / LOO  | Opening auction participation                  | Scheduled, opt-in per order           |
| STP LMT    | Kill-switch exit in thin-liquidity instruments | Used by kill-switch cleanup only      |

Not supported in v1: OCA groups, algos beyond what the execution head implements locally, options-related types, spreads, combos.

---

## 5. TIF (Time-In-Force)

| TIF | Usage                                                            |
| --- | ---------------------------------------------------------------- |
| DAY | Default for intraday execution                                   |
| IOC | Used by immediate-liquidity algorithm                            |
| GTC | Used for multi-day scheduled child orders when explicitly chosen |
| GTD | Used when the execution window has a hard deadline               |

---

## 6. Order State Machine

Full IBKR order-state enumeration mapped to Midas states:

| IBKR state          | Midas state                       | Terminal?                  |
| ------------------- | --------------------------------- | -------------------------- |
| `PendingSubmit`     | `submitted_pending`               | no                         |
| `PendingCancel`     | `cancel_pending`                  | no                         |
| `PreSubmitted`      | `submitted_waiting` (broker-held) | no                         |
| `Submitted`         | `working`                         | no                         |
| `Filled` (partial)  | `partial_filled`                  | no                         |
| `Filled` (complete) | `filled`                          | yes                        |
| `Cancelled`         | `cancelled`                       | yes                        |
| `ApiCancelled`      | `cancelled_api`                   | yes                        |
| `Inactive`          | `inactive_flagged`                | no (requires intervention) |

`inactive_flagged` is a trap state — IBKR returns this when an order is technically open but will not execute (bad limit, risk reject). Midas treats this as a rejection and surfaces it to the user.

---

## 7. Rejection Code Taxonomy (Partial; Expanded As Encountered)

| IBKR code / class                  | Midas classification  | Default handling                                          |
| ---------------------------------- | --------------------- | --------------------------------------------------------- |
| 201 (order rejected — risk)        | `rejected.risk`       | Audit; surface to user; no auto-retry                     |
| 202 (order cancelled — risk)       | `cancelled.risk`      | Audit; surface to user                                    |
| 399 (forwarded to destination)     | info                  | Logged                                                    |
| Insufficient margin / buying power | `rejected.margin`     | Audit; tighten envelope auto-tighten trigger; user alert  |
| Halted instrument                  | `rejected.halted`     | Kill all outstanding for instrument; audit; notification  |
| No market data permission          | `rejected.no_data`    | Alert; block further orders for instrument until resolved |
| Price outside range                | `rejected.price_band` | Execution head re-prices once, then escalates             |
| Unknown contract                   | `rejected.contract`   | Universe-error; block; audit; manual review               |

All `rejected.*` states write to `orders` with full IBKR message; the `api.ibkr_health` rule aggregates rejection rate over rolling windows.

---

## 8. Partial-Fill-During-Pending-Approval Protocol (Redteam H-4)

A real failure mode not covered in Phase 01: the execution head begins working a parent order while an approval is still in-flight on the mobile app. Partial fills accumulate. The user's biometric arrives after the quote moved 2%.

### 8.1 Rule

Orders that require user approval under the current autonomy level MUST NOT begin working until approval is confirmed. The `autonomy.level_breach` + `escalate.urgent_band` compliance rules gate submission, not just proposal.

### 8.2 Quote-Moved-Since-Brief Handling

Every approval ships with the quote snapshot at brief-composition time. At the moment of biometric confirmation:

- Fresh quote is pulled (`exec.freshness_at_execution` rule)
- If mid-price has moved by more than `Δ` (regime-adaptive: Calm 0.5%, Elevated 0.3%, Urgent 0.2%) since the brief, the approval **does not auto-execute**
- UI surfaces a modal: "Price moved X% since brief. Proceed at current price, set a limit, or cancel?"
- User confirms explicitly; audit records both prices

### 8.3 In-Flight Approval + Rapid Market Move

If during the approval window (the time between decision proposal and user action) the market moves such that the approval's thesis is materially invalidated (e.g. the "If rejected" case materializes), the decision is **auto-revised**: user sees "Since proposing this, [thing] happened. Here is the updated proposal." No auto-execution of the stale proposal.

---

## 9. IBKR Paper Trading Realism

The Redteam H-3 critique: IBKR paper fills are optimistic.

### 9.1 What Paper Fills Get Wrong

- Instant fills at the mid (no queue, no partial, no reprice)
- Zero market impact
- Optimistic NBBO (quote snapshots may be stale)
- No halts, no risk reject, no exchange throttle
- Unrealistic auction behavior

### 9.2 What This Spec Requires

- **Paper-to-live adjustment factor** (PLAF) per `specs/13- §6` applied to all paper-computed costs before the compliance agent reads them
- Paper-trading report (`08-` §6.2) reports both raw-paper and PLAF-adjusted performance; user sees both
- **Canary period in live:** first N days live run at L1 regardless of paper-trading cleanness (already in `08-` §6.4) AND with a weekly PLAF recalibration. This is the honest way to discover paper-vs-live drift.
- The paper→live gate does NOT claim "clean paper report → safe in live." It claims "clean paper report → safe to begin carefully calibrated live trading with conservative sizing and L1 approval on every decision."

### 9.3 Partial Fills In Paper

IBKR paper does not simulate partial fills realistically. Midas synthesizes partial-fill training scenarios in a dedicated fabric namespace (`fills_synthetic`) to ensure the order state machine handles them before the user ever sees a real partial in live.

---

## 10. Halts, Auctions, Circuit Breakers

| Event                                             | Detection                             | Response                                                                                              |
| ------------------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Single-name halt (LULD, news-pending, volatility) | IBKR status feed + price-band rejects | Cancel outstanding; notify user; `warn.halted` added to affected instrument universe-status           |
| Opening auction                                   | Scheduled (9:30 ET ± market-specific) | Orders flagged "first 15 min" use wider spread + impact; MOO opt-in only                              |
| Closing auction                                   | Scheduled                             | MOC opt-in only; last 15 min wider spread                                                             |
| LULD limit-up/down                                | IBKR + price-band rejects             | Participation cap tightens to 1%; user escalation                                                     |
| Market-wide circuit breakers (Level 1/2/3)        | NYSE / NASDAQ status feed             | All pending cancelled; no new orders until exchange resumes + compliance re-evaluates; UI Crisis band |

---

## 11. FX, Currency Exposure, Sweep

- Account base can be SGD or USD; per-instrument-class currency of trade differs
- Midas tracks exposure per currency in the fabric
- **No auto-hedge in v1** — currency exposure is tracked and reported, hedged positions are user-explicit decisions
- IBKR auto-sweep between USD / SGD per account config; Midas reads the sweep policy and surfaces it in Settings

---

## 12. Compliance Rules Added To Registry

| Rule ID                        | Predicate                                      | Severity                               |
| ------------------------------ | ---------------------------------------------- | -------------------------------------- |
| `api.ibkr_rate_limit`          | In-flight request rate > 40/min soft cap       | throttle (queue drains at slower rate) |
| `api.ibkr_session_invalid`     | Session token invalid / refresh failed         | block + escalate                       |
| `exec.quote_moved_since_brief` | Fresh quote vs brief quote > Δ regime-adaptive | escalate (user re-confirm)             |
| `warn.halted`                  | Instrument in halt state                       | warn + block new orders for instrument |
| `warn.auction_window`          | Order submitted during opening/closing 15 min  | warn                                   |

---

## 13. Relationship To Other Specs

- `specs/03-universe-and-data.md` — `quotes`, `fills`, `fills_synthetic`, `fee_schedule`, `cost_attribution`, `sweep_history` tables
- `specs/11-compliance-and-risk.md` — rules above land in `11-` §3
- `specs/13-execution-cost-and-microstructure.md` — PLAF mechanics, participation caps, execution algorithms
- `specs/15-ibkr-integration.md` milestone (`todos/active/15-ibkr-integration.md`) — implementation todos read from this spec
