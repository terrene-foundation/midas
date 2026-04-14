# Round 1 Red Team — Senior Portfolio Manager Perspective

**Reviewer:** Senior PM, 25 years multi-asset, persona adopted for this round
**Scope:** `specs/_index.md`, `00-first-principles.md`, `01-user-persona.md`, `02-value-chain.md`, `07-evidence-first-decision.md`, `08-autonomy-and-trust.md`, `09-surfaces-and-attention.md`, `10-moments-of-truth.md`, `12-performance-and-track-record.md`
**Date:** 2026-04-14

---

## Framing

I have read this spec set the way I would read a prospectus for a new mandate — asking whether a real person managing real money could operate inside it and come out ahead of the benchmark on both P&L and process quality. The architecture is unusually coherent for Round 1. The failure modes below are **not** "nice to have" polish — they are the places where the spec will quietly defeat the user during the one week of the year when it matters most.

Three cross-cutting concerns run through all the findings:

1. **The spec optimizes for the wrong equilibrium.** It describes what a disciplined user with infinite patience would do. The persona in §1 is described accurately (tired, 30-second calm budget, mobile-first), but the decision surfaces still assume that user reads a seven-section brief carefully. They will not. That is the whole point of FP-13.
2. **Attribution is being asked to carry more weight than it can.** Brinson is a decomposition, not a causal story. Using 3-month Brinson as the gate for L2→L3 promotion is noise-driven with high probability for a weeks-to-months strategy. This is the "mathematically precise nonsense" trap.
3. **The envelope is treated as a hard contract, but the widening path is soft.** A user in a drawdown will widen their envelope. The spec says "biometric required" as if that were a friction. It is not. It is two seconds.

---

## CRITICAL

### C-1 — 3-month Brinson windows are statistically insufficient to gate L2→L3 promotion

**File:** `specs/12-performance-and-track-record.md` §3.4, §6.1; `specs/08-autonomy-and-trust.md` §7
**Severity:** CRITICAL

**Description:**
§3.4 explicitly names 3-month rolling as the "promotion contract window" and §6.1 lists "Brinson allocation effect (3-month rolling)" as the **primary** component for L2/L3 upgrades. §8 (08-) confirms: "M routine rebalances executed cleanly + positive Brinson allocation effect over the window."

For a strategy rebalancing weekly-to-monthly with a weeks-to-months horizon, 3-month Brinson contains ~12 weekly observations. Standard error on an allocation effect from 12 observations is enormous — the t-statistic required to reject "noise" at 95% is roughly ±1.5% allocation effect per quarter on a ~12% equity vol portfolio. Most of the time the number is inside the noise band and the system is promoting (or refusing to promote) based on a random draw.

This is not a theoretical worry. I have seen quant PMs ship beautiful autonomy contracts that turned into "promote on lucky quarter, demote on unlucky quarter" ratchets. The user rapidly learns the ladder is random and stops trusting it — at which point the whole FP-14 mechanism (track record earns latitude) is dead.

**Why it matters:**

- FP-14's violation test is that autonomy is "earned through demonstrated performance." A noise-gated ladder is not earned performance.
- 12 observations of Brinson allocation effect cannot distinguish a 30-bps-per-quarter skill signal from zero skill at conventional power levels. The spec promotes authority on a statistic that cannot support the decision.
- The user will see L2→L3 promotions and L3→L2 demotions ping-pong in correlated market states (a bad quarter demotes, the next quarter recovers, promotion proposed again) — attribution ping-pong is the mechanism by which institutional risk committees lose faith in quant models. Reproducing it in single-user form is worse, because there is no committee to steady the user.

**Concrete fix:**

1. Make the primary promotion window **12-month rolling**, not 3-month. The 3-month window becomes a _veto_ input (bad 3-month blocks promotion) but not a _trigger_.
2. Require the Brinson allocation effect to be **statistically distinguishable from zero** using a t-stat or bootstrap confidence interval computed from the NAV time series, not a point estimate. State the threshold explicitly — e.g., "t > 1.3 on 12-month Brinson, OR 12-month allocation effect > 100bps AND 3-month not negative."
3. Require **pool consistency**: allocation effect positive in at least 8 of 12 trailing months, not just the aggregate. An aggregate is satisfied by one lucky month.
4. Add a **minimum-activity gate**: the user's envelope must have produced at least K rebalances that actually tilted away from SAA-static in the window. Otherwise there is nothing for "allocation effect" to even measure.
5. Document in §6.1 that the track record score uses **statistical significance**, not point estimates, so the promotion contract cannot be gamed by lucky short-window draws.

Without this, FP-14 is aspirational. The ladder promotes on noise and the user learns to ignore it.

---

### C-2 — Envelope-widening has no cooldown, no drawdown lockout, and Midas has no opinion on it

**File:** `specs/10-moments-of-truth.md` §7; `specs/08-autonomy-and-trust.md` §1
**Severity:** CRITICAL

**Description:**
§7 of 10- is the envelope-change flow. The rule set is: biometric required to widen; Midas "may not propose envelope widening — only tightening." That is the entire defense.

