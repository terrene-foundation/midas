# Value Audit Report - Round 10 (Final)

**Date**: 2026-04-22
**Auditor Perspective**: Singapore-domiciled self-directed investor with $100K-$500K on Interactive Brokers. Skeptical. Demanding real proof before trusting capital.
**Method**: Brief-to-spec-to-code traceability, mock-data sweep, value flow walk, post-round-9 change analysis

---

## Executive Summary

Midas has undergone significant hardening since round 9. The three CRITICAL mock data violations (PLACEHOLDER_DATA in AttentionReport, hardcoded $50,000 dollar impact multiplier, placeholder gates in PaperToLiveFlow) have been resolved. The paper-to-live flow now queries real subsystem health endpoints and fetches paper trading reports from the backend. The weekly attention data now comes from `/pulse/attention/weekly` rather than a zero-filled constant.

However, a buyer evaluating this on April 22 would still find **four systemic gaps** that prevent the product from delivering its core value proposition:

1. **No onboarding frontend** -- A new user lands in a shell with a sidebar pointing to surfaces they cannot populate. The backend OnboardingRouter exists (4-step state machine with proper sequencing gates), but there is no frontend wizard to drive it. A Singapore investor who just downloaded the app sees "No positions" and "No pending decisions" with no path to set up their brokerage connection, risk profile, or paper trading account.

2. **Backtest panels receive empty data** -- The backtest scorecard headline numbers (CAGR, Sharpe, drawdown) now compute from real return series, but the RegimeBreakdown and SubHorizonConsistency panels receive hardcoded empty arrays (`periods={}`, `horizons={}`). The regime breakdown and consistency views -- the artifacts that would justify trusting the strategy -- are blank.

3. **Debate agent lacks live portfolio context** -- The DebateAgent runs a single-turn LLM call. The frontend has a polished multi-turn UI with InlineVisualization, ToolActionBar, and provenance pointers. But the backend does not inject live portfolio positions, current weights, or regime state into the debate context. A user asking "why am I holding 15% NVDA?" gets a generic LLM response, not a grounded analysis citing the portfolio's actual position.

4. **No mobile support** -- The product brief requires iOS and Android. The ViewportGate in the Sidebar blocks all screens below 1024px with a clear message: "Midas is optimized for desktop and tablet (1024px+). Please visit on a larger screen." The user persona specifies mobile as the primary device for decisions.

The architecture earns trust. The regime-adaptive shell, the compliance rule engine with 19 blocking rules, the kill switch with process lock, the biometric-gated approvals, the OOD honesty banner, and the quote-moved detection are all genuine implementations -- not decorations. But a Singapore investor with $250K on the line would look at the empty backtest panels and the generic debate responses and reach for their phone to call Schwab.

---

## What Was Promised (Brief Traceability)

From `briefs/01-product-brief.md`:

| Promise                                         | Spec Reference          | Status                                                            |
| ----------------------------------------------- | ----------------------- | ----------------------------------------------------------------- |
| Autonomous decisions, "make me money"           | specs/07, specs/08      | PARTIAL -- pipeline exists, analyst output depends on fabric data |
| Regime detection and display                    | specs/06, specs/09 S6   | IMPLEMENTED -- RegimeRenderer, 4-band cross-fade, RegimeGauge     |
| Don't trade without asking in turbulent markets | specs/10 S2, specs/11   | IMPLEMENTED -- ApprovalFlow, ReAuthModal, 19 blocking rules       |
| Backtest across all market conditions           | specs/09 S9.2, specs/11 | PARTIAL -- metrics compute, panels empty, no benchmark comparison |
| Transaction cost accuracy                       | specs/13                | WEAK -- 4 cost scenarios, no microstructure model                 |
| Web/iOS/Android                                 | specs/09                | WEB ONLY -- ViewportGate blocks mobile                            |
| I want to debate with the AI                    | specs/07                | PARTIAL FAIL -- single-turn LLM, no live data injection           |
| ETF diversification / sector rotation           | specs/03 S1.2           | IMPLEMENTED -- ETF scoring engine with factor map                 |
| Data fabric / caching                           | specs/03 S3.3           | IMPLEMENTED -- 23 fabric models, DataFlow-backed                  |
| No over-trading / fee concern                   | specs/13, specs/11      | PARTIAL -- rebalancing frequency cap, no live fee tracking        |

