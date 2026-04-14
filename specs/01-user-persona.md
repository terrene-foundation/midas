# User Persona

**Status:** GOVERNING. Product decisions trace to this user. When a design choice is unclear, ask "does this serve this user's job?"

---

## 1. The User

A **Singapore-domiciled self-directed investor** with their own capital on Interactive Brokers. Sophisticated enough to already make allocation decisions, but tired of being the only person in the room — no investment committee, no risk office, no quant desk. The user knows what an institutional desk does and wants that stack for themselves without paying someone else to hold the steering wheel.

| Dimension                    | Value                                                                                                                                  |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Domicile                     | Singapore (no capital gains tax, MAS regulatory frame)                                                                                 |
| Capital source               | Their own, not clients' — no fiduciary relationship to others                                                                          |
| Broker                       | Interactive Brokers (Web API v1.0 / TWS)                                                                                               |
| Portfolio size               | $100K–$500K range (affects liquidity constraints, position sizing)                                                                     |
| Sophistication               | Understands portfolio construction, can read a backtest, knows the difference between Sharpe and Sortino, recognizes overfitting smell |
| Risk temperament             | Risk-loving but not reckless — "go big or go home, but don't be stupid"                                                                |
| Time budget                  | Under 30 seconds on a calm day; under 2 minutes on a turbulent day; unknown upper bound during crisis                                  |
| Primary device for decisions | Mobile (iOS or Android)                                                                                                                |
| Primary device for analysis  | Web (desktop/laptop, min 1024px)                                                                                                       |
| Motivation                   | Autonomy; not losing to their own emotions; the conviction that a disciplined system beats a panicked human                            |

---

## 2. Job-To-Be-Done

> **"Run my own institutional-grade portfolio desk without it running my life."**

Not "make me money" (too vague), not "manage my portfolio" (a robo-advisor claim). The job has two halves that must both be satisfied:

1. **Institutional-grade execution** — the system does what a portfolio desk does, at the level a portfolio desk does it.
2. **Doesn't run my life** — the attention cost to the user is bounded and predictable; calm days take seconds, turbulent days take minutes, and the system earns more autonomy as its track record accumulates.

A product that satisfies only half fails the user. Half-one alone is a trading platform that eats the user's weekends; half-two alone is a robo-advisor that makes no real decisions.

---

## 3. Decisions The User Owns (Non-Delegable)

These never move to Midas regardless of autonomy level. They are the **trust boundary** (see `08-autonomy-and-trust.md`).

| Decision                                                                                                       | Why non-delegable                                                                                                                                                                                                                             |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk envelope** — drawdown tolerance ceiling, volatility target band, concentration cap, universe exclusions | The envelope defines the space the system is allowed to operate in. Only the user can widen or narrow it.                                                                                                                                     |
| **Paper → live transition**                                                                                    | Real capital comes off the bench only on explicit human action + biometric + clean paper-trading report.                                                                                                                                      |
| **Autonomy level promotion**                                                                                   | Downgrades are automatic; promotions require the user to see the evidence (track record, calibration, attribution) in a Decisions surface event and approve.                                                                                  |
| **Turbulent-regime approvals**                                                                                 | Any move proposed in Elevated / Urgent / Crisis regime state is reviewed in the Decisions surface before execution (exact threshold modulated by autonomy level and confidence posterior).                                                    |
| **Kill switch**                                                                                                | Instantly halts all trading. Accessible from Pulse and Settings. Recovery requires biometric + deliberate user action.                                                                                                                        |
| **Model promotion across champion/challenger boundary**                                                        | When a challenger meets its promotion contract, the promotion becomes a decision in the Decisions surface. The user sees shadow P&L, regime-conditional attribution, and which past decisions would have differed, then approves or declines. |

---

## 4. Activities Midas Does FOR The User

Inside the envelope and inside the granted autonomy level, Midas runs without asking. These activities must be continuous and autonomous or the value contract is broken.

