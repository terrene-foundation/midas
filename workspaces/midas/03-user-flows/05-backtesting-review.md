# User Flow: Backtesting Review

## Trigger

User wants to evaluate strategy performance, validate before going live, or explore alternative strategies.

## Entry Points

1. **From Debate**: AI suggests "Want me to backtest that scenario?"
2. **From Backtest tab**: Direct navigation
3. **From Onboarding**: First-time strategy validation before activation
4. **From Settings**: After changing risk parameters, review impact

## Goal

User gains confidence that the strategy works across market conditions, or identifies specific weaknesses to address.

---

## Flow

### Step 1: Strategy Scorecard (Default View)

**Screen**: Backtest overview — outcome-oriented, not chart-oriented.

```
CURRENT STRATEGY PERFORMANCE
Backtest Period: Jan 2005 — Apr 2026 (21 years)

                    Midas      60/40     S&P 500
Total Return:       +847%      +312%     +524%
Annualized:         +11.2%     +7.1%     +9.2%
Worst Drawdown:     -19.3%     -29.4%    -55.2%
Recovery Time:      4.2 mo     14.8 mo   5.5 yr
Sharpe Ratio:       1.42       0.68      0.72
Sortino Ratio:      2.18       0.94      0.98
Annual Turnover:    180%       12%       0%
Est. Annual Costs:  1.8%       0.1%      0%

Net of Costs:       +9.4%      +7.0%     +9.2%
```

**Key insight surfaced**: "Net of transaction costs, Midas outperforms the S&P 500 by 0.2% annually with 65% less drawdown. The primary value is risk management, not raw return."

### Step 2: Regime Breakdown

**User taps "See regime breakdown"**

```
REGIME PERFORMANCE (annualized returns)

                    Midas      60/40     S&P 500
Bull / Low Vol      +14.2%     +9.8%     +18.1%
Bull / High Vol     +18.7%     +8.2%     +22.4%
Bear / Deflation    +4.1%      -8.3%     -28.6%
Bear / Inflation    +2.8%      -12.1%    -18.4%
Sideways            +8.3%      +5.1%     +3.2%

KEY INSIGHT: Midas underperforms in strong bull markets
(it's more conservative) but dramatically outperforms
in all adverse conditions. The compounding advantage
comes from avoiding deep drawdowns.
```

**User can tap any regime cell** to see the actual periods, trades, and allocation snapshots.

### Step 3: Drill Into Specific Period

**User taps "Bear / Deflation"**

```
BEAR / DEFLATIONARY PERIODS

2008-2009 Financial Crisis
- Midas return: -8.2% (vs S&P -55.2%)
- Key actions: Shifted to 60% bonds/gold by Oct 2008
  Detected regime via yield curve + credit spread signals
- Timeline: [interactive chart showing allocation changes]

March 2020 COVID Crash
- Midas return: -6.1% (vs S&P -33.8%)
- Key actions: Reduced equity to 30% by Mar 12,
  re-entered equities by Apr 8
- Timeline: [interactive chart]

Note: Midas detected both regime shifts within 2-3 weeks
of the initial decline. It did not predict them — it
responded systematically to deteriorating signals.
```

### Step 4: "What If" Exploration

**User asks from Debate or Backtest screen**: "What if I used 30% max drawdown tolerance instead of 20%?"

```
SCENARIO: Drawdown Tolerance 30% (current: 20%)

                    30% Tol    20% Tol    Difference
Annualized Return:  +12.1%     +11.2%     +0.9%
Worst Drawdown:     -27.8%     -19.3%     -8.5% worse
Sharpe Ratio:       1.31       1.42       -0.11
Max Recovery Time:  8.2 mo     4.2 mo     +4.0 mo

INTERPRETATION: Higher drawdown tolerance captures +0.9%
annual return but at the cost of experiencing a -27.8%
peak-to-trough decline (in 2008). The Sharpe ratio is
lower, meaning the extra return doesn't compensate for
the extra risk.

Recommendation: The current 20% tolerance produces
better risk-adjusted returns.

[APPLY 30% TOLERANCE]  [KEEP CURRENT]  [TRY ANOTHER VALUE]
```

### Step 5: Sub-Horizon Consistency

**User taps "Consistency Check"**

```
ROLLING 3-YEAR PERFORMANCE (out-of-sample)

Period              Midas    S&P 500   Beat?
2005-2007           +9.8%    +8.2%     Yes
2006-2008           +1.2%    -8.4%     Yes
2007-2009           -2.1%    -16.3%    Yes
2008-2010           +12.4%   +3.8%     Yes
...
2021-2023           +4.2%    +2.1%     Yes
2022-2024           +11.3%   +8.7%     Yes
2023-2025           +13.1%   +14.8%    No

SUMMARY: Midas outperformed in 18 of 20 rolling 3-year
windows. The 2 underperformance periods were both strong
bull markets (2017-2019, 2023-2025) where conservative
positioning lagged a surging equity market.

This is the expected pattern — Midas trades short-term
bull market capture for drawdown protection.
```

### Step 6: Transaction Cost Sensitivity

**User taps "Cost Analysis"**

```
TRANSACTION COST BREAKDOWN (annual average)

Bid-ask spreads:     0.82%
Slippage:            0.31%
Commissions:         0.04%
Dividend WHT drag:   0.39%  (30% on US-source dividends; reducible via UCITS)
                    -------
Total annual cost:   1.78%

SENSITIVITY:
If costs were 50% higher:  Net return drops to +8.5%
If costs were 50% lower:   Net return rises to +10.3%
If weekly rebal → monthly: Costs drop to 0.92%, net +10.1%

INSIGHT: Switching to monthly rebalancing saves 0.86%
in costs while reducing net return by only 0.2%.
This is worth considering.

[SWITCH TO MONTHLY]  [KEEP WEEKLY]  [DEBATE THIS]
```

---

## Success Criteria

- User can assess strategy quality in < 2 minutes (scorecard)
- Regime breakdown builds trust: "It protects me when it matters"
- "What if" scenarios are instant (pre-computed or fast-computed)
- Sub-horizon consistency prevents false confidence from cherry-picked periods
- Cost sensitivity helps user optimize the cost/performance tradeoff
- Every insight is actionable — leads to parameter change, debate, or confirmation
