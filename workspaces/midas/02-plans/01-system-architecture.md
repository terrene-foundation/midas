# Plan: System Architecture

---

## Overview

Midas is structured as five layers that compose vertically. Each layer is independently testable and deployable.

```
┌─────────────────────────────────────────────┐
│              FRONTEND LAYER                  │
│   React/Next.js (web) + Flutter (mobile)    │
├─────────────────────────────────────────────┤
│              API LAYER (Nexus)               │
│   REST + WebSocket + MCP                    │
├─────────────────────────────────────────────┤
│           AI AGENT LAYER (Kaizen)           │
│   Analyst · Debate · Monitor agents         │
├─────────────────────────────────────────────┤
│           STRATEGY ENGINE                    │
│   Signals · Optimizer · Risk · Backtest     │
├─────────────────────────────────────────────┤
│              DATA LAYER (DataFlow)          │
│   Market data fabric · Portfolio store ·    │
│   Decision log · PostgreSQL + Redis         │
└─────────────────────────────────────────────┘
```

---

## Layer 1: Data Layer

### Responsibilities

- Ingest and cache market data from EODHD / Yahoo Finance
- Store portfolio state, position history, transaction log
- Store decision audit trail (every AI decision with full reasoning)
- Store debate transcripts
- Regime state cache (Redis)
- Market data polling scheduler

### DataFlow Models

```
MarketPrice      — ticker, date, OHLCV, adjusted_close, source
Instrument       — ticker, name, asset_class, liquidity_tier, expense_ratio
Portfolio        — user_id, snapshot_date, total_value, cash_balance
Position         — portfolio_id, ticker, shares, cost_basis, current_value, weight
Decision         — id, timestamp, type, ticker, action, rationale_json, status, confidence
DecisionOutcome  — decision_id, actual_outcome, counterfactual_outcome
DebateThread     — id, decision_id, started_at, resolved_at, resolution
DebateMessage    — thread_id, role, content, data_refs_json, timestamp
RegimeState      — timestamp, regime, vix, indicators_json
RebalanceEvent   — id, timestamp, before_snapshot, after_snapshot, trades_json, total_cost
BacktestResult   — strategy_id, period, metrics_json, regime_metrics_json
Signal           — timestamp, signal_type, ticker, value, confidence
```

### Data Fabric Pattern

```
Source (EODHD/Yahoo) → Ingestion Workflow → PostgreSQL (historical)
                                          → Redis (latest, TTL-based)

Strategy Engine → reads from PostgreSQL/Redis (never from source)
Frontend → reads from Redis (hot) or PostgreSQL (cold) via API
```

**Polling schedule**:

- Screen active: 1-minute intervals (prices, regime indicators)
- Screen inactive: 15-minute intervals (regime monitoring only)
- Daily batch: Full EOD data pull at market close + 30min
- Weekly batch: Fundamental data refresh (expense ratios, yields)

### Caching Strategy

| Data Type          | Store      | TTL                             | Invalidation                |
| ------------------ | ---------- | ------------------------------- | --------------------------- |
| Latest prices      | Redis      | 60s (active) / 15min (inactive) | Next poll                   |
| Regime state       | Redis      | 60s                             | On change detection         |
| Historical OHLCV   | PostgreSQL | Permanent                       | Daily EOD update            |
| Portfolio snapshot | PostgreSQL | Permanent                       | On trade execution          |
| Backtest results   | PostgreSQL | Until strategy params change    | Invalidate on config change |

---

## Layer 2: Strategy Engine

### Responsibilities

- Signal generation (6 signal families)
- Portfolio optimization (BL + HRP + Risk Parity ensemble)
- Risk management (CVaR, drawdown, position limits)
- Backtesting framework
- Transaction cost modeling
- Rebalancing decision engine

### Module Structure

```
src/midas/strategy/
├── signals/
│   ├── momentum.py          # Time-series + cross-sectional
│   ├── carry.py             # Yield differentials
│   ├── macro.py             # Regime indicators (yield curve, PMI, spreads)
│   └── volatility.py        # Vol regime, inverse-vol scaling
├── optimizer/
│   ├── black_litterman.py   # Signal → views → posterior returns → weights
│   ├── hrp.py               # Hierarchical Risk Parity
│   ├── risk_parity.py       # Equal risk contribution
│   └── ensemble.py          # Constrained average of methods
├── risk/
│   ├── cvar.py              # Conditional Value-at-Risk
│   ├── drawdown.py          # Drawdown monitoring + de-risking
│   ├── limits.py            # Position size, concentration, volatility target
│   └── regime.py            # Regime detection (HMM + heuristic)
├── backtest/
│   ├── engine.py            # Walk-forward backtesting core
│   ├── costs.py             # Transaction cost model (spread, slippage, gap, tax)
│   ├── metrics.py           # Sharpe, Sortino, drawdown, deflated Sharpe
│   └── regime_tagger.py     # Tag historical periods with regimes
├── execution/
│   ├── rebalancer.py        # Threshold-based rebalancing logic
│   ├── order_builder.py     # Convert target weights → trade orders
│   └── cost_checker.py      # Pre-trade cost estimate
└── universe.py              # Instrument universe management
```