- Universe construction and maintenance (ETF + S&P 1500 with data-driven selection)
- Data ingestion into the fabric
- Feature computation (both for latent learners and for factor overlays)
- Representation learning and continuous inference of `z_t` (the latent market state posterior)
- Model pool execution — predictive heads, generative heads, allocation heads
- Model routing via the meta-router
- Champion/challenger shadow execution for every pool layer
- Proposed allocations, trade lists, and cost-aware sizing
- Pre-trade compliance checks (PACT rules engine)
- Execution routing to IBKR
- Post-trade reconciliation and NAV computation
- Performance measurement and Brinson attribution
- Calibration tracking per model head
- Continuous degradation monitoring and automatic champion demotion
- Drafting decision briefs and counterfactuals
- Detecting user-override patterns and proactively surfacing parameter-tuning suggestions

---

## 5. Failure Modes (From The User's POV, Not The System's)

These are the things the user is most afraid of. Every design decision is checked against whether it makes one of these more or less likely.

### 5.1 Silent Betrayal

Midas executes something dumb while the user is asleep or offline, and the first they hear of it is a loss. The user trusted the autonomy level and the system broke the implicit contract — either by acting outside the envelope, by executing on stale data, or by taking an action whose rationale the user would have rejected.

**Guardrails:** envelope is enforced pre-trade by the PACT rules engine; stale-data detection is a hard gate; kill switch is always one tap away; every autonomous action writes a full brief to the Decisions history even if no notification fires; any action outside `z_t` states Midas has seen often enough to be calibrated on triggers escalation.

### 5.2 Being The Bottleneck

Notifications pile up, the user can't parse them fast enough, and the system stalls waiting. Midas becomes a second job. The attention cost exceeds any alpha it captures. This is where the product dies from success.

**Guardrails:** attention budget tracks decision-seconds per day and flags fatigue; notification tiering is strict; routine approvals batch into digests; Elevated-regime approvals compress to the essentials; Urgent/Crisis approvals have hard time-to-decide budgets with configurable defaults on expiry; `09-surfaces-and-attention.md` owns the full attention contract.

### 5.3 Fake Confidence

Midas sounds authoritative in its briefs but can't defend its reasoning when challenged in Debate. The user is unable to distinguish real competence from hallucinated confidence. This is the failure mode that makes every other feature toxic — the user loses the ability to trust their own trust signals.

**Guardrails:** every claim in a brief traces to a fabric row or a model version or a tool call; the Debate agent can re-run the optimizer, call tools against real data, and modify a pending decision; calibration curves are visible; the "what would change my mind" appendix is mandatory; frontier LLMs required for decision-adjacent work.

### 5.4 Regime Blindness

The system feels right in the regimes it has seen and fails silently in the regime the user most needs it to survive — the one that has never happened before. A 2008 that is not 2008. A COVID-crash that is not COVID-crash.

**Guardrails:** continuous state rendering means the system does not need a pre-defined label to react to an unseen state; confidence is always a posterior, so an unfamiliar `z_t` shows low confidence and escalates automatically; adversarial backtesting and synthetic tail augmentation are explicit concerns in `05-model-pool-and-meta-router.md`.

---

## 6. Time Budget Contract

The user's time with Midas is a contract, not a hope. Violations are design bugs.

| Regime state | Time to "I can close the app"        | Time to act on any pending decision                                            |
| ------------ | ------------------------------------ | ------------------------------------------------------------------------------ |
| Calm         | ≤ 30 seconds                         | n/a (no decision pending is the norm)                                          |
| Elevated     | ≤ 60 seconds                         | ≤ 2 minutes per decision                                                       |
| Urgent       | ≤ 30 seconds to see what's happening | ≤ 2 minutes per decision, hard window enforced                                 |
| Crisis       | Unbounded (user is engaged)          | Immediate for kill switch / envelope change; other decisions paused by default |

---

## 7. What The User Is Not

Making this explicit so we don't build for a phantom audience.

- **Not a day trader.** Intraday tools are out of scope.
- **Not a novice.** No hand-holding explanations of what a Sharpe ratio is.
- **Not managing other people's money.** No fiduciary layer, no KYC of third parties, no regulatory audit for v1.
- **Not on a US tax framework.** No tax-loss harvesting, no lot-level cost basis tracking for tax optimization.
- **Not asking for an academic paper.** Interpretability is valuable only after working models earn it.

---

## 8. How This Persona Is Used

Every spec, plan, and implementation decision is evaluated against three questions:

1. Which of this user's owned decisions does this serve?
2. Which of their failure modes does this make more or less likely?
3. Does this respect the time budget in the relevant regime state?

If a proposed feature cannot answer all three, it is either wrong, misnamed, or belongs in a later version.
