---
type: DISCOVERY
date: 2026-04-09
created_at: 2026-04-09T23:00:00+08:00
author: agent
project: midas
topic: Frontier techniques divide into 3 implementation tiers — Tier 1 is ready now with existing Python libraries
phase: analyze
tags: [frontier-research, implementation-readiness, architecture]
---

## What Was Discovered

Frontier portfolio management research (2024-2026) divides cleanly into three implementation readiness tiers:

**Tier 1 (ready now)**: BOCPD for real-time regime detection, TDA/persistent homology for topological market state, wavelet regime analysis, online portfolio selection with transaction costs, CPCV backtesting with multiple testing correction, options microstructure signals, cross-asset connectedness (Diebold-Yilmaz), EVaR optimization, FinBERT/LLM-as-analyst.

**Tier 2 (moderate effort)**: Temporal Fusion Transformers for multi-horizon allocation, risk-aware RL (CVaR-PPO), GNN for contagion, diffusion models for scenario generation, optimal transport for regime detection, attention-based dynamic risk budgeting, adversarial backtesting.

**Tier 3 (research frontier)**: Causal regime drivers, meta-learning for regime adaptation, continuous optimal stopping for drawdown, Sig-Wasserstein scenarios.

The recommended architecture for Midas v1 combines Tier 1 building blocks with select high-value Tier 2 components (TFT and dynamic risk budgeting).

## Why It Matters

This tiering resolves the tension between "push the frontier" (SPEC-01 FP-5) and "deliver a working system." The Tier 1 techniques are genuinely frontier (published 2024-2025, institutional validation) AND have production-ready Python implementations. We don't have to choose between ambition and feasibility.

Key insight: BOCPD + TDA for regime detection is significantly more sophisticated than basic HMM, has institutional validation (Bank of England, quant funds), and runs in milliseconds per observation. This should replace HMM as the primary regime detection method, with HMM as a baseline comparator.

## Follow-Up

- During /todos, prioritize Tier 1 implementations and TFT (highest-value Tier 2)
- Create a Tier 2 backlog for post-v1 enhancement
- Monitor Tier 3 research for breakthroughs that become implementable

## For Discussion

- Should the regime detection system use BOCPD as primary with HMM as fallback, or run both in ensemble? The ensemble approach adds robustness but also complexity and the risk of conflicting signals.
- TFT provides interpretable variable selection — which variables are important at which horizon. Should this interpretability be surfaced in the AI debate interface? ("At the 1-month horizon, credit spreads are the dominant signal; at 1-week, momentum dominates.")
- The LLM-as-analyst finding (Kim et al. 2025, Chicago Booth) shows LLMs rivaling median human analysts for earnings estimates. Should Midas integrate this directly, using its own LLM to generate earnings-based signals from transcripts, rather than relying on consensus estimates?
