# Plan: Data Layer

---

## Overview

The data layer is the foundation. All other layers (strategy engine, AI agents, frontend) read from it — never directly from external sources. This is the "data fabric" pattern from the brief.

---

## 1. Market Data Ingestion

### Sources

| Source                     | Data                                        | Frequency                  | Fallback           |
| -------------------------- | ------------------------------------------- | -------------------------- | ------------------ |
| **EODHD** (primary)        | EOD prices, fundamentals, dividends, splits | Daily batch + on-demand    | Yahoo Finance      |
| **Yahoo Finance** (backup) | EOD prices, basic fundamentals              | On EODHD failure           | None (last resort) |
| **Perplexity** (optional)  | News summaries, market sentiment            | On-demand (debate, regime) | Degrade gracefully |
| **IBKR**                   | Account positions, balances, order status   | Real-time via API          | Cache last known   |

### Ingestion Workflows (Kailash Core SDK)

**Daily EOD Workflow** (runs at market close + 30 min):

1. Fetch EOD data for all instruments in universe from EODHD
2. Validate: check for anomalies (>20% daily move, zero volume, missing data)
3. Cross-validate suspicious data points against Yahoo Finance
4. Store validated data in PostgreSQL
5. Update Redis cache with latest prices
6. Flag any data quality issues for review

**Instrument Universe Workflow** (runs weekly):

1. Refresh instrument metadata (expense ratios, yields, sector classification)
2. Check for corporate actions (splits, mergers, ticker changes)
3. Update liquidity tier classifications based on recent volume
4. Validate ETF continuity (has any ETF been delisted?)

**Real-Time Polling Workflow** (runs on schedule):

1. When screen active: poll EODHD/Yahoo at 1-min intervals for watched tickers
2. Update Redis cache with TTL = 60s
3. Check regime indicators (VIX, credit spreads, yield curve)
4. If regime change detected → trigger Monitor Agent

### Data Quality Validation

Every data point is validated before storage:

```python
# Validation rules
- Price must be > 0
- Volume must be >= 0
- Daily return must be < 25% (flag for manual review if exceeded)
- Adjusted close must account for splits/dividends
- No future dates
- No duplicate entries (ticker + date unique)
- Cross-source validation for suspicious data points
```

**On validation failure**: Log warning, attempt fallback source, flag for review. Never store unvalidated data. Never silently skip.

---

## 2. Database Schema (PostgreSQL via DataFlow)

### Core Tables

**instruments**

```
id              SERIAL PRIMARY KEY
ticker          VARCHAR(20) UNIQUE NOT NULL
name            VARCHAR(200)
asset_class     VARCHAR(50) NOT NULL  -- us_equity, intl_equity, em_equity, precious_metal, govt_bond, corp_bond, reit, commodity, dividend
liquidity_tier  INTEGER NOT NULL DEFAULT 2  -- 1=deep, 2=good, 3=moderate, 4=thin
expense_ratio   DECIMAL(6,4)
yield_annual    DECIMAL(6,4)
is_active       BOOLEAN DEFAULT TRUE
metadata_json   JSONB
updated_at      TIMESTAMP DEFAULT NOW()
```

**market_prices**

```
id              SERIAL PRIMARY KEY
instrument_id   INTEGER REFERENCES instruments(id)
date            DATE NOT NULL
open            DECIMAL(12,4)
high            DECIMAL(12,4)
low             DECIMAL(12,4)
close           DECIMAL(12,4)
adjusted_close  DECIMAL(12,4)
volume          BIGINT
source          VARCHAR(20) NOT NULL  -- eodhd, yahoo
validated       BOOLEAN DEFAULT FALSE
created_at      TIMESTAMP DEFAULT NOW()

UNIQUE(instrument_id, date, source)
INDEX ON (instrument_id, date DESC)
```

**portfolios**

```
id              SERIAL PRIMARY KEY
name            VARCHAR(100)
ibkr_account_id VARCHAR(50)
created_at      TIMESTAMP DEFAULT NOW()
```

**portfolio_snapshots**

