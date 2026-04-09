# SPEC-03: UI/UX Specification

**Status**: APPROVED — User approved UX plans. This spec locks the decisions.
**Date**: 2026-04-09

---

## 1. Design Identity

### Midas Is an Executive Briefing, Not a Trading Terminal

The user persona is a sophisticated investor who delegates and oversees — closer to a CEO reviewing their team's work than a day trader watching charts. The UX reflects this: executive briefing, not Bloomberg terminal.

**Design language**: Calm Authority. The more chaotic the market, the calmer the UI should feel. Urgency is communicated through structured visual changes, not visual noise.

---

## 2. Information Architecture (Locked)

```
MIDAS
├── Pulse (Home)          — "Is everything okay?" in 5 seconds
├── Decisions             — Pending approvals + decision history
├── Debate                — Structured AI discussion (THE differentiator)
├── Portfolio             — Allocations, P&L, rebalancing
├── Backtest              — Strategy scorecard, regime breakdown
├── Signal                — News feed filtered by portfolio impact
└── Settings              — Risk parameters, autonomy, preferences
```

**Layer model**:

- Active engagement (80% of time): Pulse, Decisions, Debate
- Reference: Portfolio, Backtest
- Passive awareness: Signal

---

## 3. Navigation (Locked)

### Web: Left Rail + Contextual Panels

- Six items: Pulse, Decisions, Debate, Portfolio, Backtest, Signal
- Left rail with icon + label, collapsible to icons
- Debate panel slides in from right as overlay on any screen
- Minimum width: 1024px (tablet and above; phone users use mobile app)

### Mobile: Bottom Tab Bar + Sheet

- Five tabs: Pulse, Decisions, Debate, Portfolio, More
- Debate also available as bottom sheet from any screen
- Biometric gating on trade approvals

---

## 4. Regime-Adaptive Layout (Locked)

The UI physically restructures based on market operational regime. This is the most distinctive UX feature.

| Regime   | Pulse Layout                              | Information Density | Regime Banner    |
| -------- | ----------------------------------------- | ------------------- | ---------------- |
| Calm     | Portfolio value hero, sparse, peaceful    | Low                 | Muted, small     |
| Elevated | Approval queue promoted, amber accents    | Medium              | Prominent, amber |
| Urgent   | Approval queue dominates, action-oriented | High                | Full-width, warm |
| Crisis   | Emergency banner, trading paused          | Maximum             | Red, critical    |

Transitions between layouts animate smoothly (500ms).

---

## 5. Core UX Patterns (Locked)

### 5.1 Decision Brief Format

Every AI decision is presented as a structured argument, not a notification:

1. **Thesis** — why this action, grounded in data
2. **If Approved** — consequences, costs, new allocation
3. **If Rejected** — consequences, risk, exposure
4. **Historical Precedent** — comparable past decisions + outcomes
5. **Actions** — Approve / Modify / Reject / Debate

### 5.2 Three-Level Transparency

- **One-liner** (lists/cards): headline + first sentence of thesis
- **Brief** (decision detail): full structured argument
- **Full reasoning** (on demand): complete chain of thought, every data point

### 5.3 Urgency Communication

| Tier     | Treatment                           | Meaning            |
| -------- | ----------------------------------- | ------------------ |
| Routine  | Standard card, no urgency cues      | Can wait days      |
| Elevated | Warm accent, decision window shown  | Act within hours   |
| Urgent   | Full-width banner, haptic on mobile | Act within minutes |

Never cry wolf. Reserve Urgent for genuinely time-constrained situations.

### 5.4 Debate as First-Class Interaction

- Entry points everywhere (any decision, position, news item)
- AI personality: respectful but direct portfolio manager. Will disagree.
- Every claim grounded in data. No fabricated numbers.
- Debates end in actionable conclusions.
- Thread memory across sessions.
- Override patterns surfaced proactively.

### 5.5 Counterfactual Tracking

