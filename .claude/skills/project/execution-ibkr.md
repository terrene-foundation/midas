# Execution & IBKR Integration

**Spec authority:** `specs/13-execution-cost-and-microstructure.md` (GOVERNING), `specs/14-ibkr-integration.md` (GOVERNING)
**Purpose:** Transaction cost decomposition, PLAF, IBKR Web API contract, order state machine, compliance rules

---

## Transaction Cost Decomposition

Total expected cost = E[C_spread] + E[C_impact] + E[C_commission] + E[C_tax] + E[C_slippage] + E[C_gap]

Each term is a **distribution** (mean + variance); compliance reads the **upper quantile** (e.g. 90th percentile).

| Term           | Formula                                                                          | Key Inputs                                                                        |
| -------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `C_spread`     | `0.5 × spread × \|qty\| × aggressiveness_factor`                                 | bid-ask from `quotes` table, time-of-day adjustments                              |
| `C_impact`     | `γσ(q/ADV)^0.5 + ησ(q/V_schedule)` (Almgren-Chriss)                              | regime-conditional; Kyle's lambda, Obizhaeva-Wang, or deep-learned as challengers |
| `C_commission` | IBKR schedule (fixed or tiered)                                                  | Account config, exchange fees, FINRA TAF, SEC §31                                 |
| `C_tax`        | Dividend-WHT drag over expected holding period                                   | Singapore domicile: no CG tax; US dividends: 30% withholding                      |
| `C_slippage`   | `quantile_regression(vol, time_of_day, liquidity_tier, order_type, regime_band)` | From `fills` table with PLAF adjustment                                           |
| `C_gap`        | Historical gap distribution per instrument per discontinuity type                | Overnight, post-halt, post-earnings                                               |

Missing cost inputs → `data.stale_cost_inputs` compliance rule trips (**blocks**).

---

## Paper-Live Adjustment Factor (PLAF)

IBKR paper fills are optimistic. PLAF applies to all paper-computed costs before the compliance agent reads them.

| Component | Default seed | Notes                                |
| --------- | ------------ | ------------------------------------ |
| Spread    | `× 1.5`      | Bayesian update as live data arrives |
| Impact    | `× 2.0`      |                                      |
| Slippage  | `+ X bps`    | Added slippage quantile              |

**PLAF gate:** clean paper report → NOT "safe in live." Clean paper → "begin carefully calibrated live trading with conservative sizing and L1 approval on every decision."

**First live period:** weekly PLAF update until stabilization. Canary: first N days run at L1 regardless of paper quality.

---

## IBKR Web API v1.0 — Rate Limits

| Limit               | Value                                        | Enforcement                             |
| ------------------- | -------------------------------------------- | --------------------------------------- |
| Global request rate | 50 req/min (IBKR hard limit)                 | **40/min soft cap** (20% safety margin) |
| Concurrent orders   | Conservative default (10 open parent orders) | Child-order scheduler enforces          |
| HTTP 429            | Temporary suspension + backoff               | Exponential backoff, queue drain        |

**Implementation:** `IBKRAdapter` uses `asyncio.PriorityQueue` per tier. Drain worker picks highest non-empty queue first.

**Priority tiers** (higher drains first):

| Tier | Type                                    | Drain Order |
| ---- | --------------------------------------- | ----------- |
| 5    | ORDER_SUBMIT (highest — money at risk)  | 1st         |
| 4    | FRESH_QUOTE (trade-adjacent compliance) | 2nd         |
| 3    | POSITION_BALANCE                        | 3rd         |
| 2    | ORDER_STATUS                            | 4th         |
| 1    | MONITORING                              | 5th         |
| 0    | BULK_DATA (lowest)                      | 6th         |

Compliance-gate check never starves: Tier 1–3 always drain before Tier 4–6.

---

## Order State Machine

IBKR states mapped to Midas canonical states:

| IBKR state         | Midas canonical     | Terminal?           |
| ------------------ | ------------------- | ------------------- |
| `PendingSubmit`    | `submitted_pending` | no                  |
| `PendingCancel`    | `cancel_pending`    | no                  |
| `PreSubmitted`     | `submitted_waiting` | no                  |
| `Submitted`        | `working`           | no                  |
| `Filled` (partial) | `partial_filled`    | no                  |
| `Filled`           | `filled`            | **yes**             |
| `Cancelled`        | `cancelled`         | **yes**             |
| `ApiCancelled`     | `cancelled_api`     | **yes**             |
| `Inactive`         | `inactive_flagged`  | no — **trap state** |

**`inactive_flagged` is a trap.** IBKR returns this when an order is technically open but will not execute (bad limit, risk reject). Midas treats this as a rejection and surfaces to user.

---

## Rejection Taxonomy

| IBKR code/class                    | Midas classification  | Handling                                         |
| ---------------------------------- | --------------------- | ------------------------------------------------ |
| 201 (order rejected — risk)        | `rejected.risk`       | Audit; surface to user; no auto-retry            |
| 202 (order cancelled — risk)       | `cancelled.risk`      | Audit; surface to user                           |
| Insufficient margin / buying power | `rejected.margin`     | Audit; envelope auto-tighten trigger             |
| Halted instrument                  | `rejected.halted`     | Cancel all outstanding; notify; block new orders |
| No market data permission          | `rejected.no_data`    | Alert; block further orders until resolved       |
| Price outside range                | `rejected.price_band` | Re-price once, then escalate                     |
| Unknown contract                   | `rejected.contract`   | Universe-error; block; manual review             |

