# Redteam Round 1 — Quant Researcher

**Persona:** Senior quant researcher, 15+ years at a top systematic hedge fund
**Spec set audited:**

- `/Users/esperie/repos/training/midas/specs/_index.md`
- `/Users/esperie/repos/training/midas/specs/00-first-principles.md`
- `/Users/esperie/repos/training/midas/specs/03-universe-and-data.md`
- `/Users/esperie/repos/training/midas/specs/04-latent-first-architecture.md`
- `/Users/esperie/repos/training/midas/specs/05-model-pool-and-meta-router.md`
- `/Users/esperie/repos/training/midas/specs/06-continuous-regime-rendering.md`
- `/Users/esperie/repos/training/midas/specs/12-performance-and-track-record.md`

**Overall assessment:**
This is a spec set that has read the right papers and uses the right vocabulary but has not done the work a quant shop actually does before it lets a model touch real capital. It is structurally coherent — the latent-first spine, pool + router, three-loop adaptation, continuous rendering — and the reframe away from the Phase 01 HMM/DCC-GARCH framing is correct. But it is dangerously silent on the mechanics that separate a model that looks brilliant in a notebook from one that survives production: point-in-time fundamentals, walk-forward protocol, survivorship bias on the S&P 1500, corporate-action handling, shadow-lane contamination risk, router overfitting to its own meta-decisions, and — most critically — any honest assessment of whether the `z_t` spine is learnable from a single retail investor's data depth. The promotion contract in §5 reads like a checklist of virtues, not a statistical procedure with a family-wise error rate. The calibration story is aspirational — "conditional on `z_t` neighborhood" — but never says how you cross-validate a calibration curve conditioned on a latent you are simultaneously learning. The spec set is ready to start implementation only if the reader assumes every detail below will be filled in silently. If you build it as written, it will overfit the backtest, fail in live, and the failure will not be visible until money is lost. Fix the items marked CRITICAL before a single line of model code is written.

---

## CRITICAL Findings

### C-1: No point-in-time protocol for fundamentals, macro, or universe membership

**File:** `03-universe-and-data.md` §4.3 (Walk-Forward Discipline), §1 (Universe), §2.2 (Fundamentals)

**Description:**
§4.3 says "feature value at time `t` may depend only on data known at time `t`" and handles restated fundamentals by "separate revision records." That is one sentence where there should be a protocol. The spec does NOT specify:

1. **Fundamental availability lag.** 10-K filings are released 60–90 days after period end. The spec treats EODHD Fundamentals as "Daily" in §2.2 without specifying the `available_at` timestamp vs the `period_end` timestamp. A naive join (`fundamentals.period_end = t`) leaks the future by 60–90 days — this is the single most common backtest leak in the industry.
2. **Macro release timing.** FRED series are released with lag (CPI ~2 weeks, GDP ~1 month, PMI monthly). The spec says "auxiliary inputs" without specifying the release-timestamped join. OECD CLI is released with a 60-day lag and heavily revised.
3. **Universe membership as-of date.** §1.3 says universe changes are "logged in a `universe_changelog` table" but there is no statement that backtest universe membership is resolved AS-OF the backtest date. S&P 1500 is particularly dangerous — Russell/S&P reconstitutions happen in Q2, and using today's constituents for a 2019 backtest guarantees survivorship bias of 40–120 bps/year.
4. **Revision tracking for FRED.** FRED data gets revised months after initial release. The primary vs revised vintages (ALFRED archive) are not mentioned anywhere.

**Why it matters:**
Every one of these is a silent future-leak. A latent learner trained on leaked features learns to exploit the leak and reports beautiful Sharpe numbers that evaporate the day you go live. The Phase 01 red team's Brinson work (§12-3) becomes meaningless if the attribution benchmark uses forward-leaking data.

**Concrete fix:**
Add a new section `03-universe-and-data.md §4.5 Point-in-Time Protocol` that mandates:

- Every fundamental row carries `(period_end, filed_at, restated_at, source_vintage)`. Joins use `filed_at <= t`, never `period_end <= t`.
- Every macro series carries `(observation_date, release_timestamp)`. Joins use `release_timestamp <= t`.
- FRED pulls archive vintage (ALFRED) not revised series, OR they use `release_timestamp` to freeze to first-release values.
- Universe membership joins use `universe_changelog.effective_date <= t`, excluding future additions AND retaining names that were later delisted (no survivorship). Delisted tickers retain their price history up to delist date.
- A canonical `as_of_date` parameter threads through every feature query, every model train call, every shadow decision write.
- A Tier 2 regression test: train on a past slice, verify features at a held-out date contain zero information filed after that date. This is mechanical and cheap; its absence is inexcusable.

---

### C-2: Shadow lane is not a real shadow lane until it proves it

**File:** `05-model-pool-and-meta-router.md` §5.2 (Shadow Lane Mechanics)

**Description:**
§5.2 says shadow decisions "are written to `shadow_decisions` table, never to the order manager" and are "isolated." That is the weakest possible contract. Four specific leaks the spec does not defend against:

1. **Fabric contamination.** If the shadow lane reads from the same `features` table that the live lane wrote (§3.3 of `03-`), and a shadow model's training schedule runs before the live lane's feature computation for day `t`, the shadow model can influence the live feature (via shared caches, shared pgvector state, or retraining triggers).
2. **Training data leakage across lanes.** If the outer-loop retrains the champion AND the challengers on `features v2` which was shaped by decisions the champion made, the champion has an endogeneity advantage over cold-start challengers that have never influenced the data. Shadow P&L reported in §5.2 does not adjust for this.
3. **Latent state coupling.** §2.1 of `04-` says `z_t` is the "inference pool's" output, and §5 of `04-` shows one inference pool. Does the shadow lane use a separate inference pool or the champion's? If it's the champion's, the challenger is not an independent experiment. If it's separate, the spec doesn't say where it lives.
4. **Order manager veto is stated but not tested.** There is no Tier 2 integration test required that a shadow decision writes to `shadow_decisions`, hits the order manager boundary, and is rejected. Without the test, the separation is a convention.

**Why it matters:**
The Phase 5.11 orphan in kailash-py Python shipped 2,407 LOC of "trust integration" that never ran — the manager-shape pattern (`TrustAwareQueryExecutor`) is exactly what `shadow_lane` looks like here. Per `rules/orphan-detection.md`, every `db.X` facade needs a production call site AND a Tier 2 wiring test in the same PR. The spec has specified the surface without specifying the wiring.

**Concrete fix:**
Add to `05-§5.2`:

- Shadow lane MUST have its own dedicated `features_shadow_v{N}` namespace in the fabric, OR read from an immutable snapshot of `features` pinned at shadow-decision time.
- Shadow lane MUST have its own inference pool instance — the champion's `z_t` is NOT shared into the challenger evaluation.
- Shadow-to-order-manager isolation is verified by a Tier 2 test: `test_shadow_decision_does_not_reach_order_manager.py` — publish a shadow decision, assert zero IBKR calls, assert `shadow_decisions` row exists, assert `orders` row does not.
- A monthly audit (written into `/redteam`) greps for any code path where `shadow_decisions` and `orders` are constructed from the same fabric query without separate snapshots.

---

### C-3: The router is a model with no overfitting protocol

**File:** `05-model-pool-and-meta-router.md` §4.2, §4.5

**Description:**
§4.2 says the router is "a contextual bandit or mixture-of-experts or Bayesian model averaging layer — trained on historical `(context, head outputs, realized outcome)` tuples." §4.5 says the router "itself is scored by the outcomes of its decisions."

Five problems:

