# Plan: AI Debate System

---

## Overview

The debate system is Midas's primary differentiator. It allows users to challenge, question, and refine investment decisions through evidence-based conversation with the AI. Built on Kailash Kaizen agents with tools backed by portfolio data, market data, and the backtest engine.

---

## 1. Agent Architecture

### Three Kaizen Agents

**Analyst Agent** — generates decision briefs

```
Role: Convert strategy engine outputs into human-readable structured arguments
Trigger: New Decision record or regime change
Output: Structured brief (thesis, if_approved, if_rejected, precedents)

Tools:
- get_portfolio_state()         → current positions, weights, value
- get_regime_state()            → current regime + indicators
- get_decision_history(n=10)    → recent decisions and outcomes
- get_signal_values(ticker)     → current signal readings
- get_price_history(ticker, n)  → historical prices
- get_comparable_decisions(decision) → similar past decisions + outcomes
```

**Debate Agent** — handles user conversations

```
Role: Engage in evidence-based investment discussion
Trigger: User sends a message in debate thread
Personality: Respectful but direct portfolio manager. Will disagree. No sycophancy.

Tools:
- get_portfolio_state()         → current positions, weights, value
- get_position_detail(ticker)   → entry price, P&L, weight, signals
- get_price_history(ticker, n)  → historical prices
- get_regime_state()            → current regime + indicators
- get_decision_detail(id)       → full decision brief
- get_decision_history(n=20)    → past decisions with outcomes
- get_override_patterns()       → user's override history with outcomes
- run_scenario_backtest(params) → what-if backtest
- get_correlation_data(tickers) → correlation between instruments
- get_news_context(topic)       → Perplexity news lookup
- update_decision(id, changes)  → modify a pending decision
- suggest_parameter_change(param, value) → propose settings adjustment
```

**Monitor Agent** — continuous background watchdog

```
Role: Watch for regime changes, drift, and threshold breaches
Trigger: Polling schedule (1-min active, 15-min inactive)
Output: Alerts, regime change notifications, approval requests

Tools:
- get_latest_prices(tickers)    → current prices from cache
- get_regime_indicators()       → VIX, spreads, yield curve
- get_portfolio_drift()         → current vs target weights
- get_drawdown_state()          → current drawdown from peak
- create_decision(params)       → create new decision for approval
- send_notification(type, data) → push notification to user
```

---

## 2. Debate Agent Behavior Rules

### Personality Specification

```
System prompt core:
"You are a direct, evidence-based portfolio manager. You have access to
the user's portfolio data, market data, and backtesting tools.

RULES:
1. Never agree just to be agreeable. If the user is wrong, say so with evidence.
2. Every factual claim must reference specific data. Use tools to fetch data
   before making claims. Never fabricate numbers.
3. When you disagree, structure as: acknowledge valid points → present
   contradicting evidence → explain implications → ask what they want to do.
4. When the user makes a good point you hadn't considered, say so explicitly:
   'That's a strong point I hadn't weighted properly.'
5. Always drive toward an actionable conclusion. After 3-4 exchanges, ask:
   'Based on this discussion, do you want to update the decision?'
6. Reference past debates and override patterns when relevant.
7. Use inline data when it strengthens the argument — sparklines, comparison
   tables, distribution charts. Keep them small and contextual.
8. Express confidence in natural language: 'I'm fairly confident' (70-80%),
   'I'm uncertain but leaning toward' (50-70%), 'The data strongly supports'
   (80%+). Never show raw percentages in conversation.
9. If the user consistently overrides a category of decisions, proactively
   suggest parameter adjustment rather than repeating the same recommendation."
```

### Conversation Patterns

**Pattern: Challenge a Decision**

```
User: "Why did you recommend selling NVDA?"
Agent: [calls get_decision_detail, get_price_history, get_signal_values]
→ Presents thesis with data
→ Shows comparable past decisions
→ Asks if user wants to discuss specific aspects
```

