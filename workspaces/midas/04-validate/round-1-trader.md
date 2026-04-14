# Redteam Round 1 — Buy-Side Trader

**Persona:** Senior buy-side trader, institutional equity desk, 20 years
**Spec set audited:** `specs/_index.md`, `01-user-persona.md`, `02-value-chain.md`, `03-universe-and-data.md`, `08-autonomy-and-trust.md`, `10-moments-of-truth.md`, `11-compliance-and-risk.md`
**Date:** 2026-04-14

## Overall assessment

This spec set reads like a DL/ML architecture spec with a portfolio-management vocabulary layered on top. It is internally coherent on abstractions (latent state, meta-router, PACT rules) and aggressively specified on autonomy/UX guardrails. It is structurally silent on virtually every aspect of actual order execution on a live venue. There is no order type policy, no child-order scheduler, no market-impact model, no spread/slippage estimator, no venue/auction-state handling, no IBKR throttle/rate-limit design, no halt/LULD handling, no FX hedge specification, no dividend withholding mechanics in the cost budget, and no acknowledgment that IBKR paper fills lie. `02-` §5.2 is seven bullet points where a live-trading spec would have a dedicated document. `11-` §3.1 lists `env.cost_budget` and `exec.freshness_at_execution` as rules but defines no function to compute either. The brief owner explicitly asked for "accurate algorithms for transaction costs — fees, price impact, slippage, gap up, gap down" — the spec does not deliver any of these. This is not implementation-ready; this is a research-platform spec with a trading veneer. A clean paper-trading report under this spec will NOT predict live performance, and the L0→L1 gate as written does not notice.

---

## CRITICAL Findings

### C-1. No transaction cost model. `11-` §3 / §4, `02-` §5.1–5.2

**Description:** The cost budget appears as a compliance rule (`env.cost_budget`) and a hard safety limit, and `02-` §3.3 says "every proposed trade must clear expected-alpha > expected-cost with cost estimated by the execution pool" — but the cost function is nowhere specified. There is no bid-ask spread model. No commission schedule. No exchange/regulatory fee table (SEC §31, FINRA TAF, NSCC). No market impact model (linear? sqrt-law? Almgren-Chriss?). No slippage decomposition. No gap-risk model for overnight, opening-auction-only execution, or halts. "Cost budget" is declared; the thing it budgets is undefined.

**Why it matters in practice:** Cost-aware sizing without a real cost model is cost-indifferent sizing with a checkbox. On S&P 600 small caps at $100–$500K portfolio size, a single poorly-sized trade can be 5–20% of ADV; a half-spread there is 30–100bps, not the 2bps you see on SPY. A model trained on EODHD OHLCV has zero signal about the spread it will cross. The alpha > cost gate will systematically approve trades whose modeled cost is near zero while real cost is a material drag. Over a year this is the difference between positive and negative attribution at the Selection layer. Compounded with the attention budget, you will ship a system whose Brinson Selection effect in paper is +X%, reality is -Y%, and the user upgrades to L2 on fiction.

**Concrete fix:**

1. Add a new spec `specs/13-execution-cost-and-microstructure.md` that defines:
   - Commission schedule (IBKR tiered/fixed per symbol class) as data.
   - Exchange/regulatory fee tables (SEC §31, FINRA TAF, NSCC, OCC where relevant).
   - Half-spread estimator per instrument, from rolling quoted-spread samples (requires spread ingestion — see C-3).
   - Market impact model — specify the functional form. Start with sqrt-law (`impact = σ · sqrt(Q/ADV)`) as default; document Almgren-Chriss (temporary + permanent) as an option. Specify where calibration coefficients come from and how they update.
   - Gap risk model: overnight return variance conditional on recent vol state; auction-only execution penalty; LULD/halt expected-slippage factor.
2. Every proposed trade gets a cost estimate with uncertainty band. `exec.freshness_at_execution` becomes a member of a broader `exec.cost_model_delta` rule (did realized execution cost fall within model CI).
3. Cost model is a first-class head with its own calibration tracking, same as the return heads.