```
id              SERIAL PRIMARY KEY
portfolio_id    INTEGER REFERENCES portfolios(id)
snapshot_date   TIMESTAMP NOT NULL
total_value     DECIMAL(14,2)
cash_balance    DECIMAL(14,2)
metadata_json   JSONB  -- risk metrics at snapshot time
created_at      TIMESTAMP DEFAULT NOW()

INDEX ON (portfolio_id, snapshot_date DESC)
```

**positions**

```
id              SERIAL PRIMARY KEY
portfolio_id    INTEGER REFERENCES portfolios(id)
instrument_id   INTEGER REFERENCES instruments(id)
shares          DECIMAL(12,4)
cost_basis      DECIMAL(12,4)
current_price   DECIMAL(12,4)
current_value   DECIMAL(14,2)
weight          DECIMAL(6,4)  -- as fraction of portfolio
target_weight   DECIMAL(6,4)
updated_at      TIMESTAMP DEFAULT NOW()

INDEX ON (portfolio_id, instrument_id)
```

**decisions**

```
id              SERIAL PRIMARY KEY
portfolio_id    INTEGER REFERENCES portfolios(id)
instrument_id   INTEGER REFERENCES instruments(id)
decision_type   VARCHAR(50) NOT NULL  -- rebalance, regime_response, signal_triggered, risk_limit
action          VARCHAR(20) NOT NULL  -- buy, sell, hold
proposed_change DECIMAL(6,4)  -- weight change as fraction
urgency         VARCHAR(20) NOT NULL  -- routine, elevated, urgent
confidence      DECIMAL(4,2)  -- 0.00 to 1.00
rationale_json  JSONB NOT NULL  -- structured brief: thesis, if_approved, if_rejected, precedents
status          VARCHAR(20) NOT NULL DEFAULT 'pending'  -- pending, approved, rejected, modified, expired, executed
decision_window INTERVAL  -- how long user has to respond
expires_at      TIMESTAMP
created_at      TIMESTAMP DEFAULT NOW()
resolved_at     TIMESTAMP
resolved_by     VARCHAR(20)  -- user, default_action, system

INDEX ON (portfolio_id, status)
INDEX ON (created_at DESC)
```

**decision_outcomes**

```
id              SERIAL PRIMARY KEY
decision_id     INTEGER REFERENCES decisions(id) UNIQUE
actual_return   DECIMAL(8,4)  -- what actually happened
counterfactual  DECIMAL(8,4)  -- what would have happened with opposite choice
measured_at     TIMESTAMP  -- when outcome was measured
measurement_period VARCHAR(20)  -- 1d, 1w, 1m
```

**trades**

```
id              SERIAL PRIMARY KEY
decision_id     INTEGER REFERENCES decisions(id)
instrument_id   INTEGER REFERENCES instruments(id)
side            VARCHAR(4) NOT NULL  -- buy, sell
shares          DECIMAL(12,4)
target_price    DECIMAL(12,4)
filled_price    DECIMAL(12,4)
slippage        DECIMAL(12,4)
commission      DECIMAL(8,2)
total_cost      DECIMAL(8,2)  -- commission + spread + impact
ibkr_order_id   VARCHAR(50)
status          VARCHAR(20) NOT NULL  -- pending, submitted, filled, cancelled, failed
submitted_at    TIMESTAMP
filled_at       TIMESTAMP
```

**debate_threads**

```
id              SERIAL PRIMARY KEY
portfolio_id    INTEGER REFERENCES portfolios(id)
decision_id     INTEGER REFERENCES decisions(id)  -- nullable (not all debates are about a decision)
context_type    VARCHAR(50)  -- decision, position, news, strategy, general
context_ref     VARCHAR(200)  -- reference to what started the debate
resolution      VARCHAR(200)  -- how the debate was resolved
started_at      TIMESTAMP DEFAULT NOW()
resolved_at     TIMESTAMP
```

**debate_messages**

```
id              SERIAL PRIMARY KEY
thread_id       INTEGER REFERENCES debate_threads(id)
role            VARCHAR(10) NOT NULL  -- user, assistant
content         TEXT NOT NULL
data_refs_json  JSONB  -- references to data points cited
created_at      TIMESTAMP DEFAULT NOW()
```

**regime_history**

