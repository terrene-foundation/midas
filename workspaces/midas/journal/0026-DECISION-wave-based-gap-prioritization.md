---
type: DECISION
date: 2026-04-26
created_at: 2026-04-26T10:00:00
author: co-authored
session_id: session-4
session_turn: 1
project: midas
topic: Wave-based gap prioritization for remaining 7 architectural gaps
phase: todos
tags: [planning, prioritization, wave-strategy]
---

# Decision: Wave-Based Gap Prioritization

## Context

Red team rounds 8-12 identified 7 open architectural gaps (GAP-1 through GAP-7) ranging from CRITICAL to MEDIUM severity. Sessions 1-3 completed all M00-M21 milestones through codification (commit `14c6a28`). These 7 gaps are what remains before v1 is complete.

## Decision

Organize the 7 gaps into 4 waves ordered by value-chain dependency (what unblocks the next):

- **Wave 1 (1 session):** Onboarding frontend (GAP-1, CRITICAL) + adapter test edge cases + backtest engine + weight fix
- **Wave 2 (2 sessions):** Brief composer grounding (GAP-3) + debate multi-turn (GAP-4) + ModelRegistry fix (GAP-6)
- **Wave 3 (1-2 sessions):** IBKR order states + rejection taxonomy (GAP-2, CRITICAL)
- **Wave 4 (1 session):** Notification system (GAP-5)

## Rationale

1. **Onboarding is the user gate** — nothing else matters if users can't get in. Backend state machine exists; frontend just needs building.
2. **Decision quality is the value proposition** — after users can enter, they need real briefs and real multi-turn debate (FP-8, FP-13).
3. **Execution trust before paper trading** — IBKR states must be correct before any real order flow. Trust comes from verifiable track record (FP-14).
4. **Notifications last** — they amplify real content. Building them before the content exists means testing against stubs.

## Alternatives Considered

- **Severity-first ordering** (CRITICAL gaps first): Would do IBKR before debate, but IBKR doesn't unblock user value the way debate does.
- **Parallel all-at-once**: Would exceed per-session capacity budget across all gaps simultaneously.
- **Frontend-first**: Only addresses GAP-1 and GAP-5, leaves decision engine incomplete.

## Consequences

- Total 5-6 sessions to close all 7 gaps
- Each wave has clear unblock criteria for the next
- Wave 1 can be parallelized across 3 agents (frontend, tests, backtest)

## For Discussion

1. Should Wave 2's GROUP F (ModelRegistry) move to Wave 1 since it's small and has no frontend dependency?
2. Does IBKR order states (Wave 3) need to land before paper trading can begin, or is the existing partial implementation sufficient?
3. Are there gaps not captured in rounds 8-12 that should be added to the waves?
