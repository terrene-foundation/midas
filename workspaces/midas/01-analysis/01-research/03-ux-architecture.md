# UX Architecture: Midas

**Date**: 2026-04-09

---

## User Persona

Risk-loving investor who trusts their own judgment but wants AI leverage. Values being informed over being in control of every action. Intervenes selectively, not constantly. Technically sophisticated but outcome-oriented.

Closer to a **CEO reviewing their team's work** than a day trader watching tickers. The UX reflects that: executive briefing, not trading terminal.

---

## 1. Information Architecture

```
MIDAS
|
+-- Pulse (Home/Dashboard)
|   +-- Portfolio State (hero)
|   +-- Regime Status Banner
|   +-- Pending Approvals (promoted to top when present)
|   +-- Recent AI Actions (last 24-48h)
|   +-- Market Context Strip
|
+-- Decisions
|   +-- Pending Approvals (turbulent market queue)
|   +-- Decision History (all past AI actions with rationale)
|   +-- Decision Detail
|       +-- AI Rationale (structured argument)
|       +-- Market Context at Decision Time
|       +-- Expected vs Actual Outcome
|       +-- Cost Breakdown
|
+-- Debate (AI Discussion)
|   +-- Active Thread
|   +-- Thread History
|   +-- Quick Challenge (from any decision)
|
+-- Portfolio
|   +-- Allocations (current + target)
|   +-- P&L (by position, by period)
|   +-- Rebalancing Schedule + History
|   +-- Transaction Cost Analysis
|
+-- Backtest
|   +-- Strategy Performance Scorecard
|   +-- Regime-Specific Results
|   +-- Comparison View
|
+-- Signal (News/Sentiment)
|   +-- AI-Curated Feed (relevance-filtered to YOUR portfolio)
|   +-- Sentiment Gauges
|   +-- Regime Indicators
|
+-- Settings
    +-- Risk Parameters
    +-- Approval Thresholds
    +-- Notification Preferences
    +-- AI Behavior Tuning
```

**Layer model**: Pulse/Decisions/Debate = active engagement (80% of time). Portfolio/Backtest = reference. Signal = passive awareness.

---

## 2. Key Screen Concepts

### 2.1 Pulse (Home)

**Purpose**: Answer "Is everything okay?" in under 5 seconds.

**Critical pattern — Regime-Driven Layout Adaptation**: The dashboard changes shape based on market conditions. Calm markets = sparse, peaceful (portfolio value dominates). Turbulent markets = approval queue takes hero position, regime banner becomes visually prominent, information density increases. The UI's tension level matches the market's tension level.

```
+-----------------------------------------------+
| REGIME: ELEVATED VOLATILITY                    |
+-----------------------------------------------+
|  $2,847,312          +1.2% today               |
|  Portfolio Value      +18.4% YTD               |
+-----------------------------------------------+
| ! APPROVAL NEEDED (2)              time-left   |
| [Reduce NVDA 15%]            [Approve | Debate] |
| [Add TLT 8%]                 [Approve | Debate] |
+-----------------------------------------------+
| RECENT ACTIONS                                  |
| 2h ago  Trimmed AAPL 3%  "Sector rotation..."  |
| 6h ago  Added BTC 2%     "Momentum signal..."   |
+-----------------------------------------------+
| VIX 24.3 (+12%)  |  SPX -0.8%  |  DXY +0.3%  |
+-----------------------------------------------+
```

### 2.2 Decisions (Approval Workflow)

Every AI decision presented as a **structured brief**, not a notification:

1. **Thesis** (why this action)
2. **If Approved** (consequences + costs)
3. **If Rejected** (consequences + risk)
4. **Historical Precedent** (similar past decisions and outcomes)
5. **Action buttons** (Approve / Modify / Reject / Debate)

**Time-pressure UX**: Subtle progress bar (not countdown timer) showing decision window. Color shifts from neutral to warm as window narrows. If window closes, AI takes configurable default action.

**Modification flow**: Inline constrained editing — "How much? When? What instead?" AI immediately recalculates consequences.

### 2.3 Debate (AI Discussion)

**The product's primary differentiator.** Not a chatbot sidebar — a structured adversarial discussion about investment decisions, grounded in portfolio data.

**Design rules**:

1. **No sycophancy**: AI must be willing to say "You are wrong, and here is why." A financial AI that agrees with everything is dangerous. Personality: "respectful but direct portfolio manager."
2. **Always grounded**: Every AI claim links to data. No vague "markets are uncertain" — specific numbers, historical comparisons.
3. **Actionable conclusions**: Debates end in decisions. AI periodically asks: "Want to update the decision based on this?"
4. **Entry points everywhere**: Can be invoked from any decision, position, or news item.
5. **Inline data visualization**: Small contextual charts as argument support, not full-page dashboards.
6. **Thread memory**: AI remembers patterns. "You've rejected NVDA reductions 3 times. Realized loss from those holds: $18,400. Adjust my threshold?"

### 2.4 Portfolio

Reference screen for detailed analysis. Uses **horizontal bar comparison** for allocations (not pie charts):

```
US Equity    ████████████████░░░  42% (target: 35%) +7%
Intl Equity  ██████████░░░░░░░░░  22% (target: 25%) -3%
Fixed Income ████████░░░░░░░░░░░  18% (target: 20%) -2%
```

