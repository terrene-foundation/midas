# Plan: Frontend

---

## Overview

Two frontends: React/Next.js for web (primary, built first) and Flutter for mobile (iOS + Android, built second). Both share the same API layer and design language.

---

## 1. Web Frontend (React/Next.js)

### Tech Stack

| Concern       | Choice                       | Rationale                                    |
| ------------- | ---------------------------- | -------------------------------------------- |
| Framework     | Next.js (App Router)         | SSR for initial load, API routes for BFF     |
| State         | React Query (TanStack Query) | Server state management, cache, polling      |
| Real-time     | WebSocket (native)           | Regime updates, price polling, notifications |
| Charts        | Recharts or Visx             | Lightweight, React-native charting           |
| UI Components | Shadcn/ui (customized)       | Accessible, composable, easy to theme        |
| Styling       | Tailwind CSS                 | Rapid iteration, design system enforcement   |
| Typography    | Geist (Vercel)               | Humanist sans-serif, tabular figures, free   |

### Page Structure

```
app/
├── layout.tsx                  # Shell: left rail nav + main content
├── page.tsx                    # Redirect to /pulse
├── pulse/
│   └── page.tsx                # Dashboard — regime banner, portfolio hero, decisions, actions
├── decisions/
│   ├── page.tsx                # Pending + history list
│   └── [id]/
│       └── page.tsx            # Decision detail — structured brief + actions
├── debate/
│   ├── page.tsx                # Thread list
│   └── [threadId]/
│       └── page.tsx            # Active debate thread
├── portfolio/
│   ├── page.tsx                # Allocations, positions, P&L
│   └── rebalancing/
│       └── page.tsx            # Rebalancing history + schedule
├── backtest/
│   └── page.tsx                # Scorecard, regime breakdown, scenarios
├── signal/
│   └── page.tsx                # News feed with portfolio impact tags
└── settings/
    └── page.tsx                # Risk profile, approval thresholds, preferences
```

### Key Components

**RegimeBanner** — top of every page

- Displays current regime (Calm / Elevated / Urgent / Crisis)
- Visual treatment changes with regime (muted → warm → urgent)
- Shows key indicators: VIX, SPX change, credit spreads

**DecisionCard** — used in Pulse and Decisions

- One-liner thesis
- Urgency indicator (color-coded)
- Time remaining (progress bar, not countdown)
- Action buttons: Approve / Modify / Reject / Debate
- Expandable to full brief

**DebatePanel** — slide-in overlay from right edge

- Can be invoked from any page (contextual)
- Shows conversation thread with inline data visualizations
- Input field at bottom with "Attach Data" option
- Resolution buttons at top when AI suggests an action

**AllocationBar** — horizontal bar comparison

- Current weight (filled) vs target weight (track)
- Overweight/underweight color coding
- Click to drill into position detail

**BacktestScorecard** — numbers-first, charts-second

- Key metrics in large type (return, drawdown, Sharpe)
- Benchmark comparison columns
- Regime breakdown table below

**NotificationToast** — real-time WebSocket events

- New decision pending → toast with quick-approve action
- Regime change → banner flash
- Trade executed → subtle confirmation

### Real-Time Data Flow

```
WebSocket connection on mount:
  → regime_change    → update RegimeBanner, potentially restructure Pulse layout
  → price_update     → update portfolio value (smooth animation, not flicker)
  → decision_new     → add to pending queue, show toast
  → decision_executed → move from pending to recent, confirmation animation
  → debate_message   → update active debate thread

React Query polling (when WebSocket is insufficient):
  → Portfolio state: every 60s
  → Signal values: every 60s
  → Backtest results: on-demand only
```

### Responsive Breakpoints

| Breakpoint  | Layout                                                | Target  |
| ----------- | ----------------------------------------------------- | ------- |
| ≥1280px     | Full layout: left rail expanded + main + debate panel | Desktop |
| 1024-1279px | Left rail collapsed (icons) + main + debate panel     | Laptop  |
| 768-1023px  | Bottom tab bar + main (no simultaneous debate panel)  | Tablet  |
| <768px      | Not supported — use mobile app                        | Phone   |

---

## 2. Mobile Frontend (Flutter)

### Architecture

| Concern          | Choice             | Rationale                               |
| ---------------- | ------------------ | --------------------------------------- |
| State management | Riverpod           | Recommended for Flutter, good for async |
| Navigation       | Go Router          | Declarative, deep link support          |
| HTTP             | Dio                | Interceptors, retry, timeout            |
| WebSocket        | web_socket_channel | Flutter standard                        |
| Charts           | fl_chart           | Performant, customizable                |
| Local storage    | Hive               | Fast key-value for offline cache        |

### Screen Structure

```
lib/
├── screens/
│   ├── pulse/           # Home dashboard
│   ├── decisions/       # Pending + history + detail
│   ├── debate/          # Thread list + active thread
│   ├── portfolio/       # Allocations + positions
│   ├── more/            # Backtest, Signal, Settings
│   └── onboarding/      # First-time setup flow
├── widgets/
│   ├── regime_banner.dart
│   ├── decision_card.dart
│   ├── allocation_bar.dart
│   ├── debate_sheet.dart       # Bottom sheet for contextual debate
│   ├── backtest_scorecard.dart
│   └── news_item.dart
├── services/
│   ├── api_service.dart         # REST client
│   ├── websocket_service.dart   # Real-time connection
│   ├── notification_service.dart
│   └── biometric_service.dart
└── models/
    ├── portfolio.dart
    ├── decision.dart
    ├── debate.dart
    └── regime.dart
```

