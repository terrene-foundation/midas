# Midas Architecture — Latent-First Investment System

The architectural spine: data flows through representation learners into a continuous latent state z_t, which drives all decisions. Observable factors are explanation overlays, not decision inputs.

**Specs authority:** `specs/04-latent-first-architecture.md` (governing), `specs/00-first-principles.md` (FP-9, FP-10, FP-11)

---

## The Spine

```
DATA FABRIC → REPRESENTATION LEARNERS (pool) → STATE INFERENCE (pool)
    → POSTERIOR OVER CONTINUOUS z_t → DECISION HEADS (pool) + RENDERING LAYER
    → META-ROUTER → FRONTIER LLM (brief/debate)
```

Every arrow is a posterior, not a point estimate. Every box is a pool, not a single model.

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
