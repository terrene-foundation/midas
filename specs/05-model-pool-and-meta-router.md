# Model Pool and Meta-Router

**Status:** GOVERNING. Defines the champion/challenger infrastructure, the three-loop adaptation mechanism, and how no-free-lunch is operationalized.

Anchored to FP-9 (DL-dominant, no free lunch), FP-14 (track record earns latitude), and the owner's turn-4 correction: _"there is no one model that always dominates, we want to know the pool of models and have a smart mechanism to experiment and adapt."_

---

## 1. Principle

> **No model always dominates. The system IS the selector.**

Midas does not pick a model. It holds a **pool** at every layer where a choice exists and runs a **model-of-models** that routes, weights, promotes, and demotes based on continuous calibration against real outcomes. The mechanism is the product.

This has three concentric loops operating at three different timescales:

1. **Inner loop — online calibration** (continuous)
2. **Middle loop — contextual routing** (per decision)
3. **Outer loop — population-based promotion** (weekly to monthly)

Plus a **safety reflex** that runs faster than promotion: automatic degradation-triggered demotion.

---

## 2. Pools (by layer, not by name)

Every layer listed below holds a pool. Concrete architectures are examples for orientation — the pool is open and the meta-router decides what the champion is at any time.

| Layer                            | Pool families (examples)                                                                                                                                  | Challenger baselines                                        |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| **Representation learning**      | Self-supervised transformers, MAE, contrastive encoders, VAEs, diffusion of market state, deep SSMs (S4/Mamba/Kalman-NN), foundation TS models fine-tuned | PCA, factor loadings, static embeddings                     |
| **State inference**              | Deep Bayesian filters, normalizing flows, neural Kalman, energy-based posteriors, GP-SSM hybrids                                                          | HMM with fixed state count, Kalman filter                   |
| **Return — time-series**         | TCN families, transformers (iTransformer, PatchTST, Crossformer), Mamba/S4, neural ODEs, foundation TS models                                             | Time-series momentum, ARIMA, exponential smoothing          |
| **Return — cross-sectional**     | CNNs over the cross-section, graph neural networks, cross-sectional transformers, equivariant networks                                                    | Fama-French + momentum regression, ranked factor composites |
| **Volatility / tail risk**       | Deep GARCH hybrids, realized-vol transformers, normalizing-flow tail models, quantile DL, score-based diffusion                                           | GJR-GARCH, HAR-RV, EVT-POT                                  |
| **Allocation / policy**          | PPO, SAC, TD3, CVaR-PPO, risk-aware RL, Decision Transformer, offline RL, meta-RL for transfer                                                            | Mean-Variance, Black-Litterman, HRP, Risk Parity            |
| **Execution / sizing**           | Cost-aware RL, contextual bandits for venue/timing, sequence models for impact                                                                            | Static TWAP/VWAP, linear impact model                       |
| **Embeddings (text)**            | Multiple parallel encoders — domain-tuned, frontier-LLM embeddings, instruction-tuned, sparse+dense hybrids                                               | TF-IDF, static word embeddings                              |
| **Language (decision-adjacent)** | Frontier only (Opus-class, GPT-5-class, next-gen reasoning) per FP-12                                                                                     | Cheaper models only for background bulk work                |

**Rule:** any spec, plan, or implementation that names one specific model as "the" choice at any of these layers is wrong. Implementations reference the pool + router, not a specific entry.

---

## 3. Inner Loop — Online Calibration (Continuous)

### 3.1 What It Does

Every head's predictions are scored against outcomes in real time. Each head maintains a **live posterior over its own local reliability** — not a global accuracy number, but a calibration curve conditioned on input state.

### 3.2 Metrics Tracked Per Head

| Metric                                              | Use                                                                       |
| --------------------------------------------------- | ------------------------------------------------------------------------- |
| Regime-conditional hit rate                         | Is this head right in this kind of market?                                |
| Quantile calibration curve                          | When this head says 70% confidence, is it actually right 70% of the time? |
| Horizon-specific loss (1/3/6 month)                 | Does this head decay across horizons?                                     |
| Directional accuracy                                | Basic signed correctness                                                  |
| Information coefficient (for cross-sectional heads) | Rank correlation with realized returns                                    |
| Tail hit rate (for risk heads)                      | Does the tail estimate cover realized tail events?                        |
| Brier score (for classification-like outputs)       | Calibration across probability bins                                       |
| Disagreement with peers                             | How correlated are this head's outputs with other pool members?           |

### 3.3 Storage

Calibration records write to the `model_registry` fabric table with timestamps, model version, input latent-space coordinates, predicted value, realized outcome, and loss. Historical calibration is queryable by the router and by the Debate agent.

