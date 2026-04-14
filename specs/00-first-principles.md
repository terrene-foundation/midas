# First Principles

**Status:** GOVERNING. Any design, plan, or implementation that contradicts a principle here is wrong by definition. Principles marked [REFRAMED] supersede their Phase 01 counterparts.

---

## FP-1: Institutional Infrastructure, Democratized

Midas is not a robo-advisor and does not compete with retail products. It puts the complete front / middle / back office of an institutional-grade portfolio operation into the hands of an individual. The comparison is "owning your own portfolio desk" vs "paying someone else to make decisions for you."

**Violation test:** if a feature reads like "we're better than [retail product]", it is wrong. Features are evaluated against institutional capabilities.

---

## FP-2: Data Drives Everything

No hardcoded tickers, static allocation percentages, fixed parameter values, or human-curated universes. The system reconstructs its entire strategy from data.

**Violation test:** if removing a ticker symbol from code would break the system, the design is wrong.

---

## FP-3: Dynamic Over Static, Always

Every parameter, threshold, allocation, and risk limit responds to current market conditions. Static defaults are acceptable only as seed values the system immediately begins overriding.

**Violation test:** if Midas could be unplugged for six months, plugged back in, and behave identically — it is not dynamic enough.

---

## FP-4: Investing, Not Trading

Midas manages portfolio investments on timescales of weeks to months. No intraday decisions, no day-trading language, no "entries" and "exits." Position changes are allocation adjustments. Rebalancing happens at most weekly, often monthly, and only when the system decides it is warranted.

**Violation test:** if a feature would be equally useful to a day trader, it is probably wrong for Midas.

---

## FP-5: Push the Frontier

Frontier techniques over textbook methods. If research says something is "not feasible yet," investigate whether current tools make it feasible now. The system must get smarter over time — learning from its own decisions, user overrides, and new data.

**Violation test:** if a quant professor in 2015 would nod approvingly at the entire design, it is not frontier enough.

---

## FP-6: Singapore Domicile, No US Tax Framework

The user is domiciled in Singapore. No capital gains tax. No tax-loss harvesting, no wash sale rules, no tax-lot tracking. Relevant considerations: US dividend withholding (30% unless treaty, ~15% for Ireland-domiciled UCITS), multi-currency exposure (SGD base, USD instruments), MAS regulatory frame for any future commercialization.

---

## FP-7: Mandatory Paper Trading Before Live

Minimum two weeks of paper trading before any real capital is at risk. Non-skippable. The paper period produces a validation report across every subsystem (data, representation, state inference, models, router, optimizer, risk, compliance, execution, approval workflow). Transition to live requires user review of the report + explicit action + biometric.

---

## FP-8 [REFRAMED]: Evidence-First Co-Decision

The prior principle — "the AI debate is the product" — stands but in a sharper form. Midas's job is to **assemble the evidence**; the user's job is to **weigh it**; the decision is **ours, not mine or yours**. The Debate surface is not rhetorical debate — it is a joint evidence review where the Debate agent must be able to propose alternative allocations, re-run the optimizer under user-proposed constraints, and generate counterfactuals on demand. A Debate surface that can only narrate is dead.

**Operational consequences:**

- Every recommendation carries a **"what would change my mind"** appendix — the specific evidence or threshold that would flip the call.
- Confidence is a distribution, not a number. Briefs show the evidence with its uncertainty; the decision is where the user and Midas meet.
- Evidence provenance is unbroken: every number in a brief traces to a row in the fabric, a model version in the registry, or a tool call in the debate transcript.

**Violation test:** if the Debate agent has no tool that _writes_ to a pending decision's weights, the debate is narration on a PDF.

---

## FP-9 [NEW]: DL-Dominant, No Free Lunch

Deep learning is the default for every layer where a choice exists: representation, state inference, returns prediction, volatility/tail modeling, cross-sectional ranking, asset allocation, execution. Classical methods (factor models, MVO, Black-Litterman, HRP, GARCH variants) are **baselines in the challenger lane and explanatory overlays**, never the champion.

No single model dominates across all market conditions. Midas does not pick one — it holds a **pool** at every layer and runs a **model-of-models** that routes, weights, promotes, and demotes based on continuous calibration against outcomes. The system IS the selector.

