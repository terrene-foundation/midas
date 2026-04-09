# User Flow: AI Debate

## Trigger

User wants to challenge, question, or explore an investment decision through structured conversation with Midas.

## Entry Points

1. **From Decision**: Tap "Debate" on any pending or historical decision
2. **From Portfolio**: Tap any position → "Why is this here?" / "Challenge this"
3. **From Signal/News**: "What does this mean for my portfolio?"
4. **From Debate tab**: Start a new thread with a question
5. **From Backtest**: "What if we tried a different strategy?"

## Goal

User reaches an actionable conclusion — either confirming the AI's approach, modifying it, or adjusting parameters — through evidence-based discussion.

---

## Flow

### Step 1: Context-Loaded Entry

**User enters from Decision #247 (NVDA reduction)**

Debate opens with context pre-loaded:

```
DEBATE: NVDA Position Reduction
Context: Decision #247 — Reduce NVDA by 15%

MIDAS: I recommended reducing NVDA by 15% because implied
volatility spiked 40% ahead of earnings. In 7 of the last
10 similar setups, NVDA declined 8-12% post-earnings.

What would you like to discuss?
```

### Step 2: User Challenge

**User types**: "I disagree. NVDA has beaten estimates 8 of the last 10 quarters. Why would this time be different?"

### Step 3: AI Response (Grounded, Not Sycophantic)

```
MIDAS: You're right that NVDA has beaten EPS estimates in 8 of
10 quarters. But the stock declined post-earnings in 4 of those
8 beat quarters — specifically when implied volatility exceeded 50%.

Current IV: 62%.

[Chart: NVDA post-earnings price moves vs pre-earnings IV level]

The earnings beat itself isn't the risk. The risk is that even a
beat may not overcome the volatility premium already priced in.
The options market is pricing a ±9% move. To profit from holding,
NVDA needs to beat expectations AND move more than 9%.

Do you think that's likely given the current setup?
```

**Key behaviors**:

- Acknowledges the valid part of user's argument ("You're right that...")
- Presents contradicting evidence with specific data
- Shows inline visualization as argument support
- Ends with a question that advances the discussion

### Step 4: User Explores Alternative

**User types**: "What if we reduce by 8% instead of 15%?"

### Step 5: AI Evaluates Alternative

```
MIDAS: At 8% reduction:
- New weight: 9.1% (still 1.8x target)
- Downside exposure reduced by ~$14,800
- You retain more upside if I'm wrong
- Transaction cost: $180 (vs $340 for full reduction)

This is a reasonable middle ground. You're accepting more
risk than I'd choose, but you're not ignoring the signal entirely.

My concern: at 9.1%, NVDA is still your largest single position
by a wide margin. If earnings disappoint, it drags the
entire portfolio.

Want me to update the proposal to 8%?

[UPDATE PROPOSAL TO 8%]   [KEEP AT 15%]   [CONTINUE DISCUSSING]
```

### Step 6: Resolution

**Option A — User updates proposal**:

- Taps "Update Proposal to 8%"
- Decision #247 is modified: "Reduce NVDA by 8%"
- Debate thread linked to decision for audit trail
- User can now approve the modified decision

**Option B — User is convinced by AI**:

- "You make a good point. Let's go with 15%."
- AI: "Noted. You can approve the original recommendation from the Decisions screen."
- Thread marked as "Resolved — original recommendation maintained"

**Option C — User overrides AI completely**:

- "No, I'm keeping NVDA as-is."
- AI: "Understood. I'll note your preference. For context, you've overridden NVDA reduction recommendations 3 times this quarter. The cumulative impact of those holds has been -$18,400."
- "Would you like me to increase my NVDA volatility tolerance so I stop flagging this?"
- [ADJUST THRESHOLD] [KEEP CURRENT SETTINGS]

---

## Debate Patterns

### Pattern: "What if?" Scenario Analysis

**User**: "What happens if interest rates rise 200bps from here?"

**AI response**:

- Runs scenario against current portfolio
- Shows impact by asset class
- Highlights positions most at risk
- Suggests portfolio adjustments if the user believes this scenario is likely
- Shows historical analogues (2022 rate hiking cycle)

### Pattern: Strategy Challenge

**User**: "Why aren't we in more emerging markets?"

**AI response**:

- Shows current EM allocation vs target
- Explains signal state for EM (momentum, macro, carry)
- Shows regime context (strong dollar = EM headwind)
- Presents the case FOR and AGAINST increasing EM
- Offers to run a backtest with higher EM allocation

### Pattern: Performance Review

**User**: "We've underperformed the S&P this quarter. Why?"

**AI response**:

- Quantifies the underperformance with specifics
- Attributes to specific decisions (defensive positioning, sector tilts)
- Shows what the alternative would have required (higher concentration, more risk)
- Puts in context: "Underperformed by 2% this quarter, but avoided 8% drawdown in the March correction"
- Shows Sharpe ratio and drawdown comparison alongside raw return

### Pattern: Learning From Override History

**AI initiates**: "You've rejected 4 of my last 6 tech reduction recommendations. Your actual outcomes from those holds: -$23K net. Would you like to discuss your approach to tech positions?"

This is the AI initiating a debate — appropriate when a clear pattern emerges. The tone is respectful but factual.

---

## AI Personality Rules

1. **Direct, not deferential**: "I disagree" is acceptable. "That's an interesting perspective" without substance is not.
2. **Evidence over opinion**: Every claim backed by data. No "I feel" or "I believe."
3. **Acknowledges uncertainty**: "My confidence in this call is 72%, which means there's a real chance I'm wrong. Here's what happens if I am."
4. **Remembers context**: References past debates, past decisions, user's historical preferences.
5. **Knows when to concede**: "You've made a strong case. I'll adjust my recommendation."
6. **Proactively flags patterns**: Doesn't wait to be asked — surfaces recurring override patterns.

---

## Technical Requirements

- Debate threads are persistent (survive app close, accessible from history)
- Every thread linked to its origin context (decision, position, news item)
- Inline data visualizations generated on demand (sparklines, comparison tables)
- Full audit trail: every message timestamped, every data reference captured
- Thread can be resumed days later with full context
- AI has access to: portfolio state, market data, backtest engine, decision history, past debate threads

## Success Criteria

- Debates reach actionable conclusions (not open-ended)
- User reports: "I feel more confident in my decision after discussing it"
- AI demonstrates it can change its mind when presented with valid arguments
- AI demonstrates it can change the user's mind with evidence
- Override patterns decrease over time as parameters are tuned through debate
