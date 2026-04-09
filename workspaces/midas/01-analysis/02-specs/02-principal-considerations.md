# SPEC-02: Principal Considerations

**Status**: GOVERNING — These guide all strategy, risk, data, and architecture decisions.
**Date**: 2026-04-09

---

## PC-1: Risk Is a Continuous Function, Not a Step Ladder

Risk management uses continuous, differentiable response functions that adapt in real-time. No discrete thresholds, no if-else ladders, no static parameters set during onboarding and forgotten.

### Drawdown Response

The system uses a sigmoid drawdown response function:

```
exposure_multiplier = 1 / (1 + exp(k * (drawdown - d_mid)))
```

Where `k` (steepness) and `d_mid` (midpoint) are themselves functions of:

- Current regime probability distribution
- Recent performance trajectory
- Recovery velocity (not just drawdown depth)
- Time spent in drawdown

The Grossman-Zhou (1993) insight governs the shape: tolerate small drawdowns (convex region), cut aggressively near the constraint (steep region).

### Volatility Response

Asymmetric: scale DOWN exposure faster than scaling UP.

- Vol spike → exponential decay of exposure
- Vol decline → linear ramp-up with lag
- Conditional targeting: target vol itself adjusts to opportunity set (high-Sharpe regime → higher target)

### Self-Tuning

All risk parameters are treated as hyperparameters optimized via Bayesian optimization (Optuna/BoTorch) on rolling walk-forward backtests. The system discovers its own optimal risk tolerance per regime via multi-objective Pareto frontier (return vs drawdown vs turnover).

**Violation test**: If a risk parameter is a literal constant in the codebase (not output of an adaptive process), it must be justified as a seed value that the system will override.

---

## PC-2: The Instrument Universe Is Data-Derived, Not Human-Curated

The system algorithmically constructs its investable universe. No hardcoded ticker lists.

### Selection Criteria (All Algorithmic)

1. **Expense ratio**: Lower is better, with threshold for inclusion
2. **Correlation structure**: Hierarchical clustering to group similar ETFs, select best representative per cluster
3. **Holdings-level overlap**: Eliminate redundancy by analyzing actual underlying holdings, not just return correlation
4. **Missing exposure detection**: Factor analysis (Fama-French + sector/geographic/thematic) to identify portfolio gaps
5. **Liquidity**: Minimum average daily volume for autonomous execution feasibility
6. **Structural integrity**: AUM floor, fund age, tracking error vs index

### Dynamic Maintenance

- Universe reviewed on a scheduled basis (monthly or quarterly)
- Instruments enter when they fill a gap or improve on an existing selection
- Instruments exit when liquidity drops, expense ratio rises, overlap becomes excessive, or a better alternative appears
- Every addition/removal is logged with rationale and backtest impact

### Singapore Investor Considerations

- Evaluate Ireland-domiciled UCITS ETFs as alternatives to US-domiciled (dividend withholding tax: 30% US vs 15% Ireland for many markets)
- Include USD/SGD currency exposure as a factor in universe construction
- IBKR-accessible instruments across US, European, and Asian exchanges

**Violation test**: If adding or removing a specific ETF requires a code change rather than a data update, the design is wrong.

---

## PC-3: Investing, Not Trading

Midas operates on portfolio investment timescales. Every design decision must respect this.

| Aspect           | Investing (Midas)              | Trading (NOT Midas)        |
| ---------------- | ------------------------------ | -------------------------- |
| Horizon          | Weeks to months                | Minutes to days            |
| Rebalancing      | Weekly max, often monthly      | Continuous                 |
| Data granularity | End-of-day primary             | Tick/minute                |
| Language         | Allocation, exposure, regime   | Entry, exit, setup, signal |
| Decision unit    | Portfolio composition          | Individual trade           |
| Sector rotation  | Monthly to quarterly cycles    | Never intraday             |
| Risk frame       | Portfolio drawdown, volatility | Per-trade stop-loss        |

### What This Means for Implementation

- No intraday data feeds required (polling for UI freshness only)
- Backtesting at daily granularity, not tick-level
- Execution timing matters less than allocation accuracy
- Transaction costs modeled per rebalancing event, not per trade
- Position changes are always framed as "portfolio is moving from allocation A to allocation B"

**Violation test**: If a feature description uses the word "trade" as a verb without qualification, reframe it in portfolio language.

---

## PC-4: Institutional Capability, Democratized

Every feature should be evaluated against: "Does an institutional portfolio desk have this capability?" If yes, Midas should provide it. If Midas provides something an institution wouldn't use, question why.

### Institutional Capabilities to Democratize

| Institutional Capability        | Midas Implementation                                        |
| ------------------------------- | ----------------------------------------------------------- |
| Multi-factor risk decomposition | Component VaR, drawdown beta per position                   |
| Dynamic correlation monitoring  | DCC-GARCH, Diebold-Yilmaz spillover index                   |
| Regime-conditional allocation   | HMM + ensemble regime detection → allocation adjustment     |
| Scenario stress testing         | Synthetic scenario generation, crisis correlation matrices  |
| Portfolio attribution           | Regime-specific performance, factor-level attribution       |
| Risk budgeting                  | Adaptive risk budgets that expand/contract with opportunity |
| Compliance monitoring           | Position limits, concentration checks, drift monitoring     |
| Investment committee debate     | AI debate agent (replacing human committee discussion)      |

