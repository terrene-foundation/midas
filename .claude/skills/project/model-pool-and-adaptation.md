# Model Pool and Adaptation — Three-Loop System

**Spec authority:** `specs/05-model-pool-and-meta-router.md` (GOVERNING), `specs/04-latent-first-architecture.md` (GOVERNING)
**Purpose:** Champion/challenger infrastructure, three-loop adaptation, promotion contract

---

## Architectural One-Liners (Never Violate)

> **A.** "Midas decides from a continuous probabilistic latent state z_t inferred from data; observable factors are the rosetta stone for user-facing explanation, not the decision input."

> **B.** "No model always dominates. The system IS the selector."

> **C.** "Any spec, plan, or implementation that names one specific model as 'the' choice at any layer is wrong. Implementations reference the pool + router, not a specific entry."

---

## The Three-Loop Mechanism

### Inner Loop — Online Calibration (Continuous)

Every head's predictions are scored against real outcomes in real time. Each head maintains a **live posterior over its own local reliability** — conditioned on input state, not a global accuracy number.

**Does:** write calibration records to `model_registry` fabric table with timestamps, model version, input latent-space coordinates, predicted value, realized outcome, and loss.

**Does NOT:** retrain models, silently down-weight a head, emit user-facing output.

### Middle Loop — Contextual Routing (Per Decision)

For every decision context, the **meta-router** takes current latent state z_t and decides: which pool members to consult, how to blend or select, what the overall confidence is. The router is itself a model — contextual bandit or mixture-of-experts or Bayesian model averaging.

**Which model wins can change without retraining.** The router can shift a pool member from blended-in to blended-out in the same hour.

### Outer Loop — Population-Based Promotion (Weekly to Monthly)

New model architectures run in **shadow mode** — full decision pipeline, zero financial risk. Promoted when they meet the explicit promotion contract.

**Safety reflex:** automatic degradation-triggered demotion runs faster than promotion.

---

## Pool Families by Layer

Every layer holds a pool. Concrete architectures are examples; the pool is open and the meta-router decides what the champion is at any time.

| Layer                        | Champion families                                                                                | Challenger baselines                                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| Representation learning      | SSL transformers, MAE, contrastive, VAEs, diffusion, deep SSMs, foundation TS fine-tuned         | PCA, factor loadings, static embeddings                                       |
| State inference              | Deep Bayesian filters, normalizing flows, neural Kalman, energy-based posteriors, GP-SSM hybrids | HMM with fixed state count, Kalman filter                                     |
| Return — time-series         | TCN, transformers (iTransformer, PatchTST, Crossformer), Mamba/S4, neural ODEs                   | ARIMA, exponential smoothing                                                  |
| Return — cross-sectional     | CNNs, GNNs, cross-sectional transformers, equivariant networks                                   | Fama-French + momentum regression                                             |
| Volatility / tail risk       | Deep GARCH hybrids, realized-vol transformers, normalizing-flow tail, quantile DL                | GJR-GARCH, HAR-RV, EVT-POT                                                    |
| Allocation / policy          | PPO, SAC, CVaR-PPO, Decision Transformer, offline RL, meta-RL                                    | **Mean-Variance, Black-Litterman, HRP, Risk Parity** — always challenger only |
| Execution / sizing           | Cost-aware RL, contextual bandits, sequence models                                               | Static TWAP/VWAP, linear impact                                               |
| Embeddings (text)            | Multiple parallel domain-tuned + frontier-LLM encoders                                           | TF-IDF, static word embeddings                                                |
| Language (decision-adjacent) | Frontier only (Opus-class, GPT-5-class, next-gen reasoning)                                      | Cheaper models only for background bulk                                       |

---

## Shadow Lane Isolation Contract

| Property  | Value                                                                              |
| --------- | ---------------------------------------------------------------------------------- |
| Data      | Same live fabric                                                                   |
| Decisions | Written to `shadow_decisions` table, never to order manager                        |
| Output    | Hypothetical P&L, hypothetical Brinson attribution, hypothetical override outcomes |
| Isolation | Shadow cannot affect positions, cost budgets, or the user                          |
| Duration  | Minimum shadow window before promotion contract evaluated                          |

**Shadow lane cannot call the IBKR adapter.** Shadow flow calls to `ibkr_adapter.submit_order`, `order_manager.submit`, `positions.write`, or `orders.write` are a violation.

---