**Violation test:** if a decision path references one specific model name as "the" choice rather than a pool + router, it is wrong.

---

## FP-10 [NEW]: Latent Over Observable

Observable factors (momentum, value, carry, size, quality, vol) are symptoms, not causes. The drivers of returns and risk are hidden. Midas's core job is to **learn latent drivers from data** through representation learning, and to drive decisions from the latent state, not from the factor residuals.

Econometric factors are kept for two purposes: (a) seeding the search space and regularizing the representation learner, (b) providing a human-readable rosetta stone for the brief. They do not drive the decision.

**Violation test:** if the allocator's dominant input is a factor exposure vector rather than a learned latent state, the architecture is upside-down.

---

## FP-11 [NEW]: Continuous State, No Regime Labels

Regimes are not buckets. The model emits a **posterior distribution over a continuous learned latent state** `z_t`. "Bull / Bear / Sideways / Calm / Elevated / Urgent / Crisis" are rendering projections computed by the UI from `z_t`, not classifications produced by the model.

The model never emits a regime label. The UI derives a visualization from the continuous state. Transition detection is a continuous-time change-point posterior, not a discrete flip event.

**Violation test:** if any model output is a string label naming a regime, the model is wrong. Regime labels live only in the rendering layer.

---

## FP-12 [NEW]: Frontier LLMs for Decision-Adjacent Work

Opportunity cost of a misframed investment decision dwarfs every API call Midas will ever make. Frontier language models (Opus-class, GPT-5-class, or whatever sits at the frontier when a decision is made) are the default for:

- Analyst brief generation
- Debate agent (argument, counter-argument, tool invocation, optimizer re-runs)
- Research Assistant RAG synthesis
- Latent-state-to-factor-language projection in briefs
- Any path where the user reads the output and acts on it

Cheaper models are permitted only for bulk background work (log summarization, audit rollups, embedding generation where a domain encoder matches the frontier). Cost budget flows to opportunity-cost-weighted calls.

**Violation test:** if a decision-adjacent call is routed to a non-frontier model to save API spend, the cost model is wrong.

---

## FP-13 [NEW]: Attention Is Sacred

The user has finite attention and infinite other demands on it. Every pixel, notification, and brief is evaluated against: _does spending this attention here earn the user more than it costs them?_ UX decisions are attention decisions. Progressive disclosure is tied to dollars-at-stake. A routine approval never looks like an Urgent approval even if the UI has bandwidth to show both.

**Operational consequences:**

- A daily **attention budget** tracks how many decision-seconds the user has spent and alerts when the pattern signals fatigue.
- A brief for a $500 rebalance and a brief for a $50K tactical shift do not share a template.
- Notifications are tiered by regime posterior, not by category. Silent in Calm, structured push in Elevated, haptic + sound in Urgent, emergency banner in Crisis.
- The UX team works with AI UX specialists on adaptive density; information density is a function of decision weight, not surface bandwidth.

**Violation test:** if the UI shows the same density for a $500 trim and a $50K tactical shift, attention is being wasted.

---

## FP-14 [NEW]: Track Record Earns Latitude

Midas's autonomy is not a setting; it is a currency **earned through demonstrated performance**, measured by Brinson attribution (allocation effect + selection effect), model calibration, and user override convergence. Autonomy upgrades are proposed by the system when a threshold is met, approved by the user in the Decisions surface, and never silently promoted. Downgrades are automatic when a degradation contract trips.

**Operational consequences:**

- Every decision is scored after the fact against its counterfactual.
- Calibration curves per model head are tracked and surfaced when the user asks why a recommendation has the confidence it has.
- Autonomy upgrades are one of the decision types that appear in the Decisions surface; the user sees the evidence (track record + calibration + attribution) and approves or declines.

**Violation test:** if an autonomy level can be silently increased by the system without the user seeing the evidence in a Decisions surface event, the track-record contract is broken.

---

## Application

Every plan, spec, implementation decision, and user flow is checked against these principles. Contradictions are either justified explicitly in writing or the plan is wrong. No implicit overrides. Review happens at `/redteam` and again at `/codify`.