---

## Page-by-Page Audit

### Pulse (`/pulse`)

**What I See**: Portfolio value hero, daily change %, regime gauge, top 5 positions, regime-adaptive cross-fade between calm/elevated/urgent/crisis layouts.

**Value Assessment**:

- Purpose clarity: CLEAR -- "Is everything okay in 5 seconds"
- Data credibility: REAL -- `/pulse/` and `/pulse/regime` endpoints with 5s polling
- Value connection: CONNECTED -- regime gauge, positions, NAV all wired
- Action clarity: OBVIOUS -- elevated/urgent layouts surface pending decisions

**Client Questions**:

- Where is the recent actions feed? The calm layout shows positions but not what Midas did yesterday ("Rebalanced bonds +2%")
- Where is the market context strip (VIX, SPX, DXY)?
- Who do I notify if the regime gauge seems wrong?

**Verdict**: VALUE ADD (with gaps) -- Core pulse works. Missing recent actions feed and market context strip are MEDIUM gaps, not blocking.

---

### Decisions (`/decisions`)

**What I See**: Status tabs (pending/approved/declined), decision cards with confidence distribution, dollar impact, decision window progress bar, expand for full brief, approve/decline flows with biometric gate, debate button.

**Value Assessment**:

- Purpose clarity: CLEAR -- "Hands the user the approval tap with enough context to say yes/no"
- Data credibility: REAL -- decisions come from `/decisions/` endpoint with status filtering
- Value connection: CONNECTED -- brief rendering, approval flow, quote-moved guard all wired
- Action clarity: OBVIOUS -- spatially separated approve/reject buttons (spec 10 S2.2 compliant)

**Client Questions**:

- The brief says "confidence: 73%" -- what is this confidence IN? The probability of the move being profitable? The probability of avoiding a drawdown?
- "Comparable Past Decisions" section in briefs -- is this populated or is it empty?
- The dollar impact ($X) -- where does this come from? Is this the expected P&L or just the notional value traded?

**Verdict**: VALUE ADD -- This is the strongest surface. Spec-compliant moments of truth are genuinely implemented.

---

### Debate (`/debate`)

**What I See**: Thread list, message bubbles with provenance pointers, inline visualizations (chart/table/text), tool action bar, resolution states, slide-in overlay available from any surface.

**Value Assessment**:

- Purpose clarity: CLEAR -- "Joint evidence review where the user can argue with Midas"
- Data credibility: MIXED -- UI is real, but backend DebateAgent runs single-turn LLM without live portfolio context
- Value connection: PARTIAL -- ToolActionBar exists with 10 MCP tools, but tools are not invoked with live portfolio data
- Action clarity: OBVIOUS -- thread persistence, message history, inline visualizations

**Client Questions**:

- When I ask "what if I reduce NVDA from 15% to 8%?", does the system compute the portfolio impact or return a generic LLM response?
- The provenance pointers -- do these actually trace to fabric rows or are they decorative?
- "You MUST disagree when evidence warrants" -- how does the system know when evidence warrants?

**Verdict**: NEUTRAL (trending toward VALUE DRAIN) -- Excellent component library built on a single-turn LLM foundation. Cannot deliver on the "evidence-grounded debate" promise without live data injection.

---

### Portfolio (`/portfolio`)

**What I See**: NAV hero, allocation bars (horizontal, with target vs current drift), position list sortable by weight/P&L/drift, position detail sheet with metrics, attribution card, risk metrics panel.

