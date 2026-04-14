# Execution Cost and Microstructure

**Status:** GOVERNING. Defines the transaction cost model, execution algorithm policy, slippage decomposition, gap risk, and participation caps.

Created in response to Redteam Round 1 — Trader C-1, C-2, C-3. The owner's brief explicitly required: _"apply accurate algorithms for transaction costs — fees, price impact, slippage, gap up, gap down."_ Phase 01 declared a `env.cost_budget` compliance rule without specifying the cost function. This spec closes that gap.

---

## 1. Principle

> **Every proposed trade is priced before it is proposed, and the price is a _distribution_, not a number. Trades that fail the cost gate never reach the Decisions surface.**

The transaction cost model is the substrate for:

- The `env.cost_budget` compliance rule (`11-` §3.1)
- Cost-aware sizing in the allocation and execution heads (`05-`)
- The "If approved" / "If rejected" brief sections (`07-` §2.3, §2.4)
- The Brinson attribution's Interaction effect (`12-` §3.1)

---

## 2. Cost Decomposition

Total expected cost of a trade = E[C_spread] + E[C_impact] + E[C_commission] + E[C_tax] + E[C_slippage] + E[C_gap].

Each term is a distribution with mean and variance; the compliance rule reads the upper quantile (e.g. 90th percentile) so we are robust to cost-tail risk.

### 2.1 Spread Cost `C_spread`

- **Inputs:** current quoted bid-ask spread from `quotes` table, rolling mean and stdev of spread in the last N minutes/days, time-of-day adjustments (opening 15 min + closing 15 min wider).
- **Functional form:** `C_spread = 0.5 × spread × |qty| × aggressiveness_factor` where aggressiveness_factor is determined by the execution algorithm (market ≈ 1.0, mid-seeking ≈ 0.3-0.6, passive ≈ 0.0 to slightly negative).
- **Uncertainty:** modeled via the rolling spread distribution, not a point estimate.

### 2.2 Market Impact `C_impact`

- **Default functional form:** **Almgren-Chriss** with square-root temporary impact and linear permanent impact: `C_impact = γ × σ × (q / ADV)^0.5 + η × σ × (q / V_schedule)` — parameters `γ`, `η` calibrated per instrument liquidity tier and regime band.
- **Challenger models in the execution pool** (per FP-9): Kyle's lambda, Obizhaeva-Wang, deep-learned impact — champion/challenger decided by out-of-sample calibration against realized impact in live and paper data.
- **Regime conditioning:** impact parameters are regime-conditional — impact is higher in Elevated/Urgent bands.

### 2.3 Commission `C_commission`

- **IBKR schedule** as data, versioned: fixed pricing OR tiered pricing based on account configuration; exchange fees; regulatory fees (FINRA TAF, SEC §31); minimum per-ticket commissions.
- **Point estimate** — commissions are deterministic given schedule + order size.
- **Updated when IBKR publishes changes.**

### 2.4 Tax / Dividend Withholding `C_tax`

- **Singapore domicile** (FP-6): no capital gains tax.
- **US-source dividends:** 30% withholding absent treaty; adjusted to ~15% for Ireland-domiciled UCITS alternatives where present.
- **C_tax in the model:** expected dividend-WHT drag integrated over the expected holding period (not the trade itself — this is a carry cost against target positions, factored into "If approved" projections).

### 2.5 Execution Slippage `C_slippage`

- **Inputs:** volatility at execution horizon, expected vs realized fill price distribution from historical IBKR fills (live and paper, with a paper-to-live adjustment factor per §6).
- **Functional form:** quantile regression on (vol, time-of-day, instrument liquidity tier, order type, regime band) → slippage quantile.
- **Uncertainty:** full distribution; compliance reads upper quantile.

### 2.6 Gap Risk `C_gap`

Gap risk = the PnL impact when an order is live across a discontinuity (open, close auction, halt resume, news event).