A 25-year PM knows the exact failure mode this omits: **the user in drawdown who widens the envelope to avoid forced selling**. This is the oldest unforced error in single-account management. The drawdown tightens the envelope internally (hard limits start biting), the PM widens the envelope to buy breathing room, the drawdown deepens, the PM widens again. I have seen this kill good shops.

The spec as written makes this trivially easy:

- A $50K thumb-tap through Face ID is not friction. The friction is psychological, and the user in drawdown is the user whose psychology is least equipped to apply it.
- There is no cooldown. The user can widen, then widen again 30 seconds later.
- There is no "you are in drawdown, envelope widening requires a 24-hour delay" gate.
- Midas is explicitly forbidden from proposing widening — but it is NOT required to actively warn against it, or to refuse to execute immediately after a widening.
- The Debate agent can `query_calibration` and `propose_alternative_allocation` but has no documented responsibility to **push back** on an envelope widening under adverse conditions.

**Why it matters:**

- This is the single most common failure mode of sophisticated single-user systems. The spec currently provides zero structural defense against it.
- The biometric gate is the only friction, and a trained thumb in a panic state clears it in under 2 seconds.
- The user persona (§5.1 "silent betrayal") lists "executing while the user is asleep" but misses the mirror failure: "the user tells it to execute something they will regret in two days, and the system complies because the biometric cleared."
- FP-14's "track record earns latitude" is meaningless if the user can simply widen the envelope and pre-empt the ladder entirely.

**Concrete fix:**

1. Add a **drawdown-conditional widening lockout**. If the portfolio is within X% of the envelope drawdown ceiling (e.g., 70% of max allowed drawdown consumed), envelope widening is blocked with a typed message: "Widening the envelope while in drawdown is blocked for 24 hours. This is a hard rule. You can tighten, or you can tap 'Initiate Cooling-Off' which schedules the widening for consideration after 24 hours."
2. Add a **cooldown on all envelope widenings**: minimum 24 hours between any two widening actions, and minimum 72 hours from any drawdown event greater than Y.
3. Require the **Debate agent to push back** on envelope widening under adverse conditions, with the pushback being a _required step in the flow_, not an optional Debate the user may open. The brief shows: "Widening this now has historically preceded a further X% drawdown in Z analogues. Are you acting because the evidence has changed, or because the pain has?"
4. Require the **widening to name its trigger** — the user must type (or select from a list) the reason. "I was wrong about my risk tolerance" vs "markets have changed" vs "I need the cash." This is a nudge, but a functioning one.
5. Midas MAY (and should) propose **envelope widening** when evidence warrants it — specifically when the drawdown is low, the envelope has been binding for an extended period, and the user's override patterns suggest the envelope is tighter than their actual risk tolerance. The current blanket prohibition is backwards: the dangerous widening is the panic widening; the safe widening is the "you have been earning for 18 months, you can handle more" widening, which Midas is currently forbidden from surfacing.
6. Add an explicit audit trail: widening actions taken within 30 days of a drawdown must be flagged in the monthly statement and in the Debate agent's priors.

This is the single most important fix in the whole review. Without it, the envelope is theater.

---

### C-3 — The seven-section brief contract is incompatible with the 30-second Calm budget

**File:** `specs/07-evidence-first-decision.md` §2; `specs/01-user-persona.md` §6; `specs/09-surfaces-and-attention.md` §4
**Severity:** CRITICAL

**Description:**
§2 of 07- specifies seven mandatory brief sections: Thesis, Evidence, If Approved, If Rejected, Historical Precedent, What Would Change My Mind, Confidence. Each section is specified as rigorous (evidence has provenance pointers, historical precedent has K analogues, confidence is a posterior with width).

§6 of 01- says the user has **30 seconds on a calm day, 2 minutes on a turbulent day**, and the primary decision device is mobile.

§4 of 09- attempts to resolve this with a "brief density matrix" — compressed for low-weight decisions, full for high-weight. **This does not actually solve the problem**, it describes it.

The problem is: the user reads the compressed brief on Calm days and learns a habit. When the Urgent day comes — the day when reading the full brief would save them a $50K mistake — they have not been practicing. The compressed-brief habit has trained them to approve with one scan. The "full structured + pinned summary card" shown on Urgent days is presented to a user whose default approach is "scan thesis, check dollar impact, tap approve." The user does not magically become a careful reader because the layout changed.

This is a well-known failure mode: **the attention budget does not solve the attention problem, it describes it.** The spec treats the budget as a monitoring surface ("flag fatigue") when it should be treated as a _design constraint_ that reshapes every flow.

**Why it matters:**

- The user fails exactly where the spec says they will be served: Urgent decisions under time pressure.
- The Debate surface is the defense against fake confidence, but the user in a 2-minute window doesn't open Debate. They tap approve.
- The "what would change my mind" section is brilliant in principle but it sits in position 6 of 7 — most users will never read it.
- A PM reading this spec would recognize the pattern: the brief is designed to demonstrate the system's rigor to the _spec reviewer_, not to be used by the operator.

**Concrete fix:**

