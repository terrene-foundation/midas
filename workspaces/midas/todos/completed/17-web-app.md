# M17 -- Web App (Next.js App Router + React Query + Shadcn/ui)

**Spec anchors:** 06, 07, 08, 09, 10, 11, 12
**Framework:** Next.js 15 App Router, React 19, React Query v5, Shadcn/ui, Tailwind CSS v4, Zustand
**Depends on:** M10 (brief composer), M11 (autonomy ladder), M12 (compliance agent), M16 (IBKR)
**Location:** `apps/web/` at project root
**Backend API:** `src/midas/api/routes.py` -- mounted at `/api/v1/{surface}`

---

## Design Tokens (authoritative for all tasks)

| Token              | Value   | Usage                         |
| ------------------ | ------- | ----------------------------- |
| bg-base            | #0F1117 | Page background               |
| bg-surface         | #1A1D27 | Card / panel background       |
| bg-elevated        | #242731 | Elevated card, hover states   |
| accent-gold        | #D4A843 | Primary accent, brand         |
| gain-green         | #34A77B | Positive returns, Calm band   |
| loss-red           | #E85D5D | Negative returns, Crisis band |
| regime-calm        | #34A77B | Calm band indicator           |
| regime-elevated    | #D4A843 | Elevated band indicator       |
| regime-urgent      | #E8914A | Urgent band indicator         |
| regime-crisis      | #E85D5D | Crisis band indicator         |
| border-radius      | 8px     | All cards, buttons, inputs    |
| transition-default | 200ms   | UI element transitions        |
| transition-regime  | 500ms   | Band interpolation animations |

Typography: Geist Sans for body, Geist Mono with `font-variant-numeric: tabular-nums` for all financial figures.

---

## Group A: Foundation (App Shell, Design System, API Client, Auth)

### A-01 -- Next.js app scaffold with App Router layout

**Spec:** 09 S5.1 (web navigation: left rail with icons + labels, collapsible to icons only)
**Objective:** Create `apps/web/` with Next.js 15 App Router, configure Tailwind CSS, install Shadcn/ui, set up the left-rail layout shell with six navigation items (Pulse, Decisions, Debate, Portfolio, Backtest, Signal) plus Settings in a footer slot.
**Scope:**

- `apps/web/package.json` with Next.js 15, React 19, Tailwind CSS v4, `@tanstack/react-query`, Zustand, Shadcn/ui CLI init
- `apps/web/app/layout.tsx` -- root layout with `<QueryClientProvider>`, Geist font loading, dark mode class
- `apps/web/app/(shell)/layout.tsx` -- left-rail sidebar with icon+label navigation items, collapsible state persisted to localStorage, minimum viewport 1024px enforced with a desktop-only gate message
- `apps/web/app/(shell)/page.tsx` -- redirect root to `/pulse`
- `apps/web/tailwind.config.ts` -- custom color tokens, border-radius, transition tokens
- `apps/web/app/globals.css` -- Tailwind directives, CSS custom properties for design tokens

**Architecture rule:** Each surface is a route group under `(shell)/` -- `/pulse`, `/decisions`, `/debate`, `/portfolio`, `/backtest`, `/signal`, `/settings`. Debate also has a slide-in overlay rendered at the shell level (not route-level).

**Acceptance:**

- `pnpm dev` starts and renders the left-rail shell
- All six nav items visible with icons, collapsible to icon-only
- Minimum viewport gate shows message below 1024px
- Dark mode renders bg-base background

---

### A-02 -- Shadcn/ui component library setup with custom theme

**Spec:** Design tokens table above
**Objective:** Install and configure Shadcn/ui with the Midas dark theme, plus create the financial-figure typography helper.
**Scope:**

- Initialize Shadcn/ui with `dark` variant, custom `apps/web/components.json`
- Override Shadcn CSS variables to map to Midas design tokens (bg-base, bg-surface, bg-elevated, accent-gold, gain-green, loss-red)
- Install components: Button, Card, Skeleton, Badge, Sheet, Dialog, Progress, Tooltip, Separator, ScrollArea, Tabs, Avatar, Command
- Create `apps/web/elements/FinancialFigure.tsx` -- wrapper that applies Geist Mono + `tabular-nums` + positive/negative color based on sign
- Create `apps/web/elements/LoadingSkeleton.tsx` -- surface-specific skeleton presets (pulse, decision-card, portfolio-row, backtest-scorecard, signal-item)

**Acceptance:**

- All Shadcn components render in dark mode with Midas color tokens
- FinancialFigure renders `+1.23%` in gain-green and `-0.45%` in loss-red with tabular-nums
- LoadingSkeleton has presets for each surface

---

### A-03 -- API client with React Query hooks

**Spec:** Backend API at `/api/v1/{surface}` (see `src/midas/api/routes.py`)
**Objective:** Create a typed API client layer with React Query hooks for every backend endpoint. One hook per endpoint; no composite hooks that call multiple endpoints.
**Scope:**

- `apps/web/lib/api-client.ts` -- base fetch wrapper with auth header injection, base URL from `NEXT_PUBLIC_API_URL` env, error typing
- `apps/web/lib/types.ts` -- TypeScript interfaces for all API response shapes: `PulseResponse`, `RegimeResponse`, `AttentionResponse`, `DecisionSummary`, `DecisionDetail`, `BriefResponse`, `PortfolioResponse`, `Position`, `Allocation`, `AttributionResponse`, `RiskMetrics`, `BacktestRun`, `BacktestResult`, `Signal`, `EnvelopeConfig`, `AutonomyState`, `KillSwitchState`, `DataSourceStatus`, `PaperLiveState`, `ComplianceRule`, `DebateThread`, `DebateMessage`
- `apps/web/lib/queries/` -- one file per surface: `usePulse.ts`, `useDecisions.ts`, `useDebate.ts`, `usePortfolio.ts`, `useBacktest.ts`, `useSignal.ts`, `useSettings.ts`, `useCompliance.ts`, `useAudit.ts`
- Each file exports named hooks: `usePulse()`, `useRegime()`, `useAttention()`, `useDecisions(status)`, `useDecision(id)`, `useBrief(id)`, `useApproveDecision()`, `useDeclineDecision()`, `useBatchReview()`, etc.
- `apps/web/lib/query-client.ts` -- QueryClient config with stale times (5s for pulse, 30s for portfolio, 60s for settings)

