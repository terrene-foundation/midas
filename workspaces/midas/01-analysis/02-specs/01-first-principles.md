# SPEC-01: First Principles

**Status**: GOVERNING — These override all other analysis, plans, and implementation decisions.
**Date**: 2026-04-09
**Authority**: User-defined, non-negotiable.

---

## FP-1: Midas Is Infrastructure, Not a Product Competing With Products

Midas is not a robo-advisor. It does not compete with Wealthfront, Betterment, or any managed service. Midas puts the **entire** back office, middle office, and front office of an institutional-grade investment operation into the hands of an individual — for free.

The comparison is not "Midas vs Wealthfront." The comparison is "having your own portfolio desk vs paying someone else to make decisions for you."

**Implication**: Never frame features in terms of competitive differentiation against existing products. Frame them in terms of institutional capabilities being democratized. The question is not "what does Wealthfront lack?" — it is "what does a portfolio desk at a hedge fund have that an individual investor doesn't?"

**Violation test**: If a sentence could appear in a "why we're better than Wealthfront" pitch deck, it is wrong.

---

## FP-2: Let Data Drive Everything

Do not pre-select instruments, strategies, parameters, or allocations. Build systems that discover optimal choices from data.

- **ETF universe**: Algorithmically constructed from expense ratios, correlations, overlap analysis, and missing exposure detection. Instruments enter and leave the universe based on data, not human curation.
- **Strategy selection**: Signals validated by their historical and out-of-sample performance, not by reputation or tradition.
- **Risk parameters**: Dynamically adapted by the system based on market conditions, not set as static numbers during onboarding and forgotten.
- **Allocation weights**: Determined by optimization algorithms that respond to current market structure, not by fixed model portfolios.

**Implication**: Any hardcoded list of tickers, fixed allocation percentages, or static parameter values in the codebase is a smell. The system should be able to reconstruct its entire investment strategy from data alone.

**Violation test**: If removing a specific ticker symbol from the code would break the system, the design is wrong.

---

## FP-3: Dynamic Over Static, Always

It is 2026. Every parameter, threshold, allocation, and risk limit should adapt to market conditions in real-time or near-real-time.

- Risk budgets expand when the opportunity set is rich, contract when danger signals appear
- Drawdown management is a continuous response function, not a step ladder
- Regime detection updates continuously, not at fixed intervals
- The system's own confidence in its models adjusts based on recent prediction accuracy
- Rebalancing frequency is determined by market conditions, not a calendar

**Implication**: "Set it and forget it" is the antithesis of Midas. Every aspect of the system should be responsive to the current state of the world. Static defaults are acceptable only as initial seeds that the system immediately begins overriding with learned behavior.

**Violation test**: If you could unplug the system for 6 months, plug it back in, and it behaves identically — it is not dynamic enough.

---

## FP-4: No Intraday, No Day-Trading, No Confusion of Investing With Trading

Midas manages a portfolio investment. It does NOT trade. These are fundamentally different activities.

- Sector rotation happens over weeks to months, never intraday
- Rebalancing happens at most weekly, often monthly
- Data granularity is end-of-day, supplemented by polling when the user is active
- There is no concept of "entries" and "exits" — there are allocation adjustments
- Position changes are portfolio-level decisions, not individual trade calls

**Implication**: Never use trading language (entries, exits, signals, setups). Use investment language (allocation, rebalancing, exposure, regime, risk budget). The system thinks in terms of portfolio composition, not individual trades.

**Violation test**: If a feature would be equally useful to a day trader, it is probably wrong for Midas.

---

## FP-5: Push the Frontier — Create What Nobody Thought Possible

The user's ambition is not to replicate known techniques. It is to combine frontier ML, institutional-grade risk management, and conversational AI in ways that have not been done before.

- When two approaches exist — textbook and frontier — choose frontier
- When research suggests something is "not feasible yet," investigate whether 2026 tools make it feasible now
- The AI debate feature should be genuinely intelligent — not a chatbot wrapper on backtesting output
- The system should get smarter over time, learning from its own decisions, the user's overrides, and new market data

**Implication**: Research the latest papers (2024-2026) before proposing any technique. If a method was published before 2020 and has not been extended, look for what replaced or improved it.

**Violation test**: If a finance professor in 2015 would nod approvingly at the entire system design, it is not frontier enough.

---

## FP-6: Singapore Domicile — No US Tax Framework

The user is domiciled in Singapore. Singapore has no capital gains tax for individuals. All US-centric tax considerations are irrelevant:

- No tax-loss harvesting
- No short-term vs long-term capital gains distinction
- No wash sale rules
- No tax-lot tracking required

**Relevant Singapore considerations**:

- Withholding tax on US-source dividends (typically 30% unless treaty)
- Ireland-domiciled UCITS ETFs may be more tax-efficient for dividend income
- No restriction on foreign investment
- Multi-currency considerations (SGD base, USD-denominated instruments)

**Implication**: Remove all US tax references from plans, strategies, and user flows. Replace with Singapore-relevant considerations (dividend withholding, UCITS alternatives, currency exposure).

---

## FP-7: Mandatory Paper Trading Before Live

Paper trading for a minimum of 2 weeks is mandatory before any real money is at risk. This is not optional and cannot be skipped.

**Purpose**: Validate all operational systems — data ingestion, signal generation, optimization, order routing, approval workflows, regime detection — with zero financial risk.

**Implication**: The system launches in paper trading mode by default. Transitioning to live requires explicit user action AND successful completion of the paper trading period. The paper trading period produces a performance report that the user reviews before going live.

---

## FP-8: The AI Debate Is the Product

The conversational AI interface where the user can challenge, question, and refine investment decisions is not a feature — it is the core product experience. Everything else (data, strategy, execution) is infrastructure that enables the debate to be meaningful.

**Implication**: The debate agent should be the most sophisticated, well-specified, and thoroughly tested component. It should have genuine domain expertise, disagree when the evidence supports disagreement, and produce insights the user could not easily derive on their own. Implementation priority: P0 alongside the strategy engine, not P2 after it.

---

## Application

These first principles are checked against every plan, spec, implementation decision, and user flow. If a decision contradicts any FP, it must be justified explicitly or changed. No implicit overrides.
