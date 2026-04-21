# Round 9 — Frontend Audit: Mock Data & Engine-First Compliance

Date: 2026-04-20
Auditor: react-specialist (convergence round)

## Executive Summary

The Midas frontend is **overwhelmingly engine-first**. All 9 query hook modules (`usePortfolio`, `useBacktest`, `usePulse`, `useDecisions`, `useSignal`, `useDebate`, `useSettings`, `useCompliance`, `useAudit`) route through a single `api-client.ts` that calls real backend endpoints. The Zustand stores derive their state from API responses (not hardcoded values). Every page renders data from `useQuery` hooks with proper loading skeletons and null-state messaging.

**However, there are 5 findings** -- 2 CRITICAL (mock/stub data violations of zero-tolerance Rule 2), 2 HIGH, and 1 MEDIUM.

---

## Step 1: Mock Data Findings

### CRITICAL-1: `PLACEHOLDER_DATA` in AttentionReport

**File:** `apps/web/elements/attention/AttentionReport.tsx:18-68`
**Line 150-151:**

```tsx
// Real implementation would fetch from /pulse/attention/weekly
const weeklyData = PLACEHOLDER_DATA;
```

A hardcoded 7-day array of zeros is the sole data source for the weekly attention report. The comment explicitly acknowledges it should be fetched from the API. This is a zero-tolerance Rule 2 violation (stubs / deferred implementation). The component renders four tabs (Decision Time, Volume, Time-to-Decide, Override Rate) all from this zero-filled constant.

**Also at line 192:** Override Rate displays a static em-dash with "not available" sub-text rather than attempting to fetch real data.

**Remediation:** Create a `useAttentionWeekly()` hook calling `GET /pulse/attention/weekly` and wire it into `AttentionReport`. Remove `PLACEHOLDER_DATA` entirely.

---

### CRITICAL-2: Hardcoded `$50,000` dollar impact in DecisionCard

**File:** `apps/web/elements/decisions/DecisionCard.tsx:109`

```tsx
const dollarImpact = decision.confidence * 50000; // Placeholder - would come from brief
```

The dollar impact displayed on every decision card is computed from a hardcoded `$50,000` multiplier, not from the brief or any API response. The comment acknowledges it is a placeholder.

**Remediation:** The `BriefResponse` type or `DecisionDetail` should include an `estimated_impact` field from the backend. Wire it through the component props.

---

### HIGH-1: Placeholder blocking conditions in PaperToLiveFlow

**File:** `apps/web/elements/safety/PaperToLiveFlow.tsx:49,56`

```tsx
met: true, // Placeholder — real impl would query subsystem health
met: true, // Placeholder — real impl would query anomaly status
```

Two of three blocking conditions for the paper-to-live transition are hardcoded to `met: true`. This means the gate always passes regardless of actual subsystem health or anomaly status.

**Remediation:** Query backend endpoints for subsystem health and anomaly status, or remove these conditions from the frontend and let the backend enforce them.

---

### HIGH-2: Placeholder report content in PaperToLiveFlow

**File:** `apps/web/elements/safety/PaperToLiveFlow.tsx:89-103`

```tsx
{
  /* Placeholder report content — real impl fetches from backend */
}
<p>Paper trading period summary will appear here...</p>;
```

The paper trading report shown before transitioning to live is static text, not fetched from any API. Users are asked to "review" content that contains no actual performance data.

**Remediation:** Fetch a paper trading report from the backend and render it in the scrollable container.

---

### MEDIUM-1: "Coming soon" stubs in PositionDetailSheet

**File:** `apps/web/elements/portfolio/PositionDetailSheet.tsx:117-132`

Two sections ("Position History" and "Risk Contribution") render static "coming soon" text. While these are supplementary sections (the core data -- metrics, allocation, drift -- comes from the API), the "coming soon" pattern is a zero-tolerance Rule 2 grey area. The PositionDetailSheet comment at line 17 also says "Placeholder for future data-fetching hooks."

**Remediation:** Either implement the data fetching for these sections or remove the empty sections entirely. A missing section is better than a stub that promises future functionality.

---

## Step 2: Engine-First Compliance

### Status: PASS (with caveats above)

All data-displaying components follow the engine-first pattern:

| Module             | Query Hook               | API Endpoint                        | Loading State  | Null State              |
| ------------------ | ------------------------ | ----------------------------------- | -------------- | ----------------------- |
| Portfolio Overview | `usePortfolio`           | `GET /portfolio/`                   | Skeleton       | "No return data"        |
| Allocation Bars    | `useAllocation`          | `GET /portfolio/allocation`         | Skeleton       | "No allocation data"    |
| Attribution Card   | `useAttribution`         | `GET /portfolio/attribution`        | Skeleton       | "No attribution data"   |
| Risk Metrics       | `useRiskMetrics`         | `GET /portfolio/risk`               | Skeleton       | "--" per metric         |
| Position List      | `usePositions`           | `GET /portfolio/positions`          | Skeleton       | "No positions"          |
| Backtest Runs      | `useBacktestRuns`        | `GET /backtest/runs`                | Skeleton       | "No backtest runs"      |
| Backtest Result    | `useBacktestResult`      | `GET /backtest/results/:id`         | Skeleton       | "Select a run"          |
| Pulse Shell        | `usePulse` + `useRegime` | `GET /pulse/` + `GET /pulse/regime` | Skeleton       | N/A                     |
| Decisions          | `useDecisions`           | `GET /decisions/?status=`           | Skeleton       | "Select a decision"     |
| Decision Brief     | `useBrief`               | `GET /decisions/:id/brief`          | N/A            | Conditional render      |
| Signals            | `useSignals`             | `GET /signal/`                      | Skeleton       | "No active signals"     |
| Debate Threads     | `useDebateThreads`       | `GET /debate/threads`               | Skeleton       | Thread list empty state |
| Debate Messages    | `useDebateThread`        | `GET /debate/threads/:id`           | Skeleton       | "No messages yet"       |
| Envelope Config    | `useEnvelopeConfig`      | `GET /settings/envelope`            | Skeleton       | "--" per field          |
| Autonomy State     | `useAutonomyState`       | `GET /settings/autonomy`            | Skeleton       | "--"                    |
| Kill Switch        | `useKillSwitch`          | `GET /compliance/kill-switch`       | N/A            | "No kill switch active" |
| Compliance Rules   | `useComplianceRules`     | `GET /compliance/rules`             | N/A            | "No rules configured"   |
| Attention Gauge    | `useAttention`           | `GET /pulse/attention`              | N/A            | Derived from store      |
| Research Search    | `api.post`               | `POST /signal/research`             | "Searching..." | "No research found"     |
| Paper-Live State   | `usePaperLiveState`      | `GET /settings/paper-live`          | Skeleton       | Conditional render      |
| Audit Log          | `useAuditLog`            | `GET /audit/?limit=`                | N/A            | N/A                     |

**API client architecture:** Single `api-client.ts` with typed `request<T>()` function handling auth token injection, 401 redirect, and error propagation via `ApiError` class. Clean separation of concerns.

**State flow:** API data flows through `useQuery` hooks into Zustand stores only for cross-component state (regime band, attention budget, kill switch). All stores initialize to safe defaults and are updated from API responses via `useEffect`.

---

## Step 3: COC Compliance

### Component Organization: PASS

All elements follow the `elements/` folder pattern:

- `elements/portfolio/` -- 7 components + index.tsx barrel
- `elements/backtest/` -- 7 components + index.tsx barrel
- `elements/pulse/` -- 5 components
- `elements/decisions/` -- 10 components + index.tsx barrel
- `elements/debate/` -- 9 components + index.tsx barrel
- `elements/signal/` -- 5 components + index.tsx barrel
- `elements/settings/` -- 9 components + index.tsx barrel
- `elements/safety/` -- 2 components
- `elements/attention/` -- 3 components
- `elements/regime/` -- 2 components

### Error Handling: MINOR FINDING

Two silent catch blocks found:

1. **`apps/web/elements/signal/ResearchSearch.tsx:41`:** `catch { setResults([]); }` -- silently swallows errors from `/signal/research`. No user-facing error message; just shows empty results.

2. **`apps/web/elements/debate/ThreadView.tsx:93`:** `catch { ... }` -- catches and silently handles. (Need to verify -- this may be intentional for the debate input, but should still surface an error state to the user.)

**Remediation:** Add error state display for the research search component (e.g., "Search failed. Please try again."). For the debate input, verify the catch block provides user feedback.

### Accessibility: PARTIAL PASS

Good:

- `role="alert"` on `OODBanner`, `KillSwitchBanner`, `FatigueWarning`
- `aria-label` on close buttons (SignalDetailSheet, DebateOverlay, Sidebar toggle, ThreadView)
- `aria-label` on action buttons (PulseUrgentLayout kill switch, approve, reject)
- Semantic HTML: `<nav>`, `<main>`, `<header>`, `<table>`, `<form>`
- `<label htmlFor>` on login form inputs

Gaps:

- No `aria-label` on sortable column headers in `PositionList`
- No `aria-live` region for dynamic content updates (e.g., pulse regime transitions)
- `FinancialFigure` component lacks `aria-label` for screen readers (values shown visually but not announced)
- Tab controls in `AttentionReport` and `DecisionsPage` lack `aria-selected` and proper `role="tablist"` semantics
- Filter controls in `SignalList` lack `aria-label`

