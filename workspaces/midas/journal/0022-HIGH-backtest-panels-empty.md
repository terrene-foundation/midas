# HIGH: Backtest Panels Receive Empty Data

**Date:** 2026-04-22
**Round:** Round 10 red team
**Severity:** HIGH

## Finding

RegimeBreakdown and SubHorizonConsistency panels receive hardcoded empty arrays (`periods={}`, `horizons={}`). The headline backtest metrics (CAGR, Sharpe, drawdown) compute from real return series, but the regime breakdown and consistency views are blank.

## Impact

The regime breakdown and consistency views -- the artifacts that would justify trusting the strategy -- are blank. A Singapore investor cannot validate the strategy's historical performance across different market regimes.

## Spec Coverage

- Spec 09 §9.2: Backtest drill-down panels
- Spec 11: Regime-aware compliance

## Resolution Path

Wire the backtest drill-down panels with real regime segmentation data, or remove the panels if they're not in v1 scope.

## Status

OPEN