### Signal → Decision Pipeline

```
1. Daily (or on-demand): Generate signals for each instrument
2. Combine signals via Black-Litterman (views + confidence → posterior)
3. Run ensemble optimizer (BL + HRP + Risk Parity → constrained average)
4. Apply risk constraints (CVaR, position limits, drawdown thresholds)
5. Compare target weights vs current weights
6. If drift > threshold OR regime change → generate rebalancing proposal
7. Estimate transaction costs for proposed trades
8. If net alpha > costs → create Decision record
9. Route Decision: autonomous execute OR human approval (based on config)
```

---

## Layer 3: AI Agent Layer (Kaizen)

### Agent Roles

**Analyst Agent**

- Inputs: Strategy engine outputs, regime state, market data
- Outputs: Structured decision briefs, regime narratives, market context summaries
- Trigger: On new Decision record or regime change
- Key constraint: Every statement must reference specific data points

**Debate Agent**

- Inputs: User messages, portfolio state, decision history, backtest access, market data
- Outputs: Evidence-based responses with inline data references
- Trigger: User initiates debate
- Key constraints:
  - No sycophancy — must disagree when evidence supports disagreement
  - Every claim grounded in data (no fabricated numbers)
  - Track debate → decision resolution
  - Remember past debates and override patterns

**Monitor Agent**

- Inputs: Continuous market data stream, portfolio state, risk thresholds
- Outputs: Regime change alerts, drift warnings, approval requests
- Trigger: Continuous (polling-based)
- Key constraint: Minimize false alarms (urgency tiers must be calibrated)

### LLM Integration

- All agents use LLM for reasoning (per agent-reasoning rule: LLM IS the router, classifier, evaluator)
- No if-else routing or keyword matching in decision paths
- Tools are dumb data endpoints: `get_portfolio()`, `get_regime()`, `run_backtest()`, `get_price_history()`
- LLM decides which tools to call, how to interpret results, what to recommend
- Model selection from .env (per env-models rule)

---

## Layer 4: API Layer (Nexus)

### Channels

- **REST API**: CRUD operations, portfolio data, decision management
- **WebSocket**: Real-time price updates, regime changes, decision notifications
- **MCP**: AI agent tool interface (debate agent tools)

### Key Endpoints

```
# Portfolio
GET    /api/portfolio                    # Current portfolio state
GET    /api/portfolio/history            # Historical snapshots
GET    /api/portfolio/allocations        # Current vs target allocations

# Decisions
GET    /api/decisions                    # List decisions (filterable)
GET    /api/decisions/:id                # Decision detail with brief
POST   /api/decisions/:id/approve        # Approve a decision
POST   /api/decisions/:id/reject         # Reject a decision
POST   /api/decisions/:id/modify         # Modify a decision
GET    /api/decisions/:id/counterfactual # What-would-have-happened

# Debate
POST   /api/debate/threads               # Start new debate thread
POST   /api/debate/threads/:id/messages  # Send message in thread
GET    /api/debate/threads/:id           # Get thread with messages

# Backtest
GET    /api/backtest/current             # Current strategy scorecard
POST   /api/backtest/scenario            # Run what-if scenario
GET    /api/backtest/regimes             # Regime-specific breakdown

# Market
GET    /api/market/regime                # Current regime state
GET    /api/market/prices/:ticker        # Latest price
GET    /api/market/signals               # Current signal values

# Settings
GET    /api/settings                     # User settings
PUT    /api/settings                     # Update settings
PUT    /api/settings/risk-profile        # Update risk parameters

# WebSocket Events
ws://  regime_change                     # Regime status updates
ws://  price_update                      # Polling price updates
ws://  decision_new                      # New decision requiring attention
ws://  decision_executed                 # Decision was executed
ws://  debate_message                    # New message in debate thread
```

---

## Layer 5: Frontend Layer

### Web (React/Next.js)

- Server-side rendering for initial load performance
- WebSocket connection for real-time updates
- Left-rail navigation (6 screens)
- Debate panel slides in from right (overlay on any screen)
- Responsive down to tablet (not phone — use Flutter app for mobile)

### Mobile (Flutter)

- Bottom tab bar (5 tabs)
- Debate as bottom sheet (contextual from any screen)
- Rich push notifications with inline actions
- Home screen widgets (small, medium, large)
- Biometric gating for approvals
- Offline support (cached last-known state)

### Shared Design System

- Dark mode primary (deep neutral `#0F1117`)
- Gold/amber accent (`#D4A843`) — sparingly
- Muted gain/loss colors (teal `#34A77B`, coral `#E85D5D`)
- Tabular figures for all financial data
- Regime-adaptive layout (information density scales with market tension)

---

## Deployment Architecture (v1 — Personal Tool)

```
Single Server / Local Machine
├── PostgreSQL (data store)
├── Redis (cache)
├── Python backend (Nexus API + Strategy Engine + AI Agents)
├── Next.js frontend (web)
└── Flutter apps (iOS/Android, connecting to local or hosted backend)
```

