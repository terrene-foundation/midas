# HIGH: MultiTurnDebateRouter Has Zero Tests

**Date:** 2026-04-27
**Round:** Round 13 red team
**Severity:** HIGH

## Finding

`MultiTurnDebateRouter` (routes_extended.py:1236) exposes 4 endpoints but has zero importing tests:

```
$ grep -rln "MultiTurnDebateRouter" tests/
# No results
```

The underlying `DebateAgent` has 19 passing tests, but the HTTP router wrapper has no tests.

## Impact

The router is the public API surface. Any refactor that breaks routing, request parsing, or response serialization will not be caught.

## Spec Coverage

- Spec 07 §3.6: Debate threads must be stateful with context injection

## Resolution Path

Add integration tests in `tests/integration/test_debate_router_wiring.py`:

1. `POST /debate/thread` — creates thread, returns thread_id
2. `GET /debate/thread/{thread_id}` — returns thread with turns
3. `POST /debate/thread/{thread_id}/turn` — adds turn with AI response
4. `GET /debate/thread/{thread_id}/context` — returns portfolio context

## Status

**RESOLVED** — `tests/integration/test_debate_router_wiring.py` created with 10 tests covering all 4 endpoints.
