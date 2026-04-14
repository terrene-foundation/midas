# Latent-First Architecture

**Status:** GOVERNING. This spec defines the architectural spine of Midas. Every downstream decision — model selection, risk management, UI rendering, debate — flows from a continuous latent market state inferred from data.

Anchored to FP-9 (DL-dominant), FP-10 (latent over observable), FP-11 (continuous state, no labels).

---

## 1. The Principle

Returns, volatility, correlation structure, and regime transitions are driven by **latent** (unobservable) causes. The factors everyone stares at — momentum, value, carry, size, quality, realized vol, spreads — are **symptoms** of those causes. A system that routes decisions through observable factors alone is inference through a projection, losing information at every step.

Midas's core architectural move: **learn the latent state directly from data using deep representation learners**, and route every decision through that state. Econometric factors are computed alongside, but as explanation overlays, not as drivers.

> **One-line statement:** _Midas decides from a continuous probabilistic latent state `z_t` inferred from data; observable factors are the rosetta stone for user-facing explanation, not the decision input._

---

## 2. The Latent State `z_t`

### 2.1 What It Is

At any time `t`, Midas maintains a **posterior distribution** `p(z_t | x_{1:t})` where:

- `x_{1:t}` = all data available up to time `t` in the fabric (prices, fundamentals, news embeddings, macro, alt-data, order-book summaries, etc.)
- `z_t` = a continuous vector of modest dimensionality representing the latent state of the market

`z_t` is:

