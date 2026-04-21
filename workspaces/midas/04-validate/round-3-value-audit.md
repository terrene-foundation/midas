# Value Audit Report - Midas Project

**Date**: 2026-04-18
**Auditor Perspective**: Enterprise CTO evaluating $500K+ AI investment platform
**Method**: Source code analysis, user flow verification, stub/fake data detection

---

## Executive Summary

The Midas project has a **STRUCTURED FOUNDATION** with real implementations in critical paths (regime rendering, debate tools, LLM integration, kill switch). However, **MULTIPLE SURFACES RETURN STUB DATA** -- hardcoded zeros and None values for core financial metrics. An enterprise buyer would receive a platform where the backtest scorecard shows "None" for CAGR, Sharpe, and drawdown -- the exact numbers that justify the investment thesis. **This is a HIGH-severity value gap.**

---

## Page-by-Page Audit

### Pulse Surface (`/api/v1/pulse`)

**What I See**: Regime banner, NAV, positions summary, pending decisions count

**Value Assessment**:
- Purpose clarity: CLEAR
- Data credibility: DEPENDS ON DB SEED (real data when DB populated)
- Value connection: CONNECTED -- regime, positions, pending decisions all surface
- Action clarity: OBVIOUS -- user sees what needs attention

**Verdict**: VALUE ADD (when DB has real positions data)

---

### Decisions Surface (`/api/v1/decisions`)

**What I See**: Pending decision cards with approve/decline/debate actions

**Value Assessment**:
- Purpose clarity: CLEAR
- Data credibility: DEPENDS ON DB SEED (real decisions when generated)
- Value connection: CONNECTED -- approve/decline/debate actions exist
- Action clarity: OBVIOUS

**Verdict**: VALUE ADD (when decisions are seeded)

---

### Debate Surface (`/api/v1/debate`)

**What I See**: Thread management, message persistence, 10 MCP tools

**Value Assessment**:
- Purpose clarity: CLEAR
- Data credibility: REAL -- `DebateTools` in `src/midas/agents/tools.py` performs actual DB queries
- Value connection: CONNECTED -- tools query real fabric tables (positions, orders, decisions, audit_log)
- Action clarity: OBVIOUS

**Client Questions**:
- "Show me the 10 tools in action with real data"
- "Can I see a debate thread that changed a decision?"

**Verdict**: VALUE ADD -- the 10 MCP tools are real data operations

---

### Backtest Surface (`/api/v1/backtest`)

**What I See**: Run endpoint, results endpoint, scenarios listing

**Value Assessment**:
- Purpose clarity: CLEAR
- Data credibility: **STUB -- scorecard returns None for all metrics**
- Value connection: BROKEN AT STEP 3 (scorecard has no real metrics)

**Critical Finding**: `BacktestDetailRouter.get_scorecard()` (lines 397-411 in `routes_extended.py`):
```python
return {
    "run_id": run_id,
    "cagr": None,        # User flow expects: +11.2%
    "sharpe": None,      # User flow expects: 1.42
    "max_drawdown": None, # User flow expects: -19.3%
    "calmar": None,
    "turnover": None,
    "win_rate": None,
}
```

**Client Questions**:
- "Where is the 21-year backtest showing Midas outperforms S&P 500 with 65% less drawdown?"
- "The user flow shows specific numbers -- where do they come from?"

**Verdict**: VALUE DRAIN -- backtest scorecard is all None

---

### Settings Surface (`/api/v1/settings`)

**What I See**: Envelope params, autonomy level, kill switch, data sources, paper/live state

**Value Assessment**:
- Purpose clarity: CLEAR
- Data credibility: MIXED
  - Kill switch: REAL implementation with confirmation codes
  - Envelope: Returns hardcoded defaults (not from DB)
  - Paper/live: Queries DB for real state
  - Data sources: Real adapter status checks
- Value connection: CONNECTED

**Verdict**: NEUTRAL -- partial real, partial hardcoded

---

## Cross-Cutting Issues (Severity-Ranked)

### CRITICAL

| Issue | Location | Evidence |
|-------|----------|----------|
| Backtest scorecard all None | `routes_extended.py:403-411` | `cagr`, `sharpe`, `max_drawdown`, `calmar`, `turnover`, `win_rate` all `None` |
| Risk metrics hardcoded zeros | `routes.py:770-778` | `volatility: 0.0`, `sharpe: 0.0`, `sortino: 0.0`, `max_drawdown: 0.0` |
| Attribution effects hardcoded | `routes.py:740-743` | `allocation_effect: 0.0`, `selection_effect: 0.0`, `interaction_effect: 0.0` |
| Attention budget not tracked | `routes.py:200-201, 209-210, 217-218` | `decision_seconds_today: 0`, `fatigue_signal: False` -- always zeros |
| Backtest regime breakdown zeros | `routes_extended.py:421-427` | All `return_pct: 0.0`, all `sharpe: None` |
| Backtest consistency all zeros | `routes_extended.py:436-439` | `positive_periods: 0, total_periods: 0, positive_fraction: 0.0` |
| Backtest cost sensitivity None | `routes_extended.py:449-454` | All `cagr: None`, all `sharpe: None` in scenarios |
| Attention report all zeros | `routes_extended.py:351-357` | `decision_seconds_this_week: 0`, `fatigue_signal_present: False`, `override_rate: 0.0` |

