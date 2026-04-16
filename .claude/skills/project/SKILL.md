# Midas Project Skills

Skills for the Midas autonomous investment assistant — a latent-first, evidence-first co-decision system for Singapore-domiciled self-directed investors.

## Architecture & Adaptation

| Skill                                                        | Purpose                                                                                                                           |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| [midas-architecture.md](midas-architecture.md)               | Core spine: latent state z_t, representation learners, decision heads, rendering layer, module surface map                        |
| [model-pool-and-adaptation.md](model-pool-and-adaptation.md) | Three-loop adaptation (inner/outer/middle), champion/challenger infrastructure, promotion contract, no-free-lunch operationalized |
| [superseded-approaches.md](superseded-approaches.md)         | Phase 01 techniques explicitly rejected (HMM, BL/HRP/RP as champions, factor-driven decisions) — do NOT re-propose                |

## Safety, Quality & Evaluation

| Skill                                                      | Purpose                                                                                                            |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| [midas-security-checklist.md](midas-security-checklist.md) | Ten security patterns from red team validation (kill switch, credential leaks, NaN guards, auth middleware)        |
| [debate-agent-contract.md](debate-agent-contract.md)       | Debate agent must mutate decisions (not narrate), non-sycophancy rules, tool suite, error handling                 |
| [evaluation-probes.md](evaluation-probes.md)               | Evaluation probe suite — calibration, router overfitting, shadow lane isolation, track record gates, safety probes |

## Key Principles (Quick Reference)

- **Latent-first**: All decisions flow through continuous probabilistic z_t, not observable factors
- **Pool-not-pick**: Every layer holds a pool with champion + challengers; no single model dominates
- **Evidence-first co-decision**: Midas assembles evidence, user weighs it, decision is shared
- **Earned autonomy**: Track record earns latitude via Brinson attribution; upgrades are user-approved
- **Attention is sacred**: Brief density scales with dollars-at-stake, not surface bandwidth
- **Singapore domicile**: No US tax, SGD base, MAS regulatory frame, IBKR-SG entity