### 3.4 What It Does Not Do

- It does not retrain models. Training is the outer loop.
- It does not silently down-weight a head. Down-weighting is the router's decision.
- It does not emit user-facing output. It writes to the fabric; consumers read it.

---

## 4. Middle Loop — Contextual Routing (Per Decision)

### 4.1 What It Does

For every decision context, a **meta-router** takes the current latent state `z_t` and decides:

- Which pool members to consult
- How to blend or select among them
- What the overall confidence should be

### 4.2 Router Structure

The router is itself a model — a contextual bandit or mixture-of-experts or Bayesian model averaging layer — trained on historical `(context, head outputs, realized outcome)` tuples. Not a fixed rule.

**Inputs:**

- Current `z_t` posterior
- Each pool member's recent calibration in similar `z_t` neighborhoods
- Each pool member's output with its uncertainty
- Current decision context (SAA vs TAA vs Security Selection vs execution)

**Output:**

- A blended recommendation with an explicit posterior over which pool members contributed and how much

### 4.3 Why A Pool Member Wins In One State And Loses In Another

This is the entire point. A DRL policy trained on a specific reward shape may dominate in one latent region and underperform in another. A classical risk-parity baseline may actually be the best choice in a narrow sliver of latent space (low-confidence regions where the DRL's training data is sparse). The router learns these boundaries from outcomes and routes accordingly.

**Which model wins can change without retraining.** The router can shift a pool member from blended-in to blended-out in the same hour, if the inner loop says that's what the data wants.

### 4.4 Routing For Embeddings and LLMs Too

The routing principle applies to the embedding pool and the language pool, not just the decision pool:

- **Embeddings:** multiple encoders run on every document; the router picks the best one for each query type
- **Language:** frontier-LLM routing — Opus for decision-adjacent, GPT-5 for specific reasoning tasks where the frontier is known to differ, with fallbacks handled by the router

### 4.5 Router Self-Evaluation

The router itself is scored by the outcomes of its decisions. A router that performs worse than a simple "always pick highest-recent-calibration" baseline is in the challenger lane and subject to promotion/demotion.

---

## 5. Outer Loop — Population-Based Challenger Promotion

### 5.1 What It Does

The slowest loop. New model architectures, new hyperparameter populations, and new training windows run in **shadow mode** — full decision pipeline, zero financial risk — and are promoted when they meet an explicit contract.

### 5.2 Shadow Lane Mechanics

| Property  | Value                                                                              |
| --------- | ---------------------------------------------------------------------------------- |
| Data      | Same live fabric                                                                   |
| Decisions | Written to `shadow_decisions` table, never to the order manager                    |
| Output    | Hypothetical P&L, hypothetical Brinson attribution, hypothetical override outcomes |
| Isolation | Shadow lane cannot affect positions, cost budgets, or the user                     |
| Duration  | Minimum shadow window before promotion contract is evaluated (weeks to months)     |

### 5.3 Population-Based Training

Multiple configurations of a single architecture train in parallel — different random seeds, different hyperparameters, different training windows. Best performers propagate; worst are retired. This is the classical Population-Based Training pattern adapted to the Midas context.

### 5.4 Promotion Contract

A challenger is promoted to champion only when **all** of the following are true, evaluated on the shadow window:

- **Dominates the current champion** on a composite objective — risk-adjusted return minus cost minus turnover, integrated over the shadow window
- **No latent region with Sharpe worse than** a floor that is itself calibrated to the current champion's worst region
- **Calibration at least as good** — the challenger's calibration curve is not worse than the champion's in any latent region with meaningful data
- **Override convergence not worse** — the user would not have overridden the challenger's decisions more than the champion's
- **Regime transfer robust** — the challenger's advantage does not depend on a single regime the training data happened to contain
- **Model-disagreement bounded** — the challenger is not a wild outlier; its recommendations are correlated enough with the current champion that the transition is not a regime change for the user

### 5.5 Promotion Is A User-Facing Decision

When a challenger clears its contract, **the promotion becomes a decision in the Decisions surface.** The user sees:

- Shadow P&L, attribution, regime breakdown
- Which past decisions would have differed
- Calibration comparison
- Override-behavior comparison
- A diff view of the allocator's behavior in representative states

The user approves or declines. This is FP-14 (track record earns latitude) made concrete — promotions require the user to see the evidence. At autonomy L4 the user may pre-delegate auto-promotion for challengers that meet a specific extended contract, but the default is always human-in-the-loop.

### 5.6 Demotion Is Automatic

A champion that fails its **degradation contract** is demoted automatically:

- Live calibration degrades below a floor tracked vs shadow calibration
- Live hit rate degrades below a trailing window floor
- User override rate exceeds a threshold
- Risk head's tail hit rate falls below coverage target
- Champion's recommendations diverge too far from recent training distribution (model is being asked to extrapolate)

Demotion demotes to the prior champion and surfaces a notification in the Decisions surface. **Safety runs faster than promotion.**

---

## 6. Challenger Ownership By Layer

Every pool layer has a champion slot and at least one challenger slot. This means at any time the system is running multiple model pipelines in parallel across the full stack:

| Layer                       | # of simultaneous lanes              | Purpose                                                          |
| --------------------------- | ------------------------------------ | ---------------------------------------------------------------- |
| Representation learner      | 1 champion + N challengers           | Continuous search for better latent geometry                     |
| State inference             | 1 champion + N challengers           | Continuous search for better posteriors                          |
| Return heads (each horizon) | 1 champion + N challengers           | Continuous search per horizon                                    |
| Vol / tail heads            | 1 champion + N challengers           | Tail calibration is where classical often wins; the lane is live |
| Allocation policy           | 1 champion + N challengers           | DRL default champion; classical baselines always in challenger   |
| Execution                   | 1 champion + N challengers           | Cost estimates are noisy; the bandit lane is always live         |
| Embeddings                  | Multiple champions (per query type)  | Routing is per-type, not global                                  |
| Language                    | 1 primary frontier model + fallbacks | Fallback escalation is automated                                 |

---

## 7. Evidence Store For The Debate Agent

All three loops write to a unified evidence store that the Debate agent consumes. When the user argues with Midas, they are arguing with a system that knows:

- Which head currently produced the recommendation
- That head's calibration posterior in the current latent region
- The other candidates the router considered and why they lost
- The shadow challengers' hypothetical alternative
- The historical analogue from the state library
- The counterfactual under the user-proposed alternative

The Debate agent calls tools that query this store and that **actually re-run the optimizer under new constraints**. This is the mechanism behind FP-8 (evidence-first co-decision). See `07-evidence-first-decision.md`.

---

## 8. What About Single-Model Simplicity?

A reasonable objection: three loops and a pool at every layer is a lot of moving parts. Wouldn't a single well-chosen model be simpler?

Yes, and it would also be wrong.

- The owner explicitly rejected single-model framing in turn 4: _"there is no one model that always dominates."_
- Phase 01 baked in specific model choices (HMM, DCC-GARCH, BL/HRP/RP ensemble) and the owner called it "econometrics-first, DL as fringe." The pool mechanism is the structural answer.
- Simplicity on the surface (one model) creates complexity underneath (a cascade of ad-hoc fixes when the one model fails in a regime it wasn't designed for).
- The pool pattern is the cheapest form of robustness that does not require a human to pick the right model in real time.

---

## 9. Compute Profile

The owner's direction (turn 4): don't worry about budget first, do what is possible.

- **Training:** GPU time on cloud (Modal / RunPod / Lambda / AWS). Expect substantial spend during the initial training-cycle phase when multiple challengers are in population-based training.
- **Inference:** smaller cloud instance or local; the meta-router's per-decision runtime is modest because champion heads are fast at inference — it is training that is GPU-heavy.
- **Storage:** the fabric holds the evidence store and historical latent states; expect growth as population-based training retains checkpoint metadata.

Population-based training can be paused or scaled down as the pool stabilizes. This is not a forever-on cost.

---

## 10. What This Commits Us To

- Every layer with a decision to make holds a pool and is managed by the three-loop mechanism
- Classical methods always appear, always in the challenger lane, never as the default champion
- Frontier LLMs are the default for decision-adjacent language work; cost-saving substitution is only allowed for background bulk work
- Promotions are user-facing decisions; demotions are automatic
- The evidence store is the substrate for Debate; if a layer does not write into the evidence store, it cannot participate in Debate
- Every implementation reference is to the pool + router, never to a specific named model

---

## 11. Relationship To Other Specs

- `04-latent-first-architecture.md` — defines `z_t`; the router's context for every decision
- `06-continuous-regime-rendering.md` — defines how `z_t` reaches the UI; routing can also be regime-conditional
- `07-evidence-first-decision.md` — defines how the router's outputs and the evidence store feed the Decisions surface and the Debate agent
- `08-autonomy-and-trust.md` — defines how track record (inner-loop metrics + outer-loop promotions) drives autonomy upgrades (FP-14)
- `11-compliance-and-risk.md` — defines the Pre-Trade Compliance Agent's veto over any router output
- `12-performance-and-track-record.md` — defines how Brinson attribution and calibration feed the promotion contract