1. Invert the brief hierarchy. The **"what would change my mind"** section is the _first_ thing the user sees, not the last. If the one thing the user reads is the kill-criterion, they have made a better decision than if the one thing they read is the thesis.
2. Add a **"decide in 10 seconds" card** at the top of every brief — regardless of density tier — with exactly three elements: (a) the one-line action, (b) the one specific counter-evidence that would flip the call, (c) a "Debate" button and an "Approve (biometric)" button that are spatially separated per §2 of 10-. Everything else is below the fold, tap to expand. This is not the compressed template; this is the universal top card on _every_ brief.
3. Audit the brief templates for **top-of-fold coverage**. The user with a 30-second budget must be able to act correctly from the top-of-fold alone, and the spec must enforce that via the brief composer, not hope for it.
4. Add a **forced-pause mechanism** for high-weight briefs: a 3-second minimum dwell time before the biometric prompt unlocks, with a "read this" emphasis on the counter-evidence card. Yes, this is friction. Friction is the point. The user asked for this when they said "don't let me make dumb decisions in a panic" — the spec is currently not delivering that.
5. Explicit test criterion in the spec: **the user must be able to correctly decline a bad recommendation by reading only the top card** on a sample set of backtested bad recommendations. This is a measurable usability gate, not an aesthetic preference.
6. Remove "tap-to-expand for full evidence" from the compressed template as the _only_ full-view affordance. Replace with a sticky "Debate" button that surfaces one-specific-concern prompts ("Why this allocation?", "Why now?", "What if I'm wrong about X?"). The user needs a conversation, not a document.

The spec as written builds a beautiful evidence product that its target user will not read. That is worse than a mediocre brief because it provides false assurance that rigor has been performed.

---

### C-4 — The kill-switch 15-minute cooldown is backwards

**File:** `specs/08-autonomy-and-trust.md` §5.4; `specs/10-moments-of-truth.md` §5
**Severity:** CRITICAL

**Description:**
§5.4 of 08-: "Cannot be cleared in the same session as it was tripped if tripped due to an automated circuit breaker — adds a 15-minute cool-down." §5 of 10- says "auto-trip adds a cool-down before the clear is allowed" and "no accidental trip."

Think about what this means in practice. The kill switch trips automatically because the drawdown crossed a circuit breaker. The user sees "TRADING PAUSED." They want to override. The cooldown is 15 minutes.

**Scenario A:** The user is right. They have correctly read a genuine panic and want to get back to market-making. The 15-minute delay costs them the opportunity.

**Scenario B:** The user is wrong. They are panicking and want to clear the switch to do something dumb. The 15-minute delay gives them time to calm down.

The spec optimizes for Scenario B. That's correct for panic selling into a crash — except the kill switch was tripped by a drawdown circuit breaker, which means the crash has _already happened_. The user is not panicking to sell; they are panicking to **buy the dip** or to **intervene in a system they no longer trust**. The 15-minute delay is the exact window in which the user forms a plan ("I'll just move this to cash, recover, re-engage") and then executes it the moment the clock allows. The cooldown does not protect the user from their worst self; it **times** their worst self.

Worse: the 15-minute value is stated without justification. Why 15 and not 30 or 60? There is no model. This is the tell-tale sign of a spec that has not thought through the moment-of-truth it is specifying.

**Why it matters:**

- A kill switch that delays recovery by a fixed interval is a performance tax in the happy case and a trigger-timer in the bad case. Both failure modes hit the same user.
- The "cannot clear in same session" rule is easy to circumvent: end the session, start a new one, clear. The spec has a structural rule it doesn't enforce mechanically.
- The user persona is explicitly "risk-loving but not reckless." The 15-minute cooldown is a tool for a different persona (the novice retail user who panic-sells).

**Concrete fix:**

1. Replace the fixed 15-minute cooldown with a **structured re-engagement protocol**: (a) user clears the kill switch with biometric, (b) system re-opens at L1 (Observer — every action requires approval) regardless of prior level, (c) system presents a "state of the world" brief that the user must read before any new action can be approved, (d) the first post-clear decision has a mandatory 60-second dwell on the brief before the biometric unlocks.
2. Explicitly **do not time-lock** the clear. Time locks optimize for the wrong failure mode and cannot distinguish "user is panicking" from "user is correct." The structural fix is process-based, not clock-based.
3. Auto-trip conditions must produce a **brief that names the specific trip reason** and the specific recovery evidence the system wants to see before acting. The user clearing a kill switch without reading the trip reason is the real failure mode, and a 15-minute wait doesn't prevent it.
4. If a cooldown is kept for any reason (e.g. to throttle rapid trip-clear-trip cycles from a user actively sabotaging their own system), the cooldown should be **exponential** (1 min, then 5, then 15, then 60) on repeated trips within a window, not a flat 15 on first trip.
5. Add an explicit test: "can a panicking user do more damage with the kill switch active or cleared?" If the answer is "cleared," the cooldown is wrong; if the answer is "active," the structural defense is wrong. The spec currently doesn't force this question.

This is a spec that thought about _tripping_ the kill switch but not about _clearing_ it. The clear is the riskier half of the operation.

---

## HIGH

### H-1 — 2 weeks of paper trading is operationally insufficient and the spec calls it "validation"

**File:** `specs/00-first-principles.md` FP-7; `specs/08-autonomy-and-trust.md` §6; `specs/10-moments-of-truth.md` §3
**Severity:** HIGH