**Acceptance:**

- Every backend endpoint has a corresponding typed hook
- Hooks return `{ data, isPending, error }` for loading-state rendering
- No `any` types anywhere in the API layer

---

### A-04 -- Auth flow (login, session, re-auth gate)

**Spec:** 11 S6.2 (JWT auth, session management), 10 S2.3 (re-auth for Urgent/Crisis approvals)
**Objective:** Implement login page, JWT session management, and a re-auth confirmation modal for high-stakes actions.
**Scope:**

- `apps/web/app/login/page.tsx` -- login form (email + password), calls `POST /api/v1/auth/login` (backend endpoint to be created), stores JWT in httpOnly cookie or localStorage with a session store
- `apps/web/lib/auth.ts` -- Zustand store for auth state: `isAuthenticated`, `user`, `token`, `login()`, `logout()`, `reAuth(password): Promise<boolean>`
- `apps/web/elements/ReAuthModal.tsx` -- password confirmation modal used for approve actions in Urgent/Crisis bands and envelope-widening changes
- `apps/web/middleware.ts` -- Next.js middleware that redirects unauthenticated users to `/login` (except `/login` itself)
- Auth token refresh: intercept 401 responses, attempt token refresh, retry

**Acceptance:**

- Unauthenticated users redirect to `/login`
- Login form submits credentials and stores session
- ReAuthModal prompts for password and returns success/failure
- Session persists across page navigations

---

### A-05 -- Global state stores (Zustand)

**Spec:** 06 S3 (continuous regime), 09 S2 (regime-adaptive reshape), 09 S8 (Debate overlay)
**Objective:** Create Zustand stores for cross-cutting UI state that does not belong in React Query (server state lives in React Query; local UI state lives in Zustand).
**Scope:**

- `apps/web/stores/regime-store.ts` -- `a_t: number`, `band: Band`, `changepointProbability: number`, `oodScore: number`, `transitionPressure: number`, computed interpolation progress between bands; write-only via WebSocket/React Query subscription
- `apps/web/stores/debate-overlay-store.ts` -- `isOpen: boolean`, `originatingContext: { type: string; id: string } | null`, `openDebate(context)`, `closeDebate()`; used by the shell-level slide-in panel
- `apps/web/stores/kill-switch-store.ts` -- `isActive: boolean`, `confirmationCode: string | null`, `setActive()`, `clear()`; derived from pulse data
- `apps/web/stores/attention-store.ts` -- `decisionSecondsToday: number`, `fatigueSignal: boolean`, `dailyCeiling: number | null`; derived from attention API

**Acceptance:**

- Each store initializes with safe defaults
- Stores are independent (no circular imports)
- Regime store exposes `a_t` as a continuous number for interpolation calculations

---

## Group B: Pulse Surface (Regime-Adaptive, Attention Budget)

### B-01 -- Regime gauge and band interpolation engine

**Spec:** 06 S3 (visualization bands), 06 S5 (transitions are continuous, 500ms drift), 09 S2 (regime-adaptive reshape)
**Objective:** Build the regime gauge component and the CSS interpolation engine that smoothly transitions between the four bands as `a_t` changes.
**Scope:**

- `apps/web/elements/regime/RegimeGauge.tsx` -- horizontal gauge showing `a_t` position on [0,1] axis, with four band regions color-coded (calm/elevated/urgent/crisis), transition-pressure indicator as a secondary mark
- `apps/web/elements/regime/useBandInterpolation.ts` -- hook that takes `a_t` and returns interpolated CSS values (accent color as RGB blend, layout weight for promoted/demoted surfaces, opacity values); uses `requestAnimationFrame` with 500ms easing
- `apps/web/elements/regime/BandColor.tsx` -- utility that returns the correct CSS color variable for a given `a_t` value, interpolating between band boundaries (0-0.25 Calm, 0.25-0.50 Elevated, 0.50-0.75 Urgent, 0.75-1.0 Crisis)
- `apps/web/elements/regime/TransitionPressureGauge.tsx` -- small gauge showing `changepointProbability` per 06 S5

**Critical rule:** No hard-flip between bands. The interpolation is always smooth. Band boundaries are soft thresholds.

**Acceptance:**

- Gauge renders `a_t` position with correct band coloring
- Moving `a_t` from 0.1 to 0.8 produces a smooth 500ms color/position animation
- Band colors interpolate at boundaries (e.g., at 0.24 the color is a blend of calm-green and elevated-gold)

---

### B-02 -- Pulse Calm layout

**Spec:** 09 S6.1 (Calm layout: portfolio value hero, small regime gauge, recent actions feed, market context strip)
**Objective:** Build the Calm-band Pulse layout. This is the default daily view -- portfolio value hero, unobtrusive regime gauge, recent autonomous actions, and market context.
**Scope:**

- `apps/web/app/(shell)/pulse/page.tsx` -- server component that wraps the PulseShell
- `apps/web/elements/pulse/PulseShell.tsx` -- client component that reads `a_t` from regime store and renders the appropriate sub-layout (Calm/Elevated/Urgent/Crisis)
- `apps/web/elements/pulse/PulseCalmLayout.tsx` -- Calm-specific layout:
  - Hero section: portfolio NAV (large, FinancialFigure), daily change %, YTD change %
  - Regime gauge (small, bottom-right of hero)
  - Recent actions feed: last 3-5 autonomous actions with one-line rationale each, tap to expand
  - Market context strip: VIX, SPX, DXY at bottom (placeholder until market data API exists)
- Each sub-component in `elements/pulse/` with its own loading skeleton

**Acceptance:**

