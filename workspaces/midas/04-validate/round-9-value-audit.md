# Value Audit Report -- Round 9

**Date**: 2026-04-20
**Auditor Perspective**: Self-directed Singapore investor considering a paid subscription for autonomous investment management. Skeptical. Has seen 50 SaaS demos this quarter.
**Method**: Source-code walkthrough, user-flow traceability, brief-to-spec-to-code mapping

---

## Executive Summary

Midas has a **coherent product skeleton** with genuine value in its regime-adaptive shell, decision approval flow, and debate overlay. The architecture is thoughtful: kill switch with process lock, OOD honesty banner, biometric-gated approvals, paper-to-live transition with server-side enforcement. These are not decorations.

However, a buyer would find **three value-destroying gaps**: (1) the backtest scorecard, the single artifact that justifies the entire investment thesis, passes hard-coded placeholder data through its regime breakdown, consistency check, and cost sensitivity panels; (2) there is no onboarding flow in the frontend -- a new user lands on a shell with a sidebar and no guidance; (3) the debate agent is a single-turn LLM call, not the multi-round, context-loaded, evidence-grounded conversation the user flows describe. The gap between what the user flow promises ("NVDA implied volatility is 62%, here is a chart") and what the code delivers ("here is a text input, send a message, get a JSON blob back") is the widest in the product.

The single highest-impact fix: **make the backtest scorecard real with computed metrics**. Nothing else in the product matters if the numbers on the backtest page are zeros.

---

## Per-Flow Assessment

### Flow 1: Onboarding (`01-onboarding.md`)

**Can the user complete this flow?** NO

The onboarding flow describes 9 steps: welcome, connect brokerage, import portfolio, risk profile, universe constraints, data sources, review, paper trading, first live briefing.

**What exists in code:**

- Backend: `OnboardingRouter` in `src/midas/api/routes_extended.py` (lines 28-159) -- a 4-step state machine (connect_brokerage, risk_profile, universe_constraints, activate) with proper sequencing gates (409 if prior step incomplete). Server-side validated.
- Frontend: **Nothing.** No `/onboarding` page. No wizard. No welcome screen. The user lands directly in the shell layout (`apps/web/app/(shell)/layout.tsx`) with a sidebar pointing to Pulse, Decisions, Debate, Portfolio, Backtest, Signal, Settings.

**What is missing:**

- No welcome screen explaining what Midas does
- No brokerage connection UI (OAuth flow, API key entry)
- No portfolio import/review screen
- No risk profile sliders (max drawdown, volatility comfort, concentration limit, autonomy level)
- No universe constraints toggles (exclude emerging markets, commodities, REITs)
- No data source configuration UI
- No review-and-activate summary screen
- No paper trading dashboard with persistent PAPER TRADING banner
- No paper trading report generation UI
- No paper-to-live transition in onboarding context (exists only in Settings)

**Moments of truth preserved?**

- The paper-to-live transition has server-side enforcement in `PaperLiveRouter.transition()` (routes_extended.py lines 954-1078): 14-day minimum, kill switch check, subsystem health check, report review gate, biometric confirmation. This is genuine. But it is unreachable from onboarding.

**Verdict: FAIL.** A new user cannot set up the product. The backend state machine exists but there is no frontend to drive it.

---

### Flow 2: Daily Monitoring -- Calm Markets (`02-daily-monitoring.md`)

**Can the user complete this flow?** PARTIALLY

**What exists:**

- Pulse page (`apps/web/app/(shell)/pulse/page.tsx`) renders `PulseShell`
- `PulseShell` (`apps/web/elements/pulse/PulseShell.tsx`) derives regime band from `a_t` and renders one of four layouts with opacity cross-fade
- `PulseCalmLayout` shows: portfolio value (NAV), daily change %, regime gauge, top 5 positions with market values
- Regime data comes from `/pulse/regime` endpoint via `useRegime()` hook, refreshing every 5 seconds
- Positions come from `/pulse/` endpoint via `usePulse()` hook

**What the user flow expects:**

- "Glance path" -- widget showing $2.8M, +0.4%, REGIME: Calm, no approvals needed
- "Quick check path" -- recent actions list with rationales, market context strip (VIX, SPX, DXY)
- Weekly summary push notification

**What is missing:**

- No recent actions list (the calm layout shows only positions, no activity feed)
- No market context strip (VIX, SPX, DXY)
- No notification system (no push notifications, no weekly summary)
- No widget (mobile/desktop widget for at-a-glance checking)

