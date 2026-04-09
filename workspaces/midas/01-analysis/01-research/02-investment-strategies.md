# Investment Strategy Research

**Date**: 2026-04-09 (revised with user corrections)

**IMPORTANT CORRECTIONS APPLIED**:

- ETF universe is DATA-DRIVEN, not pre-selected (SPEC-01 FP-2). The lists below are reference material for the algorithmic selection engine, not the final universe.
- Risk management is DYNAMIC, not static parameters (SPEC-02 PC-1). See research/05-dynamic-risk.md for the 7-layer adaptive framework.
- Singapore domicile: No US capital gains tax. Dividend withholding tax (30% on US ETFs) is relevant — evaluate UCITS alternatives.
- Investing, not trading: No intraday anything. Sector rotation on weekly-to-monthly timescales (SPEC-01 FP-4).
- Frontier research in progress — this document covers established techniques. See research/06-frontier-portfolio.md and research/07-etf-universe.md for cutting-edge additions.

---

## 1. Asset Class Analysis

### 1.1 ETF Reference Catalog (Input to Algorithmic Universe Selection)

**US Broad Market**

- **SPY** (S&P 500): Deepest liquidity, tightest spreads — best for autonomous execution
- **VTI** (Total Stock Market): Most comprehensive single-US-equity holding, 0.03% ER
- **QQQ** (Nasdaq-100): Tech-heavy momentum/growth sleeve, 0.20% ER

**International Developed**

- **VEA** (FTSE Developed Markets): Broad developed ex-US, 0.05% ER, ~4,000 holdings
- **EFA** (MSCI EAFE): Higher ER (0.32%) but more liquid — better for tactical rotation

**Emerging Markets**

- **VWO** (FTSE EM): Includes China A-shares, 0.08% ER, ~5,700 holdings
- **EEM** (MSCI EM): More liquid than VWO (better for weekly rotation), 0.68% ER

**Precious Metals**

- **GLD** (Gold): Most liquid gold ETF, 0.40% ER, avg daily volume >$1B
- **IAU** (Gold): Lower ER (0.25%), slightly less liquid — better for buy-and-hold
- **SLV** (Silver): Higher volatility (~1.5x daily range vs gold), 0.50% ER

**Fixed Income**

- **BND/AGG** (US Aggregate Bond): Core holdings, 0.03% ER, duration ~6.5yr
- **TLT** (20+ Year Treasury): Flight-to-quality instrument — strong negative equity correlation in crises (but NOT in inflationary bear markets)
- **SHY** (1-3 Year Treasury): Near-cash, minimal rate risk
- **TIP** (TIPS): Inflation-protected, critical in inflationary regimes
- **LQD** (Investment-Grade Corporate): High-quality corporate bonds
- **EMB** (EM Sovereign USD): EM sovereign debt, 0.39% ER

**REITs**

- **VNQ** (US Real Estate): ~160 holdings, 0.12% ER
- **VNQI** (Global ex-US Real Estate): Lower correlation to US REITs (~0.65)

**Commodities**

- **PDBC** (Diversified Commodity): 1099-reporting (no K-1), 0.59% ER
- **DBC** (Commodity Index): Broader but K-1 tax form — problematic for taxable accounts
- Avoid USO (crude oil) — severe contango drag (5-15% annually vs spot)

**Dividend/Income**

- **SCHD** (US Dividend Equity): Quality-screened, 0.06% ER — outperformed VYM historically
- **VYM** (High Dividend Yield): Broader, yield ~3%, 0.06% ER
- **VIGI** (International Dividend Appreciation): International dividend growers, 0.15% ER

### 1.2 Correlation Characteristics

**Critical insight**: Correlations are regime-dependent. Unconditional correlations mask spikes that occur when diversification is most needed.

| Regime                             | What Happens                                                                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Equity bear (non-inflationary)** | Equity-bond correlation goes deeply negative (-0.5). Gold rises. Traditional diversification works. (2008, 2020)                       |
| **Inflationary bear**              | Equity-bond correlation turns positive (+0.3 to +0.6). Both fall together. Commodities and gold outperform. 60/40 fails. (2022, 1970s) |
| **Risk-on rally**                  | All risk asset correlations converge toward 1.0. Only cash/short-duration bonds uncorrelated.                                          |
| **Liquidity crisis**               | Everything correlates to 1.0 except US Treasuries and sometimes gold. Even gold sold off temporarily in March 2020 (margin calls).     |