- Calm layout renders when `a_t < 0.25`
- NAV hero shows portfolio value with daily and YTD change in gain-green/loss-red
- Recent actions feed shows list items with expand/collapse
- Loading skeleton matches the Calm layout shape

---

### B-03 -- Pulse Elevated layout

**Spec:** 09 S6.2 (Elevated: approval queue at top, amber accents, regime gauge prominent, recent actions collapsed)
**Objective:** Build the Elevated-band Pulse layout. Approval queue returns to top with amber accents.
**Scope:**

- `apps/web/elements/pulse/PulseElevatedLayout.tsx` -- Elevated-specific layout:
  - Top section: 1-3 pending decision cards with thesis + dollar impact + decision window
  - Hero section: portfolio value (smaller than Calm, demoted to secondary position)
  - Regime gauge: prominent, amber-accented, larger than Calm
  - Recent actions: collapsed to two lines
  - Notification indicator showing pending push notifications

**Acceptance:**

- Elevated layout renders when `0.25 <= a_t < 0.50`
- Decision cards show pending decisions from the decisions API
- Amber accent color applied to regime gauge and decision card borders
- Layout transition from Calm to Elevated is animated (500ms regime interpolation)

---

### B-04 -- Pulse Urgent layout

**Spec:** 09 S6.3 (Urgent: full-width highest-weight decision, progress bar for window, approve/modify/reject/debate with spatial separation, kill-switch visible)
**Objective:** Build the Urgent-band Pulse layout. Single-decision focus mode with all moments-of-truth rules.
**Scope:**

- `apps/web/elements/pulse/PulseUrgentLayout.tsx` -- Urgent-specific layout:
  - Full-width: single highest-weight pending decision with summary card
  - Decision window progress bar (NOT countdown timer -- per 10 S6.1)
  - Action buttons with spatial separation: Approve at top as primary action, Reject at bottom as secondary action offset to the right (per 10 S2.2)
  - Secondary: other pending decisions as a list below the focus card
  - Minimal: portfolio value as a sidebar indicator, not hero
  - Kill-switch button: always visible in the header

**Critical rules (specs/10):**

- Approve and Reject buttons NEVER adjacent on the same row
- Decision window shown as a progress bar, never a countdown timer
- Approve requires re-auth (ReAuthModal) for Urgent/Crisis bands per 10 S2.3

**Acceptance:**

- Urgent layout renders when `0.50 <= a_t < 0.75`
- Single focus decision dominates the viewport
- Progress bar shows decision window remaining
- Approve and Reject buttons are on different visual rows / spatially separated
- Kill-switch visible in header

---

### B-05 -- Pulse Crisis layout and kill-switch banner

**Spec:** 09 S6.4 (Crisis: red emergency banner, trading paused unmistakable, kill-switch state visible, non-essential demoted), 10 S5 (kill switch unmissable)
**Objective:** Build the Crisis-band Pulse layout with the unmistakable kill-switch banner.
**Scope:**

- `apps/web/elements/pulse/PulseCrisisLayout.tsx` -- Crisis-specific layout:
  - Full-width red emergency banner at top: "TRADING PAUSED" with pulsing border animation (subtle, not aggressive -- no stress-inducing design per 10 S6.3)
  - Kill-switch state: visible, accessible, shows confirmation code status
  - Portfolio: value shown for reference but not hero; small card at bottom
  - Decisions: deferred except for envelope changes, kill-switch clear, and explicit user-initiated actions
  - All non-essential surfaces demoted: no recent actions feed, no market context strip
- `apps/web/elements/pulse/KillSwitchBanner.tsx` -- reusable banner component: red background, "KILL SWITCH ACTIVE -- TRADING PAUSED" text, clear button (routes to Settings kill-switch clear flow), always-on-top positioning

**Critical rules (specs/10 S5):**

- Kill-switch state is unmissable -- user sees "trading paused" before any number
- No decision executes while switch is active
- No "undo" affordance on the trip (10 S5.3)
- Clear button routes to Settings with process-lock flow (08 S5.4)

**Acceptance:**

- Crisis layout renders when `a_t >= 0.75`
- Red banner is the first element the user sees
- Kill-switch clear button is present and routes to Settings
- Non-essential elements are hidden or collapsed

---

## Group C: Decisions Surface (Brief Rendering, Approval Flow)

### C-01 -- Decision list and card components

**Spec:** 09 S7 (Decisions: approval tap with enough context), 09 S4 (brief density matrix)
**Objective:** Build the Decisions surface route with the decision list and decision card components.
**Scope:**

- `apps/web/app/(shell)/decisions/page.tsx` -- Decisions surface page, reads pending decisions via `useDecisions('pending')`
- `apps/web/elements/decisions/DecisionList.tsx` -- renders filtered list of decision cards with loading skeleton
- `apps/web/elements/decisions/DecisionCard.tsx` -- top-of-fold card showing: decision type, instruments, action summary, confidence badge, dollar impact, decision window progress bar, action buttons (Approve, Debate, Decline) with spatial separation per 10 S2.2
- `apps/web/elements/decisions/BatchReviewPanel.tsx` -- batch review mode for digest-form approvals (per 09 S3.2, when attention budget detects fatigue)

**Acceptance:**

- Decision list renders pending decisions from API
- Each card shows thesis, confidence, and dollar impact
- Action buttons are spatially separated
- Batch review mode available via toggle

---

### C-02 -- Brief renderer with density matrix

**Spec:** 07 S2 (brief contract: 7 mandatory sections), 09 S4 (brief density matrix: 4 levels)
**Objective:** Build the brief renderer that displays all 7 mandatory sections at variable density based on `(a_t band x dollar impact x confidence tier)`.
**Scope:**

- `apps/web/elements/decisions/BriefRenderer.tsx` -- renders brief based on density level:
  - **Compressed** (low weight): thesis + key number + "what would change my mind" + tap-to-expand
  - **Structured** (medium): all 7 sections concise
  - **Full** (high): full structured + pinned summary card + calibration history + pool disagreement callout
  - **Extreme** (crisis/OOD): full brief + honesty banner + required review before action