**Value assessment:**

- The regime-adaptive shell is genuinely well implemented. The four-band cross-fade (`PulseShell` lines 40-71) with derived layout bands is smooth and architecturally sound.
- The calm layout correctly prioritizes portfolio value and position summary.
- But the user flow promises "confirm everything is fine in under 30 seconds" -- this requires the recent actions feed ("Yesterday: Rebalanced bonds +2%"), which is absent.

**Verdict: PARTIAL PASS.** The core regime-adaptive pulse works. The "quick check" path is incomplete -- missing recent actions, market context, and notification layer.

---

### Flow 3: Turbulent Market Approval (`03-turbulent-market-approval.md`)

**Can the user complete this flow?** YES, with caveats

**What exists:**

- `PulseElevatedLayout` -- shows regime gauge, pending decisions list, NAV
- `PulseUrgentLayout` -- focus decision with approve/reject, kill switch button, other pending decisions list
- `PulseCrisisLayout` -- crisis banner, kill switch, single focus decision, kill-switch-activated state
- `DecisionCard` (`apps/web/elements/decisions/DecisionCard.tsx`) -- full decision card with:
  - Decision type badge, instruments, action summary
  - Confidence distribution visualization
  - Dollar impact estimate
  - Decision window progress bar (not countdown timer -- spec 10 S6.1 compliant)
  - BriefRenderer for expanded brief view
  - ApprovalFlow with multi-step: tap Approve -> ReAuthModal (biometric simulation) -> QuoteMovedDialog -> submit
  - DeclineFlow with confirmation step
  - Debate button (opens DebateOverlay)
- `ApprovalFlow` (`apps/web/elements/decisions/ApprovalFlow.tsx`) implements:
  - Re-auth gate for urgent/crisis bands (spec 10 S2.3)
  - Quote-moved detection with regime-adaptive thresholds (calm 0.5%, elevated 0.3%, urgent 0.2%, crisis 0.1%) -- spec 10 S6.4
- `BatchReviewPanel` (`apps/web/elements/decisions/BatchReviewPanel.tsx`) -- batch approve/decline for multiple decisions
- Spatial separation of Approve and Reject buttons (spec 10 S2.2) -- Approve is full-width primary, Reject is smaller and offset
- Backend: 19 blocking compliance rules in `blocking_rules.py`, kill switch with process lock in `kill_switch.py`

**Moments of truth preserved:**

1. **Approval tap**: Spatially separated buttons + ReAuthModal = compliant with spec 10 S2.1-S2.3
2. **Kill switch**: Process lock with confirmation code hash, dwell timer in settings, prominent buttons in urgent/crisis layouts
3. **Decision window**: Progress bar (not countdown) -- spec 10 S6.1 compliant
4. **Quote-moved detection**: Regime-adaptive thresholds -- spec 10 S6.4 compliant
5. **OOD escalation**: OODBanner shows "I am less calibrated in this state" when `oodScore > 0.7` -- spec 10 S8 compliant

**What is missing:**

- The user flow describes "Comparable Past Decisions" in the brief (Oct 2025: Similar setup, executed, avoided -11%). The BriefRenderer shows sections but the backend brief composition depends on DB content quality.
- Notification tiers (push, haptic, emergency) are defined in backend `NotificationRouter.DEFAULT_TIERS` but there is no push notification system.
- Window expiry with default action is described in the user flow but not visible in the UI.

**Verdict: PASS.** The turbulent market approval flow is the strongest part of the product. Spec-compliant moments of truth are genuinely implemented, not just mocked. The kill switch, biometric gate, quote-moved detection, and spatial button separation are real, wired, and enforced.

---

### Flow 4: AI Debate (`04-ai-debate.md`)

**Can the user complete this flow?** PARTIALLY

**What exists:**

- Debate page (`apps/web/app/(shell)/debate/page.tsx`) -- thread list + message view + input
- DebateOverlay (`apps/web/elements/DebateOverlay.tsx`) -- slide-in panel from any surface
- Full component library: `ThreadView`, `MessageBubble`, `DebateInput`, `ToolActionBar`, `InlineVisualization`, `ResolutionBanner`, `ThreadStatusBadge`, `ThreadList`, `ThreadCard`
- `InlineVisualization` renders chart, table, and text visualizations inline in messages
- `MessageBubble` shows provenance pointers (source, reference, snippet)
- `ToolActionBar` for invoking tools mid-debate
- `DebateAgent` (`src/midas/agents/debate.py`) -- structured steelman/red-team debate with LLM
- 10 MCP tools in `src/midas/agents/tools.py` that query real fabric tables
- Backend: thread creation, message posting, tool invocation, resolution with four outcome states

