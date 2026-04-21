---
type: DECISION
date: 2026-04-16
created_at: 2026-04-16T12:00:00Z
author: agent
session_id: midas-zai
project: midas
topic: SDK-generic reference material removed from project skills
phase: codify
tags: [skills, project-structure, sdk-generic]
---

# SDK-Generic Reference Material Does Not Belong in Project Skills

## Decision

`skills/project/` must contain only knowledge **learned from building Midas** — architectural decisions, security patterns discovered through red team, Phase 01 rejections, and Midas-specific contracts.

SDK reference material (Kailash DataFlow, Kailash ML, PACT, connection pool safety) belongs in the relevant SDK skill directories (`skills/02-dataflow/`, `skills/34-kailash-ml/`, `skills/29-pact/`, `rules/`).

## Rationale

### Wrong scope creates noise

A project skill that is a duplicate of a SDK skill:

- Signals a category error (is this Midas-specific or generic?)
- Tempts future editors to modify the project copy instead of the canonical SDK skill
- Inflates the project skills surface area without adding project-specific knowledge
- Has `paths:` frontmatter that is meaningful in SDK scope but meaningless in project scope

### The heuristic: "would this file exist if Midas didn't exist?"

- `midas-architecture.md` — YES: the latent-first spine is Midas's core architectural choice
- `midas-security-checklist.md` — YES: the 10 patterns came from red-teaming Midas specifically
- `model-pool-and-adaptation.md` — YES: the three-loop mechanism is operationalized for Midas's domain
- `evaluation-probes.md` — YES: the probe suite encodes Midas's acceptance contracts
- `execution-ibkr.md` — YES: IBKR integration patterns are Midas-specific operational decisions
- `pool-safety.md` — NO: connection pool math is the same for any DataFlow application
- `dataflow-provenance-audit.md` — NO: Provenance[T] is a DataFlow SDK feature
- `ml-quick-reference.md` — NO: kailash-ml engines are SDK infrastructure

### Evidence of harm

The audit found `dataflow-provenance-audit.md` and `fabric-cache-consumers.md` in `project/` were **byte-for-byte identical** to their counterparts in `skills/02-dataflow/`. This is the clearest possible signal: the files were copy-pasted without understanding that SDK reference material has a canonical location.

## Alternatives Considered

### Keep SDK-generic files in project skills

Rejected because: project skills load into every Midas session context; SDK-generic content crowds out Midas-specific content without adding value to this project's agents.

### Symlink from project skills to SDK skills

Rejected because: symlinks across `.claude/` directories are fragile and hard to audit; better to have agents reference the SDK skill directories directly.

### Add a "SDK reference" table in SKILL.md pointing to canonical locations

Accepted as implicit solution: the SKILL.md index for project skills should not duplicate SDK content; agents that need SDK reference should be pointed to `skills/02-dataflow/`, `skills/34-kailash-ml/`, `skills/29-pact/` via the standard skill system.

## Consequences

- `skills/project/` now has 6 focused files (down from 11)
- All 6 files are Midas-specific
- No further SDK-generic content should be added to project skills without explicit justification

## For Discussion

1. **Should there be an automated check?** A linter rule that flags `paths:` frontmatter in `skills/project/` files pointing to `packages/kailash-*` would catch this automatically on commit.

2. **What about skills that ARE Midas-specific but reference SDK patterns?** For example, a Midas-specific DataFlow usage pattern that isn't in the generic DataFlow skill — this is fine if it's Midas-specific behavior, not generic SDK reference. The heuristic remains: would this exist without Midas?
