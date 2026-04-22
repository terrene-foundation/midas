# Midas Architecture — Latent-First Investment System

The architectural spine: data flows through representation learners into a continuous latent state z_t, which drives all decisions. Observable factors are explanation overlays, not decision inputs.

**Specs authority:** `specs/04-latent-first-architecture.md` (governing), `specs/00-first-principles.md` (FP-9, FP-10, FP-11), `specs/02-value-chain.md` (operating model), `specs/12-performance-and-track-record.md` (Brinson + metrics)

---

## The Spine

```
DATA FABRIC → REPRESENTATION LEARNERS (pool) → STATE INFERENCE (pool)
    → POSTERIOR OVER CONTINUOUS z_t → DECISION HEADS (pool) + RENDERING LAYER
    → META-ROUTER → FRONTIER LLM (brief/debate)
```

Every arrow is a posterior, not a point estimate. Every box is a pool, not a single model.

---

## 14 First Principles (Quick Reference)

Every change is checked against these. Violation = BLOCK.

| ID    | Principle                                  | Violation Test                                               |
| ----- | ------------------------------------------ | ------------------------------------------------------------ |
| FP-1  | Institutional infrastructure, democratized | Reads like "better than retail"? Wrong.                      |
| FP-2  | Data drives everything                     | Removing a hardcoded ticker breaks it? Wrong.                |
| FP-3  | Dynamic over static                        | Unplugged 6 months, behaves identically? Not dynamic enough. |
| FP-4  | Investing, not trading                     | Useful to a day trader? Probably wrong.                      |
| FP-5  | Push the frontier                          | A 2015 quant prof approves? Not frontier enough.             |
| FP-6  | Singapore domicile, no US tax              | Tax-loss harvesting? Wrong.                                  |
| FP-7  | Mandatory paper trading                    | Can skip paper? Wrong.                                       |
| FP-8  | Evidence-first co-decision                 | Debate can only narrate? Wrong.                              |
| FP-9  | DL-dominant, no free lunch                 | One model as "the" choice? Wrong.                            |
| FP-10 | Latent over observable                     | Allocator reads factor exposures? Upside-down.               |
| FP-11 | Continuous state, no labels                | Model emits a regime label string? Wrong.                    |
| FP-12 | Frontier LLMs for decision-adjacent        | Saving API spend on briefs? Wrong cost model.                |
| FP-13 | Attention is sacred                        | $500 and $50K briefs share template? Wasting attention.      |
| FP-14 | Track record earns latitude                | Autonomy silently promoted? Contract broken.                 |

**Operational consequences:** FP-8 requires "what would change my mind" appendices and evidence provenance. FP-12 requires frontier models for all decision-adjacent LLM calls. FP-13 requires attention budget tracking and regime-tiered notifications. FP-14 requires Brinson attribution as autonomy currency.

---

## Value Chain (5 Blocks)

```
BLOCK 1 — INTELLIGENCE & RESEARCH
  Data Ingestion │ News & Alt-Data │ Knowledge Base │ Research Agent

BLOCK 2 — INVESTMENT MANAGEMENT (3 layers)
  SAA (monthly) → TAA (weekly/regime-conditional) → Security Selection (weekly)

BLOCK 3 — RISK, COMPLIANCE, VALUATION (cross-cutting, has veto)
  Pre-Trade Compliance │ Continuous Risk │ Valuation/NAV │ Reporting

BLOCK 4 — PORTFOLIO CONSTRUCTION & EXECUTION
  Portfolio Construction │ Trade Execution │ Allocation Adjustment

BLOCK 5 — PERFORMANCE & OPERATIONS
  Performance Measurement │ Attribution │ Order Ops │ Settlement
```

### Kailash Framework Mapping

| Block                                            | Framework             |
| ------------------------------------------------ | --------------------- |
| Data Ingestion, Feature Fabric, Feature Store    | DataFlow              |
| Representation learning, model pool, meta-router | Kailash ML + Core SDK |
| LLM analyst, debate agent, research assistant    | Kaizen                |
| Pre-Trade Compliance, envelope enforcement       | PACT                  |
| Workflow orchestration (daily pipelines)         | Core SDK              |
| Multi-channel delivery (Web + Mobile)            | Nexus                 |
| MCP tools exposed to frontier LLMs               | Kailash MCP           |

### v1 Scope Boundary

