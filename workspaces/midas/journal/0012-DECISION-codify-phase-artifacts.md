# 0012-DECISION — Codify Phase Artifacts

**Date:** 2026-04-16
**Phase:** 05 Codify
**Status:** Complete

## Context

After red team convergence (0 CRITICAL, 0 HIGH, 637 tests), extracted institutional knowledge from 14 spec files and 13 journal entries into project-level agents and skills for a downstream USE repo.

## Decisions

### 1. Six Project Skills Created

| Skill                          | Source                             | Why                                                                                      |
| ------------------------------ | ---------------------------------- | ---------------------------------------------------------------------------------------- |
| `midas-architecture.md`        | specs/04, module surface map       | Core spine reference — every agent needs z_t properties and module boundaries            |
| `model-pool-and-adaptation.md` | specs/04, specs/05                 | Three-loop mechanism is the governing pattern; all ML changes must respect pool-not-pick |
| `superseded-approaches.md`     | Journal 0011-DECISION, FP-9/10/11  | Prevents re-proposing HMM, BL/HRP/RP champions, factor-driven decisions                  |
| `evaluation-probes.md`         | 10 probe test files                | Acceptance contracts for "safe to operate" — structural vs behavioral enforcement        |
| `midas-security-checklist.md`  | Red team findings (0011-DISCOVERY) | 10 security patterns from real vulnerabilities found during validation                   |
| `debate-agent-contract.md`     | specs/07, red team findings        | Debate must mutate decisions, not narrate; 10 MCP tools required                         |

### 2. One Project Agent Created

`midas-architect` — architecture guardian with 14 FP quick-check table, superseded approaches blocklist, 10-point review checklist. Validates all changes against latent-first spine integrity.

### 3. Five SDK-Generic Skills Deleted

Removed duplicates of Kailash SDK docs that had no Midas-specific content: `pool-safety.md`, `dataflow-provenance-audit.md`, `fabric-cache-consumers.md`, `ml-quick-reference.md`, `pact-enforcement-modes.md`. These belong in SDK skill directories, not project-level.

### 4. README Replaced

Generic COC template README replaced with Midas-specific README covering architecture, principles, status, project knowledge artifacts, specs, and development instructions.

### 5. cc-artifacts Compliance

Agent description trimmed from 169 to 107 chars (under 120 limit). All skills under 400 lines. SKILL.md progressive disclosure validated.

## Rationale

Knowledge was extracted from specs (domain truth), journals (decisions and trade-offs), and test files (acceptance contracts). The codification preserves not just what was built but why — particularly the superseded approaches and the security patterns from real red team findings.