- **Inputs:** historical gap distribution per instrument at each known discontinuity (overnight, post-halt, post-earnings), plus a regime multiplier.
- **Application:** any order that cannot execute in a single continuous trading window carries a `C_gap` term = expected gap-PnL under the conditional distribution.
- **Compliance rule:** orders where `C_gap` exceeds a regime-adaptive threshold (tighter in Elevated/Urgent) require user approval even under L3/L4 autonomy.

---

## 3. Cost Function Inputs (Fabric Requirements)

For the cost model to compute, these inputs must be in the fabric. Missing inputs → stale-data gate trips (rule `data.stale_cost_inputs`, added).

| Input                        | Source                        | Cadence                              |
| ---------------------------- | ----------------------------- | ------------------------------------ |
| Quoted bid/ask (latest)      | `quotes` table (new in `03-`) | Real-time when active, EOD otherwise |
| Rolling spread statistics    | Derived                       | Updated each ingestion               |
| Trailing realized volatility | Features                      | Daily                                |
| ADV (average daily volume)   | Prices                        | Daily                                |
| Historical gap distributions | Derived                       | Weekly                               |
| IBKR commission schedule     | `fee_schedule` table (new)    | On IBKR publication                  |
| Execution slippage history   | `fills` table (new)           | Continuous                           |

---

## 4. Execution Algorithm Policy

Orders are not sent as single market orders. The execution head chooses a parent→child decomposition:

### 4.1 Algorithm Catalog (pool, not a pick — per FP-9)

| Algorithm                                         | When preferred                                          | Child order style                                 |
| ------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| Immediate liquidity                               | Very small size vs ADV, Urgent/Crisis band, exit path   | Marketable limit at bid+k or ask−k                |
| VWAP / TWAP                                       | Medium size, Calm/Elevated band, no directional urgency | Participation-cap tracking a volume or time curve |
| POV (Percentage of Volume)                        | Medium-to-large, liquidity-sensitive                    | Dynamic participation bounded by cap              |
| Implementation Shortfall (Almgren-Chriss optimal) | Large orders where impact dominates                     | Front-loaded or back-loaded per trader aversion   |
| Liquidity-seeking / passive midpoint              | Any size when cost is the binding constraint            | Passive midpoint resting with periodic repricing  |
| Auction participation                             | Opening/closing auctions for index-rebalancing days     | MOO / MOC                                         |

### 4.2 Selection Rule

The execution head (`05-` T-05-14 pool) selects per `(order_size / ADV, regime band, liquidity tier, deadline)`. Choice is logged for every order and feeds calibration against realized cost.

### 4.3 Participation Cap (New Compliance Rule `exec.participation_cap`)

- Default cap: order represents ≤ 5% of expected trading-session ADV unless user explicitly overrides.
- Regime-adaptive: tighter in Elevated (3%), Urgent (2%), Crisis (pause unless user overrides).
- Small-cap (S&P 600) gets a stricter cap — 2% default, 1% in Elevated+.

### 4.4 Child Order Scheduler

- Parent order → schedule of child orders per chosen algorithm.
- Each child carries its own TIF (Time-In-Force), venue preference (IBKR SmartRouting default; primary-exchange override available), price limit, reprice policy.
- IBKR rate-limit-aware pacing: child submission rate stays under 40 req/min (safety margin on the 50/min budget per Phase 01 A-H4), with priority queue (new child-submits beat polling queries).

---

## 5. Liquidity Tiering

Universe instruments are tiered by liquidity at `as_of` date. Tiering drives cost model parameters AND the participation cap.

| Tier          | Typical instruments                                        | Impact calibration                                               |
| ------------- | ---------------------------------------------------------- | ---------------------------------------------------------------- |
| L1 (deep)     | SPY, QQQ, IEF, TLT, GLD — top large-cap ETFs and mega-caps | Smallest γ, η                                                    |
| L2 (liquid)   | Sector ETFs, S&P 500 large caps                            | Default                                                          |
| L3 (moderate) | Smaller sector/style ETFs, S&P 400 mid caps                | Wider γ, η; participation cap tightens                           |
| L4 (thin)     | S&P 600 small caps, niche ETFs (AUM floor critical)        | Maximum caution; Elevated band auto-tightens to 1% participation |

