# User Flow: Turbulent Market Approval

## Trigger

Market regime shifts to Elevated or Urgent. Midas has proposed actions that require human approval.

## Goal

User makes informed approval/rejection decisions quickly, with full context, without panic.

---

## Flow

### Step 1: Notification

**Push notification** (rich, actionable):

```
MIDAS — Approval Needed
Reduce NVDA by 15% ($133K). Volatility spike ahead of earnings.
Confidence: High. Decision window: 4 hours.
[Approve]  [View Details]
```

**If urgent** (e.g., flash crash developing):

- Sound + haptic
- Notification appears as banner even if phone is locked
- Decision window shown prominently

### Step 2: Decision Detail

**User taps "View Details"** — opens Decision screen directly (deep link).

**Screen layout**:

```
REDUCE NVDA POSITION BY 15%
Urgency: Elevated  |  Window: ~4h  |  Cost: $340

THESIS
Implied volatility spiked 40% ahead of earnings.
Historical pattern: NVDA drops 8-12% on vol expansion
in 7 of last 10 instances. Current position is 2x target weight.

IF APPROVED
- Sell 150 shares at ~$890 ($133,500)
- Estimated slippage: $180
- Dividend WHT note: No capital gains tax (Singapore). US WHT: 30% on dividends from this position.
- New NVDA weight: 6.2% (target: 5%)

IF REJECTED
- Position stays at 12.4% (2x target)
- Max estimated drawdown: -$28,000 (18% scenario)
- AI confidence in this call: 72%

COMPARABLE PAST DECISIONS
Oct 2025: Similar setup, executed, avoided -11%
Mar 2025: Similar setup, user rejected, lost -8%

[APPROVE]  [MODIFY]  [REJECT]  [DEBATE]
```

### Step 3a: Approve

**User taps Approve**

- Biometric confirmation (Face ID / fingerprint)
- Confirmation: "NVDA reduction approved. Executing at next opportunity."
- Returns to Pulse — action moves from "Pending" to "Recent Actions"
- Execution status updates: "Pending" → "Submitted" → "Filled at $889.50"

### Step 3b: Modify

**User taps Modify**

- Inline editing appears:
  - "Reduce by: [15%] → [slider: 5-20%]"
  - "Execute: [Now] / [At market open] / [Limit order at $___]"
- AI recalculates consequences in real-time as user adjusts
- User confirms modified version → biometric → execute

### Step 3c: Reject

**User taps Reject**

- Confirmation: "You're keeping NVDA at 12.4%. Midas will continue monitoring."
- Optional: "Why? [Too aggressive / I disagree with the thesis / Bad timing / Other]"
- Feedback recorded — AI tracks this for pattern learning
- Counterfactual tracking begins (what would have happened)

### Step 3d: Debate

**User taps Debate**

- Debate sheet slides up with this decision pre-loaded as context
- AI presents its argument, user challenges
- Debate may result in: approval, modification, rejection, or parameter adjustment
- See User Flow: AI Debate for full debate flow

### Step 4: Multiple Pending Approvals

**When 3+ approvals are pending** (e.g., regime shift triggered portfolio-wide rebalancing):

- Decisions screen shows all pending as cards
- "Batch Review" button at top
- Batch view: summary table of all proposed actions with total cost
- AI flags which actions are "routine rebalancing" vs "exceptional — review individually"
- [Approve All Routine] [Review Each]

### Step 5: Window Expiry

**If user doesn't respond before decision window closes**:

- AI takes its default action (configured in Settings):
  - Conservative default: hold (do nothing)
  - Aggressive default: execute the recommendation
- Push notification: "Decision window closed. Midas [held / executed] as per your default setting."
- Action logged with "expired — default applied" tag

---

## Regime Escalation Path

| Regime   | UI Behavior                         | Notification            | Default Action               |
| -------- | ----------------------------------- | ----------------------- | ---------------------------- |
| Calm     | No approvals needed                 | Silent/weekly           | AI executes autonomously     |
| Elevated | Approvals for large moves           | Standard push           | Configurable                 |
| Urgent   | All non-trivial moves need approval | Prominent push + haptic | Conservative hold            |
| Crisis   | All trading paused                  | Emergency notification  | Full stop, cash preservation |

---

## Edge Cases

- **User is asleep / unreachable**: Default action applies. Morning briefing shows what happened.
- **Multiple rapid regime changes**: Midas batches decisions rather than spamming approvals
- **IBKR API is down**: "Cannot execute. Midas is monitoring and will execute when connection restores." Clear warning on Pulse.
- **User approves but market has moved**: "Price moved 2% since recommendation. Still proceed? [Yes at market / Set limit / Cancel]"
- **Conflicting approvals**: User approves action A which contradicts previously approved action B — Midas warns and asks for clarification

## Success Criteria

- Decision-making time: < 2 minutes for simple approve/reject
- User confidence: "I understood what was happening and why"
- Zero accidental approvals (biometric + spatial separation of buttons)
- Zero missed critical decisions (notification tiers ensure delivery)