**Value Assessment**:

- Purpose clarity: CLEAR -- "Inspect what you actually own, what's drifting, what rebalancing cost"
- Data credibility: REAL -- positions from `/portfolio/positions`, allocation from `/portfolio/allocation`, risk from `/portfolio/risk`
- Value connection: CONNECTED -- drift highlighting, P&L attribution
- Action clarity: HIDDEN -- position detail sheet has "coming soon" sections for history and risk contribution

**Client Questions**:

- The allocation bars show "current" vs "target" -- what determines the target? Is this the SAA, TAA, or something else?
- The attribution decomposition -- is this Brinson-Fachler or something simpler?
- "Position History" and "Risk Contribution" are "coming soon" -- when?

**Verdict**: VALUE ADD -- Core portfolio inspection works. "Coming soon" sections are MEDIUM gaps.

---

### Backtest (`/backtest`)

**What I See**: Scenario selector, scorecard (CAGR, Sharpe, max drawdown, Calmar, turnover, win rate), equity curve, regime breakdown panel (empty), sub-horizon consistency panel (empty), cost sensitivity panel, what-if panel (not wired).

**Value Assessment**:

- Purpose clarity: CLEAR -- "Build trust that the strategy survives the conditions you fear"
- Data credibility: MIXED -- Scorecard numbers compute from real return series, but regime/consistency panels are empty
- Value connection: PARTIAL -- Headline metrics exist but drill-down panels are blank
- Action clarity: HIDDEN -- What-if panel exists but has no backend

**Client Questions**:

- Where is the benchmark comparison (S&P 500, 60/40 passive)?
- The "regime breakdown" and "sub-horizon consistency" panels say "No data available" -- is this because no backtests have been run, or because the panels aren't wired?
- The return series computation -- how does it handle position sizing? Is it a simple $10K per trade or does it use actual portfolio weights?

**Verdict**: VALUE DRAIN -- Headline scorecard looks impressive until the user scrolls to find blank drill-down panels. A Singapore investor would look at this and wonder if the numbers are real.

---

### Signal (`/signal`)

**What I See**: Signal feed with direction indicators (bullish/bearish), source attribution, strength meter, research search with natural language query.

**Value Assessment**:

- Purpose clarity: CLEAR -- "Filters news and research down to items that touch your book"
- Data credibility: REAL -- signals from `/signal/` endpoint, research from `/signal/research`
- Value connection: CONNECTED -- filtered by portfolio relevance
- Action clarity: HIDDEN -- Research search shows "Searching..." then results, but unclear what triggers a re-evaluation

**Verdict**: VALUE ADD -- Clean signal surface, useful filtering, good attribution.

---

### Settings (`/settings`)

**What I See**: Envelope parameters (vol target, drawdown ceiling, concentration cap), autonomy level viewer with upgrade proposals, kill switch with process lock, paper-to-live transition, compliance rules viewer, data source status, attention budget report.

**Value Assessment**:

- Purpose clarity: CLEAR -- "Retune envelope, autonomy, and preferences"
- Data credibility: MIXED -- Envelope, autonomy, kill switch are real. Paper-to-live now queries real subsystem health and fetches real reports (fixed since round 9).
- Value connection: CONNECTED -- All settings surface to real backend state
- Action clarity: OBVIOUS -- Clear section separation, meaningful defaults

**Verdict**: VALUE ADD -- Settings surface is production-quality.

---

### Onboarding (NOT FOUND)

**What I See**: Nothing. A new user lands in the shell layout with a sidebar. No welcome screen. No brokerage connect. No risk profile.

**Value Assessment**:

- Purpose clarity: ABSENT
- Data credibility: N/A
- Value connection: DEAD END
- Action clarity: ABSENT

**Client Questions**:

- How do I connect my Interactive Brokers account?
- What is my risk envelope?
- How do I start paper trading?
- How long until I can see real recommendations?