- `apps/web/elements/decisions/BriefSection.tsx` -- renders a single brief section (Thesis, Evidence, IfApproved, IfRejected, HistoricalPrecedent, WhatWouldChangeMind, Confidence) with provenance indicators
- `apps/web/elements/decisions/HonestyBanner.tsx` -- "I am less calibrated in this state" banner for OOD conditions per 10 S8.1
- `apps/web/elements/decisions/ConfidenceDistribution.tsx` -- renders confidence as a distribution (not single number) per 07 S2.7

**Acceptance:**

- Brief renders all 7 sections when density is Structured or above
- Compressed brief shows thesis + key number with tap-to-expand
- HonestyBanner renders when OOD score exceeds threshold
- Confidence shows as a range/distribution, never a single number

---

### C-03 -- Approval flow with re-auth and quote-moved guard

**Spec:** 10 S2 (approval tap: spatial separation, biometric/re-auth, quote-moved-since-brief), 10 S6.4 (quote-moved check at approval time)
**Objective:** Build the full approval flow including re-auth gate and quote-moved-since-brief check.
**Scope:**

- `apps/web/elements/decisions/ApprovalFlow.tsx` -- manages the multi-step approval flow:
  1. User taps Approve
  2. If Urgent/Crisis band OR above dollar threshold: show ReAuthModal (10 S2.3)
  3. After re-auth: fetch fresh quote from backend, compare to brief-time quote
  4. If price moved > regime-adaptive threshold (Calm 0.5%, Elevated 0.3%, Urgent 0.2%): show QuoteMovedDialog
  5. If price within threshold: submit approval
- `apps/web/elements/decisions/QuoteMovedDialog.tsx` -- "Price moved X% since brief. Proceed at current price, set a limit, or cancel?" per 10 S6.4
- `apps/web/elements/decisions/DeclineFlow.tsx` -- decline action, no re-auth required but confirmation step needed
- Approval and decline both call the backend API: `POST /api/v1/decisions/{id}/approve` or `/decline`

**Critical rules:**

- Approve and Reject are NEVER adjacent on the same row (10 S2.2)
- Re-auth required for Urgent/Crisis bands (10 S2.3)
- Quote-moved check happens AFTER re-auth, BEFORE submission (10 S6.4)
- If thesis invalidated mid-window, decision is auto-revised with update (10 S6.4)

**Acceptance:**

- Approve in Calm/Elevated below threshold: direct submission
- Approve in Urgent/Crisis: re-auth modal appears first
- Quote moved beyond threshold: QuoteMovedDialog shows with proceed/limit/cancel options
- Decline: confirmation step, no re-auth

---

## Group D: Debate Surface (Thread, Tools, Resolution)

### D-01 -- Debate slide-in overlay and thread list

**Spec:** 09 S5.1 (Debate opens as slide-in from right, overlayable on any screen), 09 S8.1 (universal accessibility), 09 S8.2 (thread list)
**Objective:** Build the Debate slide-in overlay that opens from any surface, plus the dedicated Debate tab with thread list.
**Scope:**

- `apps/web/elements/debate/DebateOverlay.tsx` -- Shadcn Sheet component sliding from right, renders over current surface, reads `originatingContext` from debate-overlay store
- `apps/web/elements/debate/DebateOverlayTrigger.tsx` -- small floating button rendered on every surface that opens the Debate overlay with the current context (decision ID, position ticker, signal ID, etc.)
- `apps/web/app/(shell)/debate/page.tsx` -- dedicated Debate tab showing thread list
- `apps/web/elements/debate/ThreadList.tsx` -- list of recent/active threads with: originating context, resolution state badge (updated/maintained/open/envelope-change), last activity timestamp, tap to resume
- `apps/web/elements/debate/ThreadCard.tsx` -- individual thread in the list

**Acceptance:**

- Debate overlay slides in from right on any surface
- Overlay pre-loads with the current surface's context
- Dedicated Debate tab shows thread list with resolution state badges
- Thread list reads from debate API

---

### D-02 -- Debate thread composer and message rendering

**Spec:** 07 S3.2 (debate is joint evidence review), 07 S3.3 (10 tool affordances), 07 S3.4 (confidence and uncertainty), 09 S8.3 (composition affordances)
**Objective:** Build the thread view with message rendering, user input, and tool-action buttons.
**Scope:**

- `apps/web/elements/debate/ThreadView.tsx` -- renders full thread with messages and input
- `apps/web/elements/debate/MessageBubble.tsx` -- renders agent or user message; agent messages show provenance pointers for every claim (07 S3.4)
- `apps/web/elements/debate/DebateInput.tsx` -- free-text input for the user, submit calls `POST /api/v1/debate/threads/{id}/messages`
- `apps/web/elements/debate/ToolActionBar.tsx` -- toolbar of action buttons the agent surfaces per 07 S3.3:
  - "Update decision to X%"
  - "Keep at Y%"
  - "Run alt-backtest"
  - "Show calibration curve"
  - "Retrieve analogues"
  - "Recompute with constraint"
  - "Generate counterfactual"
  - "Surface override pattern"
  - "Query fabric"
  - "Query head"
- `apps/web/elements/debate/InlineVisualization.tsx` -- renders charts/tables generated by tool calls inline in the thread

**Acceptance:**

- Thread view renders messages in chronological order
- Agent messages show provenance indicators
- User can type and submit messages
- Tool action buttons appear when agent surfaces them
- Inline visualizations render within the thread flow

---

### D-03 -- Debate resolution states

**Spec:** 07 S3.5 (4 resolution states: updated, maintained, open, envelope-change)
**Objective:** Build the resolution UI that shows thread state and routes the user to the appropriate next step.
**Scope:**