Tier membership is re-evaluated on the same cadence as the universe review (monthly ETFs, quarterly S&P 1500).

---

## 6. Paper-vs-Live Adjustment

IBKR paper-trading fills are well-known to be optimistic (instant mid fills, no impact, stale NBBO). The cost model applies a **paper-to-live adjustment factor** (PLAF) to costs computed in paper-trading mode:

- PLAF is calibrated from the _one_ documented comparison: real historical IBKR live fills on similar instruments vs paper-fill data on the same instruments during the same windows.
- Default PLAF: 1.5× on spread, 2× on impact, +X bps added slippage. These are seeds — Bayesian update as live data accumulates.
- Paper-trading report (`08-` §6.2) reports costs BOTH raw-paper AND PLAF-adjusted. User reviews both.
- First live period uses an extended calibration window (weekly PLAF update) until stabilization.

---

## 7. Gap-Up / Gap-Down Handling (Explicit)

When an order is live across a known discontinuity:

| Discontinuity                      | Default behavior                                                                                                                                                        |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overnight (no-halt)                | Pending orders auto-cancelled at close unless GTC+extended; re-evaluated at open with fresh compliance check (fresh-price + gap-risk rules)                             |
| Opening auction                    | Never execute at market-on-open unless auction participation explicitly chosen; first 15 min use wider spread model                                                     |
| Closing auction                    | Only submit MOC orders when explicitly scheduled; last 15 min wider spread model                                                                                        |
| Halt resume                        | All outstanding orders for halted instrument auto-cancelled on halt detection; user notified; re-evaluation after halt clears triggers a new Decision                   |
| Earnings / event                   | Universe instruments flagged event-adjacent carry a `warn.event_adjacent` warning; execution defaults to deferring rebalance unless decision is explicitly event-driven |
| Circuit breaker (market-wide LULD) | All pending orders paused; trading halts until exchange resumes and compliance re-evaluates                                                                             |

---

## 8. Realized Cost Attribution

Every executed trade writes a `cost_attribution` row:

- Expected cost (mean + upper-quantile) at decision time
- Realized cost decomposed into spread / impact / commission / tax / slippage / gap
- Difference = cost-prediction error, feeds calibration of every cost term

Persistent systematic cost underestimation = degradation contract on the cost model; champion demotes, challenger promotes.

---

## 9. Compliance Rules Added To Registry

| Rule ID                                                            | Predicate                                       | Severity |
| ------------------------------------------------------------------ | ----------------------------------------------- | -------- |
| `env.cost_budget` (already exists; now has a computable predicate) | expected-cost upper quantile > remaining budget | block    |
| `data.stale_cost_inputs`                                           | any cost-model input is older than threshold    | block    |
| `exec.participation_cap`                                           | order size > tier-adjusted ADV cap              | block    |
| `warn.event_adjacent`                                              | instrument has a known event within window      | warn     |
| `warn.wide_spread`                                                 | current spread > (rolling_mean + N×stdev)       | warn     |

---

## 10. Relationship To Other Specs

- `specs/03-universe-and-data.md` — `quotes`, `fills`, `fee_schedule`, `cost_attribution` tables added
- `specs/05-model-pool-and-meta-router.md` — execution-head pool owns cost-model champions/challengers and execution-algorithm selection
- `specs/11-compliance-and-risk.md` — rules above added to `11-` §3
- `specs/14-ibkr-integration.md` — IBKR-specific rate limits, order types, rejection codes
- `specs/12-performance-and-track-record.md` — realized costs feed Brinson Interaction term and the track record score
