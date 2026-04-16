# Midas

Autonomous investment assistant — a latent-first, evidence-first co-decision system for Singapore-domiciled self-directed investors.

---

## Architecture

```
FABRIC → REPRESENTATION LEARNERS (pool) → STATE INFERENCE (pool)
  → POSTERIOR OVER z_t → DECISION HEADS (pool) + RENDERING LAYER
  → META-ROUTER → FRONTIER LLM (brief/debate)
```

All decisions flow through a continuous probabilistic latent state z_t inferred from data. Observable factors are explanation overlays, not decision inputs. No single model dominates — every layer holds a pool managed by a three-loop adaptation mechanism (inner calibration, middle routing, outer population-based promotion).

## Key Principles

| Principle                  | Summary                                                  |
| -------------------------- | -------------------------------------------------------- |
| Latent-first               | Decisions from continuous z_t, not observable factors    |
| Pool-not-pick              | Every layer: champion + challengers, meta-router selects |
| Evidence-first co-decision | Midas assembles evidence, user weighs it                 |
| Earned autonomy            | Track record earns latitude via Brinson attribution      |
| Attention is sacred        | Brief density scales with dollars-at-stake               |
| Singapore domicile         | No US tax, SGD base, MAS regulatory frame, IBKR-SG       |

## Implementation Status

21 milestones implemented, 637 tests passing, red team converged (0 CRITICAL, 0 HIGH).

Core modules: data fabric, representation learners, state inference, decision heads, meta-router, debate agent, autonomy ladder, execution engine, IBKR adapter, compliance agent, kill switch, brief composer, top-of-fold card, attribution engine, monitoring, surfaces.

## Project Knowledge

Domain knowledge is codified in project-level agents and skills:

| Artifact                                              | Purpose                                               |
| ----------------------------------------------------- | ----------------------------------------------------- |
| `.claude/agents/project/midas-architect.md`           | Architecture guardian — latent-first spine compliance |
| `.claude/skills/project/SKILL.md`                     | Skill index and quick reference                       |
| `.claude/skills/project/midas-architecture.md`        | Core spine, z_t properties, module surface map        |
| `.claude/skills/project/model-pool-and-adaptation.md` | Three-loop adaptation, promotion contract             |
| `.claude/skills/project/superseded-approaches.md`     | Phase 01 techniques NOT to re-propose                 |
| `.claude/skills/project/evaluation-probes.md`         | 10 evaluation probe acceptance contracts              |
| `.claude/skills/project/midas-security-checklist.md`  | 10 security patterns from red team                    |
| `.claude/skills/project/debate-agent-contract.md`     | Debate agent tool suite and non-sycophancy rules      |

## Specifications

Governing specs live in `specs/`. Key documents:

- `specs/04-latent-first-architecture.md` — Architecture spine
- `specs/05-model-pool-and-meta-router.md` — Three-loop adaptation
- `specs/07-evidence-first-decision.md` — Decision protocol
- `specs/08-autonomy-and-trust.md` — Autonomy ladder
- `specs/10-moments-of-truth.md` — Safety moments
- `specs/14-ibkr-integration.md` — IBKR integration

## Development

Built with the [Kailash SDK](https://github.com/terrene-foundation/kailash-py) ecosystem and COC (Cognitive Orchestration for Codegen) workflow.

```bash
# Setup
cp .env.example .env   # Edit with your API keys
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Test
pytest tests/ --ignore=tests/test_dataflow.py -x

# Run
claude
```

## License

Apache License, Version 2.0.