- `apps/web/elements/debate/ResolutionBanner.tsx` -- banner at top of thread showing current resolution state:
  - **Decision updated**: "Recommendation updated. Review and approve/reject." with link back to Decisions surface
  - **Decision maintained**: "Recommendation stands. Return to decisions." with dismiss
  - **Open/thinking out loud**: "Thread active. Resume anytime." with no forced action
  - **Envelope change proposed**: "This implicates your trust boundary." with link to Settings envelope flow
- `apps/web/elements/debate/ThreadStatusBadge.tsx` -- small colored badge for thread list

**Acceptance:**

- Each resolution state renders with the correct banner text and action
- "Decision updated" links back to the specific decision in Decisions surface
- "Envelope change proposed" routes to Settings with envelope context

---

## Group E: Portfolio Surface (Allocation, Positions, Drift)

### E-01 -- Portfolio overview and allocation bars

**Spec:** 09 S9.1 (horizontal allocation bars, not pie charts; target vs current with drift highlighted), 12 S3 (Brinson attribution)
**Objective:** Build the Portfolio surface with allocation visualization using horizontal bars (NOT pie charts -- this is an anti-pattern per 09 S11).
**Scope:**

- `apps/web/app/(shell)/portfolio/page.tsx` -- Portfolio surface page
- `apps/web/elements/portfolio/PortfolioOverview.tsx` -- NAV hero, total return, risk summary
- `apps/web/elements/portfolio/AllocationBars.tsx` -- horizontal bars showing:
  - Target weight (background bar, muted color)
  - Current weight (foreground bar, accent color)
  - Drift highlighted in loss-red when exceeding threshold
  - No pie charts -- ever (anti-pattern lint in Group J)
- `apps/web/elements/portfolio/AttributionCard.tsx` -- Brinson attribution display: allocation effect, selection effect, interaction effect per 12 S3
- Loading skeletons for each component

**Acceptance:**

- Allocation bars render target vs current with drift highlighting
- No pie charts exist anywhere in the component
- Attribution card shows three decomposition effects
- All data from portfolio API with loading skeletons

---

### E-02 -- Position list with sorting and drill-through

**Spec:** 09 S9.1 (position list sortable by weight, P&L, drift; each position links to history, risk contribution, debate thread)
**Objective:** Build the sortable position list with drill-through to position detail.
**Scope:**

- `apps/web/elements/portfolio/PositionList.tsx` -- table/list of positions sortable by: weight, unrealized P&L, drift from target, risk contribution
- `apps/web/elements/portfolio/PositionRow.tsx` -- individual position row showing: ticker, quantity, avg cost, current price, market value, unrealized P&L, drift percentage, risk contribution badge
- `apps/web/elements/portfolio/PositionDetailSheet.tsx` -- slide-in sheet when tapping a position:
  - Position history (mini chart or table)
  - Contribution to portfolio risk
  - Link to debate thread if one exists for this position
  - Link to related decisions

**Acceptance:**

- Position list renders all positions from API
- Sorting works on weight, P&L, drift columns
- Tapping a position opens detail sheet with history and links
- FinancialFigure used for all numeric values

---

### E-03 -- Risk metrics display

**Spec:** 12 S2 (primary metrics: Sharpe, Sortino, max drawdown, tracking error, VaR, volatility, IR, alpha, M-squared, Treynor)
**Objective:** Build the risk metrics section of the Portfolio surface.
**Scope:**

