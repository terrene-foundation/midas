# Analysis Synthesis: Midas

**Date**: 2026-04-09

---

## 1. Product Identity

### Midas Is Democratized Institutional Infrastructure

Midas does not compete with robo-advisors. It replaces the need for them entirely. It puts the complete back office, middle office, and front office of an institutional-grade portfolio operation into the hands of an individual — for free.

The comparison is not "Midas vs Wealthfront." It is: "Having your own portfolio desk vs paying someone else to make decisions for you."

**What this means**:

- Features are evaluated against institutional capabilities, not retail product gaps
- The sophistication ceiling is what a hedge fund portfolio desk can do
- The AI debate replaces the investment committee process
- The strategy engine replaces the quant research desk
- The risk management replaces the risk office

### Graduated Autonomy Model

| Level         | Behavior                                                                         | When                                                     |
| ------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **Observer**  | Monitors, analyzes, recommends — never executes                                  | Day 1 (new user)                                         |
| **Co-Pilot**  | Executes routine rebalancing autonomously; asks approval for large/unusual moves | After user configures thresholds                         |
| **Autopilot** | Executes all decisions within risk envelope; alerts on regime changes            | After user explicitly opts in + track record established |

Users choose their level. The system nudges toward higher autonomy as trust builds through demonstrated performance.

---

## 2. Institutional Capabilities Being Democratized

Midas does not differentiate against retail products. It replicates institutional capabilities.

### Core Institutional Capabilities

1. **Investment Committee → AI Debate**: The AI debate agent replaces the human investment committee process. It challenges theses, demands evidence, tracks decision outcomes, and learns from overrides. This is the centerpiece — P0 implementation priority.

2. **Quant Research Desk → Adaptive Strategy Engine**: Multi-signal framework with ML-driven allocation, self-tuning parameters, and regime-conditional optimization. Uses frontier techniques (DCC-GARCH, Bayesian Kelly, transformer-based signals) — not textbook MPT.

3. **Risk Office → Dynamic Risk System**: 7-layer adaptive risk framework. Continuous drawdown response (sigmoid, not step ladder). Self-tuning via Bayesian optimization. Real-time correlation breakdown detection. Position-level drawdown beta monitoring.

4. **Portfolio Operations → Regime-Aware Everything**: UX, notifications, information density, approval routing, and rebalancing frequency all adapt to market regime autonomously.

5. **Compliance → Radical Transparency**: Every decision comes with structured brief (thesis, if-approved, if-rejected, precedents). Full audit trail. Counterfactual tracking after every override.

6. **Data & Analytics → Data-Driven Universe**: Algorithmically constructed ETF universe based on expense ratios, correlations, overlap analysis, and missing exposure detection. No human curation.

---

## 3. Dynamic Risk Framework

The brief says "go big or go home" and "don't be reckless." Static parameters are insufficient — the risk system must be fully adaptive.

### Approach: Every Risk Parameter Is Dynamic

Risk is NOT a table of fixed numbers. It is a 7-layer adaptive system (see SPEC-02 and research/05-dynamic-risk.md):

1. **Real-time measurement**: GJR-GARCH volatility, DCC correlations, EVT tail risk
2. **Regime detection**: HMM + ensemble validation, continuous probability updates
3. **Adaptive risk budgeting**: Volatility targeting with asymmetric response, Bayesian Kelly, risk recycling
4. **Continuous drawdown management**: Sigmoid response function (not thresholds), recovery-aware, CPPI-inspired ratcheting floor
5. **Position-level governance**: Component VaR, drawdown beta, safe-position-becomes-risky detection
6. **Self-tuning**: Bayesian optimization of parameters quarterly, multi-objective Pareto frontier
7. **Contagion monitoring**: Diebold-Yilmaz spillover, diversification ratio, crisis correlation stress testing

### Seed Values (Initial Seeds Only — System Overrides These)

The following are starting points that the self-tuning system will optimize. Users can adjust during onboarding.

| Seed Parameter             | Initial Value               | Dynamic Behavior                                                    |
| -------------------------- | --------------------------- | ------------------------------------------------------------------- |
| Drawdown response midpoint | -15%                        | Shifts based on regime, recent performance, recovery trajectory     |
| Volatility target          | 15-20% annualized           | Adjusts to opportunity set (high-Sharpe → higher target)            |
| Max single-position        | 15% of portfolio            | Tightens in crisis, relaxes in high-conviction calm markets         |
| Rebalancing frequency      | Monthly default, weekly max | Regime-driven: calm → monthly, elevated → biweekly, urgent → weekly |
| Human approval threshold   | Moves >5% of portfolio      | Adapts with autonomy level progression                              |