**What the user flow expects vs. what exists:**

| Flow Expectation                                                       | Implementation Status                                                                                                                                  |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Context-loaded entry from decision                                     | PARTIAL -- DebateOverlay accepts context, but entry from decision card opens overlay with `context.id` and `context.type` only                         |
| AI presents thesis with specific data                                  | PARTIAL -- DebateAgent generates steel_man/red_team via LLM, but does not pull live data from fabric in the debate prompt                              |
| User challenges with counter-argument                                  | YES -- text input, message persistence                                                                                                                 |
| AI responds with evidence, not sycophancy                              | PARTIAL -- system prompt says "disagree when evidence warrants" but the agent does not have access to live portfolio/market data in the debate context |
| Inline visualizations (sparklines, comparison tables)                  | YES -- InlineVisualization component supports chart/table/text rendering                                                                               |
| "What if?" scenario analysis with portfolio impact                     | NOT IMPLEMENTED -- no scenario engine wired to debate                                                                                                  |
| Resolution with decision update                                        | PARTIAL -- DebateResolutionRouter supports four states, but updating a live decision from debate requires manual steps                                 |
| Override pattern tracking ("you've overridden 4 of 6 recommendations") | NOT IMPLEMENTED in debate context                                                                                                                      |

**Critical gap:**
The `DebateAgent.debate()` method (debate.py lines 70-146) runs a **single LLM call** with the brief summary and user position, requesting JSON output. This is not a multi-round, interactive conversation. The user flow describes a dynamic back-and-forth where the AI pulls live data, runs scenarios, and presents charts. The actual implementation is a one-shot JSON generation. The frontend `DebatePage` does support multi-turn messaging, but the backend does not maintain debate context across turns -- each message addition is independent.

**Non-sycophancy enforcement:**
The system prompt includes "You MUST disagree when evidence warrants it; do not confabulate" (debate.py line 25). This is text-level enforcement. The real protection would be (a) injecting live data that may contradict the user, (b) provenance pointers on every claim, and (c) override tracking that the agent can reference. Only (b) is partially present (MessageBubble renders provenance_pointers, but they are not generated by the current agent).

**Verdict: PARTIAL FAIL.** The debate surface is the most ambitious feature and the most incomplete. The component library is excellent (InlineVisualization, ToolActionBar, ResolutionBanner). But the AI does not have real-time portfolio data in its context, does not run scenarios, and does not track override history. A user asking "what if we reduce NVDA by 8% instead of 15%?" would get a generic LLM response, not the computed portfolio impact the flow promises.

---

### Flow 5: Backtesting Review (`05-backtesting-review.md`)

**Can the user complete this flow?** PARTIALLY

**What exists:**

- Backtest page (`apps/web/app/(shell)/backtest/page.tsx`) with ScenarioSelector, BacktestScorecard, EquityCurve, RegimeBreakdown, SubHorizonConsistency, CostSensitivity, WhatIfPanel
- Backend: `BacktestDetailRouter` in routes_extended.py with:
  - `get_scorecard()` -- computes CAGR, Sharpe, max_drawdown, Calmar, turnover, win_rate from decision return series
  - `get_regime_breakdown()` -- uses z_scale from latent_state or percentile fallback
  - `get_consistency()` -- monthly and quarterly positive-period fractions
  - `get_cost_sensitivity()` -- four cost scenarios (current, double, half, zero)

**Previous round 3 finding (RESOLVED):**
Round 3 found the scorecard returning `None` for all metrics. The current implementation (`_compute_metrics` at routes_extended.py lines 579-628) now computes real metrics from return series using numpy. This is a genuine fix.

**What is missing:**

