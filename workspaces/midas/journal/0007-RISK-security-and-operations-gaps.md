---
type: RISK
date: 2026-04-09
created_at: 2026-04-09T22:00:00+08:00
author: agent
project: midas
topic: Red team found security and operations gaps disproportionate to the system's ability to execute real trades
phase: analyze
tags: [security, operations, red-team, critical]
---

## Risk Identified

The analyst red team identified a pattern: Midas can execute real trades on a real brokerage account, but its security and operational specifications are weaker than a typical web application:

1. **No API authentication**: Endpoints that approve trades and modify risk settings have zero auth specification. On a VPS, anyone who discovers the address can approve trades.
2. **No job scheduler**: The strategy engine, data ingestion, and Monitor Agent all require background execution, but no scheduling infrastructure is specified (no cron, no Celery, no task queue).
3. **No credential storage**: IBKR OAuth tokens and API keys have no encrypted storage specification.
4. **No paper trading mode**: No safe path to test trade execution without real money.
5. **Stale cache during execution**: 60-second price cache means share calculations during fast-moving markets could be wrong by thousands of dollars.

## Likelihood and Impact

- **Likelihood**: CERTAIN — these are missing specifications, not edge cases
- **Impact**: CRITICAL — the system handles real money. An unauthenticated API, a dropped background job, or a stale price during a $133K trade are not theoretical risks — they are guaranteed failure modes if not addressed.

## Mitigation

All five gaps have resolution paths documented in `06-red-team-findings.md`. Key actions for /todos:

1. Add API authentication to system architecture (minimum: API key or JWT for v1)
2. Add background worker architecture (Kailash workflow scheduling or dedicated worker process)
3. Specify credential encryption (application-level encryption, key from .env)
4. Launch in paper trading mode by default; real trading requires explicit opt-in
5. Add fresh-price fetch bypass for trade execution path

## Follow-Up

- These items should be P0 in the /todos phase — they gate live trading safety
- The paper trading requirement specifically should be an implementation prerequisite: no real trades until the system has run in paper mode for a user-defined period
- Security review agent should be engaged during /implement gate

## For Discussion

- The analyst noted the system "has less security specification than a typical TODO app." Is this because the analysis phase correctly focused on product/strategy research and defers security to implementation? Or is it a genuine oversight that should have been caught earlier?
- Should the paper trading period be mandatory (e.g., 30 days minimum before real trading is allowed), or should the user be able to skip it? A mandatory period builds trust but frustrates sophisticated users who want to go live immediately.
- The background job architecture gap raises a broader question: should Midas use Kailash's workflow scheduling for background jobs, or a simpler approach (APScheduler, cron) for v1? The framework-first rule says check Kailash first, but the analyst noted "a simpler Python scheduler would suffice for single-user v1."