**Pattern: "What if?" Scenario**

```
User: "What happens if rates rise 200bps?"
Agent: [calls run_scenario_backtest with rate shock]
→ Shows portfolio impact by position
→ Identifies most affected positions
→ Suggests hedging actions if impact is significant
→ Offers to adjust allocation
```

**Pattern: Performance Challenge**

```
User: "We're underperforming the S&P"
Agent: [calls get_portfolio_state, get_decision_history, run_scenario_backtest]
→ Quantifies underperformance precisely
→ Attributes to specific decisions (defensive positioning, etc.)
→ Shows the tradeoff: "Underperformed by 2%, but avoided -8% drawdown"
→ Shows risk-adjusted comparison (Sharpe, Sortino)
```

**Pattern: Override Learning**

```
Agent detects: user has rejected 3+ similar recommendations
Agent initiates: "You've rejected [category] recommendations [N] times.
Outcome of those holds: [data]. Would you like me to adjust my
[parameter] so I stop flagging this?"
[ADJUST THRESHOLD]  [KEEP CURRENT]  [DISCUSS FURTHER]
```

---

## 3. Decision Brief Generation

The Analyst Agent generates structured briefs for every decision:

```json
{
  "decision_id": 247,
  "headline": "Reduce NVDA position by 15%",
  "urgency": "elevated",
  "confidence": 0.72,
  "decision_window": "4 hours",
  "estimated_cost": 340,

  "thesis": "Implied volatility spiked 40% ahead of earnings. Historical pattern shows NVDA declines 8-12% on vol expansion in 7 of last 10 instances. Current position at 12.4% is 2x target weight.",

  "if_approved": {
    "action": "Sell 150 shares at ~$890",
    "proceeds": 133500,
    "slippage_estimate": 180,
    "dividend_wht_note": "No capital gains tax (Singapore). US dividend WHT: 30% on this position.",
    "new_weight": 0.062,
    "target_weight": 0.05
  },

  "if_rejected": {
    "current_weight": 0.124,
    "target_weight": 0.05,
    "max_estimated_loss": 28000,
    "scenario": "18% decline post-earnings",
    "ai_confidence_in_decline": 0.72
  },

  "precedents": [
    {
      "date": "2025-10-15",
      "action": "executed",
      "outcome": "avoided -11% decline"
    },
    {
      "date": "2025-03-22",
      "action": "user_rejected",
      "outcome": "position declined -8%"
    }
  ],

  "signals": {
    "momentum": -0.6,
    "volatility": -0.8,
    "macro": "neutral",
    "carry": 0.1
  }
}
```

### Brief Rendering

The frontend renders this JSON into the three-level disclosure:

1. **One-liner**: `headline` + first sentence of `thesis`
2. **Full brief**: All sections formatted as the decision card
3. **Raw data**: Signal values, full historical comparison (on demand)

---

## 4. Grounding & Anti-Hallucination

### Data Grounding Protocol

Every AI statement that includes a number or factual claim must be backed by a tool call:

```
BLOCKED: "NVDA typically drops after earnings" (no data cited)
ALLOWED: "NVDA declined in 4 of the last 8 post-earnings sessions where
         IV exceeded 50% [calls get_price_history, filters by condition]"
```

### Inline Data Visualization

When the Debate Agent cites data, it can include visualization markers:

```json
{
  "type": "comparison_table",
  "title": "NVDA Post-Earnings Moves vs Pre-Earnings IV",
  "data": [
    { "date": "2026-01", "iv": 45, "post_move": "+3.2%" },
    { "date": "2025-10", "iv": 58, "post_move": "-11.1%" }
  ]
}
```

The frontend renders these inline as small contextual charts/tables within the conversation.

### Confidence Calibration

Track the Debate Agent's predictive accuracy over time:

```
- For every decision where AI expressed confidence:
  - Record: confidence level + actual outcome
  - Build calibration curve: "When AI says 70% confident, is it right 70% of the time?"
  - Display calibration in user-facing trust metrics
  - Use calibration to improve future confidence expressions
```

---

## 5. Thread Management

### Thread Lifecycle

```
Created → Active → Resolved
                 → Stale (no messages for 7 days, auto-archive)
```

### Context Window Management

Debate threads can get long. To maintain quality:

1. **Thread summary**: After 10+ exchanges, generate a running summary of key points
2. **Context injection**: Each new message includes:
   - Thread summary (if exists)
   - Last 5 messages (full)
   - Original decision context
   - Current portfolio state (refreshed)
3. **Cross-thread memory**: The agent can reference other threads:
   "We discussed a similar NVDA situation in Thread #231 on March 15..."

### Resolution Types

| Resolution             | Description                                       |
| ---------------------- | ------------------------------------------------- |
| **Decision updated**   | Debate led to modifying a pending decision        |
| **Decision confirmed** | User confirmed original recommendation            |
| **Decision rejected**  | User decided against AI recommendation            |
| **Parameter adjusted** | Debate led to settings change                     |
| **Informational**      | No action needed — user just wanted to understand |
| **Stale**              | Thread abandoned without explicit resolution      |

---

## 6. Proactive AI Behavior

The AI doesn't just respond — it initiates when patterns emerge:

### Override Pattern Detection

```python
def check_override_patterns(user_id):
    recent_overrides = get_overrides(user_id, last_90_days)

    # Group by category (e.g., "tech_reduction", "bond_increase")
    patterns = categorize_overrides(recent_overrides)

    for category, overrides in patterns.items():
        if len(overrides) >= 3:
            # Calculate outcome of overrides vs what AI recommended
            user_outcome = sum(o.actual_return for o in overrides)
            ai_counterfactual = sum(o.counterfactual for o in overrides)

            if user_outcome < ai_counterfactual:
                # User is consistently making worse decisions in this category
                suggest_parameter_adjustment(category, overrides)
            else:
                # User is outperforming AI in this category
                adjust_ai_sensitivity(category, reduce=True)
```

### Regime Change Briefing

When regime changes, the Monitor Agent creates a brief for the Debate Agent to present:

```
"Market regime has shifted from Calm to Elevated.
Key indicators: VIX rose from 16 to 27, credit spreads widened 80bps.

What this means for your portfolio:
- TLT (+8.2% of portfolio): likely to benefit from flight to quality
- NVDA (12.4%): elevated risk due to concentration
- VWO (6.1%): EM typically underperforms in risk-off environments

I'm proposing 3 rebalancing actions. Want to review them?"
```

---

## 7. News Integration (Perplexity)

### Usage Pattern

News is NOT a primary signal. It is used for:

1. **Debate grounding**: When user asks about current events, AI can fetch relevant news
2. **Context enrichment**: Decision briefs can include relevant news context
3. **Regime narrative**: Help explain WHY regime changed (not just that it changed)

### Implementation

```python
# Perplexity tool for Debate Agent
def get_news_context(topic: str, portfolio_relevant: bool = True) -> dict:
    """Fetch news summary relevant to the topic.
    If portfolio_relevant, filter to news affecting held positions."""

    response = perplexity.search(
        query=f"Latest news about {topic} affecting investment markets",
        max_results=5
    )

    if portfolio_relevant:
        held_tickers = get_portfolio_tickers()
        response = filter_by_relevance(response, held_tickers)

    return {
        "summaries": response.summaries,
        "portfolio_impact": assess_impact(response, portfolio),
        "sources": response.sources
    }
```

### Portfolio Impact Tagging

Every news item displayed to the user includes:

```
IMPACT: High / Medium / Low / None
AFFECTED POSITIONS: [list of tickers with % of portfolio]
RELATED DECISIONS: [any pending decisions related to this news]
```

Items with "None" impact are deprioritized or hidden.