After every override, track what would have happened. Surface this in:

- Decision history (retrospective annotations)
- Debate threads (when relevant patterns emerge)
- Trust calibration metrics over time

### 5.6 Override as Learning

When user consistently overrides a category of decisions, the system suggests parameter adjustment rather than repeating the same recommendation.

---

## 6. Design System (Locked)

### Color Tokens

```
// Backgrounds (dark mode primary)
--bg-base:        #0F1117
--bg-surface:     #1A1D27
--bg-elevated:    #242731

// Text
--text-primary:   #E8E9ED
--text-secondary: #8B8D97
--text-muted:     #5A5C66

// Accent
--accent-gold:    #D4A843    (Midas gold — sparingly)

// Semantic
--color-gain:     #34A77B    (muted teal, not neon green)
--color-loss:     #E85D5D    (muted coral, not fire-engine red)

// Regime
--regime-calm:    #34A77B
--regime-elevated:#D4A843
--regime-urgent:  #E8914A
--regime-crisis:  #E85D5D
```

### Typography

- Sans-serif: Geist or equivalent humanist face with tabular figure support
- Monospace: Geist Mono for all financial figures
- Scale: 28-32px hero, 20px headline, 16px title, 15px body, 13px label, 12px caption
- All monetary values in monospace with tabular-nums

### Components

- Cards: 8px radius, bg-surface, no drop shadows
- Buttons: Approve (gold filled) opposite Reject (text-only loss color) — NEVER adjacent on mobile
- Touch targets: 48px minimum, 56px for financial actions
- Motion: 200ms ease transitions, purposeful only. No decorative animation.

### Information Density by Screen

| Screen    | Density     | Rationale                              |
| --------- | ----------- | -------------------------------------- |
| Pulse     | Low         | Scannable in 5 seconds                 |
| Decisions | Medium      | Enough to decide without scrolling     |
| Debate    | Variable    | Conversation low; inline data medium   |
| Portfolio | High        | Reference screen, user came to analyze |
| Backtest  | Medium-high | Scorecards first, charts on demand     |
| Signal    | Low         | Feed format, one item at a time        |

---

## 7. Mobile-Specific (Locked)

### Rich Notifications

Information-rich, actionable. Not "Tap to review" — show the decision, cost, confidence, window.

### Notification Tiers

- Silent: Routine actions (in-app only)
- Standard push: Decision pending, regime change
- Prominent push (sound + haptic): Urgent approval needed

### Widgets

- Small: Portfolio value + daily change + regime dot
- Medium: Above + pending decisions
- Large: Mini Pulse

### Offline

Last-known state with timestamp. Decisions visible but not actionable. "Offline — decisions paused."

### Biometric

Required for: trade approvals, risk parameter changes. Optional for: portfolio value display.

---

## 8. Outcome-Oriented Presentation (Locked)

### Backtest: Numbers First, Charts Second

Primary display is a scorecard, not a line graph:

```
Total Return:    +X%   (Benchmark: +Y%)
Worst Drawdown:  -X%   (Benchmark: -Y%)
Sharpe Ratio:    X.XX  (Benchmark: Y.YY)
```

Equity curve exists but is below the fold.

### Portfolio: Horizontal Bars, Not Pie Charts

```
Asset Class  ████████████░░░░  42% (target: 35%) +7%
```

### News: Relevance-Filtered

Every item tagged with portfolio impact (High/Medium/Low/None). No impact = deprioritized.

---

## 9. Anti-Patterns (Blocked)

- Purple-to-blue gradients, neon accents, glassmorphism
- Constantly flickering price tickers
- Auto-refresh that loses scroll position
- Modals for critical financial actions
- "AI startup demo" aesthetic
- Countdown timers (use progress bars instead — awareness, not panic)
- Generic chatbot sidebar for the debate interface
- Pie charts for allocation comparison

---

## Application

This spec is the authoritative reference for all frontend implementation. Deviations require explicit user approval.