### Singapore Domicile Implications

- No capital gains tax — rebalancing has zero tax friction
- No tax-loss harvesting required — simplifies the strategy engine significantly
- Dividend withholding tax (30% on US ETFs) — evaluate UCITS alternatives
- USD/SGD currency exposure — partial dynamic hedge recommended (50-70%)

### Hard Safety Limits (Non-Dynamic)

These do NOT self-tune. They are circuit breakers.

| Limit                  | Value             | Behavior                                                             |
| ---------------------- | ----------------- | -------------------------------------------------------------------- |
| **Emergency stop**     | -30% from peak    | All trading halted. 100% cash/short bonds. Human review required.    |
| **Kill switch**        | Manual activation | Immediately disable all trading. Accessible from Pulse and Settings. |
| **Paper trading gate** | 2 weeks minimum   | No real money until paper validation report reviewed and approved.   |

---

## 4. Architecture Decisions

### 4.1 Tech Stack

| Layer                | Choice                                       | Rationale                                                                                |
| -------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **Backend**          | Python (Kailash Core SDK + DataFlow + Nexus) | Quantitative finance ecosystem is Python-native; Kailash provides workflow orchestration |
| **Strategy Engine**  | Python (numpy, scipy, pandas)                | Portfolio optimization, signal generation, backtesting                                   |
| **AI/LLM**           | Kailash Kaizen agents                        | Debate interface, decision explanation, regime narrative                                 |
| **Database**         | PostgreSQL                                   | Time-series market data, portfolio history, decision audit trail                         |
| **Cache**            | Redis                                        | Aggressive market data caching, session state                                            |
| **Frontend Web**     | React/Next.js                                | Rich data visualization, real-time updates                                               |
| **Frontend Mobile**  | Flutter                                      | Cross-platform iOS + Android from single codebase                                        |
| **Broker API**       | IBKR Web API v1.0 (OAuth 2.0) + ib_async     | Future-proof unified API with OAuth; ib_async for TWS fallback                           |
| **Market Data**      | EODHD All-in-One ($99.99/mo) + Yahoo backup  | 150K+ tickers, 70+ exchanges; per brief data fabric pattern                              |
| **News/Sentiment**   | Perplexity API                               | Integrated Morningstar, SEC/EDGAR, FactSet data; per brief                               |
| **Backtesting**      | vectorbt (research) + NautilusTrader (prod)  | Fast iteration + backtest-to-live execution parity                                       |
| **Regime Detection** | HMM (hmmlearn) + VIX indicators + ensemble   | Institutional-grade (validated by Two Sigma, SSGA research)                              |

### 4.2 Data Architecture

**Data Fabric Pattern** (per brief: "store whatever you have collected and re-use"):

```
Market Data Sources → Data Fabric (PostgreSQL + Redis)
                          ↓
              Strategy Engine reads from fabric
              (never directly from source)
```

- **PostgreSQL**: Historical prices, fundamentals, portfolio snapshots, decision log, debate transcripts
- **Redis**: Latest prices (polling cache), regime state, session data
- **Polling**: When screen is active, poll at 1-minute intervals. When inactive, poll at 15-minute intervals for regime monitoring only.
- **Data freshness**: Display "as of [timestamp]" on all market data. No pretense of real-time.

### 4.3 Strategy Engine Architecture

```
Signals Layer
  ├── Time-series momentum (10-month SMA)
  ├── Cross-sectional momentum (12-1 month)
  ├── Volatility-adjusted momentum
  ├── Carry (yield differentials)
  ├── Macro regime (yield curve, PMI, credit spreads)
  └── Volatility regime (inverse vol scaling)
          ↓
Signal Combiner (Black-Litterman views)
          ↓
Portfolio Optimizer (ensemble: BL + HRP + Risk Parity)
          ↓
Risk Manager (CVaR constraints, drawdown thresholds, position limits)
          ↓
Execution Layer (IBKR API, cost-aware order sizing)
```

