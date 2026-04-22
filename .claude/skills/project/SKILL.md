# Midas Project Skills

Skills for the Midas autonomous investment assistant — a latent-first, evidence-first co-decision system for Singapore-domiciled self-directed investors.

## Architecture & Adaptation

| Skill                                                        | Purpose                                                                                                                           |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| [midas-architecture.md](midas-architecture.md)               | Core spine, 14 first principles, value chain, performance measurement, open items, architecture rules                             |
| [model-pool-and-adaptation.md](model-pool-and-adaptation.md) | Three-loop adaptation (inner/outer/middle), champion/challenger infrastructure, promotion contract, no-free-lunch operationalized |
| [data-fabric-and-universe.md](data-fabric-and-universe.md)   | Universe selection, 29-table fabric catalog, freshness rules, feature store, data source catalog                                  |
| [superseded-approaches.md](superseded-approaches.md)         | Phase 01 techniques explicitly rejected (HMM, BL/HRP/RP as champions, factor-driven decisions) — do NOT re-propose                |

## Product Contract

| Skill                                                | Purpose                                                                                                              |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| [user-persona-contract.md](user-persona-contract.md) | Singapore investor persona, 6 non-delegable decisions, 4 failure modes, time budget contract, "what the user is not" |

## Safety, Quality & Evaluation

| Skill                                                      | Purpose                                                                                                                   |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| [midas-security-checklist.md](midas-security-checklist.md) | Security patterns from red team rounds 1-12 (tool allowlists, conditional auth, batch endpoints, frontend mock detection) |
| [debate-agent-contract.md](debate-agent-contract.md)       | Debate agent must mutate decisions (not narrate), non-sycophancy rules, tool suite, error handling                        |
| [evaluation-probes.md](evaluation-probes.md)               | Evaluation probe suite — calibration, router overfitting, shadow lane isolation, track record gates, safety probes        |
| [execution-ibkr.md](execution-ibkr.md)                     | IBKR execution adapter, order state machine, cost model, FX sweep, PLAF algorithms                                        |

## Key Principles (Quick Reference)

- **Latent-first**: All decisions flow through continuous probabilistic z_t, not observable factors
- **Pool-not-pick**: Every layer holds a pool with champion + challengers; no single model dominates
- **Evidence-first co-decision**: Midas assembles evidence, user weighs it, decision is shared
- **Earned autonomy**: Track record earns latitude via Brinson attribution; upgrades are user-approved
- **Attention is sacred**: Brief density scales with dollars-at-stake, not surface bandwidth
- **Singapore domicile**: No US tax, SGD base, MAS regulatory frame, IBKR-SG entity