### Responsive Design: PASS

Responsive patterns are consistent across all pages:

- Grid layouts use `grid-cols-1 lg:grid-cols-N` pattern throughout
- `PortfolioOverview`, `RiskMetricsPanel`, `PositionRow` use `sm:` and `md:` breakpoints
- `PositionList` hides sort headers on mobile, shows on `sm:`
- `AttentionReport` stat cards use `grid-cols-2 sm:grid-cols-4`
- ViewportGate blocks screens below 1024px with clear messaging
- All pages use consistent padding and spacing

---

## Step 4: Page Completeness

| Page          | Path                          | Status | Notes                                                                              |
| ------------- | ----------------------------- | ------ | ---------------------------------------------------------------------------------- |
| Root redirect | `/(shell)/page.tsx`           | PASS   | Redirects to `/pulse`                                                              |
| Layout        | `/(shell)/layout.tsx`         | PASS   | Sidebar + OOD banner + attention gauge + debate overlay                            |
| Pulse         | `/(shell)/pulse/page.tsx`     | PASS   | Full regime-adaptive shell with 4 layouts                                          |
| Portfolio     | `/(shell)/portfolio/page.tsx` | PASS   | NAV hero, allocation, attribution, risk, positions, detail sheet                   |
| Backtest      | `/(shell)/backtest/page.tsx`  | PASS   | Scenario selector, scorecard, equity curve, regime/sub-horizon/cost/what-if panels |
| Decisions     | `/(shell)/decisions/page.tsx` | PASS   | Status tabs, decision list, brief view, approve/decline flows                      |
| Debate        | `/(shell)/debate/page.tsx`    | PASS   | Thread list, message view, send                                                    |
| Signal        | `/(shell)/signal/page.tsx`    | PASS   | Signal feed with direction indicators                                              |
| Settings      | `/(shell)/settings/page.tsx`  | PASS   | Envelope, autonomy, compliance, kill switch, paper-to-live, attention report       |
| Login         | `/login/page.tsx`             | PASS   | Email/password form with error handling                                            |

**Notable:** The Backtest page passes empty arrays for `RegimeBreakdown` and `SubHorizonConsistency` (`periods={[]}` and `horizons={[]}`). These components handle the empty state correctly ("No regime data available", "No sub-horizon data available"), but the data should eventually come from the backtest result API. This is acceptable for now -- the components are wired correctly, just the backend doesn't yet provide these fields.

---

## Summary Table

| Category       | Finding ID | Severity | File:Line                                   | Description                                                                                 |
| -------------- | ---------- | -------- | ------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Mock data      | CRITICAL-1 | CRITICAL | `attention/AttentionReport.tsx:18,151`      | `PLACEHOLDER_DATA` zero-filled constant used as sole data source                            |
| Mock data      | CRITICAL-2 | CRITICAL | `decisions/DecisionCard.tsx:109`            | Hardcoded `$50,000` dollar impact multiplier                                                |
| Mock data      | HIGH-1     | HIGH     | `safety/PaperToLiveFlow.tsx:49,56`          | Two blocking conditions hardcoded to `met: true`                                            |
| Mock data      | HIGH-2     | HIGH     | `safety/PaperToLiveFlow.tsx:89`             | Static placeholder report text instead of fetched data                                      |
| Stub           | MEDIUM-1   | MEDIUM   | `portfolio/PositionDetailSheet.tsx:117,129` | "Coming soon" sections for position history and risk contribution                           |
| Error handling | MINOR-1    | MINOR    | `signal/ResearchSearch.tsx:41`              | Silent catch on search error, no user feedback                                              |
| Error handling | MINOR-2    | MINOR    | `debate/ThreadView.tsx:93`                  | Silent catch, needs verification of user feedback                                           |
| Accessibility  | MINOR-3    | MINOR    | Multiple                                    | Missing ARIA attributes on interactive elements                                             |
| Completeness   | INFO-1     | INFO     | `backtest/page.tsx:49,50`                   | Empty arrays passed to RegimeBreakdown/SubHorizonConsistency (components handle gracefully) |

**Total findings: 9** (2 CRITICAL, 2 HIGH, 1 MEDIUM, 4 MINOR/INFO)

---

## Remediation Priority

1. **CRITICAL-1:** Replace `PLACEHOLDER_DATA` with `useAttentionWeekly()` hook
2. **CRITICAL-2:** Wire dollar impact from brief/backend response
3. **HIGH-1:** Query real subsystem health and anomaly status for paper-to-live gate
4. **HIGH-2:** Fetch real paper trading report from backend
5. **MEDIUM-1:** Remove or implement "coming soon" sections
6. **MINORs:** Add error states and ARIA attributes