```
id              SERIAL PRIMARY KEY
detected_at     TIMESTAMP DEFAULT NOW()
regime          VARCHAR(30) NOT NULL  -- calm, elevated, urgent, crisis
vix             DECIMAL(6,2)
credit_spread   DECIMAL(6,2)
yield_curve     DECIMAL(6,4)
indicators_json JSONB  -- all indicators at detection time
previous_regime VARCHAR(30)
```

**signals**

```
id              SERIAL PRIMARY KEY
generated_at    TIMESTAMP DEFAULT NOW()
signal_type     VARCHAR(50) NOT NULL  -- ts_momentum, xs_momentum, carry, macro, vol_regime
instrument_id   INTEGER REFERENCES instruments(id)  -- nullable for portfolio-level signals
value           DECIMAL(8,4)
confidence      DECIMAL(4,2)
metadata_json   JSONB
```

**rebalance_events**

```
id              SERIAL PRIMARY KEY
portfolio_id    INTEGER REFERENCES portfolios(id)
triggered_at    TIMESTAMP DEFAULT NOW()
trigger_reason  VARCHAR(50) NOT NULL  -- drift, regime_change, drawdown, manual
regime_at_time  VARCHAR(30)
before_snapshot JSONB NOT NULL  -- positions + weights before rebalancing
after_snapshot  JSONB NOT NULL  -- positions + weights after rebalancing
trades_json     JSONB NOT NULL  -- list of trade summaries
total_cost      DECIMAL(10,2)  -- total transaction costs
net_turnover    DECIMAL(6,4)   -- portfolio turnover as fraction

INDEX ON (portfolio_id, triggered_at DESC)
```

**backtest_results**

```
id              SERIAL PRIMARY KEY
strategy_hash   VARCHAR(64) NOT NULL  -- hash of strategy params for cache invalidation
period_start    DATE
period_end      DATE
metrics_json    JSONB NOT NULL  -- total_return, annualized, sharpe, sortino, max_dd, etc.
regime_metrics  JSONB  -- per-regime breakdown
cost_metrics    JSONB  -- transaction cost breakdown
created_at      TIMESTAMP DEFAULT NOW()

INDEX ON (strategy_hash)
```

**user_settings** (SEED values — system overrides via self-tuning, per SPEC-02 PC-1)

```
id              SERIAL PRIMARY KEY
portfolio_id    INTEGER REFERENCES portfolios(id)
-- Risk seeds (initial values; adaptive system overrides these)
max_drawdown_seed    DECIMAL(4,2) DEFAULT 0.20  -- seed for sigmoid midpoint
volatility_target_seed DECIMAL(4,2) DEFAULT 0.18  -- seed; adapts to opportunity set
max_position_seed    DECIMAL(4,2) DEFAULT 0.15  -- seed; tightens in crisis
approval_threshold DECIMAL(4,2) DEFAULT 0.05
rebalance_drift DECIMAL(4,2) DEFAULT 0.05
default_action  VARCHAR(20) DEFAULT 'hold'  -- hold, execute
autonomy_level  VARCHAR(20) DEFAULT 'copilot'  -- observer, copilot, autopilot
asset_classes   JSONB  -- enabled asset classes
-- Non-dynamic settings
paper_trading   BOOLEAN DEFAULT TRUE  -- SPEC-01 FP-7: mandatory paper mode
kill_switch_active BOOLEAN DEFAULT FALSE  -- emergency trading halt
updated_at      TIMESTAMP DEFAULT NOW()
```

**adaptive_risk_params** (self-tuned overrides, updated by Layer 6 Bayesian optimization)

```
id              SERIAL PRIMARY KEY
portfolio_id    INTEGER REFERENCES portfolios(id)
regime          VARCHAR(30) NOT NULL  -- which regime these params are optimal for
dd_response_k   DECIMAL(6,2)  -- sigmoid steepness
dd_response_mid DECIMAL(6,4)  -- sigmoid midpoint
vol_target      DECIMAL(6,4)  -- adaptive volatility target
max_position    DECIMAL(6,4)  -- adaptive position limit
ensemble_w_bl   DECIMAL(4,2)  -- BL weight in ensemble
ensemble_w_hrp  DECIMAL(4,2)  -- HRP weight in ensemble
ensemble_w_rp   DECIMAL(4,2)  -- Risk Parity weight in ensemble
calmar_score    DECIMAL(6,4)  -- performance metric for this parameter set
optimized_at    TIMESTAMP DEFAULT NOW()
valid_from      TIMESTAMP  -- when this param set became active
valid_until     TIMESTAMP  -- NULL = currently active

INDEX ON (portfolio_id, regime, valid_until)
```