**Description:**
FP-7 mandates "minimum two weeks of paper trading." §6 of 08- lists the report contract and says the paper period "produces a validation report across every subsystem." §3 of 10- treats paper→live as a moment-of-truth gate.

Two weeks is ~10 operating days. A PM knows what can pass cleanly in 10 days and still miss a dozen production failure modes:

- **No quarterly earnings cycle.** The sector rotation model may never have seen a real earnings-season transition. The single most reliable alpha source in S&P 1500 equities passes through a blind spot.
- **No month-end or quarter-end rebalancing cycles** in the window (or if there is, only one). The spec runs weekly-to-monthly rebalances — the user sees maybe 2-3 rebalances total. That is not a track record, it is three data points.
- **No Fed meeting, or only one.** Fed days are the single largest source of regime transition signal in the reference period. A 2-week window may see zero.
- **No dividend ex-dates of consequence** (depending on timing). FP-6 mentions US dividend withholding — the paper period may never produce a real withholding event.
- **No IBKR weekly maintenance window** (Sunday downtime, Friday settlement quirks) may land inside the 2 weeks.
- **No data-vendor anomaly** (a stale feed, a bad tick, a revised fundamental) may land inside the 2 weeks.
- **No evidence of how the system handles a drawdown**, because a 2-week random sample may see flat or up markets. The calibration for Crisis-band behavior has zero data.

The spec says §6.3 "at least one simulated regime transition the system handled" must be in the report — but "simulated" is doing heavy lifting. A simulated transition is a different animal from a real one. The paper-trading report checks that the subsystem _ran_, not that it _handled_ a real out-of-distribution event.

**Why it matters:**

- FP-7's violation test is that the paper period must be "non-skippable." The spec makes it non-skippable but also makes it too short to catch the failure modes paper trading exists to catch.
- The user goes live with false confidence. The moment-of-truth §3 says "paper trading is the only chance to discover that a subsystem is broken without financial consequence" — if the paper window is too short to exercise the subsystems, the moment of truth is a ritual, not a check.
- The "Go Live" button under FP-7 becomes a rite of passage rather than a release gate.

**Concrete fix:**

1. Keep the 2-week **minimum** but require the paper report to include an **explicit coverage ledger**: which subsystems ran, which rebalance types were exercised, which band states were observed, which calendar events (earnings, FOMC, dividend ex-dates) occurred. The report is blocked if any critical-coverage bucket is empty.
2. Require an **adversarial replay** of at least N historical regime transitions through the paper pipeline _before_ the 2-week paper period begins. The paper period runs on live data; the adversarial replay runs on a curated history of regime transitions, drawdowns, and data anomalies. Both pass gates.
3. Require the paper period to span a **minimum number of rebalance cycles**, not a minimum number of calendar days. "2 weeks OR 3 complete rebalance cycles, whichever is longer."
4. Update FP-7 to acknowledge explicitly that 2 weeks is a **floor, not a sufficient window**, and that the adversarial replay is the real validation substrate. The current spec language suggests 2 weeks of paper = validated, which is not honest.
5. Re-word §10- §3 to remove "paper trading is the only chance to discover that a subsystem is broken." It is _a_ chance, and a partial one at that. The adversarial replay is where the real discovery happens.

---

### H-2 — The "sophisticated self-directed investor" persona is under-stress-tested

**File:** `specs/01-user-persona.md` §1, §7
**Severity:** HIGH

**Description:**
The persona in §1 describes a user who "knows the difference between Sharpe and Sortino, recognizes overfitting smell." §7 says "Not a novice. No hand-holding explanations of what a Sharpe ratio is."

A 25-year PM knows this user profile is **less common than it presents itself**. The stated persona (knows Sharpe vs Sortino, reads backtests, recognizes overfitting smell) describes maybe 5% of self-directed investors with $100K-$500K. The user who _thinks_ they are this persona and actually is not is far more common — they have read Taleb and Poundstone but don't actually know what a VaR backtest looks like. They are the real target of a single-user institutional system because they are exactly the population that will pay for this.

The spec is written for the idealized version. That produces a product that, under stress, leaves the real user without the scaffolding they need. Examples:

- The Debate agent "can always quote calibration" (§4.3 of 10-) — but quoting a 0.78 calibration number to a user who doesn't have an internalized model of what 0.78 means is a comfort blanket, not information.
- The "what would change my mind" appendix assumes the user can read a threshold like "implied vol below X" and do something with it. The real user may not have a mental model for implied vol dynamics at all.
- The brief density matrix (§4 of 09-) compresses briefs for Calm and expands for Crisis. For a stated-sophisticated-but-actually-confused user, both fail: the compressed brief omits the reasoning they need, and the full brief overloads them.
- The overall architecture pushes the user to _own_ decisions (FP-8) while the user may be better served by a product that _also_ has opinions and _also_ defends them. The spec's "assemble evidence, weigh together" framing is more demanding on the user than "here's my recommendation, here's what would change it, push back if you disagree."

**Why it matters:**

- A product built for the idealized persona fails the actual persona silently. The user reports high satisfaction until the market tests them and they blow up.
- FP-8's co-decision protocol is elegant but demanding. It assumes a user who _can_ weigh evidence; the user who _should_ weigh evidence may not know they can't.
- The persona section makes it impossible to design the fallback: the spec says "not a novice, no hand-holding" so the product cannot include the educational scaffolding the real user needs without violating the persona.

