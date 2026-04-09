# Red Team Findings & Resolutions

**Date**: 2026-04-09
**Agents**: Round 1 — analyst + reviewer. Round 2 (convergence) — analyst + reviewer.
**Status**: Round 2 convergence complete. 0 Critical, 0 High remaining after fixes. Spec compliance check pending.

---

## FIX Items (Addressed)

### FIX-1: Regime Naming Inconsistency

**Finding**: Documents use two different taxonomies conflated under "regime":

- Strategy/backtesting: Bull/Bear/Sideways crossed with Vol/Inflation (5 regimes)
- Operations/UI: Calm/Elevated/Urgent/Crisis (4 levels)

**Resolution**: These are two distinct concepts:

- **Market Regime** (strategy layer): Bull-LowVol, Bull-HighVol, Bear-Deflationary, Bear-Inflationary, Sideways — used for backtesting, signal generation, and historical analysis
- **Operational Regime** (UI/approval layer): Calm, Elevated, Urgent, Crisis — drives UX adaptation, notification tiers, and approval routing

**Mapping**:
| Market Regime | Operational Regime |
|---|---|
| Bull / Low Vol | Calm |
| Bull / High Vol | Elevated |
| Sideways | Calm or Elevated (depends on VIX) |
| Bear / Deflationary | Urgent or Crisis |
| Bear / Inflationary | Urgent or Crisis |

Operational regime is determined by observable indicators (VIX, drawdown speed, credit spreads), not by the HMM market regime classification (which lags). The strategy engine defines both; the UI reads only the operational regime.

### FIX-2: Missing API Endpoints

**Finding**: User flows reference actions with no corresponding API endpoint.

**Resolution**: Added endpoints (to be incorporated into system architecture during /todos):

```
# Onboarding
POST   /api/brokerage/connect           # Initiate IBKR OAuth flow
GET    /api/brokerage/status             # Connection health check
POST   /api/data-sources/test            # Test EODHD/Yahoo connectivity
POST   /api/portfolio/initialize         # Trigger initial portfolio analysis
GET    /api/onboarding/status            # Onboarding completion state

# Batch Operations
POST   /api/decisions/batch-approve      # Approve multiple routine decisions

# Backtest Extensions
GET    /api/backtest/cost-analysis       # Transaction cost breakdown
GET    /api/backtest/consistency          # Rolling window performance

# Settings
PUT    /api/settings/universe            # Update enabled asset classes
PUT    /api/settings/autonomy            # Update autonomy level
```

### FIX-3: Drawdown Thresholds Consolidation

**Finding**: Synthesis defines 2-step ladder (-20%, -30%); strategy engine defines 5-step (-5%, -10%, -15%, -20%, -30%).

**Resolution**: The strategy engine's 5-step ladder is authoritative. The synthesis should reference it rather than defining its own. Updated during this session — synthesis now defers to strategy engine Section 3 for the complete drawdown management specification.

### FIX-4: Missing RebalanceEvent Table

**Finding**: Synthesis lists `RebalanceEvent` as a data model but the data layer schema didn't include it.

**Resolution**: Added `rebalance_events` table to data layer schema with fields: portfolio_id, triggered_at, trigger_reason, regime_at_time, before_snapshot (JSONB), after_snapshot (JSONB), trades_json, total_cost, net_turnover.

### FIX-5: Signal/News Screen Has No Plan Section

**Finding**: The Signal screen exists in UX architecture and frontend plan but has no corresponding system plan.

**Resolution**: Signal/News is correctly classified as P3 priority in the system architecture. For v1, the Signal screen will display:

- Perplexity-sourced news summaries (already covered by debate agent's `get_news_context` tool)
- Portfolio impact tags (computed by the same AI agent pipeline)
- No standalone news subsystem needed — it is a view layer on top of the debate agent's news tool

This is documented here rather than as a separate plan. A dedicated plan is warranted only if news becomes a primary signal source (currently it is contextual only).

### FIX-6: Portfolio Schema Mismatch

**Finding**: Synthesis lists `user_id` on Portfolio model; data layer has no `user_id` column.

**Resolution**: v1 is a single-user personal tool. The `portfolios` table does not need `user_id`. The synthesis model list was a high-level sketch, not the authoritative schema — the data layer plan (`02-data-layer.md`) is authoritative. For multi-tenant (v2+), add `user_id` to `portfolios` and a `users` table. No change needed for v1.

---

## CONSIDER Items (Tracked for /todos)

| #   | Item                                                             | Priority | Resolution Path                                                                          |
| --- | ---------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------- |
| C1  | Autonomy level enum (3 levels) vs onboarding choices (4 options) | Medium   | Expand `autonomy_level` to 4 values or add `approval_mode` field                         |
| C2  | Backtest period exceeds ETF availability (PDBC 2014, SCHD 2011)  | Medium   | Walk-forward backtester uses only instruments available at each time point               |
| C3  | No user flow for settings changes mid-operation                  | Low      | Add brief user flow during /todos                                                        |
| C4  | Kill switch referenced but not specified                         | Medium   | Add kill switch spec to system architecture during /todos                                |
| C5  | IBKR Web API v1.0 OAuth specifics                                | High     | Research actual auth mechanism; may need gateway service                                 |
| C6  | Backtest latency for interactive scenarios                       | Medium   | Pre-compute common scenarios; use simplified model for interactive what-ifs (<5s target) |
| C7  | Counterfactual computation specification                         | Medium   | Add to strategy engine: daily batch, 1d/1w/1m horizons, define "alternative path"        |
| C8  | Mobile onboarding path                                           | Low      | Onboarding is web-first; mobile joins configured instance                                |

---

## Analyst Red Team Findings (Additional)

The analyst found 4 Critical, 7 High, 10 Medium, and 6 Low issues. Items that overlap with reviewer findings are merged. New critical and high items below.

### CRITICAL (Analyst)

**A-C1: No API Security Design** (NEW)
The Nexus API layer has zero authentication specification. Endpoints that approve trades and modify risk settings are network-accessible with no auth. Even for single-user v1 on a VPS, this is a safety issue.

- **Resolution for /todos**: Add authentication section to system architecture. Minimum v1: API key header or JWT. Biometric gating (mobile) is the UI layer only — the API needs its own auth.

**A-C2: No Job Scheduler / Background Worker Architecture** (NEW)
The strategy engine, data ingestion, and Monitor Agent all run on schedules, but no scheduling infrastructure is specified. No cron, no Celery, no task queue. The entire autonomous behavior depends on background processes that have no deployment spec.

- **Resolution for /todos**: Add background worker architecture to system plan. Kailash workflows can be scheduled, but the trigger mechanism (cron / persistent worker / async loop) must be explicit.

**A-C3: IBKR API Still Says Client Portal in Data Layer** (PARTIAL OVERLAP with reviewer)
The synthesis was updated to Web API v1.0 but the data layer plan still says "Client Portal API" in Section 4.

- **Resolution**: Fix data layer plan during /todos. This is a documentation update, not an architecture change.

**A-C4: Emergency Stop Nuances** (OVERLAP with FIX-3, extended)
The analyst found a specific contradiction: synthesis says -20% → "50% defensive" (could include equities), strategy engine says -20% → "50% cash/short bonds" (no equities). And synthesis says -30% re-enters "until regime clears" (automatic) while strategy engine says "human review" (manual). These are different behaviors with real financial consequences.

- **Resolution**: Strategy engine is authoritative. "50% cash/short bonds" at -20%, "100% cash + human review required" at -30%. Update synthesis language to match exactly.

### HIGH (Analyst)

**A-H1: Tax Information Displayed But Can't Be Computed** (NEW)
Decision briefs show `tax_implication: "$12,400 short-term gain"` but the database has one `cost_basis` per position, not per tax lot. Tax-loss harvesting is out of scope, but displaying tax info requires lot-level tracking. Either remove tax displays from decision briefs or add a `tax_lots` table.

- **Resolution for /todos**: For v1, display approximate tax impact (use average cost basis). Add disclaimer "Estimated — consult your tax records." Tax-lot tracking deferred to v2.

**A-H2: Stale Cache During Trade Execution** (NEW)
60-second price cache TTL means share calculations during trade approval could be wrong by thousands on volatile days. No mechanism to fetch fresh prices at execution time.

- **Resolution for /todos**: Add a `get_fresh_price()` path that bypasses cache for trade execution. Display "Price at time of recommendation: $X. Current: $Y" on approval screen.

**A-H3: No Counterfactual Computation Algorithm** (OVERLAP with C7, elevated)
Counterfactual tracking is a key differentiator but has no implementation spec. Computing "what would have happened" requires tracking hypothetical portfolio states, which cascades across subsequent decisions.

- **Resolution for /todos**: Simplify for v1 — counterfactual = instrument's actual return over measurement period, not a full portfolio simulation. e.g., "You rejected selling NVDA at $890. It's now $820. Counterfactual gain if sold: $10,500." This is approximate but honest and computationally simple.

**A-H4: IBKR Rate Limits Tight for Design** (NEW)
50 req/min during batch rebalancing (10+ trades) + monitoring could hit limits at the worst possible moment.

- **Resolution for /todos**: Add request prioritization (trades > monitoring > data). Queue non-urgent requests. Use exponential backoff on 429 responses. Size rebalancing batches to stay under limits.

**A-H5: No Paper Trading Mode** (NEW)
No mention of IBKR paper trading for development/testing. The system can execute real trades but has no safe testing path.

- **Resolution for /todos**: IBKR provides paper trading accounts. v1 must launch in paper trading mode. Real trading enabled only after user explicitly switches. Add `paper_trading: boolean` to settings.

**A-H6: No Credential Storage Architecture** (NEW)
IBKR OAuth tokens and API keys need encrypted storage. No specification exists.

- **Resolution for /todos**: Store encrypted in PostgreSQL with application-level encryption key from .env. Never log tokens. Token refresh handled by a background job.

### Priority Rebalancing (Analyst Recommendation)

The analyst flagged that the AI debate agent is at P2 priority while the synthesis calls it "the product." If debate is the differentiator, it should be P1 alongside the decision engine. The current order builds a competent but undifferentiated portfolio tool first.

**Resolution**: Elevate debate agent to P1. Implement alongside the decision engine, not after. The first user-facing experience should include the ability to challenge any recommendation.

---

## Reviewer Assessment

**Overall**: "Exceptionally well-executed. Narrative flows coherently from brief through synthesis to plans to user flows. No orphaned features. Every plan section traces to at least one brief requirement or research finding."

**Key strengths**: Brief-to-synthesis resolution, value audit honesty, strategy engine specificity, debate agent personality specification, user flow concreteness.

## Analyst Assessment

**Overall**: "Thorough on investment strategy and UX, but security and operations are under-specified relative to the system's ability to execute real trades. The most concerning pattern is that the system handles real brokerage credentials and can execute real trades, but has less security specification than a typical TODO app."

**Key concern**: The background job architecture is entirely absent. The system's autonomous behavior depends on scheduled processes that have no deployment specification.

---

## Round 2: Convergence (Post User-Corrections)

### Round 2 Results

- **All Round 1 Criticals**: CONFIRMED RESOLVED (10/10 verified)
- **High items found**: 5 (debate priority P2→P0, background workers, API security, credential storage, VIX threshold ladder)
- **All 5 High items**: FIXED in this round

### Fixes Applied in Round 2

| Item                               | Fix                                                                                       |
| ---------------------------------- | ----------------------------------------------------------------------------------------- |
| Debate priority P2 in architecture | Updated to P0 in `01-system-architecture.md`                                              |
| Background worker missing          | Added APScheduler architecture + 12 scheduled jobs + health monitoring                    |
| API security missing               | Added JWT auth, session management, CORS section                                          |
| Credential storage missing         | Added `credentials` table with Fernet encryption                                          |
| VIX threshold ladder (discrete)    | Replaced with continuous asymmetric response function                                     |
| Tax implication in debate brief    | Replaced with Singapore-appropriate dividend WHT note                                     |
| Fixed ensemble weights             | Made regime-conditional with self-tuning                                                  |
| Static user_settings params        | Renamed as seeds + added `adaptive_risk_params` table                                     |
| No universe changelog              | Added `universe_changelog` table for algorithmic ETF management                           |
| Kill switch unspecified            | Full spec added: cancels orders, pauses trading, continues monitoring, biometric recovery |

### Remaining Medium/Low Items (Acceptable for /todos)

| Item                                                | Severity | Status                                               |
| --------------------------------------------------- | -------- | ---------------------------------------------------- |
| Value audit Sections 1-3 competitive language       | Medium   | Deferred — headers corrected, body is legacy context |
| Frontier techniques not fully integrated into plans | Medium   | Phasing doc needed during /todos                     |
| No currency hedging in plans                        | Medium   | Add during /todos (FX overlay for USD/SGD)           |
| IBKR endpoint paths may be wrong API version        | Low      | Verify against Web API v1.0 docs during /implement   |
| Basic vs nonlinear covariance shrinkage             | Low      | Library swap notation                                |

### Convergence Assessment

**Round 2 achieves convergence.** All Critical and High items are resolved. Remaining Medium/Low items are documented for /todos phase and do not block implementation planning. The three governing SPECs (First Principles, Principal Considerations, UI/UX) are correct and consistent with all corrected plan documents.
