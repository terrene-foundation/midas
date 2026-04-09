# Value Audit Report: Midas

**Date**: 2026-04-09 (revised with user corrections)
**Perspective**: Evaluating democratized institutional investment infrastructure

---

## Executive Summary

**REVISED**: The initial audit framed Midas as competing with robo-advisors. This was fundamentally wrong. Midas is not a robo-advisor competitor — it is democratized institutional investment infrastructure. It puts the entire back office, middle office, and front office of a portfolio operation into one person's hands, for free.

The correct evaluation frame: does Midas successfully replicate institutional capabilities for an individual investor? The AI debate feature replaces the investment committee. The strategy engine replaces the quant desk. The risk system replaces the risk office. The question is not "why not Wealthfront?" — it is "can one person run their own portfolio desk?"

**Key finding preserved from original audit**: The AI debate capability is the centerpiece — no institution or product provides an AI that genuinely argues back with evidence. This is the moat.

**Corrections applied**: Singapore domicile (no US tax), dynamic risk (not static parameters), data-driven ETF universe (not pre-selected), investing not trading (no intraday anything).

---

## 1. Value Proposition Strength

### What the brief claims is different

- Autonomous decisions (not just allocation recommendations)
- AI debate capability (discuss decisions with the AI)
- Agile sector rotation (active management, not passive indexing)
- Regime-dependent rebalancing (adaptive, not calendar-based)

### Is the differentiation real?

**Partially real, partially cosmetic.**

The robo-advisor market (Wealthfront, Betterment, Schwab Intelligent Portfolios, Vanguard Digital Advisor) already handles ETF allocation, rebalancing, and tax-loss harvesting for 0.25% AUM or less. Midas needs to answer: _why would someone trust an unproven AI over Vanguard's 50-year track record?_

**Real differentiation candidates:**

- **Regime-dependent rebalancing** is genuinely different from calendar rebalancing. Most robo-advisors rebalance on drift thresholds or time intervals. If Midas can demonstrate that regime detection (bull/bear/sideways/crisis) produces measurably better outcomes net of transaction costs, this is defensible. But the burden of proof is enormous — you are claiming to time the market, which is the single most contested claim in finance.

- **AI debate capability** is the most interesting and underexplored feature. No existing robo-advisor lets you argue with it. This is not an investment feature — it is a _trust and education_ feature. It could be the actual product differentiator, but the brief treats it as a checkbox rather than the centerpiece.

- **Autonomous execution on IBKR** is technically differentiating but legally complex (see regulatory section).

**Cosmetic differentiation:**

- "Comprehensive backtesting" — every quant platform has this (QuantConnect, Zipline, Backtrader are free)
- "Accurate transaction cost modeling" — table stakes for any serious system, not a selling point
- "Modern UI for rapid decision-making" — every fintech says this; means nothing until demonstrated

### The uncomfortable question

If Midas uses EODHD (end-of-day data) as its primary source and rebalances at most once per week, it is not a trading system — it is a weekly allocation advisor. That is fine, but the brief's language ("agile sector rotation," "rapid decision-making") implies something faster. This mismatch will confuse users.

---

## 2. Target User Credibility

The brief does not name a target user. This is a critical omission.

| Persona                                              | Fit      | Problem                                                                                           |
| ---------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------- |
| **Passive retail investor** ($10K-$100K)             | Low      | Already served by Wealthfront/Betterment at 0.25% AUM. Will not trust unknown AI.                 |
| **Active retail trader**                             | Low      | Wants intraday data, options, leverage. Weekly rebalancing is too slow.                           |
| **Self-directed sophisticated investor** ($100K-$1M) | **High** | Has IBKR account already. Wants augmented decision-making. The AI debate feature is perfect here. |
| **High-net-worth** ($1M+)                            | Low      | Has a human advisor. Trust barrier is insurmountable for unproven AI.                             |
| **Quant hobbyist / developer**                       | Medium   | Wants to build strategies. But this person builds their own system, they don't buy one.           |

**Most credible persona**: Self-directed investor with $100K-$500K on IBKR who is already making their own decisions and wants an AI co-pilot — not an AI pilot.

**Product vision mismatch**: The brief describes full autonomy ("makes investment decisions for me"). The credible buyer wants augmented intelligence ("helps me make better decisions"). These require different UX, trust models, and regulatory treatment.