### 4.4 AI Agent Architecture (Kaizen)

Three AI agent roles:

1. **Analyst Agent**: Generates market analysis, regime classification narrative, decision rationales. Reads from data fabric + strategy engine outputs. Writes structured briefs.

2. **Debate Agent**: Handles conversational interactions. Has access to portfolio data, decision history, backtest engine, market data. Must be opinionated and evidence-based. Personality: "respectful but direct portfolio manager."

3. **Monitor Agent**: Continuous background process. Watches regime indicators, portfolio drift, news sentiment. Triggers approval workflows when thresholds crossed. Generates proactive alerts.

### 4.5 Key Technical Risks

| Risk                                         | Severity | Mitigation                                                            |
| -------------------------------------------- | -------- | --------------------------------------------------------------------- |
| IBKR API instability / rate limits           | HIGH     | Retry with backoff; queue orders; graceful degradation                |
| EODHD data quality (bad corporate actions)   | HIGH     | Cross-validate with Yahoo Finance; flag anomalies                     |
| Strategy overfitting to backtest             | HIGH     | Walk-forward validation, deflated Sharpe, parameter stability testing |
| LLM hallucination in debate                  | MEDIUM   | Ground every claim in data; never let AI fabricate numbers            |
| Latency in approval workflow                 | MEDIUM   | Rich push notifications with inline actions; configurable defaults    |
| Portfolio optimization numerical instability | MEDIUM   | Use HRP as fallback when BL/risk-parity fails to converge             |

---

## 5. Commercialization Path

### Phase 1: Personal Institutional Infrastructure (v1)

- Single-user, self-hosted or local
- No regulatory requirements (personal tool, not advice to others)
- The full institutional capability stack running on one machine
- Mandatory 2-week paper trading before live
- Proves that institutional-grade portfolio management can be democratized

### Phase 2: Open Infrastructure (v2)

- Multi-user capable
- Position as infrastructure/tools (not investment advice)
- Open-source core with optional hosted service
- Architecture supports multi-tenant but regulatory strategy must be confirmed before commercialization

**Note**: The brief mentions "consider commercializing." The infrastructure model (giving users the tool) has different regulatory implications than the advisory model (managing users' money). Singapore-based MAS regulations apply, not SEC/FINRA.

---

## 6. Scope for v1

### In Scope

- Brokerage connection (IBKR read + write)
- Data fabric (EODHD + Yahoo Finance + caching)
- Strategy engine (signal generation, portfolio optimization, risk management)
- Backtesting framework (walk-forward, regime-specific, cost-aware)
- Decision engine (regime detection, approval workflows, structured briefs)
- AI debate interface (grounded in portfolio data)
- Web frontend (React/Next.js) — primary platform
- Mobile frontend (Flutter) — iOS + Android
- Onboarding flow with risk profile configuration

### Out of Scope (v1)

- Multi-user / multi-tenant
- Options / leverage strategies
- Real-time streaming data
- Social features / strategy sharing
- Regulatory compliance infrastructure (deferred until commercialization decision)
- Payment processing

### Removed From All Plans (User Corrections)

- US tax-loss harvesting (Singapore domicile — no capital gains tax)
- US tax-lot tracking (irrelevant)
- Pre-selected ETF universe (data-driven instead)
- Static risk parameters (dynamic adaptive system instead)
- Robo-advisor competitive framing (infrastructure framing instead)

---

## 7. Resolved Questions

| Question                     | Resolution                                                                                                  | Source        |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------- |
| Personal tool or commercial? | Personal tool v1, commercialization considered later                                                        | User feedback |
| Tax situation?               | Singapore domicile. No CGT. Dividend withholding tax on US ETFs (30%) relevant.                             | User feedback |
| Risk defaults acceptable?    | Static defaults rejected. Dynamic adaptive risk system required. Seed values acceptable as starting points. | User feedback |
| Paper trading?               | Mandatory 2 weeks minimum before live                                                                       | User feedback |
| UI/UX?                       | Approved as designed                                                                                        | User feedback |

### Remaining Open Questions

1. **Starting portfolio size?** Affects liquidity constraints and which instruments are practical for autonomous execution.
2. **Benchmark preference?** What does "success" look like? Maximize risk-adjusted returns (Sharpe/Calmar)? Minimize drawdowns? Beat a specific index?