**Implication**: Static correlation assumptions are dangerous. The system must estimate conditional correlations given the current regime.

### 1.3 Liquidity Tiers

| Tier                         | Examples                        | Suitability                   |
| ---------------------------- | ------------------------------- | ----------------------------- |
| **Tier 1** (>$500M daily)    | SPY, QQQ, TLT, GLD, HYG         | Any rotation frequency        |
| **Tier 2** ($100-500M daily) | VEA, VWO, VNQ, SLV, TIP, SCHD   | Weekly rotation               |
| **Tier 3** ($10-100M daily)  | VNQI, VIGI, EMB, PDBC           | Monthly or less               |
| **Tier 4** (<$10M daily)     | Niche commodity, small-cap intl | Avoid for autonomous rotation |

Rule: Only rotate into instruments where position < 1% of average daily volume.

---

## 2. Portfolio Construction Methods

### 2.1 Recommended Ensemble Approach

Combine three methods for robustness:

**Black-Litterman** (signal integration)

- Anchors to market equilibrium returns, blends in algorithmic "views" (momentum, macro, carry signals)
- Naturally handles signal uncertainty, prevents extreme positions
- Best framework for combining multiple signals into a portfolio

**Hierarchical Risk Parity (HRP)** (robust weight estimation)

- No matrix inversion needed (numerically stable)
- No expected return estimates needed
- Handles highly correlated assets without concentration
- Outperforms MVO and risk parity in out-of-sample tests (Lopez de Prado 2016)

**Risk Parity** (baseline)

- Equalizes risk contribution across asset classes
- No return estimates needed
- Strong in inflationary environments (high bond+commodity weight)
- Drawdowns typically 30-50% smaller than equity-heavy portfolios

**Final weights**: Constrained average of these methods, subject to position size limits and liquidity constraints.

### 2.2 Avoid Pure Mean-Variance Optimization (MVO)

MVO is an "error maximizer" — extremely sensitive to expected return inputs (Michaud 1989). Small input changes produce wildly different portfolios. If used at all, constrain heavily or use minimum variance only (no return estimates).

---

## 3. Signal Generation

### Multi-signal framework (six families)

1. **Time-series momentum**: Is the asset above its 10-month moving average? (Faber 2007)
2. **Cross-sectional momentum**: Which assets have highest 12-1 month momentum? (Jegadeesh & Titman 1993)
3. **Volatility-adjusted momentum**: Return / trailing volatility
4. **Carry**: Yield differentials (bond yields, dividend yields, commodity contango/backwardation)
5. **Macro regime**: Investment clock positioning (growth + inflation indicators)
6. **Volatility regime**: Scale exposure inversely with realized volatility (Moreira & Muir 2017)

**Dual momentum filter** (Antonacci 2014): Only hold an asset if trailing return exceeds T-bills. If nothing passes, hold cash/SHY.

**Combine via Black-Litterman**: Each signal generates a "view" with confidence. BL blends views with market equilibrium for final weights.

---

## 4. Risk Management

### Primary: Volatility Targeting

Scale portfolio exposure inversely with realized volatility. When vol is low (VIX < 15), full or levered exposure. When vol is high (VIX > 30), reduce to 50-70%. Produces higher Sharpe ratios than static allocation (Moreira & Muir 2017). No option premiums needed.

### Secondary: CVaR Constraints

Use Conditional Value-at-Risk (expected loss given tail event) as optimization constraint. Superior to VaR because it captures tail magnitude and is a coherent risk measure (Rockafellar & Uryasev 2000).

### Drawdown Management

- Define thresholds: -5%, -10%, -15%, -20%
- At each threshold, reduce equity by 25% of exposure
- At -20%, fully in cash/short-duration bonds
- **Require signal confluence** to avoid whipsaws: drawdown threshold AND negative momentum AND deteriorating macro

### Position Sizing

Use fractional Kelly (0.25-0.50 of full Kelly) as sanity check on optimizer output. If optimizer says 40% EM equities but half-Kelly says max 15%, investigate.

### No Simple Stop-Losses

