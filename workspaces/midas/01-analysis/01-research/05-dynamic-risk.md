# Dynamic Risk Management Research

**Date**: 2026-04-09
**Scope**: Frontier adaptive risk techniques for autonomous portfolio systems

---

## Core Framework: 7-Layer Dynamic Risk System

Every parameter adapts. Nothing is static.

### Layer 1 — Real-Time Risk Measurement

- **GJR-GARCH** for volatility forecasting (captures leverage effect: negative returns increase vol more than positive)
- **Yang-Zhang estimator** for intraday volatility from OHLC data (more efficient than close-to-close)
- **DCC-GARCH** (Engle 2002) for dynamic conditional correlations
- **EVT/GPD** (Extreme Value Theory / Generalized Pareto Distribution) for tail risk estimation from limited observations

### Layer 2 — Regime Detection

- HMM (2-3 states) with regime probabilities updating daily
- Feeds all downstream risk decisions

### Layer 3 — Adaptive Risk Budgeting

- **Volatility targeting with asymmetric response**: Scale DOWN faster (exponential) than scale UP (linear ramp). Captures empirical asymmetry — vol spikes are fast, declines are slow. (Moreira & Muir 2017, Harvey et al. 2018)
- **Conditional volatility targeting**: Target vol itself varies with opportunity set. High-Sharpe regimes → higher target vol. Low-Sharpe → lower target.
- **Bayesian Kelly**: Integrate Kelly fraction over posterior distribution of returns/volatilities. Naturally conservative when uncertainty is high. (MacLean, Thorp & Ziemba 2011)
- **Risk recycling**: When positions close, freed risk budget enters a recycling pool. Maintain real-time risk budget ledger where each position consumes marginal contribution to portfolio vol.

### Layer 4 — Continuous Drawdown Management

- **Sigmoid response function** (NOT discrete threshold ladder):
  ```
  exposure = 1 / (1 + exp(k * (drawdown - d_mid)))
  ```
  Smooth, differentiable. k and d_mid adapt to regime.
- **Recovery-aware**: Track drawdown level AND recovery velocity. Model drawdown dynamics as Ornstein-Uhlenbeck process. Estimate expected time-to-recovery.
- **CPPI-inspired ratcheting floor**: Floor = peak \* (1 - max_acceptable_drawdown). Floor ratchets up with gains, never decreases (TIPP variant, Estep & Kritzman 1988).
- **Response function self-adapts**: When recent performance is strong and vol is low, response curve is more tolerant. In high-uncertainty regimes, curve becomes aggressive.
- **Grossman-Zhou insight**: Optimal drawdown-controlled strategy is convex — tolerate small drawdowns, cut aggressively near constraint.

### Layer 5 — Position-Level Risk Governance

- **Component VaR monitoring**: Real-time decomposition of portfolio VaR into per-position contributions.
- **Drawdown beta**: Regress position returns on portfolio returns during drawdown periods only. High drawdown beta = preferential reduction target. (Goldberg & Mahmoud 2017)
- **Safe position detection**: Rolling beta to risk factors (equity, rates, credit, vol). If a "safe" position's factor exposure is rising, flag it (e.g., bonds in 2022).
- **Dynamic position sizing**: size = f(signal_strength, current_vol, regime, remaining_risk_budget). Naturally larger when signals strong, vol low, regime favorable.

### Layer 6 — Self-Tuning

- **Bayesian optimization** (Optuna/BoTorch) of risk parameters on rolling walk-forward backtest. Run quarterly.
- **Multi-objective Pareto frontier** (pymoo NSGA-II/III): return vs drawdown vs turnover. System operates at different frontier points depending on regime.
- **Meta-learning**: Track which parameter configurations performed best in which regimes. Build institutional memory.

### Layer 7 — Correlation & Contagion Monitoring

- **Diebold-Yilmaz spillover index** (2012): Total spillover rising = systemic risk increasing.
- **Diversification ratio monitoring**: DR = sum(w_i \* sigma_i) / sigma_portfolio. Dropping toward 1 = diversification failing → reduce total risk.
- **Crisis correlation matrix**: Estimated only from crisis periods. Periodic stress test under crisis correlations.
- **Minimum Spanning Tree**: Monitor tree structure changes. Star-shaped = contagion. (Mantegna 1999)

---

## Adaptive Covariance Estimation

- **Nonlinear shrinkage** (Ledoit & Wolf 2020): Optimally compresses eigenvalues without fixed shrinkage target. Adapts automatically to estimation quality.
- **Oracle Approximating Shrinkage** (Chen et al. 2010): Shrinkage intensity adapts to sample size and dimensionality.
- **Regime-conditional**: In volatile regimes with fewer effective observations, shrinkage increases automatically.

Python: `sklearn.covariance.LedoitWolf` for basic; `ledoit_wolf` package for 2020 nonlinear version.

---

## Filtered Historical Simulation (FHS) for Self-Calibrating VaR

1. Fit GJR-GARCH to each return series
2. Extract standardized residuals (returns / conditional vol)
3. Bootstrap from standardized residuals
4. Rescale by CURRENT conditional vol for forward-looking scenarios
5. VaR/CVaR automatically adapts to current vol regime while preserving empirical tails

(Barone-Adesi, Giannopoulos & Vosper 1999)

---

## Singapore-Specific Risk Factors

### USD/SGD Currency Risk

- MAS manages SGD via trade-weighted basket band (not interest rates)
- SGD tends to appreciate gradually vs USD in normal times
- In global risk-off, SGD weakens (natural hedge for Singapore investor holding USD assets)
- **Recommended**: Partial hedge (50-70%), dynamic based on USD/SGD momentum

### Asia-Pacific Regional Risks

- China policy risk (regulatory actions create correlated APAC selloffs)
- Japan monetary policy spillovers (BOJ yield curve control changes)
- USD/Asia FX channel (Fed tightening → EM capital outflows)
- Commodity sensitivity (oil, palm oil, iron ore affect ASEAN differently)
- Taiwan Strait / South China Sea geopolitical tail risk

---

## Key Python Libraries

| Library                 | Purpose                                    |
| ----------------------- | ------------------------------------------ |
| `arch`                  | GARCH family, volatility forecasting       |
| `hmmlearn`              | Regime detection                           |
| `optuna` / `BoTorch`    | Bayesian optimization for parameter tuning |
| `pymoo`                 | Multi-objective optimization (NSGA-II/III) |
| `scipy.stats.genpareto` | EVT tail risk estimation                   |
| `sklearn.covariance`    | Ledoit-Wolf shrinkage                      |
| `PyMC` / `NumPyro`      | Bayesian inference                         |
| `copulas`               | Copula-based dependence                    |
| `networkx`              | Contagion network analysis                 |
| `cvxpy`                 | Convex portfolio optimization              |
