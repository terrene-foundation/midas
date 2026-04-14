# Moments of Truth

**Status:** GOVERNING. The UX rules on this page cannot be broken. These are the flows where a bad UX decision costs real money, real trust, or both.

---

## 1. Why This Spec Exists Separately

Most UX decisions are tradeoffs. The decisions in this spec are not tradeoffs — they are guardrails. Breaking one of these rules is a bug in a category above aesthetic disagreement.

The list is deliberately short. Anything added here has to earn its place with evidence that breaking it causes real harm.

---

## 2. The Approval Tap

**Context:** the user is about to approve a trade. Could be $500, could be $50K. The tap commits money.

### 2.1 The Rule

Approve and Reject **must be spatially separated** and Approve **must be biometric-gated**.

### 2.2 What "Spatially Separated" Means

On mobile, the Approve button and the Reject button are never adjacent on the same horizontal row. They are on different rows, or one is a primary action at the top and the other is a secondary action at the bottom. Thumb-reach for Approve requires deliberate movement, not a slip.

On web, similar — never side-by-side with matching prominence. The Reject action is smaller and offset.

### 2.3 What "Biometric-Gated" Means

On mobile, Approve triggers Face ID or fingerprint before the order is submitted. The biometric is not a formality — it is the real authorization gate. The UI makes clear that the biometric is the moment of commitment.

On web, the equivalent is a password-protected confirmation step (a re-auth challenge) for any approval in Urgent/Crisis bands or above a dollar threshold.

### 2.4 Why

A $133K thumb-slip is unrecoverable. The spatial separation and the biometric are the two compounding defenses. Neither alone is sufficient.

### 2.5 What The Rule Does Not Prevent

- Wrong decisions that were deliberate (the user chose to approve a bad trade consciously) — no UX rule can prevent this, and Debate + brief quality are the defense
- Approval-without-reading-the-brief — the attention budget tracks this as a fatigue signal (`09-`)
- Malicious access to the device — device security is the user's responsibility

---

## 3. The Paper→Live Transition

**Context:** the user is about to enable live trading after paper trading.

### 3.1 The Rule

- The transition is **explicit user action** only — never automatic, never a default, never "continue" in a wizard
- Minimum 2-week paper period is enforced at the **Pre-Trade Compliance Agent**, not just in the UI
- The user **must** have opened the paper-trading report
- The transition requires biometric
- No affordance in the UI labeled "skip paper trading", ever

### 3.2 Why

Paper trading is the only chance to discover that a subsystem is broken without financial consequence. Skipping it makes the entire validation layer a lie. This rule is derived directly from FP-7.

### 3.3 First Seven Live Days

Even after a clean paper report and an explicit Go Live, the first seven live days run at autonomy L1 (Co-Pilot, every decision user-approved) regardless of what L2/L3 would otherwise propose. Track record has to exist in live data before higher autonomy is proposable. This is enforced by the autonomy module (`08-`), not a UX convention.

---

## 4. The Debate Non-Sycophancy Rule

**Context:** the Debate agent must disagree with the user when data supports the disagreement.

### 4.1 The Rule

A Debate agent that always concedes to the user is worse than no Debate. The agent must:

- Disagree when evidence warrants
- Present counter-evidence with specific data
- Decline to confabulate justifications for user-proposed actions the model cannot support
- Honestly surface calibration weakness when it exists
- Refuse to generate a rationale for an action that contradicts its own recommendation unless the user explicitly asked to proceed anyway

### 4.2 Why

The failure mode the rule prevents is the user's "fake confidence" fear (see `01-user-persona.md` §5.3). An agent that agrees with everything the user says is indistinguishable from a hallucinator. The user loses the ability to trust their own trust signals — this is the toxic failure mode that makes every other feature worthless.

### 4.3 Enforcement

- Frontier LLMs only (FP-12) — cheaper models are too easily nudged into sycophancy
- System prompt includes an explicit "disagree when evidence warrants; do not confabulate" directive
- Calibration is always quotable — the agent can always back up its position with data
- Every claim carries a provenance pointer (FP-8)
- Override-outcome tracking surfaces when the user overrides a correct recommendation; the agent can reference this directly in future debates without being accusatory (it is a data point, not a rebuke)

### 4.4 The Other Half Of The Rule

The agent also **must concede** when the user makes a stronger case. A stubborn agent is as bad as a sycophantic one. The agent's job is to reach the right answer, not to preserve its prior.

---

## 5. The Kill Switch / Crisis State

**Context:** the user has tripped the kill switch, or the system has auto-tripped it.

### 5.1 The Rule

- The kill-switch state is **unmissable** — the user sees "trading paused" before any number on the screen
- All non-essential surfaces are demoted
- The kill-switch clear affordance is visible and requires biometric + deliberate action
- Auto-trip adds a cool-down before the clear is allowed
- No decision executes while the switch is active — period, regardless of autonomy level

### 5.2 Why

The kill switch is the last line of defense. If it can be missed, bypassed, or ignored, it is not a kill switch. Crisis states are where calm UI decisions matter most and where the user's attention is most impaired.

### 5.3 What Must Not Happen