Academic evidence on stop-losses is mixed to negative for diversified portfolios (Kaminski & Lo 2014). Stop-losses convert temporary unrealized losses into permanent realized losses. Manage risk at portfolio level instead.

### Tail Hedging

- Permanent gold allocation (5-10%) as structural tail hedge
- Volatility targeting handles most tail risk mechanically
- Avoid continuous put buying (3-5% annual drag overwhelms returns)

---

## 5. Rebalancing Strategy

### Threshold-Based with Weekly Monitoring

- Check positions weekly (never more than once per week per brief)
- Rebalance only when drift exceeds tolerance band (3-5%) OR strong tactical signal triggers
- Threshold-based produces 20-40 bps higher returns with lower turnover than calendar-based (Masters 2003)

### Regime-Dependent Frequency

| Regime              | Frequency        | Rationale                                                   |
| ------------------- | ---------------- | ----------------------------------------------------------- |
| Low vol (VIX < 15)  | Monthly          | Markets trending, slow drift, rebalancing interrupts trends |
| High vol (VIX > 25) | Weekly (at max)  | Rapid drift, concentration risk increases                   |
| Regime transitions  | Immediate review | Correlations and volatilities shift; target weights move    |

### Singapore Domicile — No Tax Friction on Rebalancing

Singapore has no capital gains tax. This is a significant structural advantage:

- Rebalancing decisions are purely driven by portfolio optimization, with zero tax drag
- No need for tax-lot tracking, tax-loss harvesting, or wash sale rule compliance
- The only tax consideration: US dividend withholding tax (30% for Singapore residents)
- **Mitigation**: Evaluate Ireland-domiciled UCITS ETFs as alternatives for dividend-paying instruments (15% withholding under Ireland-US treaty, passed through to Singapore investors)

### Transaction Cost Budget

For weekly-rotation portfolio with 20-40% monthly turnover:

- Spread + slippage: 5-15 bps per trade
- Annual total: ~1-3% of portfolio
- **Signals must generate >1-3% annual alpha just to break even**

---

## 6. Backtesting Framework

### Walk-Forward Analysis (mandatory)

- Minimum 3-year training window, 6-12 month test window
- Rolling (not anchored) for regime-changing markets
- Report only out-of-sample performance

### Multiple Sub-Horizon Validation

Test across distinct regimes:

- 2000-2003 (tech crash)
- 2003-2007 (bull)
- 2007-2009 (financial crisis)
- 2009-2012 (recovery)
- 2013-2019 (low-vol bull)
- 2020 (COVID crash)
- 2021 (speculative)
- 2022 (inflationary bear)
- 2023-2026 (AI-driven recovery)

Strategy must produce positive risk-adjusted returns in majority of sub-periods.

### Overfitting Defenses

1. Fewer parameters (1-3, not 10+)
2. Economic rationale for every parameter
3. Parameter stability (+/- 20% should degrade gracefully)
4. Cross-asset validation
5. Deflated Sharpe Ratio for multiple testing correction (Bailey & Lopez de Prado 2014)

### Transaction Cost Model

Must include: commissions, bid-ask spread, market impact (sqrt model), gap risk (weekend gaps), and tax drag.

### Regime-Specific Reporting

Performance table per regime. A 1.5 Sharpe overall with -0.5 Sharpe in bear markets is critical information.

---

## 7. Key Academic References

| Paper                               | Contribution                        |
| ----------------------------------- | ----------------------------------- |
| Markowitz (1952)                    | Mean-variance optimization          |
| Black & Litterman (1992)            | Bayesian return estimation          |
| Jegadeesh & Titman (1993)           | Momentum anomaly                    |
| Ledoit & Wolf (2004)                | Covariance shrinkage                |
| Rockafellar & Uryasev (2000)        | CVaR optimization                   |
| Antonacci (2014)                    | Dual momentum                       |
| Lopez de Prado (2016)               | Hierarchical Risk Parity            |
| Moreira & Muir (2017)               | Volatility-managed portfolios       |
| Asness, Moskowitz & Pedersen (2013) | Value and momentum everywhere       |
| Hurst, Ooi & Pedersen (2017)        | Century of trend-following evidence |
| Bailey & Lopez de Prado (2014)      | Deflated Sharpe ratio               |