**Verdict**: VALUE DRAIN -- A new user cannot set up the product. The backend OnboardingRouter exists (4-step state machine) but there is no frontend to drive it.

---

## Value Flow Analysis

### Flow: New User Sets Up Account

**Steps Traced**:

1. User visits app → lands at `/pulse` shell → No onboarding wizard
2. User sees sidebar → clicks Settings → sees envelope, autonomy, kill switch
3. User cannot find brokerage connection → no onboarding flow exists
4. User tries to navigate → sees "No positions", "No pending decisions"

**Flow Assessment**:

- Completeness: BROKEN AT STEP 1
- Narrative coherence: CONTRADICTORY -- product brief says "connect Interactive Brokers", specs say "9-step onboarding", actual UI shows none of this
- Evidence of value: ABSENT -- user cannot reach any value milestone

**Where It Breaks**: No onboarding page exists in the frontend. The backend OnboardingRouter is fully implemented but unreachable from the UI.

---

### Flow: Daily Monitoring (Calm Markets)

**Steps Traced**:

1. User opens Pulse → sees portfolio value, daily change, regime gauge, top positions
2. User looks for recent actions → not present in calm layout
3. User looks for market context (VIX, SPX, DXY) → not present
4. User wants to confirm "everything is fine" → regime gauge confirms calm

**Flow Assessment**:

- Completeness: BROKEN AT STEP 2
- Narrative coherence: STRONG for core pulse, WEAK for complete calm flow
- Evidence of value: DEMONSTRATED for regime detection, MISSING for recent actions and market context

**Where It Breaks**: Recent actions feed and market context strip are absent from the calm layout. The user can confirm "calm" but cannot see what Midas did recently.

---

### Flow: Turbulent Market Approval

**Steps Traced**:

1. Regime shifts elevated/urgent → Pulse shows approval queue
2. User taps highest-weight decision → DecisionCard expands with full brief
3. User taps Approve → ReAuthModal (biometric simulation) → QuoteMovedDialog → submit
4. Backend validates with 19 compliance rules → executes or blocks

**Flow Assessment**:

- Completeness: COMPLETE
- Narrative coherence: STRONG
- Evidence of value: DEMONSTRATED -- spec-compliant moments of truth are genuinely wired

**Where It Breaks**: None. This is the strongest flow in the product.

---

### Flow: AI Debate

**Steps Traced**:

1. User opens Debate from decision card → DebateOverlay slides in with context
2. User types "why am I holding 15% NVDA?"
3. Backend DebateAgent generates response via single LLM call
4. Response renders with InlineVisualization, provenance pointers

**Flow Assessment**:

- Completeness: THEORETICAL (Step 3 is single-turn, not the multi-round evidence-grounded debate promised)
- Narrative coherence: WEAK -- UI supports multi-turn, backend does not
- Evidence of value: PROMISED (component library exists) but UNDEMONSTRATED (no live data injection)

**Where It Breaks**: The DebateAgent does not have live portfolio positions, regime state, or position weights in its context. The debate cannot ground responses in the user's actual portfolio.

---

### Flow: Backtest Review

**Steps Traced**:

1. User navigates to Backtest → sees scenario selector
2. User selects scenario → scorecard renders with CAGR, Sharpe, drawdown
3. User scrolls to RegimeBreakdown → sees "No regime data available"
4. User scrolls to SubHorizonConsistency → sees "No sub-horizon data available"
5. User tries WhatIfPanel → exists but not wired to backend

**Flow Assessment**:

- Completeness: BROKEN AT STEP 3
- Narrative coherence: CONTRADICTORY -- headline promises "comprehensive backtesting", drill-down shows empty panels
- Evidence of value: PROMISED (scorecard numbers) but UNDERMINED (blank drill-down)

**Where It Breaks**: RegimeBreakdown and SubHorizonConsistency panels receive empty arrays from the frontend. The backend computes regime data but the frontend does not request it, or the frontend requests it but the backend does not return it.