**Concrete fix:**

1. Split the persona into **two sub-personas**: "calibrated sophisticated" (the stated one) and "aspirational sophisticated" (the real one). Design decisions that differ between them must be flagged.
2. For the aspirational-sophisticated sub-persona, add an explicit **competence-inference layer**: the system infers from the user's actions (override patterns, time-to-decide, depth of Debate engagement) whether they are actually operating at the stated sophistication level. If not, it adjusts the brief density and the educational scaffolding _without hiding anything_.
3. Allow the brief to surface **educational side-bars** as optional expansions for concepts the user has not interacted with. "What is implied vol?" is a tap-to-expand that only appears if the user has never clicked through an implied vol explanation and is about to act on one. This is not hand-holding; it is one-time scaffolding.
4. Update §7 ("What The User Is Not") to acknowledge the gap between self-identified and actual sophistication, and to commit to _inferring_ sophistication from behavior, not trusting the onboarding questionnaire.
5. Add a **"I'm not sure what this means"** affordance on every brief element. Tapping it doesn't show a textbook — it shows a one-paragraph operational framing ("this is the standard deviation of daily returns; values above X historically precede Y") that the user can act on.
6. Run the Debate agent's anti-sycophancy directive (§4 of 10-) with explicit guidance to **not assume sophistication**. An agent that insists on calibration-talk with a user who doesn't have an internalized calibration model is performing rigor, not providing it.

---

### H-3 — The Debate agent's "concede when user is right" pole is under-specified and will collapse into sycophancy

**File:** `specs/07-evidence-first-decision.md` §3; `specs/10-moments-of-truth.md` §4
**Severity:** HIGH

**Description:**
§4 of 10- has the anti-sycophancy rule. §4.4 ("The Other Half") says "the agent also must concede when the user makes a stronger case. A stubborn agent is as bad as a sycophantic one."

This pair is in tension, and the spec hand-waves the resolution ("the agent's job is to reach the right answer"). In practice:

- An LLM in a multi-turn debate has no ground truth for "the user is right." The model will converge to the user's prior under pressure because that is what frontier LLMs do in long conversations. The sycophancy arc is well-documented in the literature.
- The "disagree when evidence warrants; do not confabulate" system prompt is a standard technique and it has standard failure modes: the model disagrees once, the user pushes back, the model finds a new frame in which the user is right, and concedes. Over 10 turns, the user has trained the model to tell them what they want to hear.
- The override-outcome tracking (§4.3 of 10-) is the theoretical defense — the agent can say "you overrode three similar and lost X." But this only fires after the fact; it does not prevent the model from folding mid-debate.
- The spec does not specify the **evidentiary standard** the user must meet to flip the recommendation. "Stronger case" is not a measurable threshold. The frontier LLM will decide what counts as stronger, and under social pressure will find that the user's case is stronger more often than it actually is.

A PM has seen this pattern fail in "AI investment committee" products repeatedly. The agent starts strong, the user learns which arguments cause concession, the agent learns the user's preferred frames, and within a month the "debate" is the user rationalizing their priors with LLM assistance.

**Why it matters:**

- The whole fake-confidence defense (user persona §5.3) depends on the Debate agent being a meaningful counterparty. A sycophantic debate surface is _more toxic_ than no debate surface because it produces the **feeling** of rigor without the substance.
- FP-12's "frontier LLMs only" is a necessary condition for non-sycophancy but not a sufficient one. Frontier LLMs are _still_ prone to long-context sycophancy.
- The evidence-first co-decision model (FP-8) depends on the agent being able to hold its ground. If it cannot, the "co-decision" is the user deciding with an agreement-generator.

**Concrete fix:**

1. Specify an **evidentiary threshold** for Debate agent concession. "Concede" is not a natural-language decision for the model — it is a decision the model must justify with a tool call. E.g., the agent can only mutate a pending decision via `update_decision` if it can produce an updated evidence tuple (new fabric query, new head invocation, new precedent) that supports the mutation. Without a new evidence input, the user's rhetoric alone cannot move the recommendation.
2. Add a **concession audit**: every time the Debate agent concedes in a thread, the concession is logged with the specific evidence input that caused the flip. If the aggregate pattern shows concessions occurring without new evidence ("concession without evidence" count), the monthly statement flags it and the agent's system prompt is re-tightened.
3. Split the Debate agent into two roles: a **steelman** role (defends the current recommendation), and a **red team** role (argues the counter-position). The user argues with the steelman; the steelman argues with the red team internally. This is operationally a multi-agent pattern. The owner has pointed at it obliquely via "Debate tools include counterfactuals" but the spec doesn't commit to the structural separation.
4. Add a **disagreement floor** in the Debate metric: in any window, the agent must disagree with the user some fraction of the time, or a flag fires. This is counter-intuitive — "we measure how often the agent disagrees" — but it is the only structural defense against the model drifting toward agreement.
5. Periodically **replay** past debates against an independent frontier LLM that has not been in the thread. If the replay agent reaches a different conclusion, flag the original thread as a potential sycophancy incident.
6. State explicitly in §4 of 10-: **the user cannot flip a recommendation via Debate alone** — they must either present new evidence the agent can verify, or execute the override manually through the Decisions surface with the override-outcome tracker active. Debate is for _exploring_, not for _forcing a flip_.

