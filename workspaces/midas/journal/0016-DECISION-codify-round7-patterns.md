# 0016-DECISION: Codify Round 7 Security Patterns

**Date:** 2026-04-19
**Phase:** 05-codify
**Context:** After resolving all 18 deferred security and spec compliance findings through 7 implementation shards, codifying the institutional knowledge into project skills and agents.

## Decisions

### 1. Security Checklist Expanded to Cover Rounds 1-7

Updated `midas-security-checklist.md` from 10 patterns to 17 patterns. New additions:

- **IDOR protection** — JWT sub matching on mutation endpoints (from SA-C2)
- **Rate limiting** — custom per-IP sliding-window, no external deps (from SC-H2)
- **Re-auth tokens** — 5-min JWT with `type=reauth` for approve/decline (from SC-H1)
- **DB access safety** — `_get_db()` raises 503, never returns None (from SA-M1)
- **Password hashing** — PBKDF2-HMAC-SHA256 600k iterations as fallback (from SA-M4)
- **Session concurrency detection** — mass revocation on stolen token use (from SA-M5)
- **Kill switch hash persistence** — confirmation code hash in audit_log, not instance vars (from SA-H1)

**Why:** These patterns are recurring — the next session building API routes needs them pre-loaded.

### 2. Architecture Skill Updated for API Module

Updated `midas-architecture.md` api/ module description to include rate limiting, JWT auth, and IDOR-protected mutations.

**Why:** The api/ surface changed significantly; the skill must reflect current state.

### 3. Architect Agent Review Checklist Extended

Extended from 10 to 16 items, adding: IDOR, rate limiting, DB safety, re-auth, first-seven-days enforcement, kill switch persistence.

**Why:** The architect is the last gate before commit — new security checks must be in its checklist.

## No New Skills or Agents Created

All knowledge fit into existing artifacts. No new files needed — the patterns are incremental additions to established checklists.

## No Upstream Proposal

This is a downstream USE repo. Changes stay local in `.claude/skills/project/` and `.claude/agents/project/`.