---

## Cross-Cutting Issues

| #   | Issue                                    | Severity | Impact                                                  | Fix Category |
| --- | ---------------------------------------- | -------- | ------------------------------------------------------- | ------------ |
| 1   | No onboarding frontend                   | CRITICAL | New users cannot set up product; zero acquisition flow  | FLOW         |
| 2   | Backtest regime/consistency panels empty | HIGH     | Core trust-building artifact looks hollow               | DATA         |
| 3   | Debate agent single-turn, no live data   | HIGH     | "Evidence-grounded debate" promise undeliverable        | NARRATIVE    |
| 4   | Mobile blocked by ViewportGate           | HIGH     | User persona says mobile is primary device              | FLOW         |
| 5   | No benchmark comparison in backtest      | MEDIUM   | Scorecard lacks "Midas vs S&P 500" comparison           | DATA         |
| 6   | No recent actions in Pulse calm layout   | MEDIUM   | "30-second check" requires activity history             | DATA         |
| 7   | Return series uses fixed 0.1 weight      | MEDIUM   | Backtest numbers directionally correct but not reliable | DATA         |
| 8   | WhatIfPanel not wired                    | LOW      | "What if I change drawdown?" cannot be answered         | FLOW         |
| 9   | Position history "coming soon"           | LOW      | Supplementary section absent                            | FLOW         |

---

## Severity Table

| Issue                    | Severity | Impact                            | Fix Category |
| ------------------------ | -------- | --------------------------------- | ------------ |
| No onboarding frontend   | CRITICAL | Zero user acquisition             | FLOW         |
| Backtest empty panels    | HIGH     | Core trust proposition undermined | DATA         |
| Debate single-turn       | HIGH     | Feature differentiation broken    | NARRATIVE    |
| Mobile blocked           | HIGH     | User persona mismatch             | FLOW         |
| No benchmark comparison  | MEDIUM   | Scorecard lacks context           | DATA         |
| Missing recent actions   | MEDIUM   | Calm flow incomplete              | DATA         |
| Crude return computation | MEDIUM   | Backtest reliability questionable | DATA         |
| WhatIfPanel unwired      | LOW      | Scenario analysis unavailable     | FLOW         |

---

## Bottom Line

As a CTO evaluating this for my firm: I see a team that understands institutional investment infrastructure deeply. The regime-adaptive architecture is not something a generalist SaaS team would build. The PACT compliance engine with 19 blocking rules, the kill switch with process lock, the biometric-gated approvals, and the OOD honesty banner are evidence of genuine domain expertise.

But my $500K client with a Singapore Interactive Brokers account would not trust this system with real capital. The onboarding is missing, so they cannot set up the product. The backtest panels are blank, so they cannot evaluate the strategy. And the debate feature -- the differentiator that separates Midas from every robo-advisor -- gives generic responses instead of grounded portfolio analysis.

The single highest-leverage investment is wiring the debate agent with live portfolio data. The component library (InlineVisualization, ToolActionBar, provenance pointers) and the MCP tools (10 tools querying real fabric tables) are 80% of the work. What remains is injecting the user's actual positions, current weights, and regime state into the DebateAgent context. This would make the debate feature real.

The second highest-leverage investment is the onboarding wizard. The backend state machine exists. The frontend just needs a wizard to drive it. Without onboarding, no user ever reaches the value.

The third investment is the backtest drill-down panels. The scorecard headline numbers are now real. The blank panels below them destroy credibility. Either wire the panels to the backend data that exists, or remove the panels entirely.

**Rating: ARCHITECTURE STRONG / IMPLEMENTATION INCOMPLETE**

This is a product at approximately 55% implementation. The foundations are sound. The specific gaps are fixable. But a buyer paying $500K/year for autonomous investment management would be justified in demanding these gaps be closed before signing.
