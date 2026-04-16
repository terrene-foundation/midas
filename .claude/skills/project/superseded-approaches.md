# Superseded Approaches

Phase 01 planned several approaches that the owner explicitly rejected during the latent-first reframe (journal 0011-DECISION, specs FP-9/FP-10/FP-11). **Do NOT propose, implement, or reference these as defaults.** They may appear as baselines in the challenger lane only.

---

## Rejected: Econometrics-First Architecture

**Was:** Use observable factors (momentum, value, carry, size, quality, vol) as primary decision drivers. Econometric models as champions.

**Now:** Deep learning is the default everywhere. Factors are explanation overlays for briefs, not decision inputs. The allocator reads z_t, not factor exposures.

---

## Rejected: HMM Regime Detection

**Was:** Hidden Markov Model with discrete states (Bull/Bear/Sideways) as the primary regime model.

**Now:** Continuous posterior over latent state z_t. No discrete state labels. Regime "bands" (Calm/Elevated/Urgent/Crisis) are rendering projections computed by the UI from z_t, not model outputs. BOCPD-style continuous changepoint detection replaces discrete state transitions.

---

## Rejected: Black-Litterman / HRP / Risk Parity as Champions

**Was:** BL, HRP, and RP as the primary allocation methods.

**Now:** DRL policy networks (PPO, SAC, CVaR-PPO, Decision Transformer) as champions. BL, HRP, RP are **baselines in the challenger lane** — their outputs feed into the comparison loop but do not drive decisions unless the meta-router selects them for a specific latent region.

---

## Rejected: Factor-Driven Risk Models

**Was:** Factor exposure vectors as the primary risk input.

**Now:** Risk heads read z_t posteriors. Factor exposures are a cross-check, not the source of truth. Volatility and tail risk heads are conditioned on z_t.

---

## Rejected: Static Parameters

**Was:** Fixed allocation targets, static risk thresholds, hardcoded rebalancing schedules.

**Now:** Every parameter responds to market conditions (FP-3). Static defaults are seed values only. The system must get smarter over time.

---

## What Remains Valid

These Phase 01 elements survived the reframe and remain governing:

- 14 first principles (FP-1 through FP-14) — with FP-8, FP-9, FP-10, FP-11 added/reframed
- Evidence-first co-decision (FP-8 strengthened)
- Mandatory paper trading (FP-7)
- Autonomy earned through track record (FP-14)
- Singapore domicile, no US tax framework (FP-6)
- Attention is sacred (FP-13)
- IBKR dual API strategy (Web API + TWS)
