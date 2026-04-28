# CRITICAL: Debate AI Never Invokes LLM — Stub Implementation

**Date:** 2026-04-27
**Round:** Round 13 red team
**Severity:** CRITICAL

## Finding

`useAddMessage` in the debate frontend stores messages to `audit_log` with `action="debate_message"` and returns immediately. The AI never responds. `useAddDebateTurn` (which would invoke AI reasoning via `POST /debate/thread/{id}/turn`) is not wired to the frontend — the debate page calls `addMessage` not `addTurn`.

The `MultiTurnDebateRouter` was built in this session (backend) with 4 endpoints:

- `POST /debate/thread` — create_thread ✅
- `GET /debate/thread/{thread_id}` — get_thread ✅
- `POST /debate/thread/{thread_id}/turn` — add_turn ✅ (calls DebateAgent with portfolio context)
- `GET /debate/thread/{thread_id}/context` — get_thread_context ✅

But the frontend debate page still uses the old `addMessage` pattern that stores to `audit_log` without AI invocation.

## Impact

The spec promises "AI that changes its mind when presented with evidence." The implementation is a message store. A user who asks "show me a real debate where the AI conceded" will see a message input field.

## Spec Coverage

- Spec 07 §3.5: Debate agent must have live portfolio context
- Spec 07 §3.6: Debate threads must be stateful with context injection
- User Flow 04: AI Debate — step 3 "AI responds with evidence" is NOT IMPLEMENTED

## Resolution Path

1. Replace `useAddMessage` call in debate UI with `useAddDebateTurn`
2. Ensure the `thread_id` is initialized on debate page load (either create thread on open, or pass thread_id from decision context)
3. Wire the debate open to create a `DebateThread` with the decision's brief context
4. Add tests for `MultiTurnDebateRouter` (currently 0 tests)

## Status

**RESOLVED** — Fix committed by `fix-debate-ai` agent.

- `DebateOverlay.tsx` now uses `useCreateMultiTurnThread` + `useAddDebateTurn`
- On open: `POST /debate/thread { decision_id }` creates thread with live portfolio context
- On send: `POST /debbate/thread/{threadId}/turn { user_message }` invokes DebateAgent
- `useDebate.ts` hooks map to all 4 MultiTurnDebateRouter endpoints