- Kill-switch state buried in a menu or a modal
- Decisions that execute because "the user authorized them before the switch was tripped" — pending orders are cancelled on trip
- Automatic clearing ever
- "Undo" affordance on the trip — the user trips on purpose; there is no accidental trip
- Silent clearing on any condition

---

## 6. The Urgent Window (Decision Under Time Pressure)

**Context:** the user has a pending decision in the Urgent band with a time-to-decide window.

### 6.1 The Rule

- Window is shown as a **progress bar**, not a countdown timer
- Decision window expiry behavior is pre-configured by the user in Settings (hold / execute per-decision default)
- Window expiry writes an audit record with "expired — default applied" tag
- Window may not be shortened silently — if the model's confidence changes mid-window, a new notification can fire but the original window is preserved

### 6.2 Why

Countdown timers create panic. Progress bars communicate the same information (how much time is left) without triggering the stress response that impairs decision quality. Under time pressure the user needs to read the brief, weigh the evidence, and decide — a pulsing timer pushes them toward approving without reading.

### 6.3 The Deeper Rule

No Midas interaction is ever designed to increase the user's stress level. Urgency is communicated through structured visual changes (layout reshape, approval queue promotion) and notification tiers — not through time-pressure theatre.

### 6.4 Quote-Moved-Since-Brief + Partial-Fill-During-Approval (Redteam Trader H-4)

**Context:** the user's biometric approval arrives after the quote has moved, or after a partial fill has accumulated on a parent order that should not have started working until approval landed.

**Rules:**

- A decision that requires user approval under the current autonomy level MUST NOT begin working any orders until the user confirms. The `autonomy.level_breach` + `escalate.urgent_band` compliance rules gate **submission**, not just proposal.
- Every approval screen carries the quote snapshot captured at brief-composition time. At the moment of biometric confirmation, a fresh quote is pulled (`exec.freshness_at_execution`). If the mid price has moved since the brief by more than the regime-adaptive threshold (Calm 0.5%, Elevated 0.3%, Urgent 0.2%), the approval **does not auto-execute** — the UI surfaces "Price moved X% since brief. Proceed at current price, set a limit, or cancel?" and the user confirms explicitly.
- If during the approval window the market move invalidates the brief's thesis materially (e.g. the "If rejected" case materializes before the user taps), the decision is auto-revised with "Since proposing this, [thing] happened. Here is the updated proposal." No auto-execution of stale proposals.

Full protocol and edge cases in `specs/14-ibkr-integration.md §8`.

---

## 7. The Envelope Change

**Context:** the user is changing the trust boundary — widening drawdown tolerance, loosening concentration, adding universe exclusions, etc.

### 7.1 The Rule

- Envelope changes are always user-facing decisions with their own brief
- The brief shows the impact: simulated performance under the new envelope, simulated risk, which current positions would be affected
- Changes that **widen** the envelope require biometric
- Changes that **tighten** the envelope take effect on the next decision cycle with notification
- Midas may not propose envelope widening — only tightening

### 7.2 Why

The envelope is the trust boundary. It is the user's promise to themselves about how much risk they are willing to accept. Widening it should feel like a deliberate commitment, and the system should not nudge the user toward it.

---

## 8. The OOD Escalation

**Context:** `z_t` has moved to a region the pool has not been calibrated on. This is a failure mode the user is directly afraid of (§5.4 of `01-user-persona.md` — "regime blindness").

### 8.1 The Rule

- Out-of-distribution `z_t` detection escalates to Crisis band **regardless** of VIX, spreads, or drawdown
- All autonomy levels temporarily revert to L1 until the pool recalibrates
- The brief for any decision in this state carries an explicit **honesty banner**: _"The current state is far from where I have been calibrated. My confidence is thinner here."_
- No decision is executed without user approval, even routine rebalances

### 8.2 Why

The user's worst fear is a system that behaves confidently in a regime it has never seen. The explicit OOD escalation is the architectural answer. Better to pause and defer than to confidently execute in a state the model does not understand.

---

## 9. Enforcement Philosophy

The rules in this spec are enforced at multiple layers:

| Layer                      | Role                                                                                                              |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| UI / visual design         | First line — spatial separation, progress bars, honesty banners                                                   |
| UX interaction design      | Second — biometric gates, confirmation steps, focus mode                                                          |
| Pre-Trade Compliance Agent | Third — enforces the rules that involve trading behavior (paper→live gate, kill switch, envelope, OOD escalation) |
| Audit log                  | Forensic — every rule trigger writes a record so violations are discoverable after the fact                       |

Rules are never enforced only in the UI. If a rule exists here, it has a backend enforcement layer. The UI is the polite version; compliance is the legal one.

---

## 10. Relationship To Other Specs

- `07-evidence-first-decision.md` — Debate non-sycophancy is anchored to the brief contract
- `08-autonomy-and-trust.md` — paper→live, kill switch, envelope, first-seven-days
- `09-surfaces-and-attention.md` — approval tap spatial separation, Urgent progress-bar, notification tiers
- `11-compliance-and-risk.md` — backend enforcement of all trading-relevant rules here