**In scope:** All 5 blocks on ETF + S&P 1500 universe. v1.0 = ETF sector rotation only. v1.1 adds S&P 1500 after positive Brinson allocation effect in paper trading.

**Out of v1:** Options/leverage/derivatives, multi-tenant, commercialization, real-time streaming, dedicated explainability module, US single names beyond S&P 1500, tax-lot accounting.

---

## Performance Measurement

### Brinson-Fachler Attribution

- **Allocation effect** = (w_port - w_bench) × (r_bench - r_total). Credit for asset-class tilts.
- **Selection effect** = w_bench × (r_port - r_bench). Credit for picking winners.
- **Interaction** = (w_port - w_bench) × (r_port - r_bench). Joint credit.

Buckets: asset class → sector (11 GICS) → duration (FI) → style (equity).

**Benchmark hierarchy:** Primary = SAA-static baseline. Secondary = 60/40. Tertiary = S&P 500 total return.

**Time windows:** 12-month is the only window that triggers autonomy transitions. Short windows (1-week, 3-month) are context-only, never promotion triggers.

### Track Record Composite Score (7 Components)

1. Brinson allocation effect (3-month rolling)
2. Brinson selection effect (3-month rolling)
3. Calmar ratio (3-month rolling)
4. Calibration quality (down-weights over-confidence)
5. Override convergence (trend direction)
6. Degradation event count (each penalizes)
7. Turnover / cost drag (excessive penalizes)

Statistical discipline: all metrics are distributions with bootstrap CIs, not point estimates. Promotion requires bootstrap lower bound to exceed floor.

### Counterfactual Tracking

Every decision has a counterfactual computed after horizon closes: executed → "what if held", rejected → "what recommendation would have produced", modified → "original recommendation".

---

## The Latent State z_t

- **Continuous** — no state labels, no discrete regimes
- **Probabilistic** — full posterior distribution, not point estimate
- **Learned** — dimensions are discovered by representation learners, not pre-assigned
- **Updated continuously** — every ingestion event updates the posterior

Dimensionality: 8–32 dimensions (hyperparameter, population-tuned).

### What z_t Is NOT

- Not a hidden Markov state (superseded — see `superseded-approaches.md`)
- Not a regime label or regime probability distribution
- Not a 1:1 mapping to factor exposures

---

## Module Surface (src/midas/)

| Module             | Role                                                                                                                                                                               | Spec   |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `fabric/`          | Data fabric — ingestion, storage, adapters (IBKR, FRED, EODHD, alt-data)                                                                                                           | 03, 14 |
| `ml/`              | Representation learners + state inference pools                                                                                                                                    | 04, 05 |
| `heads/`           | Decision heads (returns, vol, allocation, execution, cross-sectional)                                                                                                              | 04 §6  |
| `router/`          | Meta-router — contextual blending, calibration, PBT harness, promotion                                                                                                             | 05     |
| `state_inference/` | Bayesian filters, changepoint detection, OOD detection, posterior combination                                                                                                      | 04 §5  |
| `agents/`          | LLM agents — analyst (brief), debate (co-decision), orchestrator, research                                                                                                         | 07, 08 |
| `attribution/`     | Brinson decomposition, NAV, counterfactual, track record scoring                                                                                                                   | 12     |
| `compliance/`      | Pre-trade compliance agent, escalation rules, envelope enforcement                                                                                                                 | 11     |
| `execution/`       | Order state machine, reconciliation, IBKR execution adapter                                                                                                                        | 13, 14 |
| `autonomy/`        | Ladder (L0–L4), envelope, trust boundary, triggers                                                                                                                                 | 08     |
| `brief/`           | Composer, density matrix, templates, top-of-fold cards                                                                                                                             | 07, 09 |
| `api/`             | FastAPI routes — health, pulse, decisions, debate, portfolio, backtest, signals, settings, compliance, audit. Rate-limited (60 req/min per-IP), JWT auth, IDOR-protected mutations | 09     |
| `shadow/`          | Shadow lane — challenger models run in isolation, monitored for promotion                                                                                                          | 05 §5  |
| `universe/`        | S&P 1500 universe management, changelog, filters                                                                                                                                   | 03     |
| `scheduler/`       | Background jobs (EOD ingestion, inference, calibration, rebalance check)                                                                                                           | 11 §7  |
| `paper_trading/`   | Paper mode enforcement, 2-week minimum gate, validation reports                                                                                                                    | FP-7   |
| `evaluation/`      | Probes — calibration, OOD, stress testing                                                                                                                                          | 04 §11 |

