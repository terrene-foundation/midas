---
type: RISK
date: 2026-04-09
created_at: 2026-04-09T21:45:00+08:00
author: agent
project: midas
topic: IBKR API authentication is more complex than plans assume
phase: analyze
tags: [ibkr, authentication, integration-risk, technical]
---

## Risk Identified

The plans assume standard OAuth 2.0 for IBKR Web API v1.0. Market research confirms the Web API v1.0 does use OAuth 2.0, but the red team review flagged that:

1. IBKR's Client Portal API historically required a running gateway process and session tokens that expire
2. The Web API v1.0 is "still rolling out" — documentation may be incomplete
3. Mobile OAuth flows through webviews can be problematic
4. Rate limits are approximately 50 requests/minute — tight for an application that polls prices, checks regime, and manages orders

The ib_async library (maintained fork of ib_insync) uses the TWS API, which requires TWS or IB Gateway running locally via TCP socket — not REST.

## Likelihood and Impact

- **Likelihood**: HIGH — this is not speculative; IBKR's auth is known to be complex
- **Impact**: HIGH — if authentication fails or sessions drop, the entire execution layer is inoperable. Approval windows could expire. Trades could fail mid-rebalancing.

## Mitigation

1. **Dual API strategy**: Use Web API v1.0 (OAuth) as primary for account data and order submission. Use ib_async (TWS API) as fallback for real-time data and complex order types.
2. **Gateway service**: Run IB Gateway as a persistent background process with automatic restart on failure.
3. **Session health monitoring**: Heartbeat check every 30s. On session loss, queue pending actions and retry with exponential backoff.
4. **Graceful degradation**: If IBKR is unreachable, switch to read-only mode. All pending decisions show "Execution paused — broker connection lost."
5. **Paper trading first**: Validate the entire auth flow in IBKR's paper trading environment before any real money integration.

## Follow-Up

- During /implement P1, dedicate a focused spike to IBKR authentication. Build a minimal proof-of-concept that connects, authenticates, reads positions, and places a paper trade.
- Document the actual auth flow (may differ from API docs) and update the data layer plan accordingly.
- Evaluate whether the IBKR Web API v1.0 OAuth flow works in Flutter webview for mobile.

## For Discussion

- Should Midas support Alpaca as an alternative broker? Alpaca has a simpler REST API, commission-free trading, and paper trading — but is US-only and lacks IBKR's instrument coverage. Having a second broker would reduce IBKR dependency but double the integration work.
- If the IBKR Web API v1.0 turns out to be immature, is falling back to TWS API + local gateway acceptable for v1? It means the user must run IB Gateway on their machine, which is a meaningful UX burden.
