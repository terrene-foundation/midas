---
type: GAP
date: 2026-04-09
created_at: 2026-04-09T21:30:00+08:00
author: agent
project: midas
topic: Brief lacks quantitative risk parameters — system cannot be built without them
phase: analyze
tags: [risk-management, critical-gap, user-input-needed]
---

## What Is Missing

The brief states "Go big or go home" and "don't be reckless" but provides zero quantitative risk parameters. The strategy engine, backtesting framework, and regime detection all require specific numbers to function:

- Maximum portfolio drawdown tolerance (proposed default: -20%)
- Maximum single-position concentration (proposed default: 15%)
- Portfolio volatility target (proposed default: 15-20% annualized)
- Regime-specific risk budgets (proposed: 80% risk assets in bull, 40% in crisis)
- Human approval threshold (proposed: trades >5% of portfolio)
- Turbulence triggers (proposed: VIX >30, drawdown speed >2%/day, credit spreads >500bps)

## Why It Matters

Without quantified risk parameters:

- The backtesting framework cannot be validated (what are we optimizing for?)
- The drawdown management ladder has no thresholds
- "Turbulent markets" (when to ask permission) has no definition
- The regime detection system has no action triggers
- Two identical strategies could produce opposite behaviors depending on interpretation of "risk-loving but not reckless"

The value audit rated this as CRITICAL severity — the system literally cannot be built without these numbers.

## How to Resolve

1. Present the proposed defaults during `/todos` for user approval
2. Make all parameters configurable in Settings (not hardcoded)
3. Build onboarding flow to capture risk preferences (sliders with plain-language explanations)
4. Backtest across a range of parameter values to show sensitivity (helps user make informed choice)

## For Discussion

- The proposed -20% max drawdown default — in the 2020 COVID crash, a diversified portfolio dropped ~15-20% in 23 days. Would a -20% trigger have caused unnecessary de-risking that missed the V-shaped recovery? Should the trigger require signal confluence (drawdown AND negative momentum AND deteriorating macro)?
- "Risk-loving" in the brief context likely means higher allocation to equities and growth-oriented assets, not higher leverage. Is that interpretation correct, or does the user actually want leveraged strategies?
- Should the system allow the user to override risk parameters in real-time (e.g., "let me go to 25% drawdown this time"), or are the parameters hard limits that even the user cannot breach?