- The `_compute_returns_from_decisions` method (lines 640-723) builds returns from decisions + prices, but the price-weight logic is simplistic (fixed 0.1 weight per buy/sell action, no portfolio allocation model)
- `RegimeBreakdown` in the page is passed `periods={}` (hardcoded empty array at backtest/page.tsx line 49) -- the frontend component exists but receives no data from the backend regime breakdown endpoint
- `SubHorizonConsistency` receives `horizons={}` (hardcoded empty at line 50) -- same issue
- `CostSensitivity` receives `baseReturn` and `costDrag` from the run result, but these are derived from `result.cagr` and `result.turnover` which depend on the quality of the return series computation
- `WhatIfPanel` exists but has no wired backend -- "what if I use 30% max drawdown instead of 20%?" cannot be answered
- No benchmark comparison (S&P 500, 60/40) in the scorecard

**Verdict: PARTIAL PASS.** The backend metrics computation is real (no longer stubs). But the frontend panels receive empty data, the return series computation is a crude approximation, there is no benchmark comparison, and the "what if" exploration is non-functional. The backtest page would show a scorecard with computed numbers but empty regime/consistency panels and no scenario analysis.

---

## Brief Requirement Coverage Table

| #   | Brief Requirement                                 | Spec File               | Code Location                                                                                                                                                 | Status                                                                                |
| --- | ------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| 1   | ETF diversification / sector rotation             | specs/03 S1.2           | `src/midas/universe/etf_selection.py` -- FACTOR_MAP with 9 factor categories, scoring with AUM/volume/expense/tracking thresholds                             | IMPLEMENTED -- scoring engine exists, selection thresholds are spec-compliant         |
| 2   | AI debate capability                              | specs/07 S3.5           | `src/midas/agents/debate.py` -- DebateAgent with steelman/red-team, `apps/web/elements/debate/` -- 10 components, `src/midas/agents/tools.py` -- 10 MCP tools | PARTIAL -- agent is single-turn, no live data injection, no scenario engine           |
| 3   | Risk management / backtesting                     | specs/09 S9.2, specs/11 | `BacktestDetailRouter` in routes_extended.py, `blocking_rules.py` (19 rules), `kill_switch.py` (process lock)                                                 | PARTIAL -- compliance is real, backtest metrics compute but return series is crude    |
| 4   | Transaction cost accuracy                         | specs/13                | `BacktestDetailRouter.get_cost_sensitivity()` -- 4 scenarios with multiplier; no spread/impact/commission/tax decomposition                                   | WEAK -- cost sensitivity exists but no microstructure model                           |
| 5   | Web/iOS/Android                                   | specs/09                | Web only: `apps/web/` with Next.js; ViewportGate requires 1024px minimum; no mobile app; no responsive layout                                                 | WEB ONLY -- brief requires iOS + Android, ViewportGate blocks mobile browsers         |
| 6   | Data fabric / caching                             | specs/03 S3.3           | `src/midas/fabric/engine.py` -- 23 fabric models registered on DataFlow; `_register_models()` with prices, corporate_actions, latent_state, etc.              | IMPLEMENTED -- fabric pattern is real, DataFlow-based, 23 tables                      |
| 7   | "Make me money" (autonomous decisions)            | specs/08, specs/07      | `src/midas/agents/analyst.py`, `src/midas/scheduler/jobs.py`, autonomy ladder, decision pipeline                                                              | PARTIAL -- decision pipeline exists but analyst output depends on fabric data quality |
| 8   | "I want to debate with the AI"                    | specs/07                | DebateAgent + DebateOverlay + 10 tools                                                                                                                        | PARTIAL -- see Flow 4 assessment                                                      |
| 9   | "Don't trade without asking" in turbulent markets | specs/10 S2, specs/11   | ApprovalFlow, ReAuthModal, compliance rules, regime-adaptive thresholds                                                                                       | IMPLEMENTED -- strongest part of the product                                          |
| 10  | No over-trading / fee concern                     | specs/13, specs/11      | Rebalancing frequency cap in compliance, cost sensitivity analysis                                                                                            | PARTIAL -- cap exists in compliance rules, no live fee tracking                       |

---

## Commercial Readiness Assessment

### Would this product embarrass a demo?

**Yes, in three specific places.**

1. **Onboarding**: There is no onboarding flow. A new user sees a blank sidebar with no guidance. If an investor opens the app for the first time, they see... a shell with "No positions" and "No pending decisions." There is no path from "I just signed up" to "I understand what this does."

2. **Backtest empty panels**: The backtest page renders `RegimeBreakdown` with `periods={}` and `SubHorizonConsistency` with `horizons={}`. These are visible, prominent panels that say nothing. An investor looking at the backtest scorecard would see the headline numbers (CAGR, Sharpe, drawdown) but then see blank regime and consistency panels immediately below.

