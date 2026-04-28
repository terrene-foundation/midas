# HIGH: Debate Agent Lacks Live Portfolio Context

**Date:** 2026-04-22
**Round:** Round 10 red team
**Severity:** HIGH

## Finding

DebateAgent runs a single-turn LLM call without injecting live portfolio positions, current weights, or regime state. The frontend has a polished multi-turn UI with InlineVisualization, ToolActionBar, and provenance pointers, but the backend does not ground the debate in actual portfolio data.

## Impact

A user asking "why am I holding 15% NVDA?" gets a generic LLM response, not a grounded analysis citing the portfolio's actual position. The Debate surface's core value proposition ("joint evidence review") is undermined.

## Spec Coverage

- Spec 07 §3.5: Debate agent must have live portfolio context
- Spec 07 §3.6: Debate threads must be stateful with context injection

## Resolution Path

Inject live portfolio positions, current weights, regime state, and relevant position history into the DebateAgent context before each debate turn.

## Status

OPEN