Without these, the non-sycophancy rule is a system-prompt wish.

---

### H-4 — "Midas may not propose envelope widening" contradicts FP-14 and misdiagnoses the failure mode

**File:** `specs/10-moments-of-truth.md` §7.1
**Severity:** HIGH

**Description:**
§7.1: "Midas may not propose envelope widening — only tightening."

This rule is well-intended and wrong. The failure mode it thinks it prevents (the system nudging the user to widen risk to juice returns) is real but rare. The failure mode it _actually causes_:

- The user's envelope starts at a conservative default during install.
- The user earns a track record over 18 months. The envelope should widen to match their demonstrated capacity.
- FP-14 says "track record earns latitude" — but the rule forbids Midas from ever proposing the latitude.
- The user must think of it themselves. They won't. They will operate inside a too-tight envelope, underperform their actual risk tolerance, and blame the system.

More importantly, the rule forecloses the **legitimate widening** (evidence-based, post-track-record, non-panic) while doing nothing to prevent the **dangerous widening** (panic-mode, in drawdown, user-initiated). See C-2.

**Why it matters:**

- This rule pushes the product toward under-utilization of user risk capacity, which is the quiet long-term failure mode that kills single-user quant systems (the user eventually concludes "I would be doing better managing this myself with more size").
- It contradicts FP-14. FP-14 says the system earns latitude; this rule says the system cannot propose earned latitude to the user.
- It encodes the wrong mental model: it treats widening as always suspect, when in fact the danger is _context-dependent_.

**Concrete fix:**

