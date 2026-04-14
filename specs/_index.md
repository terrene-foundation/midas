# Midas Specs Index

This is the single source of domain truth for Midas. Phase commands read this index, select relevant files, and read only those files. Workspaces track process; specs track what the system IS and does.

## Governing Authority

These three files override everything else. Any plan, todo, or implementation that contradicts them is wrong by definition.

| File                     | Authority                                       |
| ------------------------ | ----------------------------------------------- |
| `00-first-principles.md` | Inviolable product axioms                       |
| `01-user-persona.md`     | Who Midas is for and what job it does for them  |
| `02-value-chain.md`      | The full operating model and v1 scope within it |

## Domain Manifest

| File                                      | Domain            | Description                                                                                                                                               |
| ----------------------------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `00-first-principles.md`                  | Axioms            | 14 inviolable principles governing every decision                                                                                                         |
| `01-user-persona.md`                      | User              | Singapore-domiciled self-directed investor, job-to-be-done, owned decisions, failure modes                                                                |
| `02-value-chain.md`                       | Operating Model   | Full front/middle/back office value chain, Kailash framework mapping, v1 scope boundary                                                                   |
| `03-universe-and-data.md`                 | Data Fabric       | ETF + S&P 1500 universe, data sources, fabric pattern, feature store, freshness rules                                                                     |
| `04-latent-first-architecture.md`         | Core Architecture | Representation-learning-first, continuous latent state z_t, econometrics as overlay                                                                       |
| `05-model-pool-and-meta-router.md`        | Model System      | Pools by function, three-loop adaptation, champion/challenger infrastructure, no-free-lunch operationalized                                               |
| `06-continuous-regime-rendering.md`       | Regime            | Continuous posterior state, no labels, UX projection onto attention-load axis                                                                             |
| `07-evidence-first-decision.md`           | Decision Model    | Co-decision protocol, Debate must be able to mutate weights, "what would change my mind" appendix                                                         |
| `08-autonomy-and-trust.md`                | Autonomy          | L0–L4 ladder, trust boundary, earned upgrades, kill switch, paper→live gate                                                                               |
| `09-surfaces-and-attention.md`            | UX                | Seven surfaces, regime-adaptive reshape, attention budget, progressive disclosure                                                                         |
| `10-moments-of-truth.md`                  | UX Safety         | Approval tap, Debate non-sycophancy, paper→live, kill switch — the rules that cannot break                                                                |
| `11-compliance-and-risk.md`               | Governance        | PACT rules engine, envelope enforcement, hard safety limits, pre-trade veto                                                                               |
| `12-performance-and-track-record.md`      | Measurement       | Brinson attribution + IR / α / M² / Treynor, calibration tracking, track-record scoring that earns autonomy                                               |
| `13-execution-cost-and-microstructure.md` | Cost & Execution  | Transaction cost decomposition (spread/impact/commission/tax/slippage/gap), execution algorithms, participation caps, PLAF for paper→live                 |
| `14-ibkr-integration.md`                  | Broker            | IBKR Web API v1.0 + TWS contract, rate limits, order state machine, rejection taxonomy, partial-fill-during-approval protocol, halts & auctions, FX sweep |

## How Phases Read This

- `/analyze`, `/todos`, `/implement`, `/redteam`, `/codify` MUST read this index at start and load only the relevant files.
- `/redteam` and `/codify` MAY read all specs.
- Any deviation from a spec during implementation MUST be reflected in the spec in the same action (MUST Rule 5 of `specs-authority.md`).

## Status

This is v1 of the spec set. The v0 analysis artifacts live at `workspaces/midas/01-analysis/02-specs/` and are superseded by these files. The reframe (DL-dominant, latent-first, continuous-state, evidence-first co-decision) resolved the prior econometrics-first framing; preserved principles are migrated, superseded principles are marked.

Redteam convergence required before the set is frozen. Current round: see `workspaces/midas/04-validate/` for findings.