3. **Debate generic responses**: If an investor types "why are you holding so much NVDA?" into the debate, they get a generic LLM response. The toolActionBar exists but the backend does not inject portfolio data into the debate context. The debate cannot say "your NVDA position is 12.4% of portfolio, which is 2x your target weight" because it does not have that data in its prompt.

### What would NOT embarrass a demo:

- The regime-adaptive shell is genuinely impressive. The cross-fade between calm/elevated/urgent/crisis with different layouts, gauges, and color schemes is polished.
- The decision approval flow with biometric gate, quote-moved detection, and spatial button separation is production-quality UX thinking.
- The kill switch with process lock, dwell timer, and confirmation code is the kind of safety engineering that builds trust.
- The OOD honesty banner ("I am less calibrated in this state") is a rare example of AI transparency done right.

---

## Cross-Cutting Issues

| #   | Issue                                                        | Severity | Impact                                                                                  | Fix Category |
| --- | ------------------------------------------------------------ | -------- | --------------------------------------------------------------------------------------- | ------------ |
| 1   | No onboarding flow in frontend                               | CRITICAL | New users cannot set up the product; commercial demo impossible                         | FLOW         |
| 2   | Backtest panels receive empty data (periods=[], horizons=[]) | HIGH     | Scorecard looks real but drill-down panels are blank                                    | DATA         |
| 3   | Debate agent is single-turn, no live data injection          | HIGH     | Debate produces generic LLM responses, not evidence-grounded investment arguments       | NARRATIVE    |
| 4   | No mobile support (ViewportGate blocks <1024px)              | HIGH     | Brief requires iOS + Android; current app blocks mobile browsers                        | FLOW         |
| 5   | No notification system (push, haptic, weekly summary)        | MEDIUM   | Calm regime user flow depends on notifications; currently absent                        | FLOW         |
| 6   | No recent actions feed in pulse                              | MEDIUM   | User cannot "confirm everything is fine in 30 seconds" without activity history         | DATA         |
| 7   | Return series computation uses fixed 0.1 weight per action   | MEDIUM   | Backtest results are directionally correct but not quantitatively reliable              | DATA         |
| 8   | No benchmark comparison (S&P 500, 60/40) in backtest         | MEDIUM   | Scorecard cannot show "Midas vs S&P 500" -- the most compelling visual in the user flow | DATA         |
| 9   | WhatIfPanel has no backend                                   | LOW      | "What if I change drawdown tolerance?" cannot be answered                               | FLOW         |
| 10  | No widget for at-a-glance monitoring                         | LOW      | User flow describes a widget; not present                                               | DESIGN       |

---

## Severity Table

| Issue                                | Severity | Impact                              | Fix Category |
| ------------------------------------ | -------- | ----------------------------------- | ------------ |
| No onboarding frontend               | CRITICAL | Blocks all new user acquisition     | FLOW         |
| Backtest empty drill-down panels     | HIGH     | Core value proposition looks hollow | DATA         |
| Debate single-turn without live data | HIGH     | Breaks "debate with AI" promise     | NARRATIVE    |
| Mobile blocked by ViewportGate       | HIGH     | Brief requires iOS/Android          | FLOW         |
| No push notifications                | MEDIUM   | Calm-market flow incomplete         | FLOW         |
| No recent actions in pulse           | MEDIUM   | "30-second check" impossible        | DATA         |
| Simplistic return series computation | MEDIUM   | Backtest numbers unreliable         | DATA         |
| No benchmark comparison              | MEDIUM   | Scorecard lacks "so what"           | DATA         |

---

## Bottom Line

If I were a CTO evaluating this for my firm, I would see a team that understands the domain deeply. The regime-adaptive architecture, the compliance rule engine, the moments-of-truth enforcement -- these are not features a generalist SaaS team would build. They reflect genuine investment domain knowledge.

But I would not pay for this product today. The value chain has three breaks: I cannot set up an account (no onboarding), I cannot trust the backtest numbers (empty panels, crude return computation), and the debate -- the feature that differentiates this from every robo-advisor -- gives me generic LLM responses instead of grounded investment analysis.

The architecture earns trust. The implementation has not yet earned the subscription. The single highest-leverage investment is making the debate agent aware of live portfolio state -- because that is the feature no competitor has, and it is 70% built (10 MCP tools exist, the component library exists, the LLM provider exists -- what is missing is the wiring).