Rebalancing history as timeline of snapshot cards (before/after/cost/rationale), not tables.

### 2.5 Backtest

**Outcome-oriented**: Primary display is a scorecard, not a line graph:

```
Total Return:       +142%   (S&P 500: +87%)
Worst Drawdown:     -18%    (S&P 500: -34%)
Sharpe Ratio:       1.84    (S&P 500: 0.92)

REGIME BREAKDOWN
Bull Markets:   +38% annualized  (benchmark: +24%)
Bear Markets:   +2% avg          (benchmark: -22%)
```

Equity curve chart exists but is secondary (below the fold).

### 2.6 Signal (News)

Every news item tagged with **portfolio impact**:

```
NVDA earnings beat estimates by 12%
IMPACT: High — You hold 12.4% NVDA. Pending decision #247.
[Go to Decision] [Debate This]

Fed signals rate pause
IMPACT: Medium — Favorable for TLT and REIT positions (~22%).
```

Items with no portfolio impact deprioritized or hidden.

---

## 3. Navigation Model

### Web: Left Rail + Contextual Panels

Six items: Pulse, Decisions, Debate, Portfolio, Backtest, Signal. Left rail (icon + label, collapsible). Debate panel slides in from right as overlay on any screen.

### Mobile: Bottom Tab Bar + Sheet

Five tabs: Pulse, Decisions, Debate, Portfolio, More (Backtest, Signal, Settings). Debate also available as bottom sheet pullable from any screen.

### Principles

1. Decisions always one tap away (badge count during turbulence)
2. Debate is a mode, not a destination (contextual invocation)
3. Every decision/thread/position has a deep link
4. No modals for critical actions (inline or dedicated screens)

---

## 4. Critical UX Patterns

### Transparency: Three-Level "Why"

- **One-liner** (lists/cards): "Trimmed NVDA 15% due to vol spike"
- **Brief** (decision detail): Thesis, consequences, precedent
- **Full reasoning** (on demand): Complete chain of thought, every data point

### Trust Calibration

- Confidence level in natural language ("High confidence" / "Uncertain but acting on risk management")
- Track record for similar decisions ("17 of 23 similar trades were profitable")
- Counterfactual retrospectives ("What would have happened if rejected")

### Urgency: Three-Tier Visual System

| Tier     | Treatment                           | Meaning            |
| -------- | ----------------------------------- | ------------------ |
| Routine  | Standard card                       | Can wait days      |
| Elevated | Warm accent, decision window shown  | Act within hours   |
| Urgent   | Full-width banner, haptic on mobile | Act within minutes |

**Never cry wolf**: Reserve Urgent tier for genuinely time-constrained situations.

### Override as Learning

When user overrides AI: confirm, record, track counterfactual. After pattern of overrides, suggest parameter adjustment: "You always hold tech longer than I recommend. Adjust my threshold?"

---

## 5. Design System Direction

### Visual Language: Calm Authority

The more chaotic the market, the calmer the UI should feel.

### Color Strategy

- **Dark mode primary** (deep neutral `#0F1117`, not pure black)
- **Surface**: `#1A1D27` for cards/panels
- **Accent**: Gold/amber (`#D4A843`) — referencing "Midas", used sparingly
- **Gain**: Muted teal `#34A77B` (not neon green)
- **Loss**: Muted coral `#E85D5D` (not fire-engine red)
- **Urgency gradient**: Routine = no change, Elevated = warm amber border, Urgent = amber background

Avoid: purple-to-blue gradients, neon accents, glassmorphism. Closer to private banking interface than SaaS dashboard.

### Typography

- Humanist/geometric sans-serif with tabular figure support (Geist, Satoshi, or Circular — NOT Inter/Roboto)
- Monospace for all financial figures (alignment)
- Strict modular scale: 28-32px headlines, 15-16px body, 12-13px data labels

### Information Density

| Screen    | Density     | Rationale                                |
| --------- | ----------- | ---------------------------------------- |
| Pulse     | Low         | Scannable in 5 seconds                   |
| Decisions | Medium      | Enough to decide without scrolling       |
| Debate    | Variable    | Conversation = low; inline data = medium |
| Portfolio | High        | Reference screen, user came to analyze   |
| Backtest  | Medium-high | Scorecards first, charts on demand       |
| Signal    | Low         | Feed format, one item at a time          |

---

## 6. Mobile-Specific

### Touch Targets

Approve/Reject buttons: minimum 48px height (ideally 56px), on opposite sides of screen. Accidentally approving a $100K trade is catastrophic UX failure.

### Rich Notifications

```
GOOD: "Midas wants to reduce NVDA by 15% ($133K). Vol spike.
       Confidence: High. Window: 4h."  [Approve] [View]

BAD:  "New decision pending. Tap to review."
```

### Notification Tiers

- **Silent**: Routine rebalancing executed (visible in app only)
- **Standard push**: Decision pending, regime change, significant P&L
- **Prominent push** (sound/haptic): Urgent approval, significant portfolio event

### Biometric Gating

Face ID / fingerprint for: approving trades, modifying risk parameters, accessing full values.

### Widgets

- **Small**: Portfolio value + daily change + regime indicator
- **Medium**: Above + pending decision count
- **Large**: Mini Pulse (value, regime, decisions, recent actions)

### Offline

Last-known state with "Last updated: [time]". Pending decisions cached but not actionable. Regime banner: "Offline — decisions paused."