### C-2. No child-order scheduler, no execution algorithm, no order-type policy. `02-` §5.2

**Description:** `02-` §5.2 says "Orders routed to IBKR Web API v1.0 ... Execution agent tracks partial fills, reroutes or cancels as needed." That is not an execution spec. It does not say:

- Does a parent order split into children? On what schedule (TWAP, VWAP, POV, IS)?
- What order types are used — LMT, MKT, MOO, MOC, MID-PRICE, ADAPTIVE? IBKR exposes 50+.
- What is the urgency/price-improvement tradeoff policy per regime band?
- What is the time-in-force policy (DAY vs GTC vs IOC vs FOK)?
- What happens when the parent is a 3% ADV rebalance of a small cap?
- When does the execution agent cancel-and-replace vs stay resting?
- Under IBKR's 50-req/min REST rate limit, how many children per minute is feasible? Is the scheduler back-pressure-aware?
- During the opening/closing auction windows, how are orders timed? Midas is EOD-driven — does the cross fire MOO, MOC, or work the book intraday?

**Why it matters in practice:** "The execution agent handles it" is the sentence that produces 15bps of unexplained slippage per rebalance. On a $300K book with 8% weekly turnover, that is ~$3.5K/year of silent leak — 1.2% of capital — that won't show up in Brinson because it hides inside realized prices. The scheduler is the difference between institutional-grade and Robinhood. The spec claims the former; the text describes the latter.

**Concrete fix:**

1. Add `specs/13-execution-cost-and-microstructure.md` §2 (or a dedicated `14-execution-scheduler.md`) covering: parent→child decomposition, default algo per size-bucket × regime-band, order-type default + override rules, TIF policy, IBKR rate-limit-aware pacing.
2. Minimum v1 policy: ETF rotation → VWAP over closing 2 hours with MOC finisher for residual; S&P 1500 single-name (v1.1) → POV (5–10%) with hard LIMIT collar, auction participation rules explicit.
3. Compliance rule `exec.participation_cap`: blocks any parent whose participation would exceed a fraction of ADV (default 5%).
4. Record realized algo fills back to the cost-model calibration loop.

### C-3. Bid-ask spread never ingested. `03-` §2.1, §2.5, `02-` §5.2

**Description:** The data catalog ingests OHLCV, corporate actions, news, macro, filings, and derived series. It does not ingest quotes. §2.1 says IBKR provides "real-time bid/ask, positions, account balance, order status" but only for "Execution-time price pull." Quotes are not in the fabric, are not in the feature store (§4), and are not available to the cost model, the selection head, or any backtest. The same spec declares a cost budget that depends on them.

**Why it matters in practice:** You cannot estimate half-spread from OHLCV. You cannot calibrate a market-impact coefficient without volume and quote data. You cannot backtest a cost-aware allocator without historical spreads. "Spread proxied from high-low-close" is the standard hack and it is wrong by 3–10× for small caps. If the spec is silent on spread ingestion, the cost model has no inputs, which is why C-1 is possible.

**Concrete fix:**

1. Add `quotes` table to the fabric (§3.3): NBBO snapshots at configurable cadence + end-of-day snapshot at minimum.
2. Document source: IBKR historical bid/ask snapshots during active polling; end-of-day NBBO from an explicit source (IBKR, EODHD Fundamentals Plus, or OPRA direct — pick one, name it).
3. Feature: rolling 20-day median quoted spread per instrument, used by cost model and by selection-head cost-gating.
4. Backfill policy: backtests use historical spreads from source; no hack-from-OHLCV estimators as primary path.

### C-4. IBKR-specific operational constraints are not specified. `02-` §5.2, `11-` §7

**Description:** The spec names IBKR four times and never engages with IBKR's actual constraints:

- **REST rate limit** — nominally 50 req/min per session; burst behavior is non-obvious; endpoint-specific caps.
- **Web API v1.0 session lifetime** — sessions expire; tickler must run; re-auth flow is manual-OOB in the worst case. Can a headless bot keep a session live 24/7 in production? The spec assumes yes.
- **Order state machine is IBKR-shaped** — `PendingSubmit / PreSubmitted / Submitted / Filled / Cancelled / ApiCancelled / Inactive` plus partials. `02-` §6.3 lists "pending → submitted → partial → filled → reconciled" which is a simplified subset. Where does `Inactive` (rejected by compliance at IBKR's end) map? Where does `ApiCancelled` vs `Cancelled` distinction live?
- **Rejection reasons** — IBKR returns specific error codes (200, 201, 202, 103, 399 warnings, etc.). Spec mentions "rejected orders" once in `02-` §6.3 as a bullet.
- **Paper vs live accounts** — different account IDs, different endpoints in practice, different fill logic, different margin models.
- **Singapore account specifics** — IBKR-SG entity, SGD sweep, multi-currency FX conversion, PFIC implications for certain ETFs. None of this appears.

**Why it matters in practice:** Phase 01 A-H4 flagged IBKR integration risk. The spec resolves it with "Kailash framework mapping" boilerplate. In production: a missed session refresh = 24 hours of no execution; rate-limit saturation during a rebalance = partial-fills orphaned in the queue; a `399 Order held while securities are located` on a hard-to-borrow name silently blocks a trade that the compliance agent passed.

**Concrete fix:**

1. Add `specs/14-ibkr-integration.md`: session lifecycle (keepalive cadence, re-auth flow, failure escalation), rate-limit budgeting (token bucket, per-endpoint), full IBKR order-state enumeration mapped to Midas state machine, rejection-code taxonomy with per-code action, paper vs live endpoint table, IBKR-SG specifics (account structure, SGD sweep, FX conversion fees, withholding).
2. Compliance rule `api.ibkr_health` (already listed) gets a concrete predicate: session-age, recent-reject-rate, rate-limit-headroom, heartbeat-age.
3. Define back-pressure: when rate-limit headroom < threshold, new submissions queue with priority; Urgent/Crisis bypass; audit records overflow.

### C-5. No halt/auction/circuit-breaker handling. `02-` §5.2, `10-` §6, `11-` §3

**Description:** The spec has zero words about what happens when:

- A target instrument is halted (LULD band exceeded, news pending, regulatory).
- Market is in opening auction (9:30 ET first print) or closing auction (last 5 min MOC imbalance).
- Market-wide circuit breaker (Level 1/2/3, 7%/13%/20%) triggers.
- An ETF's NAV diverges significantly from its intraday price during stress (ETF creation/redemption arb breaks).
- A pending Urgent-band approval is sitting in the user's notification queue while the underlying is halted or gapping.

**Why it matters in practice:** ETF liquidity is not a constant. In the March 2020 drawdown, corporate-bond ETFs (HYG, LQD) traded at -5% to -8% discounts to NAV for hours. An allocator trained on calm-state correlations between NAV and price will size LQD like it's always tight. The spec lists HYG and LQD in the v1 universe (`03-` §1.1). A target-position change to LQD during a vol spike, routed as a MKT order per default IBKR routing, executes at a price the cost model did not predict — and there is no mechanism to detect the dislocation pre-trade.

**Concrete fix:**

1. `exec.halted_instrument` blocking rule — checks halt state via IBKR status before submission; on halt, decision is held not cancelled.
2. `exec.auction_window` rule — if parent order intersects opening 5 min or closing 5 min, default is to schedule around the window unless explicitly configured MOO/MOC.
3. `exec.market_wide_halt` — MWCB L1 pauses new submissions for its 15-min window; L2 pauses for the day; L3 auto-trips kill switch.
4. `exec.etf_nav_discount` — when an ETF's IOPV vs last trade differs by > threshold, the trade is held or downsized.
5. All four map to audit records and to the brief shown to the user when the decision re-emerges.

---

## HIGH Findings

### H-1. Cost budget without dividend withholding + FX. `11-` §3, `03-` §1.2

**Description:** `03-` §1.2 acknowledges 30% US WHT for Singapore residents and Ireland-UCITS alternatives. But:

- The cost budget predicate (`env.cost_budget`) doesn't mention dividend withholding as a cost component.
- There is no explicit USD/SGD currency exposure model. The user is Singapore-domiciled; portfolio is USD-denominated via IBKR. Every USD holding is an implicit SGD-short.
- There is no hedge-decision machinery. Hedge or don't? If hedge, via which instrument (FX forward, UUP/FXE, DXY-linked)? At what net-USD threshold?
- `warn.fx_exposure` is a one-line warning rule with no computation behind it.

**Why it matters in practice:** A 10% SGD appreciation against USD wipes out a year of alpha for an unhedged Singapore investor holding SPY. The user's job-to-be-done is "institutional-grade portfolio desk." Every institutional desk with cross-currency exposure has an explicit FX policy. This one has a warning.

**Fix:** Add `specs/15-currency-and-withholding.md`: USD/SGD exposure computation (net position by currency), hedge policy (target FX exposure band, hedge instruments, hedge cost), dividend withholding modeled per-instrument per-domicile (US ETF 30%, Ireland UCITS 15%, etc.) and subtracted from expected return in the cost-gating test. Compliance rule `env.fx_exposure` becomes blocking when |net FX exposure − target| > user tolerance.

### H-2. Corporate action cross-check is hand-waved. `03-` §2.1, `03-` §6

**Description:** Spec lists EODHD as primary for "dividends, splits, corporate actions." Yahoo is "fallback + anomaly detection." There is no operational detail for:

- What counts as an anomaly (missing split factor, adjusted-close mismatch, unreported spinoff, ticker change)?
- Who flags it? On what cadence?
- What happens when EODHD and Yahoo disagree (they do, regularly, on small-cap actions and foreign-domicile ADR adjustments)?
- What is the manual-resolution workflow?
- Spinoffs, M&A cash-and-stock, rights issues, reverse splits, special dividends — how are these handled in the feature store's point-in-time discipline?

**Why it matters in practice:** A missed 3:1 split on a mid-cap name turns a 5% position into a 15% position in the model's eyes and a -67% return overnight. The latent learner trains on this as a signal. The selection head now thinks the name has momentum when it's a data error. Attribution shows "selection skill" that is a corporate-action bug. This silently corrupts the track record that earns autonomy promotion — FP-14 broken.

**Fix:** `03-` §6 gets a new subsection: corporate-action cross-check protocol (EODHD vs Yahoo vs IBKR position-adjustment events on a 3-way diff), anomaly escalation (blocking for the affected instrument until manual review OR deterministic tiebreaker), named ownership of the resolution workflow (agent or human), and an explicit list of CA types supported in v1 (splits, cash div, special div, spinoff, merger cash-only) vs deferred (rights, warrants, complex stock-plus-cash).

### H-3. Paper trading fills are not acknowledged as optimistic. `08-` §6, `10-` §3

**Description:** The paper→live gate is a moment of truth. It requires 14 days of IBKR paper and a clean report. The spec does not acknowledge a well-known fact: IBKR paper fills are optimistic. Instant fills at or near mid. Minimal slippage. No real market impact. Stale NBBO during fast markets. No rejection for hard-to-borrow, no partial fills on size, no queue priority. A clean paper report is consistent with a live strategy that loses money to spread, impact, and rejection on day 1.

**Why it matters in practice:** The paper→live gate is the core trust mechanism. If it passes strategies that will fail in live, the whole track-record-earns-autonomy contract (FP-14) is built on sand. The first 7 days at L1 mitigates this but the L1→L2 upgrade contract (`08-` §7) talks about "positive override-convergence + no degradation events + positive early calibration" — all measurable in live, good — but the paper report is being treated as nearly dispositive.

**Fix:** `08-` §6.3 gains a blocking condition: paper report must include a realized-vs-expected cost delta over the paper period. If paper fills are too clean relative to the cost model's prediction, the report fails — the cost model is miscalibrated or the paper venue is masking it, either way not ready for live. Add an explicit "paper-fill optimism penalty" to all paper-period performance metrics in the report, clearly labeled. `10-` §3 gets language acknowledging that paper fills overstate realized performance.

### H-4. Turbulent-market approval on mobile, partial-fill default behavior is undefined. `01-` §1, `10-` §6, `02-` §5.2, `08-` §4

**Description:** Chain of failure:

1. User is on mobile on poor connectivity (e.g., in an airport during a sell-off).
2. Urgent-band decision fires. Progress bar starts. Default on expiry is "user-configured hold/execute" per `10-` §6.1.
3. User attempts biometric → network hiccup → biometric response lost.
4. Meanwhile, parent order was partially submitted (in L3 within-band execution during Elevated), partial fill returned, quote moved 2–3%.
5. What is the system doing right now? Is it still working the remainder? Cancelling? Applying expiry default?
6. When the user's biometric finally lands, the decision brief the user saw is now referencing a quote 3% stale and a position-delta that's half-done.

**Why it matters in practice:** This is where kill-switch-as-theory breaks. The kill switch is one tap and biometric — but the user has to see the state to know to trip it, and the state on the phone is blurry during exactly the moments when clarity matters. The spec specifies the UX rules (`10-` §6) but specifies no backend behavior for "biometric arrives 40 seconds after expiry, partial fill already booked, quote moved."

**Fix:** `10-` §6 gets a subsection: partial-fill-during-pending-approval protocol. When a decision is in-flight and a biometric is pending: (a) quote-staleness check on biometric arrival — if quote moved > threshold, the approval is invalidated and a fresh brief is composed from current state, (b) partial-fill state is always part of the brief the user is approving — "you're approving the remainder of a parent, X shares already filled at Y price", (c) network-loss recovery — biometric retry has idempotency key, so double-tap on reconnect cannot double-submit, (d) expiry default for Urgent MUST be "hold, do not execute" when a partial fill is live — the "execute" default is only safe for fresh decisions. `08-` §5.5 gets an entry: extreme slippage between recommendation and biometric auto-trips kill switch.

### H-5. S&P 600 small-cap liquidity is treated identically to S&P 500 large-cap. `03-` §1.1, `02-` §3.3

**Description:** The v1.1 universe is "S&P 1500 constituents" — 500 large, 400 mid, 600 small. Position sizing, cost budgeting, and impact modeling are not differentiated. Liquidity floor is specified (`03-` §1.2 #2) but as a "minimum ADV" threshold — a floor is not a size policy. A $300K portfolio taking a 2% position in a $2M-ADV S&P 600 name is 30% of ADV — unworkable.

**Why it matters in practice:** The difference between SPY ($30B ADV) and a typical S&P 600 name ($5M ADV) is 4 orders of magnitude. The cost model needs to be aware of this; the allocator needs to be aware; the compliance agent needs a participation cap. None are specified.

**Fix:** Compliance rule `exec.participation_cap` (see C-2): hard block at X% of 20-day-median ADV, soft warn at X/2. Differentiated by universe tier (ETF / S&P 500 / S&P 400 / S&P 600). Cost model and selection-head gating respect this. Position sizing respects it as an upstream constraint, not a downstream veto.

### H-6. Order state machine edge cases. `02-` §6.3

**Description:** The state machine "pending → submitted → partial → filled → reconciled → attributed" doesn't enumerate:

- Cancelled after partial (child filled X, parent cancelled Y remaining — book state vs model state).
- Reject-after-submit (margin, compliance, HTB).
- Duplicate order ID (client retry on unclear network state).
- Settlement-date issues — T+2 for US equities, T+1 in force since May 2024, T+0 for some ETFs.
- Corporate-action-during-open-order (ex-date hits while order is resting overnight).
- IBKR "Inactive" (venue-side compliance rejection) is not the same as "Cancelled" and requires different handling.
- Manual override at IBKR — what if the user logs into IBKR directly and cancels a Midas-submitted order?

**Why it matters in practice:** Every one of these is a real-world occurrence at the frequency Midas plans to trade. Each one is an opportunity for the position book to diverge from IBKR's truth, which then feeds into NAV, attribution, and the next decision — silent drift in the substrate that earns autonomy.

**Fix:** `02-` §6.3 gets a full state-diagram appendix. Idempotency contract on order submission (client-order-ID discipline). IBKR-as-source-of-truth reconciliation: every state transition validates against IBKR's reported state, and a divergence triggers `api.ibkr_health` = degraded.

### H-7. Settlement (T+1/T+2) is not modeled. `02-` §6.3, `11-` §3

**Description:** US equity settlement moved to T+1 in May 2024. Most ETFs also T+1. Some instruments (international ADRs, certain options) different. The spec does not model:

- Buying-power availability across T+0 vs T+1 vs T+2 (some brokers constrain).
- Rebalance cash management — selling X on Monday to fund buying Y on Monday is NOT a cash-neutral operation at settlement level in some jurisdictions/accounts.
- Good-faith-violation / free-rider rules if the account ever operates without margin.
- Settlement reconciliation in the order-state-machine.

**Why it matters in practice:** For a $100–500K cash account on IBKR-SG, settlement frictions are real. Even on margin accounts, the spec's "no leverage" implicit posture means same-day sell-to-buy chains can trip unsettled-cash rules.

**Fix:** Settlement model explicit in new `specs/14-ibkr-integration.md` and/or `specs/13-execution-cost-and-microstructure.md`. Compliance rule `exec.settlement_available` blocks a buy whose funding is unsettled when the account type requires settled funds. Paper trading report includes settlement sanity check.

---

## MEDIUM Findings

### M-1. "Fresh price pull at execution" is under-specified. `02-` §5.2, `11-` §3.1 `exec.freshness_at_execution`

**Description:** "If the discrepancy exceeds a threshold, the decision is returned to the user." What threshold? Is it in bps? Absolute? Volatility-normalized? Same threshold for ETFs and small caps? And the "return to user" path under time pressure (Urgent band) loops back to H-4 — user sees a stale brief on re-presentation.

**Fix:** Threshold is a vol-normalized delta (`|px_fresh − px_cached| / σ_intraday`), instrument-specific, tunable in compliance rule registry. Re-presentation to user includes fresh quote + fresh brief composition.

### M-2. Meta-router can silently favor low-cost champions for wrong reasons. `02-` §3, `11-` §3.1 `env.cost_budget`

**Description:** If cost budget is a binding constraint and cost model is miscalibrated low (C-1), router selects champions whose expected net-of-cost return looks high because modeled cost is low. In live this inverts. No mechanism surfaces this.

**Fix:** Router calibration tracking includes realized-cost-vs-modeled delta per champion.

### M-3. "Data-driven" universe inclusion can oscillate. `03-` §1.3

**Description:** Monthly/quarterly ETF review means an instrument can enter and exit the universe as data drifts near the floor. Each entry/exit is a rebalance trigger with cost. Spec acknowledges changelog but no hysteresis.

**Fix:** Inclusion rules get hysteresis (enter criterion stricter than exit criterion); min-holding-period before an instrument can be re-removed.

### M-4. Audit immutability claim needs enforcement. `11-` §8

**Description:** "Immutable audit log" is asserted; implementation isn't. Postgres append-only is convention, not enforcement.

**Fix:** DDL-level triggers blocking DELETE/UPDATE, periodic hash-chain, and an explicit off-site replication requirement.

### M-5. Kill-switch auto-trip criteria are vague. `08-` §5.5

**Description:** "Severe error class" from IBKR, "rapid NAV move" without numbers. Auto-tripping is irreversible within a session (`08-` §5.4) so the thresholds matter.

**Fix:** Each auto-trip condition gets a concrete predicate with default numeric threshold, tunable in compliance rules, logged per-trip with the exact predicate that fired.

### M-6. No explicit rule blocking implicit leverage. `02-` §8, `11-`

**Description:** Options/margin/shorting are out of v1 scope. There is no compliance rule blocking accidental implicit leverage — e.g., a rebalance that relies on unsettled proceeds, or an ETF that has internal leverage (TQQQ, SSO) sneaking into the universe.

**Fix:** `env.leveraged_etf` blocking rule (explicit exclusion list for known 2x/3x products), `exec.settlement_available` as above, `env.short_position` blocking any negative target weight.

### M-7. First-live-week runs at L1 but cost model has zero live data. `08-` §6.4

**Description:** L1 still requires user approval for every trade, so this is less load-bearing than it looks — but the user's decision rests on a brief whose cost estimate has never seen live fills. The brief should flag this explicitly.

**Fix:** Brief in first N live days includes "cost model live-sample count: 0 — wide uncertainty band" banner.

---

## LOW / Observations

### L-1. Expiry-default authority

`10-` §6.1 progress-bar-not-timer is good UX but timing of expiry default under intermittent connectivity needs to be server-authoritative, not phone-authoritative. State that explicitly.

### L-2. Active-polling cadence vs decision cadence

ETF sector rotation at "weekly max" (`02-` §3.3) plus active polling quote-refresh at 1 min (`03-` §3.4) means most polling delivers no-op data. Acceptable but the infra spec should acknowledge this is primarily a UI-freshness loop, not a decision loop.

### L-3. Debate-mutation and re-biometric

The Debate agent can re-run the optimizer and mutate a pending decision (`01-` §5.3, `11-` §9). When it does, the decision re-enters the compliance flow from the top — but nothing specifies whether the user is re-prompted with a fresh biometric if the decision materially changed. It should be.

### L-4. Degraded-LLM + pending Urgent

"Frontier LLMs required for decision-adjacent work" (FP-12) during an outage: §7.3 says fall back to next-best frontier, and if all frontier unavailable, no decisions execute silently on degraded LLM. Good. But existing pending Urgent decisions — do their expiry defaults still fire? Spec silent.

### L-5. IBKR-SG custody / SIPC / MAS

IBKR-SG uses a different custody entity from IBKR-US. SIPC coverage applies to IBKR-US only. User should be told this. Also FSCS/MAS coverage specifics.

### L-6. Position reconciliation cadence

`03-` §2.1 lists IBKR as "Truth for positions; secondary for quotes." Position reconciliation cadence is unspecified. Should be event-driven (on every fill report) + scheduled sweep (EOD + on wake from sleep).

### L-7. `data.stale_price` threshold undefined

Same critique as M-1: needs concrete defaults per asset-class tier, tunable in registry.

### L-8. Holiday calendar

US holidays affect SGD-USD and IBKR-SG order routing. Spec doesn't mention a holiday calendar anywhere.

---

## What's Missing Entirely

Items the spec set does not address at all but should before live trading:

1. Execution cost model — the brief literally asked for this. Zero presence. (C-1, C-3)
2. Child-order scheduler / execution algorithm. (C-2)
3. Bid-ask spread ingestion. (C-3)
4. Halt / auction / circuit-breaker handling. (C-5)
5. IBKR-specific operational spec — session lifecycle, rate-limit budget, rejection taxonomy, paper vs live endpoint map, SG-entity specifics. (C-4)
6. FX exposure policy and hedge decision. (H-1)
7. Dividend withholding in the cost budget as first-class component. (H-1)
8. Corporate action 3-way cross-check operational protocol. (H-2)
9. Paper-fill optimism acknowledgment + realized-vs-expected delta in paper report. (H-3)
10. Partial-fill-during-pending-approval protocol. (H-4)
11. Participation cap as a compliance rule. (H-5, C-2)
12. Full order-state-machine with IBKR-native states + idempotency + reconciliation. (H-6)
13. Settlement (T+1) modeling. (H-7)
14. Holiday calendar + cross-market session handling. (L-8)
15. Implicit-leverage / leveraged-ETF blocker. (M-6)
16. SIPC / MAS coverage disclosure + custody entity clarity. (L-5)
17. Position reconciliation cadence. (L-6)
18. Quantitative, numeric thresholds for every blocking rule in `11-` §3.1 — currently all predicates are qualitative.
19. A defined cost-model calibration loop that feeds realized fills back to the cost estimator. (M-2)

The single highest-leverage fix: write `specs/13-execution-cost-and-microstructure.md` + `specs/14-ibkr-integration.md` + `specs/15-currency-and-withholding.md` before any implementation todo touches `02-` §5.2. Without these, paper trading will pass, live trading will bleed, and the track-record substrate the entire autonomy ladder rests on will be compromised from day one.