### HIGH

| Issue | Location | Evidence |
|-------|----------|----------|
| Envelope returns hardcoded defaults | `routes.py:979-986` | Not persisted to DB, always returns same values |
| `get_attention_score` never queries DB | `routes.py:191-219` | Returns zeros even when DB available |

---

## Stub/Fake Data Detection

**Command**: `grep -rn "TODO\|FIXME\|STUB\|hardcoded\|fake\|mock\|dummy" src/midas/ --include="*.py" | grep -v test`

**Result**: Only 1 match -- `src/midas/agents/tools.py:181` mentions "hardcoded list" but refers to factor map approach, not fake data.

**Zero stub returns found** -- the actual problem is **implicit stubs**: endpoints that return zeros/None instead of computed values.

---

## Regime Rendering Verification

**File**: `src/midas/regime/__init__.py`

**Finding**: CORRECTLY IMPLEMENTED

```python
@staticmethod
def get_band(a_t: float) -> AttentionBand:
    if a_t >= 0.85:
        return AttentionBand.CRISIS
    if a_t >= 0.6:
        return AttentionBand.URGENT
    if a_t >= 0.3:
        return AttentionBand.ELEVATED
    return AttentionBand.CALM
```

Maps to: Calm, Elevated, Urgent, Crisis -- matches user flow expectations.

---

## Value Flow Analysis

### Flow: User opens app in calm market

**Steps**:
1. Pulse shows regime=CALM, positions, no pending decisions
2. User closes app in < 30 seconds
3. Success: "Midas is handling things"

**Flow Assessment**:
- Completeness: COMPLETE (when DB seeded)
- Narrative coherence: STRONG
- Evidence of value: DEMONSTRATED (regime rendering works)

### Flow: User reviews backtest before going live

**Steps**:
1. Backtest scorecard shows: CAGR=None, Sharpe=None, MaxDD=None
2. User asks "What is the 21-year performance?"
3. System cannot answer

**Flow Assessment**:
- Completeness: BROKEN AT STEP 1
- Narrative coherence: CONTRADICTORY -- user flow promises specific numbers
- Evidence of value: ABSENT -- all metrics are None

### Flow: User debates a decision

**Steps**:
1. User taps "Debate" on decision
2. 10 MCP tools available for AI to query fabric
3. AI produces structured response via LLM
4. Thread persisted for audit trail

**Flow Assessment**:
- Completeness: COMPLETE
- Narrative coherence: STRONG
- Evidence of value: DEMONSTRATED -- `DebateTools` performs real DB queries

---

## Severity Table

| Issue | Severity | Impact | Fix Category |
|-------|----------|--------|--------------|
| Backtest scorecard all None | CRITICAL | User cannot see strategy performance | DATA |
| Risk metrics hardcoded zeros | CRITICAL | Portfolio risk invisible | DATA |
| Attention budget not tracked | CRITICAL | Fatigue signal absent, user overwhelmed risk | DATA |
| Attribution effects all zero | HIGH | Cannot explain decision outcomes | DATA |
| Backtest regime breakdown zeros | HIGH | Cannot see performance by market regime | DATA |
| Backtest consistency zeros | HIGH | Cannot verify strategy reliability | DATA |
| Backtest cost sensitivity None | HIGH | Cannot optimize cost/performance tradeoff | DATA |
| Attention report all zeros | HIGH | Cannot track decision fatigue | DATA |
| Envelope hardcoded defaults | MEDIUM | Cannot customize risk parameters persistently | DATA |

---

## Bottom Line

As a CTO who has seen 50 AI platform demos this quarter, here is my honest assessment:

**What works**: The Midas architecture is sound. Regime rendering is correct. The debate system with 10 MCP tools is real infrastructure -- not a demo veneer. Kill switch is implemented properly. The LLM integration via `FrontierProvider` makes real API calls. The onboarding state machine is functional.

**What doesn't**: The backtest scorecard returns `None` for every metric. Risk shows zeros. Attribution shows zeros. Attention budget tracking is absent. These are not cosmetic gaps -- they are the numbers a rational investor uses to decide whether to trust this system with $500K+ of their capital.

**The specific numbers in the user flows** (11.2% CAGR, 1.42 Sharpe, -19.3% max drawdown, 847% total return) **exist only in the user flow documentation** -- they do not exist in the implementation.

**My recommendation**: Do not take this to a board meeting until the backtest engine produces real metrics. The architecture is credible; the financial data layer is a stub.

---

## Recommended Fixes (Priority Order)

1. **Implement backtest computation** -- `BacktestDetailRouter.get_scorecard()` must compute CAGR, Sharpe, max drawdown from actual price data
2. **Implement risk metrics** -- `PortfolioRouter.get_risk()` must compute volatility, Sharpe, Sortino, VaR from position data
3. **Implement attention budget tracking** -- `get_attention_score()` must track decision_seconds_today and emit fatigue_signal when threshold exceeded
4. **Implement attribution computation** -- `get_attribution()` must compute allocation/selection/interaction effects via Brinson model
5. **Persist envelope to DB** -- `get_envelope()` must read from DB, not return hardcoded defaults