1. **The router trains on data that already contains its own past decisions.** Every head output in the training tuple is the result of a model that the router previously routed to; this is a classic closed-loop reinforcement setup and the spec treats it as a simple supervised problem.
2. **No cross-validation protocol for the router.** When the heads are themselves being retrained weekly, the router's "historical tuples" are moving targets. Is the router re-estimated on held-out `z_t` neighborhoods? Purged k-fold? Walk-forward? The spec does not say.
3. **Router promotion is unspecified.** §5 specifies champion/challenger promotion for heads but is silent on how a new router architecture is promoted. The router is the one model whose failure cascades into every downstream head.
4. **Router complexity is unbounded.** If the router is a Bayesian mixture of N heads, each with K calibration curves conditioned on a D-dimensional `z_t`, the effective parameter count grows as N·K·D. With ~8 layers × 5 pool members × 32-dim `z_t`, you are estimating order-of-magnitude 10³–10⁴ routing parameters from ~5000 decision observations (about 2–4 years of weekly rebalances). You will overfit the router before the heads.
5. **Self-evaluation is circular.** §4.5 says the router's performance is evaluated against "a simple always-pick-highest-recent-calibration baseline." But that baseline is itself a router. There is no anchor outside the pool+router system.

**Why it matters:**
The router is the single point where no-free-lunch is operationalized. If the router overfits, the entire "mechanism is the product" claim collapses into "we have a complicated thing that looks smart on the backtest." This is the no-free-lunch-for-the-router problem and the spec does not acknowledge it exists.

**Concrete fix:**
Add to `05-§4`:

- Router MUST be trained and validated on a purged, embargoed walk-forward protocol (López de Prado's PurgedKFold or equivalent) — explicitly named, with the purge length tied to the longest return-head horizon (6 months per `03-§5.3`).
- Router effective parameter count MUST be bounded relative to decision observation count; the spec states a maximum ratio (e.g., N_params <= N_obs / 20) and enforces it at training time.
- Router promotion has its own contract in `05-§5.4-router` — dominated by the same metrics as head promotion PLUS a "router stability" metric (the new router agrees with the old router in >80% of Calm-band decisions, preventing regime-change-by-router-swap).
- A naive baseline that is NOT itself a router is specified — equal-weight ensemble of all pool members is the minimum. Router is rejected if it loses to equal-weight on out-of-fold data.
- `test_router_does_not_leak_outcome_into_training.py` — Tier 2 test that the tuple `(context, head_outputs)` at time `t` contains zero information about the realized outcome at `t+h`.

---

### C-4: Latent state `z_t` is aspirational, not a plan — data depth is not honest

**File:** `04-latent-first-architecture.md` §2, §4; `03-universe-and-data.md` §5.1

**Description:**
`04-§2.2` says `z_t` dimensionality is "8 to 32 dimensions... subject to population-based tuning." `04-§4` lists nine families of representation learners (SSL transformers, MAE, contrastive, VAEs, diffusion, S4, Mamba, Kalman-NN hybrids, foundation TS models like TimesFM/Chronos/Moirai). `03-§5.1` says pre-training uses "public financial time-series corpora (cross-market, cross-asset-class, cross-frequency)."

This is name-dropping, not a plan. Specifically:

1. **The "public financial corpus" is not named.** TimesFM was trained on 100B time points from Google's internal + public datasets. Chronos was trained on 84B. Moirai used LOTSA (27B). Midas's v1 universe is ~50 ETFs + S&P 1500 = ~1550 instruments × ~5000 trading days = 7.75M observations. You cannot pre-train a transformer on 7.75M points — it will memorize. The spec must name the corpus OR specify which foundation model is being fine-tuned, not both.
2. **8–32 latent dimensions are not learnable from the Midas universe.** With 1550 instruments over ~20 years and daily frequency, even a 16-dim `z_t` with the cross-sectional structure the spec wants requires billions of effective parameter updates to converge. "Population-based tuning" across 9 families means training O(9×5) = 45 parallel checkpoints, each of which needs cloud GPU time. §9 says "don't worry about budget first" — that is a leadership decision, not a data-availability statement. Budget does not solve data depth.
3. **Self-supervised contrastive objectives require the temporal positive/negative sampling to be defined.** The spec says "temporally-adjacent states are similar" — what window? What's negative? Negative sampling from the same regime vs cross-regime negatives is the difference between a useful embedding and a collapsed one.
4. **Foundation TS model fine-tuning has known pitfalls** the spec does not mention: distribution shift between pre-training corpus and Midas universe, context-length limits (Chronos-Bolt is 512 tokens = 2 years of weekly data), frequency mismatch (Chronos trained on hourly/daily, fine-tuning on mixed frequencies is an open research question).

**Why it matters:**
The latent-first architecture is the spine of Midas. If `z_t` is not actually learnable from the data Midas has, then every downstream claim — "decisions route through posterior," "router reads `z_t` neighborhoods," "continuous rendering projects `z_t`" — is a claim about a quantity that does not exist. The system will emit a vector that is functionally random and the downstream heads will learn to ignore it. This is the Phase 5.10 failure mode (`@classify("email", REDACT)` that ships as a no-op) at a much larger scale.

**Concrete fix:**
Add to `04-§2.2` and `03-§5.1`:

- Name the pre-training corpus specifically: which dataset, how many instruments, how many observations, which frequency. "LOTSA subset" or "Chronos-Bolt as initial weights" are acceptable; "public financial corpora" is not.
- State the minimum observation count required for the latent dim at each tier (8, 16, 32) based on sample-complexity analysis. If the minimum is not met by the v1 universe, the v1 latent dim is bounded.
- Specify the contrastive objective concretely: temporal window, positive definition, negative sampling strategy, loss function, batch construction.
- Add an explicit "latent-learnability probe" as a gate before shadow promotion: mutual information between `z_t` and realized returns on held-out data, evaluated against a scrambled-`z_t` null. If `MI(z_t, r_{t+1}) <= MI(shuffle(z_t), r_{t+1}) + ε`, the latent is noise and the champion is rejected.
- State a Phase 0 milestone: before any decision head is trained, demonstrate that `z_t` has non-trivial mutual information with future returns on held-out data. This is a research gate, not an engineering gate.

---

### C-5: Calibration methodology is vibes, not statistics

**File:** `05-model-pool-and-meta-router.md` §3.2; `12-performance-and-track-record.md` §4

**Description:**
`05-§3.2` lists metrics: "regime-conditional hit rate," "quantile calibration curve," "horizon-specific loss," etc. `12-§4.1` says "every head maintains a calibration curve" and "curves are computed over rolling windows and conditional on `z_t` neighborhood."

Three critical omissions:

1. **"Conditional on `z_t` neighborhood" is under-specified.** How is the neighborhood defined? k-NN in latent space with fixed k? Kernel density with bandwidth h? Fixed Voronoi tessellation? Each choice has order-of-magnitude different bias/variance tradeoffs. The spec says "neighborhood" without a definition.
2. **No statistical significance.** A calibration curve with 30 points per bin across 10 bins requires 300 observations. At weekly rebalance cadence over 2 years, that is 104 observations total — not enough to populate a single bin per `z_t` neighborhood. The spec treats calibration as if data is infinite.
3. **No multiple-comparison correction.** §5.4 lists six promotion criteria. Evaluating six criteria on noisy data gives a family-wise Type I error around 0.26 at α=0.05. The spec does not mention Bonferroni, Holm, SPA (Hansen), or deflated Sharpe (López de Prado) — all of which are standard in systematic research and all of which dramatically raise the bar for promotion.

**Why it matters:**
The promotion contract is the gate between the model pool and real money. If the calibration check is statistically toothless, promotions are noise-driven. The system will rotate champions based on random fluctuations, making the "three-loop adaptation" mechanism a random-walk generator dressed in reinforcement-learning language.

**Concrete fix:**
Add to `05-§3` and `12-§4`:

- Specify `z_t`-neighborhood as a concrete estimator: e.g., "50-nearest-neighbors in L2 over normalized `z_t`, with a minimum of 30 observations per neighborhood before calibration is estimable."
- Minimum sample-size gates per calibration bin. If the gate is not met, the curve is marked "under-sampled" and the head cannot be promoted on that criterion until enough data accumulates.
- Explicit multiple-comparison correction on the §5.4 promotion contract: Holm-Bonferroni at family-wise α=0.05, OR deflated Sharpe ratio with the trial count tracked in `model_registry`.
- A Tier 2 test: feed a pool of 20 random heads into the promotion pipeline, verify that the Type I promotion rate is ≤ α. If the promotion pipeline certifies a random head as champion, it is broken.

---

## HIGH Findings

### H-1: Corporate-action handling is unspecified

**File:** `03-universe-and-data.md` §2.1, §3.3 (`corporate_actions` table)

**Description:**
§2.1 lists "dividends, splits, corporate actions" as EODHD coverage but the spec does not say which adjustment convention is used. Total-return series (dividends reinvested, splits adjusted) vs price-return series vs adjusted-close vs pre-adjusted OHLC are not equivalent. The latent learner will learn different dynamics depending on which series it is fed.

Spinoffs, reverse mergers, ticker changes, delistings, and ADR ratio changes are all "corporate actions" that require domain-specific handling and are not mentioned.

**Why it matters:**
A latent learner trained on price-return series treats every dividend day as a discontinuity and learns to avoid them. A learner trained on total-return series treats them correctly but produces returns that can't be directly compared to naked-price benchmarks. The Brinson attribution in §12-§3 silently assumes one or the other.

**Concrete fix:**
Add `03-§2.1.1`:

- State that the primary price series is total-return (dividends reinvested, splits adjusted, spin-offs adjusted)
- Delistings retain the history up to delist date; no back-fill
- Spinoffs: parent price is adjusted downward by spinoff fair value on ex-date; spinoff child becomes its own instrument
- Adjustment is persistent (not rolling) — historical closes are stable across reruns
- Tier 2 test: a known corporate action (AAPL 4:1 split, Aug 2020) produces the expected adjusted series

---

### H-2: Router's output to the order manager has no explicit contract

**File:** `05-§4.2 Router Structure`, `05-§7 Evidence Store`

**Description:**
§4.2 says the router's output is "a blended recommendation with an explicit posterior over which pool members contributed and how much." That is not an order contract. Specifically:

1. What units? Target weights? Target dollar amounts? Target position changes?
2. What is the tolerance band around the recommendation that triggers a rebalance?
3. How does the router resolve conflicts between two pool members that disagree on direction (not magnitude)?
4. What happens if the router's posterior is bimodal?

Without a contract, every downstream consumer (compliance agent, order manager, Debate agent) will interpret it differently and divergence will not surface until live.

**Concrete fix:**
Add `05-§4.6 Router Output Contract`:

- Output is a `TargetPortfolio` object with target weights per instrument, per-instrument confidence, an overall posterior uncertainty, and a tolerance band.
- Conflict resolution: the router emits the posterior mean; bimodal posteriors produce a lower-confidence mean that throttles action via the uncertainty mechanism in `04-§8`.
- Every consumer imports the `TargetPortfolio` type; no consumer constructs its own interpretation.

---

### H-3: No out-of-sample discipline on the attention-load function `a_t`

**File:** `06-continuous-regime-rendering.md` §2

**Description:**
§2 says `a_t` is "learned (not hand-coded) by regressing historical user-engagement and decision-window-expiry outcomes against historical `z_t`-derived features." The regression is the least scrutinized model in the spec set. It is:

1. Regressed on user-engagement, which is noisy and reflects user behavior not market state
2. Trained on data that includes the user's own overrides — feedback loop
3. Explicitly allowed to modulate approval thresholds (§5), rebalance cadence, notification tiering — this is a production decision-affecting signal, not a UX cosmetic
4. Declared "subject to the same calibration and promotion discipline as any other head" — but the promotion contract in §5 is designed for return heads, not attention regressors

**Why it matters:**
"Regime is a visualization" is the slogan, but `a_t` is wired into approval thresholds and rebalance cadence. That is not visualization. That is a control input. If the regression overfits user-behavior noise, the system will raise approval thresholds in Calm states and lower them in Crisis states — the worst possible failure mode.

**Concrete fix:**
Add to `06-§2`:

- `a_t` function is validated on held-out user-engagement data with a minimum sample size gate.
- `a_t` has its own promotion contract distinct from return heads (e.g., dominates a simple VIX-quantile baseline).
- The decision-affecting use of `a_t` (approval thresholds, cadence) is separated from the visualization use: the visualization can use a noisy `a_t`, but the control paths use a debounced, confidence-gated version.
- Tier 2 test: a held-out month of user engagement data, verify `a_t`'s decision-affecting outputs do not degrade vs a VIX-decile baseline.

---

### H-4: Walk-forward retraining cadence conflicts with population-based training

**File:** `03-universe-and-data.md` §4.4; `05-§5.3 Population-Based Training`

**Description:**
`03-§4.4` says representation learners retrain weekly during training phase, monthly after. `05-§5.3` says population-based training runs "multiple configurations... in parallel" with best performers propagating. At a 1-week retrain cadence with a population of (say) 10 configurations per architecture × 9 architectures = 90 parallel jobs, each ingesting fresh data weekly, you get:

1. 90 models × 52 weeks/year × 7.75M observations = a training budget that is not remotely profiled in §9
2. Catastrophic shortening of the effective training window for any single lineage (a 1-week new-data increment gives new configurations almost no signal)
3. Population-based training's selection pressure exceeds the rate at which new data can distinguish configurations

**Concrete fix:**

- Decouple retrain cadence from population-based training cadence. Representation learners retrain on a tick (weekly), but population-based selection runs on a longer tick (quarterly) so selection is driven by signal, not noise.
- State the population budget explicitly in `05-§5.3`: maximum concurrent configurations, maximum training hours per configuration, selection criteria for retention.

---

### H-5: Execution slippage, market impact, and fill assumptions are absent from backtests

**File:** `12-performance-and-track-record.md` §2, §5; `03-§2.1 IBKR`

**Description:**
The performance table in §2 lists "transaction cost as fraction of return" and "turnover" but does not specify the fill model. IBKR fills are not instantaneous, not free, not always at the quoted price. The spec does not say:

1. What fill model the backtester uses (mid, mid+half-spread, VWAP-over-bar, next-bar-open, worst-in-bar)
2. What slippage model (fixed bps, ADV-proportional, sqrt-impact)
3. Whether the shadow lane in `05-§5.2` uses the same fill model as live
4. How IBKR commission structure (tiered, fixed, unbundled) feeds into the cost budget

**Why it matters:**
A latent-first allocator trained with a zero-slippage fill model will learn to over-trade on small signals. A shadow lane that uses a different fill model than live will produce shadow P&L that systematically differs from live P&L, breaking the promotion contract.

**Concrete fix:**
Add `12-§2.1 Execution Model`:

- Primary fill model specified (e.g., next-bar-open with fixed 2 bps slippage)
- Shadow lane uses the same fill model
- Tier 2 test: shadow P&L over a replay of a historical week matches live P&L within a tolerance

---

### H-6: No explicit overfitting defense against backtest-to-live decay

**File:** `12-performance-and-track-record.md` §2, §6

**Description:**
The spec lists metrics but not the standard industry defenses against backtest overfitting:

1. No Deflated Sharpe Ratio (DSR, Bailey & López de Prado 2014)
2. No Probability of Backtest Overfitting (PBO)
3. No combinatorial purged cross-validation (CPCV)
4. No haircut on reported Sharpe based on trial count
5. No "minimum track record length" gate before auto-promotion

"Positive performance + good calibration + low override" (§8) is a policy, not a statistical test.

**Concrete fix:**
Add `12-§2.2 Overfitting Defenses`:

- Deflated Sharpe computed on every head's reported Sharpe, using the pool's trial count as the multiplicity
- PBO computed as part of the shadow-lane promotion contract
- CPCV or purged K-fold for every head evaluation; simple walk-forward is banned
- Minimum paper-track-record length before L2 upgrade (beyond the 2-week minimum in `00-§FP-7`)

---

### H-7: Orphan risk — pools and fabric tables specified with no production call sites named

**File:** `03-§3.3` (fabric layout); `04-§5` (state inference pool); `05-§6` (challenger ownership)

**Description:**
Per `rules/orphan-detection.md`, every `db.X`-style facade needs a production call site. The spec set has multiple components at orphan risk:

1. `latent_state` table (§3.3 of `03-`) — no code path specified that writes to it, no code path specified that reads it for analogue retrieval beyond "Debate agent." The analogue retrieval (§6 of `06-`) is described as a tool but not wired.
2. `shadow_decisions` table — write path is specified; read path (for promotion-contract evaluation in `05-§5.4`) is not tied to a named component.
3. `model_registry` — read path is implied but no component is named as the single source of truth for model version lookup.
4. `universe_changelog` — read path for as-of universe membership (per C-1) is unspecified.
5. State-inference pool (§5 of `04-`) is described at length but never said to have a wiring test; the manager-shape pattern in `rules/facade-manager-detection.md` applies.

**Why it matters:**
The Phase 5.11 orphan was `db.trust_executor` + `db.audit_store` — 2,407 LOC that looked wired but had no production call site. The spec set has the same shape for the state-inference pool and the evidence store.

**Concrete fix:**
For each of the above, the spec MUST identify:

1. The single class/module that owns the write path
2. The single class/module that owns the read path
3. The Tier 2 integration test that exercises both ends through the framework facade

Add a cross-reference matrix to `_index.md` mapping every fabric table to its owning component and wiring test.

---

## MEDIUM Findings

### M-1: `z_t` identifiability is not guaranteed

**File:** `04-§2.1`

**Description:** Continuous latent spaces from SSL transformers are notoriously non-identifiable — rotations, scalings, and permutations of `z_t` are equivalent up to an invertible transformation. The spec says the router operates on "`z_t` neighborhoods" but neighborhoods in a non-identifiable space are ill-defined. When the representation learner retrains (weekly per `03-§4.4`), the new `z_t` space is not aligned with the old. Historical calibration data keyed on old `z_t` is no longer valid.

**Concrete fix:** Specify alignment — Procrustes rotation, linear map fit to align successive `z_t` spaces — and a Tier 2 test verifying that calibration curves survive retraining.

### M-2: "Distance from training distribution" is handwaved

**File:** `04-§8`, `06-§2`

**Description:** Both specs use "distance from training distribution" as a trigger for OOD escalation but never specify the metric. L2 in `z_t` space? Mahalanobis? Energy score? Density ratio? Each gives different results. OOD detection in high-dimensional latent space is a research-grade problem; the spec treats it as a function call.

**Concrete fix:** Name a specific OOD detector, specify its training protocol, and add a calibration test on known distribution-shift events (Brexit Jun-2016, COVID Mar-2020).

### M-3: Calmar ratio on 3-month rolling windows is statistical noise

**File:** `12-§6.1`, `12-§3.4`

**Description:** Calmar ratio = annualized return / max drawdown. On a 3-month window for a weekly-rebalance portfolio, you have ~13 observations. Max drawdown is an extreme-value statistic with enormous sampling variance on 13 observations. Using it as the primary promotion input is using a random number generator.

**Concrete fix:** Use Calmar on 12-month windows only; 3-month windows use a different metric (e.g., rolling Sortino with a 60-day min window).

### M-4: Override convergence is a feedback loop the spec ignores

**File:** `12-§6.1` ("Override convergence")

**Description:** User overrides feed into the track-record score and influence promotions. But the user's override behavior is shaped by the briefs the system writes. A system that writes confident briefs gets fewer overrides and earns autonomy faster — regardless of whether the underlying decisions are better. This is a confounded feedback loop, not a performance signal.

**Concrete fix:** Override convergence is a diagnostic metric only, not a primary promotion input. Remove from the composite score or explicitly acknowledge the confounder.

### M-5: FP-3's "unplug for six months" violation test is fashionable but undefined

**File:** `00-§FP-3`

**Description:** "If Midas could be unplugged for six months, plugged back in, and behave identically — it is not dynamic enough." What does "behave identically" mean operationally? Same target weights on the same inputs? Same router decisions? The test is not falsifiable as written.

**Concrete fix:** Rewrite as a concrete procedure: freeze the system state, replay market data for 6 months, compare decisions at time `T` to decisions at time `T+6m` on the same live inputs. If ≥ X% of parameters haven't moved, flag FP-3 violation.

### M-6: "Interaction effect" in Brinson attribution is non-standard

**File:** `12-§3.1`

**Description:** Brinson–Fachler (the name in §3's heading) has allocation and selection but not "interaction" — that is Brinson–Hood–Beebower. The spec conflates the two. Quant attribution is pedantic about this and the monthly statement in §7.2 will produce numbers that are neither-nor if the code and the spec disagree.

**Concrete fix:** Pick one. If Brinson–Fachler: drop interaction. If Brinson–Hood–Beebower: rename §3 heading. State the choice explicitly.

---

## LOW / Observations

### L-1: "Retrain weekly during active training phase" is vague

**File:** `03-§4.4`

**Description:** When does "active training phase" end and "stabilization" begin? The transition is not defined.

### L-2: The model_registry schema is not specified

**File:** `03-§3.3`

**Description:** Columns, constraints, and uniqueness keys on `model_registry` are undefined. This table is the audit spine of the pool+router system and needs its own spec section.

### L-3: "Frontier LLMs" in FP-12 is a moving target

**File:** `00-§FP-12`

**Description:** "Opus-class, GPT-5-class, or whatever sits at the frontier" — how is "frontier" measured, and how is a switch between providers audited?

### L-4: "Minimum two weeks of paper trading" may be insufficient

**File:** `00-§FP-7`

**Description:** Two weeks spans 10 trading days. A latent-first system with weekly rebalancing sees 2 rebalance events in 10 days. Paper trading needs to cover enough rebalance events to populate a calibration curve. 2 is not enough; 12–26 is defensible.

### L-5: `_index.md` does not enumerate 13-28

**File:** `specs/_index.md`

**Description:** Index lists files 00–12 but `04-latent-first-architecture.md` is at index 04 in the real filesystem and cross-references documents "15–28" exist per the coc-skills navigation. Verify the spec set is complete.

### L-6: "Population-Based Training" is name-dropped without reference

**File:** `05-§5.3`

**Description:** "The classical Population-Based Training pattern" — is this Jaderberg et al. 2017? The spec should cite the paper so implementers implement the right algorithm.

---

## What's Missing Entirely

1. **Research workflow spec.** How does a quant propose a new challenger? Where does code live? What branch discipline? The spec set describes the production system but never describes how models get into it.

2. **Backtest infrastructure spec.** Event-driven vs vectorized? Replay from the fabric or from a frozen snapshot? What is the canonical Python entry point? Backtest is the forge where every model is born and the spec is silent.

3. **Data quality spec.** Outlier detection, bad-tick filters, stale-price detection, survivorship cross-checks, EODHD-vs-Yahoo discrepancy handling (§2.1 mentions cross-check but not what the resolution is). Data quality is what kills models in production more often than modeling choices.

4. **Label leakage audit protocol.** An explicit, mechanical check for each feature family: "does this feature use any data not available at prediction time?" — with the check runnable in CI.

5. **Regime-transfer robustness test.** Train on pre-2008, test on 2008-2010. Train on pre-2020, test on 2020-2021. A model that works in-sample and fails on structural breaks is the default outcome, not the exception; the spec needs to specify the gauntlet.

6. **Capacity analysis.** For a hypothetical $1M, $10M, $100M portfolio, what fraction of each instrument's ADV does the system touch? What is the expected market impact? This matters because the owner directive says "scale to institutional capital eventually" — the v1 architecture either supports that or it doesn't.

7. **Reproducibility contract.** Given a spec version, a fabric snapshot, a random seed, and a model registry entry — can a second session reproduce the same decision? The spec mentions versioning but never states "reproducibility" as a first-class contract. Without it, the Phase 01 red-team's promotion audit is impossible.

8. **Data lineage tracking.** Every decision should trace back to the exact features, exact model version, exact router state, and exact input timestamps that produced it. `12-§5` mentions the decisions table stores "full brief" but the lineage is not explicit.

9. **Paper→live transfer function.** Paper trading does not cover live-execution realities: partial fills, rejected orders, after-hours announcements, exchange halts. The paper→live gate in `00-§FP-7` does not specify how these risks are qualified during paper mode.

10. **A skeptical "what could kill this" section.** Every serious quant research plan has a "failure modes we accept" section. This spec set has a "failure modes we defend against" table (§11 of `04-`) but no "failure modes we don't know how to defend against and are accepting the risk of" section. That honesty is how you avoid being surprised.