---

## Per-Flow Verdict Summary

| Flow                         | Verdict      | Key Gap                                               |
| ---------------------------- | ------------ | ----------------------------------------------------- |
| 01 Onboarding                | FAIL         | No frontend wizard; backend state machine exists      |
| 02 Daily Monitoring          | PARTIAL PASS | Missing recent actions, market context, notifications |
| 03 Turbulent Market Approval | PASS         | Strongest flow; spec-compliant moments of truth       |
| 04 AI Debate                 | PARTIAL FAIL | Single-turn agent, no live data, no scenario engine   |
| 05 Backtesting Review        | PARTIAL PASS | Metrics compute; panels empty; no benchmarks          |

## File References

Key files examined during this audit:

- `apps/web/app/(shell)/layout.tsx` -- shell with OODBanner, AttentionBudgetGauge, DebateOverlay
- `apps/web/app/(shell)/pulse/page.tsx` -- PulseShell render
- `apps/web/app/(shell)/decisions/page.tsx` -- decision list with brief viewer
- `apps/web/app/(shell)/debate/page.tsx` -- thread list + message view
- `apps/web/app/(shell)/backtest/page.tsx` -- scorecard with empty panels at lines 49-50
- `apps/web/app/(shell)/portfolio/page.tsx` -- portfolio overview
- `apps/web/app/(shell)/settings/page.tsx` -- envelope, autonomy, kill switch, paper-to-live
- `apps/web/elements/pulse/PulseShell.tsx` -- regime-adaptive cross-fade (lines 40-71)
- `apps/web/elements/pulse/PulseCrisisLayout.tsx` -- kill switch + focus decision
- `apps/web/elements/pulse/PulseUrgentLayout.tsx` -- urgent band with biometric gate
- `apps/web/elements/pulse/PulseCalmLayout.tsx` -- calm layout with positions
- `apps/web/elements/decisions/DecisionCard.tsx` -- approval flow with spatial separation
- `apps/web/elements/decisions/ApprovalFlow.tsx` -- multi-step: reauth, quote-moved, submit
- `apps/web/elements/decisions/BatchReviewPanel.tsx` -- bulk approve/decline
- `apps/web/elements/debate/ThreadView.tsx` -- message rendering with visualization
- `apps/web/elements/debate/InlineVisualization.tsx` -- chart/table/text rendering
- `apps/web/elements/debate/DebateInput.tsx` -- message input
- `apps/web/elements/DebateOverlay.tsx` -- slide-in panel
- `apps/web/elements/safety/OODBanner.tsx` -- out-of-distribution honesty banner
- `apps/web/elements/Sidebar.tsx` -- navigation with ViewportGate (blocks <1024px)
- `apps/web/lib/queries/usePulse.ts` -- 5s polling
- `apps/web/lib/queries/useDecisions.ts` -- decision CRUD
- `apps/web/lib/queries/useDebate.ts` -- thread/message management
- `apps/web/lib/queries/useBacktest.ts` -- run/result queries
- `apps/web/stores/regime-store.ts` -- Zustand store with band derivation
- `src/midas/api/routes_extended.py` -- OnboardingRouter (lines 28-159), DecisionModifyRouter, DebateResolutionRouter, BacktestDetailRouter (lines 549-932), PaperLiveRouter (lines 935-1078)
- `src/midas/agents/debate.py` -- DebateAgent with single-turn LLM call
- `src/midas/agents/tools.py` -- 10 MCP tools for fabric queries
- `src/midas/compliance/kill_switch.py` -- process lock with confirmation hash
- `src/midas/compliance/blocking_rules.py` -- 19 blocking rules
- `src/midas/fabric/engine.py` -- 23 fabric models
- `src/midas/universe/etf_selection.py` -- ETF scoring with factor map
- `specs/_index.md` -- 15 spec files indexed
- `specs/10-moments-of-truth.md` -- governing UX safety rules
- `workspaces/midas/03-user-flows/01-onboarding.md` -- 9-step onboarding
- `workspaces/midas/03-user-flows/02-daily-monitoring.md` -- calm market flow
- `workspaces/midas/03-user-flows/03-turbulent-market-approval.md` -- crisis approval
- `workspaces/midas/03-user-flows/04-ai-debate.md` -- debate interaction patterns
- `workspaces/midas/03-user-flows/05-backtesting-review.md` -- scorecard + drill-down