For v1, everything runs on a single machine or VPS. Docker Compose for easy setup. No multi-tenant, no load balancing, no horizontal scaling.

---

## API Security (SPEC-02 PC-8)

### Authentication

- **JWT-based authentication** for all API endpoints. Token issued on login, refreshed on activity.
- Endpoints that approve trades or modify risk settings require valid, non-expired JWT.
- Mobile: biometric gating on top of JWT for trade approvals.

### Credential Storage

- IBKR OAuth tokens encrypted at rest using Fernet symmetric encryption.
- Encryption key loaded from `.env` (`MIDAS_ENCRYPTION_KEY`), never committed to code.
- Encrypted credential stored in PostgreSQL `credentials` table (see data layer plan).
- Token refresh handled by background worker. On failure, trading pauses gracefully.

### Session Management

- JWT expiry: 24 hours. Refresh token: 7 days.
- Inactivity lockout: 30 minutes (re-auth required).
- Single active session per user (v1 — single user).

---

## Background Worker Architecture

The autonomous behavior of Midas depends on scheduled background processes. Without these, nothing happens autonomously.

### Worker Implementation

- **APScheduler** for v1 (lightweight, single-process, sufficient for single-user).
- Runs as a persistent background thread within the Python backend process.
- Jobs registered at application startup. State persisted in PostgreSQL (APScheduler's job store).

### Scheduled Jobs

| Job                            | Schedule                     | Purpose                                             |
| ------------------------------ | ---------------------------- | --------------------------------------------------- |
| **EOD Data Ingestion**         | Daily, market close + 30min  | Fetch and validate EODHD data                       |
| **Signal Generation**          | Daily, after data ingestion  | Compute all 6 signal families                       |
| **Portfolio Optimization**     | Daily, after signals         | Run ensemble optimizer, generate target allocation  |
| **Risk Assessment**            | Daily, after optimization    | 7-layer risk checks, regime detection update        |
| **Rebalancing Check**          | Daily, after risk assessment | Check drift, propose rebalancing if needed          |
| **Monitor Polling (active)**   | Every 60s when UI active     | Price updates, regime indicator checks              |
| **Monitor Polling (passive)**  | Every 15min when UI inactive | Regime monitoring, drawdown checks                  |
| **Self-Tuning**                | Quarterly                    | Bayesian optimization of risk parameters            |
| **Universe Review**            | Monthly                      | Overlap analysis, gap detection, entry/exit checks  |
| **IBKR Health Check**          | Every 30s                    | Connection heartbeat, session validity              |
| **Counterfactual Computation** | Daily                        | Compute 1d/1w/1m counterfactuals for past decisions |
| **Credential Refresh**         | Before expiry                | IBKR OAuth token refresh                            |

### Health Monitoring

- Each job reports success/failure to a `job_health` table.
- If a critical job fails (data ingestion, risk assessment), trading pauses automatically.
- Dashboard shows job status in Settings screen.

### Kill Switch (SPEC-02 PC-8)

**Activation**: Available from Pulse screen (floating button) and Settings.
**Behavior**:

1. Immediately cancels all pending IBKR orders
2. Sets `kill_switch_active = TRUE` in settings
3. Pauses all background jobs that generate trades
4. Monitoring jobs continue (user can still see portfolio state)
5. Push notification: "Kill switch activated. All trading paused."
   **Recovery**: User explicitly deactivates in Settings. Requires biometric confirmation. System runs a health check before resuming.

---

## Implementation Priority (SPEC-01 FP-8: Debate is P0)

| Priority | Component                                            | Rationale                                                      |
| -------- | ---------------------------------------------------- | -------------------------------------------------------------- |
| P0       | Data layer + market data ingestion                   | Everything depends on data                                     |
| P0       | Strategy engine (signals + optimizer + dynamic risk) | Core value — institutional portfolio desk                      |
| P0       | AI debate agent                                      | THE product (SPEC-01 FP-8) — built alongside engine, not after |
| P0       | Backtesting framework (CPCV + adversarial)           | Validates strategy before live trading                         |
| P0       | Background worker + scheduler                        | Autonomous behavior depends on this                            |
| P0       | API security (JWT + credential encryption)           | Safety-critical for real trades                                |
| P1       | IBKR integration (read + write)                      | Brokerage connection                                           |
| P1       | Decision engine + approval workflow                  | Core interaction model                                         |
| P1       | Web frontend (Pulse + Decisions + Debate)            | Primary user interface — Debate is P0 feature                  |
| P1       | Paper trading mode                                   | Must validate before live (SPEC-01 FP-7)                       |
| P2       | Web frontend (Portfolio, Backtest, Signal)           | Reference screens                                              |
| P2       | Algorithmic universe construction pipeline           | Data-driven ETF selection (SPEC-02 PC-2)                       |
| P3       | Mobile app (Flutter)                                 | Mobile after web is proven                                     |
| P3       | Home screen widgets                                  | Polish feature                                                 |
