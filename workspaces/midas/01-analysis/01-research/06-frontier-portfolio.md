# Frontier Portfolio Management Research (2024-2026)

**Date**: 2026-04-09
**Scope**: Cutting-edge techniques beyond textbook approaches

---

## Implementation Readiness Tiers

### Tier 1 — Ready Now (Libraries Exist)

| Technique                                 | Library                         | What It Does                                                                                                                             |
| ----------------------------------------- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Bayesian Online Changepoint Detection** | `river`, `bayesian-changepoint` | Real-time regime shift detection with heavy-tailed extensions. O(1) per observation. Bank of England validated (2024).                   |
| **TDA / Persistent Homology**             | `giotto-tda`, `Ripser`          | Detects market state topology changes. Persistent entropy spikes before crashes. Validated on 5 crises across 3 markets (Majumdar 2024). |
| **Wavelet Regime Detection**              | `PyWavelets`, `ssqueezepy`      | Frequency-specific regime changes (microstructure vs macro). Czech National Bank uses for financial stability.                           |
| **Online Portfolio Selection**            | NumPy (<200 lines)              | Universal portfolios with transaction costs. Second-order regret bounds (Zimmert & Seldin 2024).                                         |
| **CPCV Backtesting**                      | `mlfinlab`                      | Combinatorial purged cross-validation with multiple testing correction. Lopez de Prado 2024 extensions.                                  |
| **Options Microstructure Signals**        | `py_vollib`, custom GEX         | Volatility term structure, risk-reversal skew, dealer gamma exposure. Institutional practice (SpotGamma, Nomura).                        |
| **Cross-Asset Connectedness**             | `statsmodels` VAR               | Diebold-Yilmaz directional spillover. Used by BIS, IMF, central banks.                                                                   |
| **EVaR Optimization**                     | `CVXPY` + exponential cone      | Tightest upper bound on CVaR. Built-in robustness to model misspecification (Pichler & Schlotter 2024).                                  |
| **FinBERT / LLM-as-Analyst**              | HuggingFace + API               | Aspect-based sentiment, uncertainty detection, LLM earnings analysis rivaling median analyst (Kim et al. 2025).                          |

### Tier 2 — Moderate Effort

| Technique                               | Effort                            | What It Does                                                                                                     |
| --------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Temporal Fusion Transformers**        | PyTorch Forecasting + custom loss | Multi-horizon allocation with interpretable variable selection. Oxford-Man Institute validated.                  |
| **Risk-Aware RL (CVaR-PPO)**            | FinRL + Stable-Baselines3         | Continuous portfolio optimization with CVaR constraint in the objective. JPMorgan AI Research published similar. |
| **Graph Neural Networks**               | PyTorch Geometric                 | Dynamic hypergraph for asset contagion. Captures group co-movement, not just pairwise.                           |
| **Diffusion Models for Scenarios**      | FinDiff reference code            | Synthetic market data preserving tail properties. JPMorgan, Morgan Stanley use for stress testing.               |
| **Optimal Transport Regime Detection**  | `POT` library                     | Wasserstein distance measures full distributional shift. Journal of Econometrics 2024.                           |
| **Dynamic Risk Budgeting w/ Attention** | PyTorch (small transformer)       | Attention weights over assets become risk budget inputs. Roncalli & Weisang 2024.                                |
| **Adversarial Backtesting**             | Custom + generative model         | Finds worst-case plausible scenarios. Cont (Oxford) 2025.                                                        |

### Tier 3 — Research Frontier

| Technique                               | Challenge                                | What It Does                                                                             |
| --------------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------- |
| **Causal Regime Drivers**               | Identifiability in nonstationary systems | Not just "what regime" but "why" and "what triggers transition." Schölkopf group (MPI).  |
| **Meta-Learning (MAML)**                | Task definition for regimes              | Rapid adaptation to unseen regimes with 5-10 days of data. Oxford-Man Institute 2025.    |
| **Continuous Optimal Stopping for DD**  | PDE solvers                              | Grossman-Zhou extended under model uncertainty. Optimal drawdown policy as lookup table. |
| **Sig-Wasserstein Scenario Generation** | Specialized math (rough path theory)     | Preserves path properties (autocorrelation, leverage effect).                            |

---

## Recommended Architecture: Tier 1 + Select Tier 2

For Midas v1, combine Tier 1 building blocks with high-value Tier 2 components:

**Regime Detection**: BOCPD (real-time) + TDA (topological confirmation) + HMM (baseline)
**Risk Measurement**: GJR-GARCH + EVaR + Filtered Historical Simulation
**Portfolio Construction**: TFT for multi-horizon signals → Black-Litterman → HRP ensemble
**Risk Budgeting**: Dynamic attention-based (Tier 2) with OCO fallback (Tier 1)
**Backtesting**: CPCV with deflated Sharpe + adversarial scenario stress testing
**Signals**: Cross-asset connectedness + options microstructure + LLM earnings analysis
**Validation**: Option-implied forward distributions for forward-looking assessment

---

## Key Papers (Most Impactful for Midas)

1. **Knoblauch & Damoulas (2024)** — Scalable BOCPD via streaming variational inference (ICML)
2. **Majumdar et al. (2024)** — Persistent homology early warning signals (Quantitative Finance)
3. **Zhang, Zohren & Roberts (2024)** — TFT for portfolio optimization (J. Financial Data Science)
4. **Pichler & Schlotter (2024)** — EVaR optimization (Mathematical Finance)
5. **Roncalli & Weisang (2024)** — Dynamic risk budgeting with online learning (J. Portfolio Management)
6. **Lopez de Prado & Lewis (2024)** — CPCV with multiple testing correction
7. **Guo et al. (2024)** — Optimal transport for regime detection (J. Econometrics)
8. **Coletta et al. (2024)** — FinDiff diffusion models for financial data (ICAIF)
9. **Kim et al. (2025)** — LLM-as-analyst rivaling human analysts (Chicago Booth)
10. **Kardaras & Platen (2024)** — Optimal drawdown protection under model uncertainty
