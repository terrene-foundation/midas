---
type: DISCOVERY
date: 2026-04-09
created_at: 2026-04-09T21:30:00+08:00
author: agent
project: midas
topic: Institutional validation of ML-based regime detection from Two Sigma and SSGA
phase: analyze
tags: [regime-detection, hmm, institutional-validation, strategy]
---

## What Was Discovered

Market research found published validation of ML-based regime detection from two institutional sources:

1. **Two Sigma** published research on unsupervised ML approaches to regime modeling, using multiple feature types across multiple time horizons simultaneously. Key insight: the best regime models combine features from different timeframes.

2. **State Street Global Advisors (SSGA)** published "Decoding Market Regimes with Machine Learning" (2025), validating that ML-based regime classification meaningfully improves risk-adjusted returns for institutional portfolio management.

3. **Hybrid HMM + LSTM** approaches in recent academic literature report >96% test-set accuracy for advance warning of crisis regimes.

This validates the planned 4-layer regime detection architecture:

- Layer 1: Observable indicators (VIX, breadth, yield curve, credit spreads)
- Layer 2: Statistical model (3-state HMM on multi-feature input)
- Layer 3: Ensemble validation (cross-model agreement to reduce false transitions)
- Layer 4: LLM interpretation (human-readable assessment for debate)

## Why It Matters

Regime detection is the most ambitious technical claim in Midas — "we can tell when the market is changing and adjust accordingly." Having institutional validation from Two Sigma and SSGA moves this from "speculative" to "established technique applied in a novel consumer context." The 4-layer architecture is well-grounded.

However, the research also confirms that regime detection is inherently backward-looking (you detect the regime after it starts, not before). The value is in faster detection and systematic response, not prediction.

## Follow-Up

- Source the Two Sigma and SSGA papers for implementation reference
- Evaluate `hmmlearn.GaussianHMM` vs `statsmodels.tsa.regime_switching.markov_regression` for Layer 2
- Design the ensemble validation protocol (Layer 3) — how many models must agree before declaring a regime change?
- Build regime detection as the first strategy engine component (it gates everything else)

## For Discussion

- The >96% accuracy claim for hybrid HMM+LSTM crisis prediction — this is test-set accuracy, not live trading accuracy. How much should we discount this? Backtested crisis detection is easier than real-time detection because regime labels are assigned retrospectively.
- Two Sigma uses unsupervised learning to discover regimes from data. Should Midas do the same (let the data speak) or use predefined regimes (bull/bear/sideways/crisis)? Predefined is more interpretable for the debate agent; unsupervised may discover regimes we hadn't considered.
- The ensemble validation layer (requiring cross-model agreement) reduces false transitions but adds latency. In a fast crash (March 2020: -34% in 23 days), how quickly would a consensus-based system detect the regime change versus a single-model system?