- `apps/web/elements/portfolio/RiskMetricsPanel.tsx` -- grid of risk metrics:
  - Volatility (annualized)
  - Sharpe ratio
  - Sortino ratio
  - Max drawdown
  - Tracking error vs SAA baseline
  - VaR (95%)
  - Information Ratio
  - Alpha (Jensen's)
  - M-squared
  - Treynor Ratio
- Each metric rendered as a card with the value, description, and benchmark comparison where applicable
- Metrics load from `usePortfolioRisk()` hook

**Acceptance:**

- All 10 risk metrics render with correct formatting
- Values use FinancialFigure for tabular-nums
- Benchmark comparisons shown where applicable

---

## Group F: Backtest Surface (Scorecard, Regime Breakdown, What-If)

### F-01 -- Backtest scorecard and equity curve

**Spec:** 09 S9.2 (scorecard first, equity curve second), 12 S2 (primary metrics)
**Objective:** Build the Backtest surface with scorecard-first layout.
**Scope:**

- `apps/web/app/(shell)/backtest/page.tsx` -- Backtest surface page
- `apps/web/elements/backtest/BacktestScorecard.tsx` -- scorecard grid showing: total return, Sharpe, max drawdown, Calmar, turnover, cost drag, win rate, worst drawdown period; rendered BEFORE equity curve
- `apps/web/elements/backtest/EquityCurve.tsx` -- line chart of equity over time (use a lightweight charting library or SVG-based component; avoid heavy charting dependencies)
- `apps/web/elements/backtest/ScenarioSelector.tsx` -- dropdown/selector for predefined backtest scenarios from API

**Acceptance:**

- Scorecard renders above the equity curve
- All metric cards show values with FinancialFigure
- Equity curve renders a time series
- Scenario selector lists scenarios from API

---

### F-02 -- Backtest regime breakdown and what-if panels

**Spec:** 09 S9.2 (regime breakdown using historical z_t analogues, sub-horizon consistency, cost sensitivity, what-if scenarios for envelope changes)
**Objective:** Build the regime breakdown and what-if analysis sections of the Backtest surface.
**Scope:**

- `apps/web/elements/backtest/RegimeBreakdown.tsx` -- table showing performance metrics broken down by historical `z_t` analogue periods
- `apps/web/elements/backtest/SubHorizonConsistency.tsx` -- view showing whether performance was consistent across sub-periods (not just aggregate positive)
- `apps/web/elements/backtest/CostSensitivity.tsx` -- slider/display showing how total return changes with transaction cost assumptions
- `apps/web/elements/backtest/WhatIfPanel.tsx` -- form for envelope-change what-if: user adjusts drawdown ceiling, concentration cap, etc., and sees simulated impact; calls `POST /api/v1/backtest/run` with modified parameters

**Acceptance:**

- Regime breakdown renders with performance per historical period
- What-if panel allows parameter adjustment and submits a new backtest run
- Cost sensitivity shows return impact of cost variation
- All results use loading skeletons during backtest execution

---

## Group G: Signal Surface (News Feed, Impact Tags)

### G-01 -- Signal news feed with impact filtering

**Spec:** 09 S9.3 (items filtered by portfolio impact; none=deprioritized, high=promoted; tap to drill into decision impact)
**Objective:** Build the Signal surface with portfolio-impact-filtered news feed.
**Scope:**

- `apps/web/app/(shell)/signal/page.tsx` -- Signal surface page
- `apps/web/elements/signal/SignalList.tsx` -- news feed sorted by portfolio impact (high first, none last), filterable by ticker and impact level
- `apps/web/elements/signal/SignalCard.tsx` -- individual news item showing: headline, ticker badge, sentiment indicator, portfolio impact badge (high/medium/low/none), published timestamp
- `apps/web/elements/signal/SignalDetailSheet.tsx` -- tap to drill: shows how the item would or would not affect pending decisions; links to related Debate thread if one exists
- `apps/web/elements/signal/ResearchSearch.tsx` -- search bar for RAG research corpus, calls `POST /api/v1/signal/research`

**Acceptance:**

- Signal list renders news items sorted by impact
- Impact badges are color-coded (high=loss-red, medium=accent-gold, low=regime-calm, none=muted)
- Tapping a news item opens detail sheet with decision impact analysis
- Research search returns results from the filings corpus

---

## Group H: Settings Surface (Envelope, Autonomy, Kill-Switch)

### H-01 -- Settings envelope editor

**Spec:** 08 S1 (trust boundary parameters: user-owned), 10 S7 (envelope changes: widening requires biometric, tightening is notification-only), 11 S5 (envelope enforcement)
**Objective:** Build the envelope parameter editor with proper widening/tightening distinction.
**Scope:**

- `apps/web/app/(shell)/settings/page.tsx` -- Settings surface page with tabbed sections
- `apps/web/elements/settings/EnvelopeEditor.tsx` -- form displaying current envelope parameters:
  - Drawdown ceiling
  - Vol target band (low/high)
  - Concentration caps (position, sector)
  - Cost budget ceiling
  - Universe exclusions
- `apps/web/elements/settings/EnvelopeChangeFlow.tsx` -- handles the change flow:
  - Detect whether change is widening or tightening
  - Widening: triggers ReAuthModal, shows impact brief (simulated performance under new envelope, affected positions), requires biometric confirmation
  - Tightening: shows notification of when change takes effect, no re-auth needed
  - Calls `PUT /api/v1/settings/envelope`

**Critical rules (specs/10 S7):**

- Envelope changes are always user-facing decisions with their own brief
- Widening requires biometric/re-auth
- Midas may not propose envelope widening -- only tightening (08 S1)
- Tightening takes effect on next decision cycle with notification

**Acceptance:**

- Envelope editor shows all parameters with current values
- Widening a parameter triggers re-auth and impact brief
- Tightening a parameter shows notification without re-auth
- API call includes change direction metadata

---

### H-02 -- Autonomy level viewer and upgrade proposals

**Spec:** 08 S2 (autonomy ladder: L0-L4), 08 S3 (promotion protocol), 08 S7 (upgrade contracts)
**Objective:** Build the autonomy level display with upgrade proposal handling.
**Scope:**

- `apps/web/elements/settings/AutonomyViewer.tsx` -- displays:
  - Current autonomy level with human-readable name and description
  - Days at current level
  - Upgrade eligibility status
  - What would change at the next level
  - Historical log of level changes with dates and reasons
- `apps/web/elements/settings/UpgradeProposalCard.tsx` -- when an upgrade is proposed, shows:
  - Operating history summary
  - Brinson attribution snapshot
  - Calibration snapshot
  - Override log
  - What changes at the new level
  - Approve / Decline buttons

**Acceptance:**

- Current level displayed with description
- Upgrade proposals surface as actionable cards
- Approve/Decline buttons on proposal cards
- Level change history shown

---

### H-03 -- Kill-switch controls and paper/live state

**Spec:** 08 S5 (kill switch), 08 S6 (paper-to-live gate), 10 S3 (paper-to-live transition rules), 10 S5 (kill-switch rules)
**Objective:** Build the kill-switch control panel and paper/live state display.
**Scope:**

- `apps/web/elements/settings/KillSwitchPanel.tsx`:
  - Current kill-switch status (active/cleared)
  - Activate button: one tap + re-auth confirmation
  - Clear button: visible when active, routes through process-lock flow:
    1. ReAuthModal
    2. State-of-the-world brief display (z_t, drawdown, pool disagreement, compliance events) -- user must read and acknowledge
    3. 60-second dwell timer before first post-clear decision
    4. Calls `POST /api/v1/settings/kill-switch/clear`
- `apps/web/elements/settings/PaperLivePanel.tsx`:
  - Current mode (paper/live)
  - Paper trading progress: days elapsed, days remaining for 2-week minimum
  - Eligibility for live transition: blocking conditions list (per 08 S6.3)
  - "Go Live" button: disabled until all blocking conditions met; requires:
    1. Paper report viewed and acknowledged
    2. ReAuthModal confirmation
    3. 2-week minimum enforced at backend
  - Post-transition indicator: "First 7 days at L1" banner

**Critical rules:**

- Kill-switch clear reverts to L1 regardless of prior level (08 S5.4)
- No "skip paper trading" affordance anywhere (10 S3.1)
- First 7 live days at L1 regardless (08 S6.4)
- Auto-trip cool-down is process-lock, not time-lock (08 S5.4)

**Acceptance:**

- Kill-switch panel shows status with activate/clear actions
- Clear flow includes state brief + dwell timer
- Paper/live panel shows progress and blocking conditions
- "Go Live" disabled until conditions met

---

### H-04 -- Notification preferences and data source status

**Spec:** 09 S3.3 (attention is a user setting), 09 S7 (notification tiering by band), 11 S7.2 (scheduler architecture)
**Objective:** Build notification settings and data source health display.
**Scope:**

- `apps/web/elements/settings/NotificationPreferences.tsx`:
  - Daily attention ceiling slider
  - Notification tier toggles per band (Calm: silent, Elevated: standard push, Urgent: prominent + haptic, Crisis: emergency)
  - Quiet hours configuration (batch Elevated notifications during quiet hours)
- `apps/web/elements/settings/DataSourceStatus.tsx`:
  - List of data sources with health status (healthy/error/unknown)
  - Last-seen timestamp for each source
  - Reads from `GET /api/v1/settings/data-sources`
- `apps/web/elements/settings/ComplianceRuleViewer.tsx`:
  - Read-only list of active compliance rules (v1)
  - Rule detail: name, category, severity, description
  - Reads from `GET /api/v1/compliance/rules`

**Acceptance:**

- Notification preferences render per-band toggles
- Data source status shows health for each source
- Compliance rules render read-only list

---

## Group I: Safety and Real-Time

### I-01 -- WebSocket connection for regime updates

**Spec:** 06 S5 (transitions are continuous, not events), 09 S2 (layout interpolation animated over hundreds of ms)
**Objective:** Establish a WebSocket connection that pushes `a_t` updates to the frontend for smooth regime interpolation. The backend WebSocket endpoint does not yet exist; this task creates the client-side infrastructure with a polling fallback.
**Scope:**

- `apps/web/lib/websocket.ts` -- WebSocket client that:
  - Connects to `ws://API_URL/ws/regime` (fallback: polling `/api/v1/pulse/regime` every 2s)
  - Receives `{ a_t, band, ood_score, changepoint_probability }` updates
  - Updates the regime Zustand store on each message
  - Auto-reconnects with exponential backoff
  - Falls back to polling if WebSocket connection fails after 3 attempts
- `apps/web/elements/regime/RegimeSubscription.tsx` -- component mounted at shell level that initiates the WebSocket/polling subscription and feeds data into the regime store

**Acceptance:**

- WebSocket client connects and receives regime updates
- Regime store updates trigger smooth interpolation in Pulse
- Polling fallback activates when WebSocket fails
- No jarring layout changes when switching between WS and polling

---

### I-02 -- OOD honesty banner component

**Spec:** 10 S8 (OOD escalation: honesty banner, all autonomy reverts to L1, no autonomous actions)
**Objective:** Build the re-usable OOD honesty banner that renders on any surface when `ood_score` exceeds threshold.
**Scope:**

- `apps/web/elements/safety/OODBanner.tsx` -- banner component:
  - Shows "I am less calibrated in this state" text per 10 S8.1
  - Explains what OOD means in plain language
  - Visible on Pulse, Decisions, and any surface with pending decisions
  - Condition: `ood_score > OOD_THRESHOLD` (configurable, default 0.7)
- Mount this banner in the shell layout so it appears globally when OOD is detected

**Acceptance:**

- Banner renders when ood_score exceeds threshold
- Banner text is plain language, not jargon
- Banner is visible from any surface

---

### I-03 -- Quote-moved-since-brief guard integration

**Spec:** 10 S6.4 (quote-moved check at approval time with regime-adaptive thresholds)
**Objective:** Create the client-side quote-moved guard that checks price drift between brief composition and approval submission.
**Scope:**

- `apps/web/lib/quote-guard.ts` -- utility function:
  - Takes: brief-time quote, current quote, current `a_t` band
  - Returns: `{ moved: boolean, deltaPct: number, threshold: number }`
  - Thresholds: Calm 0.5%, Elevated 0.3%, Urgent 0.2%
- Integration with ApprovalFlow (C-03): this guard runs after re-auth, before submission

**Acceptance:**

- Guard correctly computes price delta and compares to band-appropriate threshold
- Returns moved=true when delta exceeds threshold
- Integration point is between re-auth success and approval submission

---

### I-04 -- Paper-to-live transition guard UI

**Spec:** 10 S3 (paper-to-live: explicit user action, 2-week minimum, report viewed, biometric, no "skip" affordance)
**Objective:** Build the paper-to-live transition flow that enforces all blocking conditions.
**Scope:**

- `apps/web/elements/safety/PaperToLiveFlow.tsx` -- multi-step flow:
  1. Check blocking conditions (14 days, no subsystem failures, no critical anomalies)
  2. If blocked: show list of unmet conditions with explanations
  3. If eligible: show paper trading report in a review surface
  4. User must scroll through report and acknowledge ("I have reviewed this report")
  5. "Go Live" button activates only after acknowledgment
  6. Tapping "Go Live" triggers ReAuthModal
  7. Confirmation screen: "You are transitioning to live trading. First 7 days will require approval for every decision."
  8. Calls backend endpoint to transition

**Critical rules:**

- No "skip paper trading" affordance anywhere in the UI
- 2-week minimum enforced at backend AND reflected in UI
- Report must be viewed (not just opened) before button activates
- First 7 days at L1 displayed prominently after transition

**Acceptance:**

- Blocking conditions checked and displayed
- Report review requires scroll + explicit acknowledgment
- "Go Live" disabled until all conditions met
- Post-transition banner shows L1 for 7 days

---

## Group J: Testing and Accessibility

### J-01 -- Playwright E2E test foundation

**Spec:** All surface specs; testing rules (3-tier, real infrastructure)
**Objective:** Set up Playwright E2E test infrastructure with baseline tests for each surface.
**Scope:**

- `apps/web/playwright.config.ts` -- Playwright config targeting Chromium, base URL `http://localhost:3000`
- `apps/web/tests/e2e/auth.spec.ts` -- login/logout flow
- `apps/web/tests/e2e/pulse.spec.ts` -- Pulse renders, regime gauge visible, data loads from API
- `apps/web/tests/e2e/decisions.spec.ts` -- Decision list renders, brief expands, approve triggers re-auth
- `apps/web/tests/e2e/debate.spec.ts` -- Debate overlay opens from Pulse, thread list renders
- `apps/web/tests/e2e/portfolio.spec.ts` -- Portfolio renders allocation bars, position list sorts
- `apps/web/tests/e2e/settings.spec.ts` -- Settings loads envelope, autonomy, kill-switch state

**Acceptance:**

- All test files execute without error against a running dev server
- Each test verifies the surface renders with real data (not mocks)
- State persistence verified with read-back where applicable

---

### J-02 -- WCAG accessibility audit and fixes

**Spec:** 09 S5.1 (min 1024px), design tokens (contrast ratios)
**Objective:** Ensure the web app meets WCAG AA standards across all surfaces.
**Scope:**

- Run `axe-core` accessibility audit against all surface pages
- Fix findings:
  - Color contrast: verify all text meets 4.5:1 contrast ratio against dark backgrounds
  - Focus management: left-rail navigation is keyboard-navigable, debate overlay traps focus correctly
  - ARIA labels: regime gauge, progress bars, financial figures all have appropriate labels
  - Screen reader: financial figures announced with correct semantics (e.g., "portfolio value: $50,423, up 1.2 percent")
  - Skip navigation: skip-to-content link for keyboard users
- `apps/web/tests/e2e/accessibility.spec.ts` -- automated accessibility checks

**Acceptance:**

- axe-core reports zero critical/serious issues
- Keyboard navigation works across all surfaces
- Financial figures are screen-reader accessible
- Focus trap works in Debate overlay and modal dialogs

---

### J-03 -- Anti-patterns lint (ESLint custom rules)

**Spec:** 09 S11 (anti-patterns: pie charts, countdown timers, adjacent approve/reject, same template for different weight decisions)
**Objective:** Create ESLint custom rules that fail CI on spec-violating UI patterns.
**Scope:**

- `apps/web/eslint-rules/no-pie-charts.js` -- detects pie chart library imports or chart type configurations
- `apps/web/eslint-rules/no-countdown-timers.js` -- detects countdown timer components or patterns (string "countdown", "time remaining" with seconds-level precision)
- `apps/web/eslint-rules/no-adjacent-approve-reject.js` -- detects Approve and Reject buttons rendered adjacent in the same container without spatial separation
- `apps/web/eslint-rules/no-modals-for-financial-actions.js` -- detects modal/dialog usage for approval, kill-switch, or envelope change flows (use full pages or sheets instead)
- Register rules in `apps/web/eslint.config.mjs`

**Acceptance:**

- Each lint rule detects its target anti-pattern
- Rules fail CI on violation
- Existing code passes all rules

---

### J-04 -- Attention budget display and fatigue detection UI

**Spec:** 09 S3 (attention budget: decision-seconds, decision volume, notification volume, fatigue signals)
**Objective:** Build the attention budget visualization that shows users how their attention is being spent.
**Scope:**

- `apps/web/elements/attention/AttentionBudgetGauge.tsx` -- small gauge showing daily attention consumption vs ceiling
- `apps/web/elements/attention/FatigueWarning.tsx` -- warning banner: "You are approving without reading the full brief. Consider taking a break." per 09 S3.2
- `apps/web/elements/attention/AttentionReport.tsx` -- weekly report card showing: decision-seconds per day, decision volume, time-to-decide distribution, override rate
- Mount AttentionBudgetGauge in the shell header (visible from all surfaces)

**Acceptance:**

- Attention gauge renders in shell header
- Fatigue warning renders when heuristic trips
- Weekly attention report accessible from Settings

---

## Dependency Graph

```
A-01 (scaffold) ──> A-02 (components) ──> A-03 (API client) ──> A-04 (auth)
                                                                ──> A-05 (stores)
A-01..A-05 ──> B-01 (regime gauge)
B-01 ──> B-02 (Calm) ──> B-03 (Elevated) ──> B-04 (Urgent) ──> B-05 (Crisis)
A-03, A-04 ──> C-01 (decision list) ──> C-02 (brief renderer) ──> C-03 (approval flow)
A-05 ──> D-01 (debate overlay) ──> D-02 (thread composer) ──> D-03 (resolution)
A-03 ──> E-01 (allocation) ──> E-02 (positions) ──> E-03 (risk metrics)
A-03 ──> F-01 (scorecard) ──> F-02 (regime breakdown)
A-03 ──> G-01 (signal feed)
A-03, A-04 ──> H-01 (envelope) ──> H-02 (autonomy) ──> H-03 (kill-switch, paper/live)
                                        ──> H-04 (notifications)
A-05 ──> I-01 (WebSocket) ──> I-02 (OOD banner)
C-03 ──> I-03 (quote-moved guard)
H-03 ──> I-04 (paper-to-live guard)
All surfaces ──> J-01 (E2E), J-02 (accessibility), J-03 (lint rules), J-04 (attention)
```

## Execution Order (Recommended)

1. A-01 through A-05 (foundation -- must complete first)
2. B-01 through B-05 (Pulse -- the primary surface)
3. I-01 (WebSocket -- enables real-time regime updates)
4. C-01 through C-03 (Decisions -- second most critical surface)
5. D-01 through D-03 (Debate -- overlayable from any surface)
6. E-01 through E-03 (Portfolio)
7. F-01, F-02 (Backtest)
8. G-01 (Signal)
9. H-01 through H-04 (Settings)
10. I-02, I-03, I-04 (safety components)
11. J-01 through J-04 (testing and accessibility)

**Total tasks:** 38
**Estimated sessions:** 25-30 (foundation and Pulse: 7, Decisions + Debate: 5, remaining surfaces: 8, safety + testing: 5-7, buffer for integration: 3-5)

## Gate Out

Web app runs end-to-end against real backend at `http://localhost:3000`. All 7 surfaces function with live data. No mock data remaining in production code. Attention metrics collected. Anti-pattern lint passes. WCAG AA compliance verified. All E2E tests pass.
