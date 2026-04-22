# 0020-DECISION — Codify Sessions 1-3

**Date:** 2026-04-22
**Phase:** 05 (codify)
**Status:** Complete

## Decision

Codified all knowledge from sessions 1-3 (12 red team rounds, 0 CRITICAL/0 HIGH convergence) into institutional artifacts.

## What Was Codified

### New Skills (2)

1. **`user-persona-contract.md`** — From `specs/01-user-persona.md`. Covers: Singapore investor persona, 6 non-delegable decisions, 4 failure modes (Silent Betrayal, Being The Bottleneck, Fake Confidence, Regime Blindness), time budget contract, "what the user is not" list, 3 evaluation questions. ~90 lines.

2. **`data-fabric-and-universe.md`** — From `specs/03-universe-and-data.md`. Covers: 29-table fabric catalog, 8 ETF inclusion criteria, data source catalog (6 categories), freshness rules (active/inactive/never), feature store versioning, walk-forward discipline, source failure modes. ~140 lines.

### Updated Skills (2)

3. **`midas-architecture.md`** — Absorbed 3 spec domains:
   - First Principles (specs/00): 14 principles with violation tests + operational consequences
   - Value Chain (specs/02): 5-block operating model, Kailash framework mapping, v1 scope boundary
   - Performance (specs/12): Brinson-Fachler decomposition, track record composite score (7 components), counterfactual tracking
   - Added 7 open items (known gaps from rounds 8-12)
   - Added 6 architecture rules from rounds 8-12

4. **`midas-security-checklist.md`** — Added 10 new sections from rounds 8-12:
   - Tool allowlist for LLM database access (CRITICAL)
   - Conditional auth bypass (CRITICAL)
   - Batch endpoint auth (HIGH)
   - Rate limiter bounded state (MEDIUM)
   - Error response sanitization (MEDIUM)
   - Frontend mock data detection (CRITICAL)
   - Tool output honesty (CRITICAL)
   - Parse failure honesty (HIGH)
   - Silent exception swallowing in data pipelines (HIGH)
   - Compliance rule completeness (HIGH)
   - Frontend catch blocks, security middleware wiring, TODO markers

### Updated Agent (1)

5. **`midas-architect.md`** — Added 2 new skills to project table. Expanded review checklist from 16 to 23 items. New checks: tool allowlist, unconditional auth on mutations, batch endpoint auth, auto-trip wiring, backend authority for gates, no-op method detection, tool output honesty.

### Updated Index (1)

6. **`SKILL.md`** — Added new "Product Contract" section with user-persona-contract. Added data-fabric-and-universe to Architecture section. Updated descriptions.

## Why

Previous codification (round 7) covered security patterns but missed three unrepresented spec domains (user persona, data fabric, first principles/value chain/performance). Rounds 8-12 surfaced 10 new security patterns and 7 open architectural gaps that needed institutional capture.

## Spec Coverage Achievement

All 15 governing specs now have skill coverage:

- specs/00 (First Principles) → absorbed into midas-architecture.md
- specs/01 (User Persona) → dedicated user-persona-contract.md
- specs/02 (Value Chain) → absorbed into midas-architecture.md
- specs/03 (Universe & Data) → dedicated data-fabric-and-universe.md
- specs/04-11, 14 → previously covered
- specs/12 (Performance) → absorbed into midas-architecture.md
- specs/13 (Execution Cost) → covered by execution-ibkr.md

## Open Items for Future Sessions

7 architecturally-significant gaps documented in midas-architecture.md "Open Items" section: onboarding frontend (CRITICAL), IBKR order states (CRITICAL), brief composer sections (HIGH), debate multi-turn (HIGH), notification system (MEDIUM), ModelRegistry no-ops (HIGH), backtest return weights (MEDIUM).