## Promotion Contract (ALL must be true)

A challenger is promoted to champion only when:

1. **Dominates the current champion** on composite: risk-adjusted return minus cost minus turnover, over shadow window
2. **No latent region with Sharpe worse** than a floor calibrated to champion's worst region
3. **Calibration at least as good** — challenger's calibration curve not worse than champion's in any latent region (Holm-Bonferroni corrected)
4. **Override convergence not worse** — user would not override challenger's decisions more than champion's
5. **Regime transfer robust** — advantage does not depend on a single regime in training data
6. **Model-disagreement bounded** — correlated enough with champion that transition is not a regime change

**Demotion is automatic.** Champion degrades below its degradation contract → demoted to prior champion + notification surfaced.

---

## Online Calibration Metrics Per Head

| Metric                                    | Use                                                         |
| ----------------------------------------- | ----------------------------------------------------------- |
| Regime-conditional hit rate               | Is this head right in this kind of market?                  |
| Quantile calibration curve                | When head says 70% confidence, is it right 70% of the time? |
| Horizon-specific loss (1/3/6 month)       | Does this head decay across horizons?                       |
| Directional accuracy                      | Basic signed correctness                                    |
| Information coefficient (cross-sectional) | Rank correlation with realized returns                      |
| Tail hit rate (risk heads)                | Does tail estimate cover realized tail events?              |
| Brier score                               | Calibration across probability bins                         |
| Disagreement with peers                   | How correlated with other pool members?                     |

---

## Router Overfitting Protocol

- **PurgedKFold** cross-validation — prevents information leakage from train to test in temporal data
- **Parameter-count cap** — router params ≤ 10% of training observations
- **Minimum 504 observations** before router can drive live decisions
- **Naive baseline required** — "always pick head with highest recent calibration" is a required challenger; router must outperform it

**Temporal leakage:** any training record where `outcome_ts < pit_ts` is a block — the model was trained on information not available at decision time.

---

## Calibration Methodology

- **k-NN neighborhood estimator**: k grows with sample size, shrinks with dimensionality, bounded [5, min(n/4, 50)]
- **Holm-Bonferroni correction** across 6 promotion-contract criteria → family-wise α control
- **Deflated Sharpe Ratio (DSR)** accounts for overfitting bias in Sharpe estimates
- **Probability of Backtest Overfitting (PBO)** for promotion gate
- **20 random-noise heads must yield zero certified champions** — integration test

---

## Latent State z_t — Core Properties

- **Continuous** — no state labels, no discrete regimes
- **Probabilistic** — full distribution; narrow = high confidence, wide = uncertain
- **Learned** — dimensions discovered by representation learner; not pre-assigned
- **Updated every ingestion event** via state-inference head
- **A family of candidate posteriors** from multiple representation-learner champions/challengers
- **Dimensionality**: 8–32 (hyperparameter, population-tuned)

**z_t is NOT:** a hidden Markov state (Phase 01 framing, superseded), a regime label, a 1:1 mapping to factor exposures, a single frozen quantity.

---

## Evidence Store for Debate Agent

All three loops write to a unified evidence store the Debate agent consumes. The Debate agent knows:

- Which head currently produced the recommendation
- That head's calibration posterior in the current latent region
- The other candidates the router considered and why they lost
- The shadow challenger's hypothetical alternative
- The historical analogue from the state library
- The counterfactual under the user-proposed alternative

If a layer does not write into the evidence store, it **cannot participate in Debate**.

---

## Uncertainty Is a Control Signal

- **Narrow posterior** → high confidence → system may propose stronger actions within envelope
- **Wide posterior** → low confidence → smaller actions, raised approval thresholds, punt to Decisions surface
- **Bi-modal posterior** → system flags ambiguity explicitly; brief shows both modes
- **OOD z_t** → automatic escalation regardless of autonomy level

**Uncertainty is not a warning banner; it is a control signal.**

---

## What This Commits Us To

1. Every layer with a decision holds a pool managed by the three-loop mechanism
2. Classical methods always appear, always in the challenger lane, never as default champion
3. Promotions are user-facing decisions; demotions are automatic
4. The evidence store is the substrate for Debate; if a layer does not write to it, it cannot participate in Debate
5. Every implementation references pool + router, never a specific named model
6. The LLM's role is projection and communication; it never writes z_t
7. Every head's output is accompanied by its uncertainty; point estimates without posteriors are incomplete