1. Midas **may propose envelope widening** under specific, auditable conditions: (a) 12-month track record score above threshold, (b) no drawdown event in the last 90 days, (c) user's override pattern indicates the current envelope is binding, (d) paper-simulated wider envelope has outperformed in out-of-sample windows.
2. Widening proposals are **decisions** in the Decisions surface (per FP-14's spirit) — the user sees the evidence, approves or declines.
3. Widening proposals are **blocked** by the drawdown-conditional lockout from C-2. The system can only propose a widening when the user is _not_ in a condition to accept it for the wrong reasons.
4. Update §7.1 of 10- to distinguish "Midas proposes a reviewed widening decision to the user" (allowed) from "Midas autonomously widens the envelope" (forbidden forever). The current wording conflates these.

---

### H-5 — "Confidence is a distribution" is a research aesthetic; the user needs a calibrated scalar + a disagreement signal

**File:** `specs/07-evidence-first-decision.md` §2.7, FP-8
**Severity:** HIGH

**Description:**
FP-8 and §2.7 both specify that confidence is a distribution, not a number: "The confidence is a posterior over the recommendation's expected utility, accompanied by the specific factors driving it (narrow posterior on z_t, calibration on this head, precedent strength, pool agreement)."

This is correct Bayesian practice and useless for a 30-second decision. The user under time pressure will:

- Read the posterior width, not know what it means operationally
- Convert it to a mental scalar anyway ("wide = unsure")
- Miss the factor breakdown because it's below the fold
- Act on the mean

A PM who has used prediction markets, analyst consensus, and desk-level model output knows that the operational unit is: **one calibrated probability** + **one disagreement signal** ("the pool is split"). That's two numbers. The full posterior is for the post-mortem, not the decision.

Worse, the brief density matrix in §4 of 09- promises the full posterior for Urgent decisions. That's exactly backwards: Urgent is when the user has the _least_ capacity for a distribution, and the most need for "here is my calibrated bet and here is whether the pool agrees."

**Why it matters:**

- The "fake confidence" defense in §5.3 of 01- depends on confidence being legible. A distribution is illegible under time pressure.
- The spec trains the brief composer to present research-grade output to a user in a decision-making state. This is the single most common product failure mode in quant research platforms: the users of the output are not the producers of it.

**Concrete fix:**

1. The brief's confidence component is **always** a two-number header: "p(recommendation is right in this state): 0.64 (calibration-adjusted). Pool agreement: 3 of 5 heads." The full posterior is below the fold as an optional expansion.
2. Specify that the calibration-adjusted number is the output of a calibration function trained on the head's track record in the current `z_t` neighborhood — not the model's raw softmax.
3. The "posterior width" concept survives as an internal routing signal and as a monthly-statement artifact, but it does not appear in the brief's primary confidence display.
4. FP-8's "confidence is a distribution, not a number" needs a sibling sentence: "...at every layer except the user-facing primary display, which shows a calibration-adjusted scalar and a pool disagreement count. The distribution is always available on expand."
5. Test: sample 10 Urgent-band briefs, ask 3 PMs to make a decision from the top-of-fold alone in under 30 seconds. If they can't produce correct decisions on a backtested evaluation set, the confidence surface is wrong.

---

### H-6 — Brinson decomposition's "interaction" term will confuse the user and the autonomy ladder

**File:** `specs/12-performance-and-track-record.md` §3.1, §6.1
**Severity:** HIGH

**Description:**
§3.1 defines the standard Brinson-Fachler decomposition with Allocation + Selection + Interaction. §6.1 ties L2 promotion to allocation effect and L3 promotion to selection effect.

The interaction term is a known thorn in Brinson attribution. It is:

- Mathematically required for the decomposition to balance
- Operationally meaningless to most users
- Often larger in magnitude than the allocation or selection effect on short windows
- Sign-ambiguous (a manager with good allocation and good selection can have negative interaction if their high-selection buckets happen not to be their high-allocation buckets)

The spec treats interaction as a residual to report. The autonomy ladder treats allocation and selection as clean signals. They are not clean. A quarter with allocation +40 bps, selection +30 bps, interaction -60 bps yields +10 bps total but the spec's reading is "allocation is positive, selection is positive, promote." The reality is that the joint effect was negative.

**Why it matters:**

- The autonomy ladder promotes on components of a decomposition that may not sum to a positive total. That is exactly the "promoted on a lucky draw" failure mode.
- The user reading the attribution dashboard will see allocation, selection, interaction as three bars and not know what to do with them. The spec commits to showing attribution (§4 of 12-) without specifying how the interaction term is framed.
- This is compounded with C-1: short windows already make the decomposition noisy, and the interaction term is the noisiest component.

**Concrete fix:**

1. Make the promotion contract read **net of interaction**: "allocation effect + interaction-allocated-to-allocation > threshold" (using one of the standard interaction-allocation schemes: Karnosky-Singer, Brinson-Hood-Beebower, or geometric Brinson).
2. Pick **one** attribution scheme explicitly in §3 of 12- and commit to it. The standard industry practice for a long-only multi-asset mandate is the Karnosky-Singer currency-inclusive variant (FP-6 makes this relevant — SGD base, USD instruments). If not Karnosky-Singer, name the choice and defend it.
3. Dashboard presentation: show **total excess return** as the headline, with allocation, selection, and the interaction component as second-tier information. The user's primary signal is "did the whole thing work?", not "which component of a three-way decomposition was positive?"
4. Document in §6.1 that the track record score uses net-of-interaction components, not raw components.

---

## MEDIUM

### M-1 — "Under 30 seconds on a calm day" is a time budget, not a feasibility claim

**File:** `specs/01-user-persona.md` §6
**Severity:** MEDIUM

The 30-second calm budget is stated as the contract but has no measurement plan. The spec needs an explicit test: instrument the app to measure time-on-Pulse per session, and commit to the budget being a tracked metric in the monthly statement. Without this, the budget is aspirational. Add to the attention-budget dashboard (§3 of 09-) a specific "calm-day session duration" metric that is compared to the 30-second target. If the target is consistently missed, the spec must re-architect the Pulse layout — not the user's expectations.

### M-2 — Override convergence as a promotion signal is vulnerable to capitulation

**File:** `specs/08-autonomy-and-trust.md` §7; `specs/12-performance-and-track-record.md` §6.1
**Severity:** MEDIUM

"Override convergence" is listed as a positive signal for promotion: a declining override rate means increasing trust. But a declining override rate can also mean the user has _given up_ reading briefs and is tapping approve out of fatigue (the exact fatigue signal tracked in §3.1 of 09-). The spec tracks both but the autonomy ladder reads the wrong direction. Promotion contracts should require: (a) declining override rate, AND (b) no fatigue-signal trip in the window, AND (c) the user's average time-to-decide has _not_ decreased (indicating they are still engaging, not rubber-stamping). Without (c), override convergence is an anti-signal.

### M-3 — "No hardcoded tickers" (FP-2) contradicts the v1 scope of ETF sector rotation

**File:** `specs/00-first-principles.md` FP-2; `specs/02-value-chain.md` §8
**Severity:** MEDIUM

FP-2 says "removing a ticker symbol from code would break the system." §8 of 02- says v1.0 is "ETF sector rotation only." In practice, ETF sector rotation starts with a known list of sector ETFs (XLK, XLF, XLE, etc.) — those tickers have to come from somewhere. FP-2's violation test is too strong. The resolution: the universe _list_ is data (loaded from a config or a universe table), not hardcoded, but the universe _selection criteria_ is code. The spec should reword FP-2 to prevent hardcoded allocations and parameters while allowing the universe to be data-driven.

### M-4 — The "blocked" rationalization list in the compliance agent is not a rule, it is a todo

**File:** `specs/02-value-chain.md` §4.1
**Severity:** MEDIUM

The minimum rule set in §4.1 lists 8 blocking rules. Two of them are "escalates to user," which is not blocking. The spec needs a clear **blocking** vs **escalating** taxonomy: blocking rules stop the trade unconditionally; escalating rules pause the trade pending user approval. The current list mixes them. Also, "model confidence floor" is listed as escalating — what happens when the user is not available to escalate to? Does the trade default-block (correct) or default-execute (wrong)? The spec doesn't say.

### M-5 — "Regime blindness" mitigations in FP-11 and §5.4 of 01- are untested

**File:** `specs/00-first-principles.md` FP-11; `specs/01-user-persona.md` §5.4
**Severity:** MEDIUM

The spec's defense against regime blindness is that the continuous-state posterior will show low confidence in novel states. This is only true if the model is honest about its uncertainty in regions far from training. Deep models are notoriously overconfident out-of-distribution. The spec cites "continuous state rendering" and "synthetic tail augmentation" as guardrails but provides no test. Add: a calibration test suite that perturbs historical states into OOD regions and verifies the model's posterior widens appropriately. Without this, the regime-blindness defense is a hope.

### M-6 — First-7-days L1 lockout is too short

**File:** `specs/10-moments-of-truth.md` §3.3; `specs/08-autonomy-and-trust.md` §6.4
**Severity:** MEDIUM

§3.3: "the first seven live days run at autonomy L1 regardless of paper-trading performance." 7 days is not enough for a weeks-to-months-horizon strategy to demonstrate anything. It should be **at least 4 weeks**, or **until the first complete rebalance cycle has been reviewed and the calibration on that cycle meets a floor** — whichever is longer. The 7-day number appears to be a gesture, not a measured gate.

### M-7 — The "Kailash framework mapping" in §7 of 02- is a shopping list, not a constraint

**File:** `specs/02-value-chain.md` §7
**Severity:** MEDIUM

The mapping is thorough but non-binding: "any component built outside this framework needs a reason." A reason to a future implementer is a 2-sentence justification they can write in 30 seconds. The spec should name specific alternative technologies as BLOCKED ("no custom REST API; must use Nexus") rather than "needs a reason." The current wording permits drift.

---

## LOW

### L-1 — "Horizontal allocation bars (not pie charts)" aesthetic rule is correct but under-motivated

**File:** `specs/09-surfaces-and-attention.md` §9.1, §11
**Severity:** LOW

Pie charts are banned, which is correct (humans are bad at angle comparison). But the spec doesn't say _why_, so a future contributor will see it as a style preference. Add: "pie charts are banned because humans estimate angles poorly. Bar charts are banned for multi-asset comparison because they don't show composition. Horizontal stacked bars show both and are the required default."

### L-2 — The "never cry wolf" rule in §7.3 of 09- needs a threshold

**File:** `specs/09-surfaces-and-attention.md` §7.3
**Severity:** LOW

"Persistent false-urgents trigger a recalibration of `a_t` thresholds." Persistent is not defined. Add: "if 3 of the last 5 Urgent notifications resulted in no user action within the decision window, the `a_t` Urgent threshold is tightened by one step."

### L-3 — "Progress bar not countdown timer" needs a refresh cadence

**File:** `specs/10-moments-of-truth.md` §6.1
**Severity:** LOW

The progress bar is correct but an under-refreshed progress bar (updates every 60 seconds on a 10-minute window) is just a worse countdown timer. Specify: the progress bar updates continuously (sub-second tick) and never re-starts or resets.

### L-4 — "On-demand exports" are CSV + PDF but no spec for the accompanying audit trail

**File:** `specs/12-performance-and-track-record.md` §7.4
**Severity:** LOW

Exports have no spec for the included metadata (run timestamp, data freshness, model versions at export time). Forensic exports should include an exact reproducibility header so the user can cross-check against live data.

### L-5 — The "Kaizen signature" / "Kailash RAG" / "PACT D/T/R" terminology is used without introduction

**File:** `specs/02-value-chain.md` §7; `specs/07-evidence-first-decision.md` §3.3 (Tools table); `specs/09-surfaces-and-attention.md` §10
**Severity:** LOW

These terms are institutional shorthand in the COC rules but the spec is purportedly a standalone domain truth. A PM reviewer who has not read the Kailash rule set cannot evaluate whether the terminology maps to real capabilities. Each first-use should include a one-sentence definition or a pointer to the relevant spec.

---

## Process Observations (Not Findings)

1. The spec set is unusually coherent for Round 1. The failure modes above are structural, not editorial.
2. The governing principles (FP-1 through FP-14) are the strongest part of the spec. The weakest are the places where a principle is asserted without an operational test.
3. The biggest categorical gap is **what the user does under stress**. The spec specifies calm-day and crisis-day states beautifully but treats the transitions as handled. The transition moments are where real money is lost.
4. The second biggest gap is **feedback on whether the mechanisms are actually working**. The attention budget, the calibration tracker, the override-convergence metric — all of these are tracked but none of them has an explicit alarm contract: "if X breaches Y for Z days, the system does what?"

---

## Summary For The Convergence Discussion

The four CRITICAL findings are the convergence blockers:

1. **C-1 (3-month Brinson)** — the autonomy ladder currently ratchets on noise. Fix statistical significance before any other autonomy work.
2. **C-2 (envelope widening in drawdown)** — the single largest unforced-error vector in single-user quant. Fix with lockouts, not biometrics.
3. **C-3 (brief-reading in 30 seconds)** — the attention contract is currently aspirational. Fix with forced top-of-fold coverage and a universal "decide in 10 seconds" card.
4. **C-4 (kill-switch cooldown)** — the clear flow is the riskier half. Fix with structured re-engagement, not clock-based delay.

The six HIGH findings each compound one of the criticals. H-4 is the mirror of C-2 (permit earned widening while blocking panic widening). H-5 and H-6 compound C-1 (the attribution pipeline is noisier than the autonomy ladder assumes).

I would not sign off on a paper→live transition against this spec set as it stands. With the fixes above, I would.
