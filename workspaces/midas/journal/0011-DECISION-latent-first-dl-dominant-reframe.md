---
type: DECISION
slug: latent-first-dl-dominant-reframe
date: 2026-04-14
session: /todos
---

# DECISION — Latent-First, DL-Dominant, Continuous-State, Evidence-First Co-Decision

## Context

Phase 01 produced three governing specs (first-principles, principal-considerations, UI/UX) organized around an econometrics-first architecture: HMM-based regime detection, BL/HRP/RP ensemble allocation, factor-driven signals, discrete Calm/Elevated/Urgent/Crisis regime labels, and an AI Debate agent positioned as the product centerpiece.

During this session's /analyze review, the owner pushed back on six fronts:

1. Named specific models — the owner required **pools and a smart experimentation mechanism** ("no free lunch").
2. Framed LLM choice around cost — the owner required **frontier models (Opus/GPT-5 class) for all decision-adjacent work** because opportunity cost of a bad call dwarfs API spend.
3. Treated DL/ML as Tier-1 Frontier "add-ons" — the owner required **DL to be dominant, econometrics as explanation overlay**.
4. Anchored decisions on observable factors — the owner required **latent driver discovery via representation learning**.
5. Used discrete regime labels — the owner required **probabilistic functions over a continuous state space**.
6. Positioned the Debate agent as "AI decides vs user decides" — the owner required **evidence-first co-decision**: "compute and find the evidence to support your recommendations and we decide on the action together."

## Decision

Reframed the architectural spine in `specs/` v1 (13 governing files replacing Phase 01 artifacts).

**Core commitments:**

- **FP-9** (DL-dominant, no free lunch) — every layer holds a model pool; a meta-router blends/routes per context; champions and challengers run three concentric adaptation loops (inner: calibration, middle: contextual routing, outer: population-based promotion).
- **FP-10** (latent over observable) — a continuous posterior `z_t` learned via representation models is the system's state of truth; factors are a post-hoc projection for explanation.
- **FP-11** (continuous state, no labels) — the model never emits a regime label; the UI projects `z_t` onto a 1-D `a_t` attention-load axis rendered in soft-interpolated bands.
- **FP-12** (frontier LLMs for decision-adjacent work) — analyst, debate, research agents use Opus-class/GPT-5-class models only; cheaper models only for background bulk work.
- **FP-13** (attention is sacred) — decision weight, not surface bandwidth, drives brief density.
- **FP-14** (track record earns latitude) — autonomy is a currency, not a setting; upgrades are user-approved decisions, demotions are automatic.
- **FP-8 reframed** (evidence-first co-decision) — the Debate agent has tools that _mutate_ pending decisions; a read-only debate is dead.

**Universe scope** (owner's turn 4): ETF sector rotation (v1.0) → S&P 1500 single names (v1.1). ETFs chosen for natural diversification, liquidity, cost, and asset-class coverage.

**Data depth strategy** (owner's turn 4): pre-train on a large public corpus + fine-tune on the Midas universe, plus aggressive alternative data. Synthetic data reserved for stress testing.

**Interpretability** (owner's turn 4): deferred — "working models first, explain later."

## Trade-offs Accepted

- **Compute cost higher** — DL-dominant with population-based training needs GPU time. Owner accepted: "don't worry about budget first, let's do what is possible."
- **Interpretability weaker in v1** — latent-state decisions may not cleanly verbalize in factor language. Owner accepted: honest "partial interpretation" briefs are OK; transparency module comes after the models earn it.
- **More moving parts than single-model simplicity** — explicitly justified by FP-9; the alternative (one well-chosen model) was rejected by owner.
- **Requires significant training data** — starting with ETF sector rotation is a practical data-depth compromise that lets the representation learners run on a bounded universe before single-name noise.

## Consequences

- All Phase 01 econometric-spine plans superseded. The `02-plans/` files remain as historical context but are not authoritative.
- Phase 01 governing specs (`01-first-principles.md`, `02-principal-considerations.md`, `03-uiux-spec.md`) migrated into `specs/00-first-principles.md` (extended with FP-9 through FP-14), with other principles preserved.
- Redteam Round 1 (quant + PM) surfaced 9 CRITICAL findings that feed directly into the M00 milestone — these land in `specs/` updates AND in pre-commit gates before any model code writes.
- Trader redteam deferred due to rate limit — blocks paper-to-live gate (M19) until completed.

## Links

- `specs/00-first-principles.md`
- `specs/04-latent-first-architecture.md`
- `specs/05-model-pool-and-meta-router.md`
- `specs/06-continuous-regime-rendering.md`
- `specs/07-evidence-first-decision.md`
- `workspaces/midas/04-validate/round-1-quant-researcher.md`
- `workspaces/midas/04-validate/round-1-portfolio-manager.md`
- `workspaces/midas/todos/active/_index.md`
- `workspaces/midas/todos/active/00-redteam-fixes.md`