### Mobile-Specific Features

**Rich Push Notifications**

```dart
// Actionable notification with inline approve
NotificationPayload(
  title: "Midas — Approval Needed",
  body: "Reduce NVDA by 15% (\$133K). Vol spike. Confidence: High. Window: 4h.",
  actions: [
    NotificationAction(id: "approve", title: "Approve"),
    NotificationAction(id: "view", title: "View Details"),
  ],
  data: {"decision_id": 247, "deep_link": "/decisions/247"},
)
```

**Biometric Gating**

- Trade approval: Face ID / fingerprint required
- Risk parameter changes: biometric required
- Portfolio value display: optional biometric (privacy setting)

**Home Screen Widgets**

- Small: portfolio value + daily change + regime dot
- Medium: above + pending decision count + one-liner
- Large: mini Pulse (value, regime, last 3 actions)

**Offline Mode**

- Cache last-known portfolio state in Hive
- Display with "Last updated: [timestamp]" watermark
- Pending decisions visible but not actionable
- Regime banner: "Offline — decisions paused"
- Queue approval actions for when connectivity returns

**Debate Bottom Sheet**

- Invoked by long-press on any decision card or portfolio position
- Slides up from bottom, covers ~75% of screen
- Pre-loaded with context from the invoking element
- Can be dismissed by swipe down
- Maintains thread state across sheet open/close cycles

---

## 3. Shared Design System

### Color Tokens

```
// Backgrounds
--bg-base:     #0F1117    // Deep neutral (dark mode)
--bg-surface:  #1A1D27    // Cards, panels
--bg-elevated: #242731    // Hover states, active items
--bg-overlay:  rgba(15, 17, 23, 0.8)  // Debate panel backdrop

// Text
--text-primary:   #E8E9ED    // Main text
--text-secondary: #8B8D97    // Labels, descriptions
--text-muted:     #5A5C66    // Timestamps, metadata

// Accent
--accent-gold:    #D4A843    // Primary accent (Midas gold)
--accent-gold-hover: #E0B654
--accent-gold-muted: rgba(212, 168, 67, 0.15)  // Badge backgrounds

// Semantic
--color-gain:     #34A77B    // Positive returns
--color-loss:     #E85D5D    // Negative returns
--color-neutral:  #8B8D97    // Unchanged / hold

// Regime
--regime-calm:     #34A77B   // Green (same as gain)
--regime-elevated: #D4A843   // Gold (same as accent)
--regime-urgent:   #E8914A   // Orange
--regime-crisis:   #E85D5D   // Red (same as loss)
```

### Typography Scale

```
// Font family
--font-sans:  'Geist', system-ui, sans-serif
--font-mono:  'Geist Mono', 'SF Mono', monospace

// Scale
--text-hero:     32px / 1.1 / 600    // Portfolio value on Pulse
--text-headline: 20px / 1.3 / 600    // Section headers
--text-title:    16px / 1.4 / 500    // Card titles, decision headlines
--text-body:     15px / 1.5 / 400    // Body text, descriptions
--text-label:    13px / 1.4 / 500    // Labels, metadata
--text-caption:  12px / 1.4 / 400    // Timestamps, fine print

// Financial figures: ALWAYS use --font-mono with tabular-nums
```

### Component Specs

**Cards**

- Border radius: 8px
- Background: --bg-surface
- Border: 1px solid transparent (shows --regime-\* color when urgency applies)
- Padding: 16px (desktop), 12px (mobile)
- No drop shadows — rely on background color differentiation

**Buttons**

- Primary (Approve): --accent-gold background, dark text, 44px height
- Secondary (Modify): outline with --accent-gold border, 40px height
- Tertiary (Reject/Debate): text-only, --text-secondary color, 40px height
- Destructive (Reject): --color-loss text color
- Touch target: minimum 48px on mobile (56px for critical financial actions)
- Approve and Reject NEVER adjacent — opposite sides of screen on mobile

**Motion**

- Transitions: 200ms ease
- Data updates: fade-in (no flicker)
- Approval confirmation: brief checkmark draw animation
- Regime transition: smooth color interpolation (500ms)
- No bounce, no elastic, no decorative animation

---

## 4. Regime-Adaptive Layout

The UI physically restructures based on market regime. This is the most distinctive UX feature.

### Pulse Screen Adaptation

**Calm Regime**

```
[Small muted regime banner]
[Large portfolio value with breathing room]
[Spacious recent actions list — last 48h]
[Minimal market context strip]
```

**Elevated Regime**

```
[Prominent amber regime banner with indicators]
[Portfolio value + daily change]
[PENDING APPROVALS — promoted to hero position]
[Recent actions — compressed]
[Market context with more detail]
```

**Urgent/Crisis Regime**

```
[Full-width urgent banner with VIX, spreads, key indicators]
[APPROVAL QUEUE — dominates the page]
  [Each decision with urgency timer]
[Portfolio value — smaller, secondary]
[Market context — expanded, real-time updating]
```

### Implementation

```typescript
// Regime drives layout variant
const pulseLayout = useMemo(() => {
  switch (regime) {
    case "calm":
      return { heroSize: "large", approvalPosition: "hidden", density: "low" };
    case "elevated":
      return {
        heroSize: "medium",
        approvalPosition: "hero",
        density: "medium",
      };
    case "urgent":
    case "crisis":
      return { heroSize: "small", approvalPosition: "hero", density: "high" };
  }
}, [regime]);
```

Transitions between layouts animate smoothly (500ms) — no jarring page restructuring.