---

## Key Architectural Rules

1. **Every decision head reads z_t posteriors** — no head reads raw prices for core computation
2. **Classical methods are baselines, never champions** — MVO, BL, HRP, RP are in the challenger lane only
3. **The LLM never writes z_t** — it reads the posterior and translates into briefs
4. **Uncertainty is a control signal** — narrow posterior → stronger actions; wide posterior → throttle and escalate
5. **Regime labels live only in the rendering layer** — the model never emits string labels
6. **OOD detection escalates to Crisis** — regardless of VIX, spreads, or drawdown

---

## Representation Learner Shape Contracts

All pool models (SSLTransformer, VAE, MAE, DeepSSM) follow the same `forward()` pattern:

```python
def forward(self, x):
    # x.shape == (batch, seq, input_dim)
    encoded = self.encode(x)           # (batch, seq, latent_dim)
    z_pooled = self.pool(encoded)      # (batch, latent_dim)
    z_broadcast = z_pooled.unsqueeze(1).expand(-1, seq_len, -1)  # (batch, seq, latent_dim)
    recon = self.decode(z_broadcast)   # (batch, seq, input_dim)
    return z_pooled, recon             # z_pooled for downstream, recon for loss
```

**DeepBayesianFilter**: `noise_net` input is `3 * latent_dim` (not 2x). Use `.detach().numpy()` before `.numpy()` on tensors with grad.

---

## Attention Bands

Rendered from z_t + risk heads + model disagreement:

| Band       | UX Behavior                           | Notification   |
| ---------- | ------------------------------------- | -------------- |
| `calm`     | Dashboard default density             | Silent         |
| `elevated` | Structured push notifications         | Push           |
| `urgent`   | Approval queue promoted, focus mode   | Haptic + sound |
| `crisis`   | Emergency banner, kill switch visible | All channels   |

Values are lowercase strings in the `AttentionBand` enum. Escalation rules MUST match case exactly.

---

## Open Items (Known Gaps from Red Team Rounds 8-12)

These are architecturally-significant gaps identified but not yet resolved. Future sessions should address them.

| ID    | Gap                                                                                                     | Severity | Source              |
| ----- | ------------------------------------------------------------------------------------------------------- | -------- | ------------------- |
| GAP-1 | Onboarding: backend exists (`OnboardingRouter` 4-step state machine) but no `/onboarding` frontend page | CRITICAL | Value audit         |
| GAP-2 | IBKR order state machine lacks spec-required granular states; rejection code taxonomy incomplete (3/8)  | CRITICAL | Red team round 9    |
| GAP-3 | Brief composer missing 4 of 7 mandatory sections                                                        | HIGH     | Red team round 9    |
| GAP-4 | Debate agent is single-turn, not multi-round evidence-grounded conversation                             | HIGH     | Value audit         |
| GAP-5 | No notification system (no push, no weekly summary, no haptic)                                          | MEDIUM   | Value audit         |
| GAP-6 | `ModelRegistry.promote()` and `.retire()` are no-ops (orphan pattern)                                   | HIGH     | Code quality review |
| GAP-7 | Backtest return series uses fixed 0.1 weight (no portfolio allocation model)                            | MEDIUM   | Value audit         |

---

## Architecture Rules (From Red Team Rounds 8-12)

1. **Backend is the authority for thresholds** — frontend MUST NOT duplicate numeric threshold constants. Serve from API. Frontend/backend misalignment caused different regime behavior.
2. **"Automatic" in spec = scheduled job or event subscription** — not just a manual method. Kill switch auto-trip, stale-data eviction, compliance rule sync all require wiring.
3. **Every blocking gate must have backend enforcement** — frontend-only gates (e.g., paper-to-live acknowledgment) are circumventable by page refresh.
4. **Frontend mock data is a zero-tolerance violation** — `PLACEHOLDER_DATA`, `MOCK_*`, hardcoded `met: true` in safety gates. Detect with frontend-specific grep patterns.
5. **Engine-first frontend pattern** — single `api-client.ts` with typed `request<T>()`, useQuery hooks for data, Zustand only for cross-component state, all stores initialized from API responses. This is the verified reference architecture.
6. **Regime-adaptive cross-fade (PulseShell)** — four-band cross-fade with derived layout bands, opacity transitions, and different gauge/button/decision configs per band. Reference implementation for regime-adaptive UI.