**Recommendation**: Build for the co-pilot use case first. Full autonomy is a v3 feature after trust is earned through track record.

---

## 3. Technical Feasibility vs Claims

### What is technically feasible today

- Factor-based portfolio construction using ML to weight factors dynamically
- Regime detection using Hidden Markov Models, changepoint detection, or transformer-based classifiers
- Backtested strategy deployment with realistic transaction cost modeling
- NLP-driven news sentiment as one input to a multi-signal framework
- Conversational AI that explains portfolio rationale and engages in Socratic debate

### What is NOT feasible

- Consistently beating the market after fees over a multi-year horizon (no AI has demonstrated this publicly with audited returns)
- Predicting regime changes in advance (detection is inherently backward-looking; value is in faster detection, not prediction)
- "Best" decisions (there is no objective "best" in investing — every decision is a tradeoff)

### Reality mapping

| Aspiration                            | Deliverable Reality                                                                  |
| ------------------------------------- | ------------------------------------------------------------------------------------ |
| "Makes the best investment decisions" | Makes _systematic, backtested, explainable_ decisions that follow a defined strategy |
| "Autonomous"                          | Semi-autonomous with human approval for trades above configurable thresholds         |
| "Agile sector rotation"               | Weekly sector tilt adjustments based on momentum + regime signals                    |
| "AI debate capability"                | LLM-powered explanation and Socratic questioning — actually achievable and valuable  |

**Reframe**: From "AI makes the best decisions" to "AI applies disciplined, systematic strategy that removes emotional bias." The latter is honest, defensible, and more compelling to sophisticated investors who know that _not losing to yourself_ is the real goal.

---

## 4. Risk Profile Contradiction

"Risk-loving but not reckless" provides zero actionable guidance. The system needs quantitative answers:

- **Maximum drawdown tolerance?** 20%? 40%? 60%?
- **Maximum single-position concentration?** 5%? 15%? 30%?
- **Leverage policy?** No leverage? 1.2x? 2x?
- **What happens at -30%?** Double down (risk-loving) or de-risk (not reckless)?

### Recommended resolution (REVISED)

**Static quantitative parameters are insufficient.** The risk system must be fully dynamic and adaptive (see SPEC-02, research/05-dynamic-risk.md):

1. **Continuous drawdown response**: Sigmoid function, not threshold ladder. Parameters self-adapt to regime.
2. **Adaptive position limits**: Tighten in crisis, relax in high-conviction calm markets.
3. **Self-tuning vol target**: Adjusts to opportunity set via Bayesian optimization.
4. **Regime-conditional risk budgets**: Expand when opportunity is rich, contract when danger signals appear.
5. **Hard circuit breakers only**: -30% emergency stop and kill switch are the only non-adaptive limits.

The questions above (max drawdown? concentration? leverage?) are answered dynamically by the system, not statically by configuration.

---

## 5. Commercialization Viability

### Regulatory reality

**If personal tool**: No registration needed. Build freely.

**If commercial** (US context):

