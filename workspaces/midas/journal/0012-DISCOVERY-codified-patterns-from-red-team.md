---
type: DISCOVERY
date: 2026-04-16
created_at: 2026-04-16T12:00:00Z
author: agent
session_id: midas-zai
project: midas
topic: Patterns codified into project skills from red team and spec extraction
phase: codify
tags: [skills, institutional-knowledge, model-pool, evaluation, execution, ibkr]
---

# Patterns Codified Into Project Skills

## What Was Extracted

Three rounds of extraction produced four new or replacement artifacts:

### 1. `skills/project/model-pool-and-adaptation.md` (NEW)

Extracted from `specs/05-model-pool-and-meta-router.md` and `specs/04-latent-first-architecture.md`. Captures:

- **Three-loop adaptation mechanism**: inner (continuous calibration), middle (per-decision routing), outer (population-based promotion with safety reflex demotion)
- **Champion/challenger infrastructure**: shadow lane isolation contract, promotion contract (6 independent gates), automatic degradation demotion
- **Pool families by layer**: 9 functional layers from representation learning through language, with champion families and mandatory challenger baselines
- **Router overfitting protocol**: PurgedKFold, parameter-count cap (≤10% of observations), minimum 504 observation gate, naive baseline challenger requirement
- **Calibration methodology**: adaptive k-NN neighborhood sizing, Holm-Bonferroni family-wise error rate control across 6 promotion criteria, Deflated Sharpe Ratio, Probability of Backtest Overfitting
- **Evidence store for Debate**: all three loops write to unified evidence store; Debate agent knows which head produced recommendation, what the router considered, what shadow challengers would have done

### 2. `skills/project/evaluation-probes.md` (NEW)

Extracted from all 10 probe files in `tests/evaluation/probes/`. Encodes acceptance contracts as a reference skill:

- **10 probes across 8 domains**: calibration, router overfitting, shadow lane isolation, track record gates, kill switch, envelope widening, debate concession, quote-moved, top-of-fold card, latent learnability
- **Probe design principles**: synthetic injection, single top-level assertion, detailed subordinate booleans for localized failure, boundary testing at exact threshold and one-unit-past
- **Structural vs behavioral enforcement table**: which probes are enforced in code (bypass impossible) vs. which emit audit signals
- **20 random-noise heads must yield zero certified champions**: the integration test that validates family-wise Type I error control

### 3. `skills/project/execution-ibkr.md` (NEW)

Extracted from `specs/13-execution-cost-and-microstructure.md`, `specs/14-ibkr-integration.md`, and source implementation. Captures:

- **Transaction cost decomposition**: 6-term model (spread, impact, commission, tax, slippage, gap) — each a distribution, compliance reads upper quantile
- **PLAF mechanics**: seeds (1.5× spread, 2× impact, +X bps slippage), gate logic distinguishing "clean paper" from "safe live"
- **IBKR Web API v1.0 contract**: 50 req/min hard / 40/min soft cap, 6-tier priority queue, order state machine (9 IBKR states → 7 Midas canonical), rejection taxonomy (7 categories)
- **Quote-moved-since-brief**: regime-adaptive thresholds (CALM 0.5%, ELEVATED 0.3%, URGENT 0.2%), strict inequality, modal re-confirm flow
- **Execution safety rules**: NaN guard, near-zero division guard, credential safety, market-order restrictions, parent→child decomposition, PLAF on paper costs, stale inputs block

### 4. `skills/project/SKILL.md` (RESTRUCTURED)

Removed 5 SDK-generic files that had been mistakenly placed in project skills. Replaced infrastructure table with inline references to the 6 correct project skills.

---

## What Was Removed (SDK-Generic Noise)

Five files were deleted from `skills/project/`:

| File                           | Reason                                                                                        |
| ------------------------------ | --------------------------------------------------------------------------------------------- |
| `pool-safety.md`               | Duplicate of `rules/connection-pool.md`                                                       |
| `dataflow-provenance-audit.md` | Byte-for-byte duplicate of `skills/02-dataflow/dataflow-provenance-audit.md`                  |
| `fabric-cache-consumers.md`    | Byte-for-byte duplicate of `skills/02-dataflow/dataflow-fabric-cache-consumers.md`            |
| `ml-quick-reference.md`        | Generic kailash-ml reference; belongs in `skills/34-kailash-ml/`                              |
| `pact-enforcement-modes.md`    | Generic PACT reference; belongs in `skills/29-pact/`; paths frontmatter confirmed wrong scope |

---

## For Discussion

1. **Is the probe skill the right level of abstraction?** The probe files encode passing/failing booleans — the skill describes those. But the probe files themselves are the ground truth. Should the skill reference the probe files by path rather than summarizing?

2. **Should execution-ibkr.md split into two?** Execution cost decomposition (spec 13) and IBKR integration (spec 14) are separate governing specs. Keeping them in one file because they're always read together seems right — but if a future session only touches IBKR adapter code, is it confusing to load the full execution cost model?

3. **The evaluation-probes skill is 257 lines** — near the 300-line split threshold from Rule 8 of specs-authority.md. Should it be split by domain (safety probes vs. model probes vs. track-record probes)?

4. **Project skill quality gates**: The cc-audit found the original execution-ibkr.md had no `paths:` frontmatter but embedded MUST/NOT rules without DO/DO NOT examples. The rule is clear: skills carry patterns, rules carry obligations. Should `skills/project/` have an explicit "no embedded MUST/NOT without DO/DO NOT" lint?