- **Continuous**, not bucketed. No state labels. No discrete regimes.
- **Probabilistic**, not a point estimate. The whole distribution matters — a narrow posterior means high confidence, a wide posterior means uncertain state.
- **Learned**, not engineered. The dimensions of `z_t` are whatever the representation learner finds useful; they are not pre-assigned to mean "vol" or "growth." (Post-hoc interpretation is the LLM's job in the brief-generation layer.)
- **Updated continuously** — every ingestion event updates the posterior via the state-inference head.

### 2.2 Dimensionality

A starting range of 8 to 32 dimensions is expected but is itself a hyperparameter subject to population-based tuning. Too few dimensions and the model loses resolution; too many and the posterior collapses into noise. The meta-router tracks downstream loss as a function of latent dimensionality across challengers.

### 2.3 What `z_t` Is Not

- Not a hidden Markov state (that was the Phase 01 framing and it is superseded — see FP-11)
- Not a regime label, not a regime probability distribution over labels
- Not a proprietary "market state" that maps 1:1 to factor exposures
- Not a single frozen quantity — it is a **family of candidate posteriors** from multiple representation-learner champions and challengers, with the meta-router blending or routing among them per context

---

## 3. The Spine

```
             ┌──────────────────────────────────────────────┐
             │              DATA FABRIC (§3)                │
             │   prices │ fundamentals │ news │ macro │ alt │
             └──────────────────┬───────────────────────────┘
                                │
                                ▼
             ┌──────────────────────────────────────────────┐
             │     REPRESENTATION LEARNERS (pool, §4)       │
             │ SSL transformers │ MAE │ contrastive │ VAEs   │
             │ diffusion of market state │ deep SSM pool    │
             └──────────────────┬───────────────────────────┘
                                │
                                ▼
             ┌──────────────────────────────────────────────┐
             │     STATE INFERENCE (pool, §5)               │
             │ deep Bayesian filters │ normalising flows    │
             │ neural Kalman │ energy-based posteriors      │
             └──────────────────┬───────────────────────────┘
                                │
                                ▼
        ┌───────────────────────┴───────────────────────┐
        │       POSTERIOR OVER CONTINUOUS z_t           │
        │  (center of mass + full uncertainty)          │
        └───────────────────────┬───────────────────────┘
                                │
        ┌───────────────────────┴───────────────────────┐
        │                                                │
        ▼                                                ▼
┌───────────────┐                                ┌──────────────────┐
│  DECISION     │                                │  RENDERING       │
│  HEADS (§6)   │                                │  LAYER (§7)      │
│ returns, vol, │                                │ UX "regime"      │
│ allocation,   │                                │ projection,      │
│ execution     │                                │ attention axis,  │
│ (all read z_t)│                                │ factor overlay   │
└───────┬───────┘                                └──────────────────┘
        │
        ▼
┌───────────────┐
│ META-ROUTER   │  (05-model-pool-and-meta-router.md)
│ per-context   │
│ blending of   │
│ head outputs  │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ FRONTIER LLM  │  (FP-12) — analyst + debate agents
│ project z_t + │
│ head outputs  │
│ into brief    │
│ ("what would  │
│ change my     │
│ mind")        │
└───────────────┘
```

Every arrow is a posterior, not a point estimate. Every box is a pool, not a single model.

---

## 4. Representation Learner Pool

Multiple representation learners run concurrently. Each produces a candidate `z_t` family. The meta-router tracks each learner's downstream utility and routes accordingly.

**Candidate families** (examples, not a committed list):

- **Self-supervised transformers** on multi-asset, multi-horizon sequences (masked prediction, contrastive, next-horizon)
- **Masked autoencoders** on cross-sectional snapshots + temporal windows
- **Contrastive encoders** (InfoNCE-style) learning embeddings where temporally-adjacent states are similar
- **Variational autoencoders** for explicit posterior structure
- **Denoising diffusion models** of market state for generative scenario work
- **Deep state-space models** — S4, Mamba, Kalman-NN hybrids — where the latent state has an explicit dynamics equation
- **Foundation TS models** fine-tuned on Midas's universe (TimesFM, Chronos, Moirai, or whatever is on the frontier)

**Training regime** (per `03-universe-and-data.md` §5):

1. Pre-train on large public financial corpora (cross-asset, cross-market, cross-frequency)
2. Fine-tune on the Midas fabric universe
3. Continual learning / online adaptation where the architecture supports it
4. Population-based challengers running in shadow; outer-loop promotion

**Auxiliary supervision** (multi-task loss):

- Econometric factor values as auxiliary targets (stabilizes latent geometry without forcing it to match factors)
- Realized forward returns and volatility
- News-driven event indicators
- Multi-horizon consistency penalties

---

## 5. State Inference Pool

Separate from the representation learner, the state-inference pool maintains the posterior `p(z_t | x_{1:t})` under different probabilistic assumptions. This is where Bayesian structure lives.

**Candidate families:**

- **Deep Bayesian filters** — neural networks parameterizing posterior updates
- **Normalizing flows** — rich posteriors without Gaussian assumptions
- **Neural Kalman variants** — explicit linear-Gaussian dynamics with nonlinear emissions
- **Energy-based models** — implicit posterior via score matching
- **Gaussian-process state-space hybrids** — for calibrated uncertainty in low-data regions

The inference pool consumes the representation learners' outputs and produces the full posterior. Downstream heads read the posterior; the meta-router blends inference-pool outputs when multiple are simultaneously trustworthy.

---

## 6. Decision Heads

All decision-relevant quantities are **heads** that read `z_t` posteriors as input. No head reads raw prices directly for its core computation (auxiliary inputs are allowed but not the primary signal).

### 6.1 Return Heads

- Time-series return predictors conditioned on `z_t`
- Cross-sectional return predictors (rank / relative)
- Both under the pool + router pattern

### 6.2 Volatility and Tail Heads

- Continuous volatility posteriors conditioned on `z_t`
- Tail risk heads (quantile, expected shortfall, score-based) conditioned on `z_t`
- Used by the risk layer and the rendering layer (attention-load axis — `06-continuous-regime-rendering.md`)

### 6.3 Allocation Heads

- **DRL policy networks** as the champion family — PPO, SAC, CVaR-PPO, risk-aware RL, Decision Transformer, offline RL on historical trajectories, meta-RL for regime transfer
- Allocation head input is `z_t` posterior + current positions + constraints from the envelope
- Classical optimizers (MVO, BL, HRP, RP) are **baseline challengers in the model registry**, not champions — their outputs feed into the comparison and ensemble loop but do not drive the decision unless the router selects them in a specific latent region

### 6.4 Execution Heads

- Contextual bandits over venue/timing
- Cost-aware RL for sizing and child-order scheduling (within IBKR constraints)
- Consumes `z_t` to condition on current market state

### 6.5 Cross-Sectional Heads (for security selection, v1.1+)

- CNN over the cross-section (spatial structure of the universe as a grid)
- Graph neural networks over asset-relationship graphs (correlation, co-holding, sector, supply chain)
- Cross-sectional transformers with ticker-level attention
- Output: per-name conviction posterior, consumed by the security-selection layer

---

## 7. Rendering Layer (How `z_t` Reaches The User)

The model never emits a regime label. The rendering layer projects the posterior into human-readable form. Three rendering surfaces:

### 7.1 UX Regime Projection

A 1-D **attention-load axis** is computed from `z_t` + risk head + tail head + model-disagreement metric + drawdown velocity. The UI renders this as one of Calm / Elevated / Urgent / Crisis — these are visualization bands on a continuous value, not states the model reasons about.

See `06-continuous-regime-rendering.md` for the full rendering contract.

### 7.2 Factor Overlay

A projection of `z_t` onto the factor basis (the econometric overlay) gives the frontier LLM a human-readable vocabulary for writing briefs: _"conviction is coming from a quality + low-vol tilt intensifying as credit spreads widen."_ The projection is computed post-hoc; it is not the decision driver.

When the projection is poor (the latent evidence cannot be cleanly factor-explained), the brief says so honestly — this is the owner's turn-4 decision: _"yes for now, eventually we need a transparency module, but only if the models are working."_

### 7.3 Historical Analogue Retrieval

When `z_t` is close to a historical state, the system retrieves the analogue from the fabric and displays it as a reference point (per the turn-4 acceptance of partial interpretability). The Debate agent can use analogues as evidence; the user can challenge the analogy.

---

## 8. Uncertainty Is First-Class

Every output in the spine is a distribution, not a number.

- **Narrow posterior → high confidence** → the system may propose stronger actions within the envelope
- **Wide posterior → low confidence** → the system proposes smaller actions, raises approval thresholds, or punts to the Decisions surface
- **Bi-modal posterior** → the system flags ambiguity explicitly; the brief shows both modes and their implications
- **Out-of-distribution `z_t`** (far from any training state) → automatic escalation regardless of autonomy level; the system cannot be calibrated where it has not seen data

Uncertainty is not a warning banner; it is a **control signal**. Low confidence throttles action size and raises the approval threshold continuously, not by discrete thresholds.

---

## 9. Relationship To Econometric Factors

Factors are repositioned, not removed.

| Use                                 | Kept?  | Role                                                      |
| ----------------------------------- | ------ | --------------------------------------------------------- |
| Seeding representation search space | Yes    | Auxiliary loss, regularizer                               |
| Explaining decisions to the user    | Yes    | Post-hoc projection in the brief                          |
| Brinson attribution                 | Yes    | Measures SAA vs TAA vs selection effect (§12-performance) |
| Driving the allocator               | **No** | The allocator reads `z_t`, not factor exposures           |
| Driving regime detection            | **No** | Continuous `z_t` posterior replaces regime labels         |
| Being the source of truth for risk  | **No** | Risk heads read `z_t`; factors are a cross-check          |

Factors appear in the output because humans read them. They do not appear in the core decision loop.

---

## 10. Noise Handling

Financial data is noisy because people trade for many reasons (owner note, turn 4). Latent-first architecture addresses this at the right layer:

- **Denoising autoencoders** and **contrastive objectives** in the representation learner separate signal from noise before the downstream heads see anything
- **Multi-horizon consistency penalties** in training prevent heads from memorising short-horizon noise
- **Distributional losses** over point losses wherever the target is a distribution (quantile regression, score matching)
- **Robust posteriors** in the state-inference pool — heavy-tailed priors, tempered likelihoods — so a single noisy observation doesn't collapse the posterior
- **Multi-task auxiliary supervision** (factor values, realized vol, event indicators) stabilizes the latent geometry even when any single target is noisy

---

## 11. Failure Modes and Defenses

| Failure mode                                        | Defense                                                                                                           |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Representation learner fits noise                   | Population-based challengers + walk-forward validation + multi-horizon consistency penalty                        |
| `z_t` collapses (posterior becomes trivial)         | Beta-VAE-style capacity regularization + aux supervision + monitoring of latent information content               |
| Out-of-distribution state                           | Explicit OOD detector; automatic escalation; confidence throttles action                                          |
| Representation is right but heads are wrong         | Head-level champion/challenger; meta-router blends heads per context                                              |
| Heads are right but the rendering misleads the user | Rendering contract in `06-continuous-regime-rendering.md`; briefs never assert confidence the model does not have |
| Latent state drifts (concept drift)                 | Continuous calibration tracking; automatic degradation contracts trip and demote the champion                     |

---

## 12. What This Commits Us To

- The spine is not negotiable — every decision head reads `z_t` posteriors.
- Classical methods are baselines, not champions. Anywhere they appear as a "default" in an implementation, the implementation is wrong.
- The LLM's role is **projection and communication**, not decision. The LLM never writes `z_t`; it only reads the posterior and translates it into the brief.
- Every head's output is accompanied by its uncertainty; heads that emit point estimates without posteriors are incomplete.
- Explainability is a post-hoc projection; if the projection is weak, the brief says so honestly rather than forcing a weaker model.