**credentials** (encrypted brokerage credentials, per SPEC-02 PC-8)

```
id              SERIAL PRIMARY KEY
portfolio_id    INTEGER REFERENCES portfolios(id)
credential_type VARCHAR(30) NOT NULL  -- ibkr_oauth, ibkr_api_key, eodhd_api_key
encrypted_value BYTEA NOT NULL  -- Fernet-encrypted token/key
expires_at      TIMESTAMP  -- for OAuth tokens
created_at      TIMESTAMP DEFAULT NOW()
updated_at      TIMESTAMP DEFAULT NOW()

INDEX ON (portfolio_id, credential_type)
```

**universe_changelog** (per SPEC-02 PC-2: log every addition/removal)

```
id              SERIAL PRIMARY KEY
action          VARCHAR(10) NOT NULL  -- add, remove, replace
ticker          VARCHAR(20) NOT NULL
reason          TEXT NOT NULL  -- algorithmic rationale
overlap_score   DECIMAL(4,2)  -- STRAPSim overlap at time of decision
factor_gap_filled VARCHAR(100)  -- which exposure gap this addresses
backtest_impact JSONB  -- impact on backtest metrics from this change
effective_date  DATE NOT NULL
created_at      TIMESTAMP DEFAULT NOW()
```

---

## 3. Redis Cache Structure

```
midas:prices:{ticker}          → latest OHLCV + timestamp (TTL 60s)
midas:regime:current           → current regime state (TTL 60s)
midas:regime:indicators        → VIX, spreads, yield curve (TTL 60s)
midas:portfolio:snapshot       → latest portfolio summary (TTL 300s)
midas:portfolio:positions      → current positions list (TTL 300s)
midas:decisions:pending        → list of pending decision IDs (no TTL)
midas:backtest:{strategy_hash} → cached backtest results (TTL 1 day)
midas:session:{user_id}        → session data (TTL 24h)
```

**Redis Persistence**: Enable AOF (Append Only File) persistence. The pending decisions queue and regime state must survive Redis restarts. RDB snapshots as backup.

**Fresh Price at Execution**: When generating actual trade orders (not just recommendations), bypass the 60s cache and fetch fresh prices directly from IBKR or EODHD. Display both recommendation price and execution price to user: "Recommended at $890. Current: $885. Proceed?"

---

## 4. IBKR Integration

### Connection

**Primary**: IBKR Web API v1.0 (OAuth 2.0) — the future-proof unified API.
**Fallback**: ib_async (maintained fork of ib_insync) for TWS API if Web API v1.0 features are insufficient.

- Web API v1.0 merges Client Portal, Account Management, and Flex Web Service under OAuth 2.0
- No local gateway required (unlike legacy Client Portal API)
- REST + WebSocket for async streaming
- Rate limits: ~50 requests/minute — requires priority queuing (trades > monitoring > data)
- IBKR Pro recommended over Lite (SmartRouting for better execution quality)

### Read Operations

- `GET /portfolio/accounts` — account summary
- `GET /portfolio/{accountId}/positions` — current positions
- `GET /portfolio/{accountId}/ledger` — account balances
- `GET /iserver/marketdata/history` — historical data (supplement)

### Write Operations (P2)

- `POST /iserver/account/{accountId}/orders` — place orders
- `DELETE /iserver/account/{accountId}/order/{orderId}` — cancel order
- `GET /iserver/account/orders` — order status

### Safety Measures

- All write operations require explicit user approval (biometric on mobile)
- Order preview before submission (show expected fill, cost estimate)
- Maximum order size limit (configurable, default 10% of portfolio)
- Kill switch: disable all trading with one action
- Connection health monitoring with automatic retry and graceful degradation