- SEC registration as Registered Investment Adviser (RIA) required for personalized investment advice
- Form ADV disclosure of algorithms, risks, conflicts
- Fiduciary duty (must act in client's best interest)
- Annual compliance audits ($50K-$200K/year for small firm)
- FINRA regulates communications — claiming "best investment decisions" would be flagged

### Pricing models

| Model                          | Viability           | Notes                                                         |
| ------------------------------ | ------------------- | ------------------------------------------------------------- |
| AUM fee (0.25-0.75%)           | Most natural        | Needs RIA registration. At 0.50% on $10M AUM = $50K/year      |
| SaaS subscription ($50-200/mo) | Possible            | May still require RIA if providing personalized advice        |
| Performance fee                | Complex             | Generally prohibited for retail under Investment Advisers Act |
| Open source + hosted           | Viable for personal | Avoids regulatory issues but limits revenue                   |

**Decision required before building**: Personal tool or commercial product? The answer changes the architecture (multi-tenant vs single-tenant, data isolation, audit logging, compliance reporting).

---

## 6. Missing Critical Elements (Revised)

| Missing Element                     | Severity | Status                                                                                |
| ----------------------------------- | -------- | ------------------------------------------------------------------------------------- |
| **Dynamic risk framework**          | CRITICAL | RESOLVED — 7-layer adaptive system designed (SPEC-02, research/05-dynamic-risk.md)    |
| **Data-driven ETF universe**        | CRITICAL | RESOLVED — algorithmic construction spec (SPEC-02 PC-2)                               |
| **Benchmark definition**            | HIGH     | OPEN — user to define success criteria                                                |
| **Kill switch / disaster recovery** | HIGH     | RESOLVED — hard circuit breaker at -30%, kill switch in UI                            |
| **Paper trading validation**        | HIGH     | RESOLVED — mandatory 2 weeks (SPEC-01 FP-7)                                           |
| **API security**                    | HIGH     | RESOLVED — JWT auth, credential encryption specified (SPEC-02 PC-8)                   |
| **Background job scheduler**        | HIGH     | RESOLVED — explicit scheduler required (SPEC-02 PC-8)                                 |
| **Data quality validation**         | MEDIUM   | Addressed in data layer plan                                                          |
| **Execution model**                 | MEDIUM   | Addressed in strategy engine plan                                                     |
| **Dividend withholding tax**        | MEDIUM   | NEW — 30% on US ETFs for Singapore residents. Evaluate UCITS alternatives.            |
| ~~Tax-loss harvesting~~             | ~~N/A~~  | REMOVED — Singapore domicile, no capital gains tax                                    |
| ~~Tax-aware rebalancing~~           | ~~N/A~~  | REMOVED — Singapore domicile, no tax friction on rebalancing                          |
| ~~US regulatory strategy~~          | ~~N/A~~  | REMOVED — Singapore domicile, personal tool. MAS regulations apply if commercialized. |

---

## 7. Narrative Coherence (Revised)

**CORRECTION**: The original audit identified three conflicting narratives. The user resolved this: these are not three products — they are three layers of a single institutional infrastructure stack.

1. **The Strategy Engine** (back office): Quant research, backtesting, signal generation, portfolio optimization
2. **The Risk & Execution Office** (middle office): Dynamic risk management, regime detection, order execution, compliance monitoring
3. **The Investment Committee** (front office): AI debate interface, decision briefing, approval workflows, transparency

These are not alternatives to choose between. They are the minimum viable institutional stack. The AI debate (investment committee) is the user-facing layer that sits on top of the strategy engine and risk office.

**Graduated autonomy** remains valid: the system starts by showing its work and asking permission, then earns the right to operate more independently as its track record builds. This is how a new portfolio manager earns trust from an investment committee — through demonstrated competence, not claimed authority.

---

## Severity Summary (Revised)

| Issue                             | Original Severity | Current Status                                       |
| --------------------------------- | ----------------- | ---------------------------------------------------- |
| ~~No regulatory strategy~~        | ~~CRITICAL~~      | RESOLVED — personal tool, Singapore domicile         |
| ~~No quantitative risk policy~~   | ~~CRITICAL~~      | RESOLVED — dynamic adaptive risk system (SPEC-02)    |
| ~~Three conflicting narratives~~  | ~~HIGH~~          | RESOLVED — three layers of one institutional stack   |
| ~~Risk philosophy contradiction~~ | ~~HIGH~~          | RESOLVED — continuous sigmoid response, self-tuning  |
| ~~No tax awareness~~              | ~~HIGH~~          | REMOVED — Singapore, no CGT. Dividend WHT tracked.   |
| ~~No kill switch~~                | ~~HIGH~~          | RESOLVED — -30% circuit breaker + manual kill switch |
| No benchmark definition           | HIGH              | OPEN — user to define                                |
| Data quality validation           | MEDIUM            | Addressed in plans                                   |
| Execution model                   | MEDIUM            | Addressed in plans                                   |

---

## Bottom Line (Revised)

User corrections resolved the three blocking questions: (1) personal institutional infrastructure tool, (2) dynamic adaptive risk system (not static parameters), (3) Singapore-domiciled sophisticated investor running their own portfolio desk.

The remaining open question is benchmark definition — what does "success" look like?

The AI debate feature remains the centerpiece. It is the institutional investment committee, democratized. Everything else is infrastructure that makes the debate meaningful.