### What Institutions Have That We Don't (Accepted Limitations)

- Prime brokerage relationships (we use IBKR retail)
- Dark pool access (not available to retail)
- OTC derivatives (not in scope for ETF-based portfolio)
- Proprietary data feeds (we use EODHD + public data)
- Leverage beyond regulatory limits (IBKR margin rules apply)

**Violation test**: If a proposed feature has no institutional analog, ask whether it is genuinely novel (good) or a retail gimmick (cut it).

---

## PC-5: Every Signal and Model Must Be Validated, Not Assumed

No signal enters the system based on reputation or tradition. Every component earns its place through data.

### Validation Requirements

1. **Walk-forward out-of-sample testing**: Every signal, model, and parameter combination
2. **Deflated Sharpe Ratio**: Correct for multiple testing (track the number of strategy variants tested)
3. **Parameter stability**: Performance must degrade gracefully when parameters vary ±20%
4. **Regime-conditional evaluation**: Performance per market regime, not just aggregate
5. **Economic rationale**: Every parameter must have a reason rooted in market microstructure, not curve-fitting
6. **Cross-asset validation**: If a signal works for one asset class, test it on others

### What "Validated" Means

- Positive risk-adjusted performance in ≥70% of rolling out-of-sample windows
- No single regime with catastrophic performance (Sharpe < -0.5)
- Net of realistic transaction costs (spread + slippage + execution gap)
- Robust to ±20% parameter perturbation

**Violation test**: If a signal or model is included because "the literature supports it" without backtesting on Midas's specific universe and constraints, it is not validated.

---

## PC-6: The System Gets Smarter Over Time

Midas is not a static deployment. It learns and improves continuously.

### Learning Mechanisms

1. **Self-tuning risk parameters**: Bayesian optimization on rolling backtests (quarterly cycle)
2. **Signal calibration**: Track each signal's predictive accuracy over time, adjust Black-Litterman confidence weights
3. **Override learning**: Track user overrides and counterfactual outcomes. Adjust behavior when user is consistently right (or wrong)
4. **Regime model refinement**: Retrain HMM periodically with new data, potentially discovering new regimes
5. **Universe evolution**: New instruments evaluated and added when they improve the portfolio
6. **Debate knowledge accumulation**: Past debate threads inform future recommendations

### Decay and Staleness

- Models degrade as market structure evolves
- A model that was validated 2 years ago may no longer be valid
- The system must detect its own degradation (monitoring prediction accuracy, hit rates, Sharpe decay)
- When degradation is detected, trigger re-optimization or flag for review

**Violation test**: If the system deployed today would behave identically in 2 years without any human intervention or retraining, it is not learning.

---

## PC-7: Mandatory Paper Trading Validation

Before any real capital is deployed, the system must complete a minimum 2-week paper trading period that validates:

1. **Data pipeline**: Ingestion, caching, staleness detection all working
2. **Signal generation**: Signals computed daily without error
3. **Portfolio optimization**: Optimizer converges, produces reasonable allocations
4. **Risk management**: Drawdown response, position limits, regime detection all functional
5. **Execution path**: Orders generated, submitted to IBKR paper, filled, reconciled
6. **Approval workflow**: Decisions created, notifications sent, approvals processed
7. **Regime response**: At least one simulated regime change handled correctly

### Paper Trading Report

At the end of the paper period, the system generates a validation report:

- All subsystems functional (pass/fail checklist)
- Simulated P&L and risk metrics
- Any anomalies or warnings encountered
- Comparison to backtest expectations (is live behavior consistent with backtested behavior?)

User reviews the report before authorizing live trading.

**Violation test**: If the transition from paper to live requires any code change (not just a config flag), the paper trading mode is not realistic enough.

---

## PC-8: Security Proportional to Capability

The system can execute real trades on a real brokerage account. Security specifications must be proportional to this capability.

### Non-Negotiable Security Requirements

1. **API authentication**: Every endpoint authenticated (JWT minimum for v1)
2. **Credential encryption**: IBKR tokens encrypted at rest, key from .env
3. **Biometric gating**: Trade approvals require biometric on mobile
4. **Audit trail**: Every decision, approval, trade, and parameter change logged immutably
5. **Kill switch**: Immediately disable all trading, accessible from Pulse and Settings
6. **Session management**: Automatic lockout after inactivity, re-auth required
7. **Rate limit management**: IBKR API rate limits respected with priority queuing (trades > monitoring > data)

### Operational Requirements

1. **Background job scheduling**: Explicit scheduler for data ingestion, signal generation, regime monitoring
2. **Health monitoring**: Heartbeat checks on IBKR connection, data pipeline, background jobs
3. **Graceful degradation**: If any subsystem fails, trading pauses automatically. Never execute with stale or missing data.
4. **Fresh price at execution**: Bypass cache when generating actual trade orders

**Violation test**: If the system could execute a trade without the user's explicit current-session consent (biometric or equivalent), the security model is broken.

---

## Application

These considerations are checked against every implementation decision. They operate one level below the First Principles (SPEC-01): First Principles define WHAT Midas is; Principal Considerations define HOW decisions are made within that identity.