All `rejected.*` states write to `orders` with full IBKR message.

---

## Quote-Moved-Since-Brief Protocol (T-00-18)

At biometric confirmation, fresh quote pulled. If mid-price moved by more than Δ since brief:

| Regime   | Δ threshold | Strictness     |
| -------- | ----------- | -------------- |
| CALM     | 0.5%        | strictly below |
| ELEVATED | 0.3%        | strictly below |
| URGENT   | 0.2%        | strictly below |

**Approval does NOT auto-execute.** Modal surfaces: "Price moved X% since brief. Proceed, set a limit, or cancel?" Audit records both prices.

---

## Participation Caps (Compliance Rule `exec.participation_cap`)

| Regime              | Cap                      | Notes                 |
| ------------------- | ------------------------ | --------------------- |
| Calm                | ≤ 5% of ADV              |                       |
| Elevated            | ≤ 3%                     |                       |
| Urgent              | ≤ 2%                     |                       |
| Crisis              | Pause                    | unless user overrides |
| Small-cap (S&P 600) | 2% default, 1% Elevated+ |                       |

---

## Kill Switch — Process Lock

**No 15-minute timer.** Clear sequence:

```
ACTIVE → begin_clear_flow → BRIEF_READ → acknowledge_brief → BRIEF_ACKNOWLEDGED
→ complete_clear → CLEARED
```

Post-clear:

- 60-second dwell before first post-clear decision
- Autonomy reverts to L1 regardless of prior level
- `cancel_all_pending()` cancels orders in `PENDING` or `SUBMITTED` states only

---

## TWS Fallback Adapter

- Lazy connection: `ib_async.IB()` created on first call
- Port: 7496 (live), 7497 (paper)
- `fetch_sweep_events()` returns empty — ib_async does not expose FX sweep events in v1
- No auto-hedge for FX in v1 (tracked and reported only)

---

## Execution Safety Rules

### NaN/Inf Guard

```python
# DO — guard every financial float reaching a brief or API
import math
nav = positions_value + cash - unsettled
if not math.isfinite(nav):
    logger.warning("nav.non_finite", nav=nav)
    nav = 0.0
brief["nav"] = nav

# DO NOT — raw float in brief
brief["nav"] = positions_value + cash - unsettled  # NaN/Inf poisons brief
```

**Why:** NaN reaching a user-facing brief creates silent wrong decisions; Inf crashes API serialization.

---

### Near-Zero Division Guard

```python
# DO
if mid > 1e-10:
    spread_bps = (ask - bid) / mid * 10000

# DO NOT
if mid:  # passes for 0.0, gives inf spread
    spread_bps = (ask - bid) / mid * 10000
```

**Why:** `if mid` is True for 0.0, producing division-by-zero → inf, which propagates into cost estimates and compliance decisions.

---

### Credential Safety in Error Messages

```python
# DO — no response body in error
raise AdapterError(f"IBKR request failed: status={response.status_code}")

# DO NOT — response body may contain OAuth tokens
raise AdapterError(f"IBKR request failed: {response.text[:200]}")
```

**Why:** `response.text[:200]` can contain bearer tokens or session cookies from IBKR's OAuth flow, leaking credentials into logs.

---

### No Market Orders in Calm/Elevated

```python
# DO — use limit orders
order = {"type": "LMT", "limit_price": best_bid}

# DO NOT — market orders only for crisis exits
order = {"type": "MKT"}  # fills immediately but worst-case fill
```

**Why:** Market orders in Calm/Elevated guarantee immediate execution at worst-case prices; limit orders cost latency but preserve price integrity.

---

### Parent→Child Order Decomposition

```python
# DO — parent order decomposes into child schedule
children = scheduler.schedule(parent, algorithm="vwap", participation=0.03)
for child in children:
    await ibkr.submit(child)

# DO NOT — single parent order sent as-is
await ibkr.submit({"type": "MKT", "qty": 10000})  # full market order
```

**Why:** Single market orders absorb full market impact; child-order decomposition disperses impact over time and venue.

---

### PLAF on Paper Costs

```python
# DO — apply PLAF before compliance reads paper costs
paper_cost = raw_paper_cost()
adjusted_cost = {
    "spread": paper_cost["spread"] * 1.5,
    "impact": paper_cost["impact"] * 2.0,
    "slippage": paper_cost["slippage"] + Decimal("0.0002"),
}
compliance.check(adjusted_cost)

# DO NOT — check raw paper costs
compliance.check(raw_paper_cost())  # paper fills are optimistic
```

**Why:** IBKR paper fills assume instant mid-price execution with zero impact; compliance that reads raw paper costs will approve trades that would be 2–5× more expensive live.

---

### Stale Cost Inputs Block

```python
# DO — block if any input is stale
if any(is_stale(v) for v in [spread, vol, adv]):
    raise ComplianceBlock("data.stale_cost_inputs", inputs=stale_fields)

# DO NOT — compute with stale data silently
cost = compute_cost(spread=spread, vol=vol)  # spread from yesterday
```

**Why:** Stale spread or volatility data produces cost estimates that don't reflect current market conditions; a stale spread can be 10× wider than current reality.
