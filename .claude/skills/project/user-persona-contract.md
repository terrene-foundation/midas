# User Persona Contract

The product contract for Midas's user. Every surface, brief, notification, and decision flow must satisfy this contract.

**Specs authority:** `specs/01-user-persona.md` (governing), `specs/08-autonomy-and-trust.md` (trust boundary)

---

## The User

Singapore-domiciled self-directed investor with their own capital on IBKR. Sophisticated enough to run their own portfolio desk, but tired of being the only person in the room.

| Dimension       | Value                                                |
| --------------- | ---------------------------------------------------- |
| Capital source  | Their own — no fiduciary relationship                |
| Portfolio size  | $100K–$500K                                          |
| Time budget     | <30s calm day, <2min turbulent day, unbounded crisis |
| Decision device | Mobile (iOS/Android)                                 |
| Analysis device | Web desktop (min 1024px)                             |
| Motivation      | Autonomy; disciplined system beats panicked human    |

---

## Job-To-Be-Done

> **"Run my own institutional-grade portfolio desk without it running my life."**

Both halves must be satisfied: institutional-grade execution AND bounded attention cost. One half alone fails.

---

## 6 Non-Delegable Decisions (Trust Boundary)

These never move to Midas regardless of autonomy level:

1. **Risk envelope** — drawdown ceiling, vol target, concentration cap, universe exclusions
2. **Paper → live transition** — explicit human action + biometric + clean paper report
3. **Autonomy level promotion** — user sees evidence, approves in Decisions surface
4. **Turbulent-regime approvals** — Elevated/Urgent/Crisis proposals reviewed before execution
5. **Kill switch** — instantly halts all trading; recovery requires biometric + deliberate action
6. **Model promotion** — champion/challenger promotion requires user review of shadow P&L

---

## 4 Failure Modes (Guard Every Design Decision)

### Silent Betrayal

Midas executes something dumb while user is offline. First they hear is a loss.

**Guardrails:** PACT envelope enforced pre-trade; stale-data gate is hard; kill switch always one tap; every autonomous action writes full brief to Decisions history.

### Being The Bottleneck

Notifications pile up, system stalls waiting for user. Attention cost exceeds alpha captured.

**Guardrails:** Attention budget tracks decision-seconds/day; routine approvals batch into digests; Urgent/Crisis have hard time-to-decide budgets.

### Fake Confidence

Briefs sound authoritative but Debate agent can't defend reasoning when challenged.

**Guardrails:** Every claim traces to fabric row or model version or tool call; Debate can re-run optimizer and modify pending decisions; "what would change my mind" appendix is mandatory.

### Regime Blindness

System works in seen regimes, fails silently in unprecedented ones.

**Guardrails:** Continuous state — no pre-defined label needed; unfamiliar z_t shows low confidence and escalates automatically; adversarial backtesting on synthetic tails.

---

## Time Budget Contract

Violations are design bugs, not hopeful targets.

| Regime   | Time to "close the app"    | Time to act on pending decision                              |
| -------- | -------------------------- | ------------------------------------------------------------ |
| Calm     | ≤ 30 seconds               | n/a (no decision pending is the norm)                        |
| Elevated | ≤ 60 seconds               | ≤ 2 minutes per decision                                     |
| Urgent   | ≤ 30 seconds to see status | ≤ 2 minutes, hard window enforced                            |
| Crisis   | Unbounded (user engaged)   | Immediate for kill switch / envelope; other decisions paused |

---

## What The User Is Not

- Not a day trader (intraday tools out of scope)
- Not a novice (no hand-holding explanations)
- Not managing other people's money (no fiduciary layer, no KYC of third parties)
- Not on a US tax framework (no tax-loss harvesting, no lot-level cost basis)
- Not asking for an academic paper (interpretability earned, not presumed)

---

## 3 Evaluation Questions (Every Feature Must Answer)

1. Which of the user's owned decisions does this serve?
2. Which failure modes does this make more or less likely?
3. Does this respect the time budget in the relevant regime state?

If a proposed feature cannot answer all three, it is wrong, misnamed, or belongs in a later version.
