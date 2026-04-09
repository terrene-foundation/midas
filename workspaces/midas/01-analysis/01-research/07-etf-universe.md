# Data-Driven ETF Universe Construction Research

**Date**: 2026-04-09
**Scope**: Algorithmic universe selection for Singapore-domiciled investor via IBKR

---

## Core Principle: Let Data Drive Everything

No hardcoded ticker lists. The system algorithmically constructs, maintains, and evolves its investable universe.

---

## 1. Holdings-Level Overlap Analysis

### STRAPSim Algorithm (Frontier — September 2025)

Beyond simple Jaccard overlap, STRAPSim (Semantic, Two-level, Residual-Aware Portfolio Similarity):

1. Computes pairwise semantic similarity between holdings (recognizes BABA and JD.com are similar)
2. Greedy matching: transfers min(weight_A, weight_B) \* similarity_score
3. Dynamically reduces residual weights (prevents overcounting)

Outperforms Jaccard, weighted Jaccard, and BERTScore variants on real ETF datasets.

### Practical Overlap Thresholds

| Overlap % | Action                         |
| --------- | ------------------------------ |
| >70%      | Eliminate one fund (redundant) |
| 40-70%    | Acceptable if intentional tilt |
| <40%      | Good diversification           |

### Key Overlap Insights

- **VTI vs SPY**: 88% overlap. SPY entirely redundant if holding VTI.
- **VWO vs EEM**: High overlap but EEM includes South Korea (12.5%), VWO excludes it. Holdings-level analysis reveals structural difference.
- **SCHD vs VYM**: 0.95 correlation but different character (SCHD: 100 quality-screened stocks, VYM: 550+ broad high-yield).

### Data Sources for Holdings

- **Primary**: OpenBB Platform with FMP provider (unified Python API)
- **Backup**: Finnhub free tier (60 calls/min)
- **Validation**: ETF Research Center (etfrc.com) for spot-checking

---

## 2. Singapore Tax Efficiency: Ireland UCITS > US-Domiciled

**Critical finding for Singapore investors:**

|               | US-Domiciled | Ireland UCITS           |
| ------------- | ------------ | ----------------------- |
| Dividend WHT  | 30%          | 15% (US-Ireland treaty) |
| US Estate Tax | Yes (>$60K)  | None                    |
| Typical ER    | 0.03-0.07%   | 0.07-0.22%              |

**Net cost on US equity (~1.3% yield):**

- VOO: 0.03% ER + 0.39% WHT = **0.42% total**
- CSPX: 0.07% ER + 0.195% WHT = **0.265% total**

CSPX saves ~15.5 bps/year despite higher ER. On $1M = ~$1,550/year saved.

### Key Ireland UCITS Equivalents

| US ETF   | Ireland UCITS           | Index                 | ER         |
| -------- | ----------------------- | --------------------- | ---------- |
| VOO/SPY  | CSPX, VUAA              | S&P 500               | 0.07%      |
| VT       | VWRA (acc), VWRD (dist) | FTSE All-World        | 0.19%      |
| VEA/VXUS | IWDA, SWRD              | MSCI World            | 0.12-0.20% |
| AGG      | AGGU                    | Global Aggregate Bond | 0.10%      |

**Accumulating share classes preferred** (CSPX, VUAA, VWRA): dividends reinvested within fund, avoiding WHT at investor level.

### Algorithm Rule

**Default: Ireland UCITS when available.** US-domiciled only for unique exposures with no UCITS equivalent (e.g., KWEB, FM, niche thematic).

---

## 3. Missing Exposure Detection

### Multi-Dimensional Gap Analysis

Analyze across 4 dimensions simultaneously:

1. **Asset Class**: Equities (US/intl/EM/frontier), fixed income, real assets, alternatives
2. **Geographic**: US, developed intl, EM (China, India, Taiwan, Brazil, Korea), frontier
3. **Sector/Thematic**: AI/semi, biotech, clean energy, cybersecurity, China internet (KWEB), India growth
4. **Factor**: Fama-French 5-factor + momentum regression. Insignificant loadings = missing exposure.

### Commonly Missed Exposures

| Gap                       | Why Missed                           | Instrument |
| ------------------------- | ------------------------------------ | ---------- |
| China internet            | VWO gives <5% effective exposure     | KWEB       |
| Frontier markets          | VWO/EEM don't cover                  | FM         |
| TIPS/inflation protection | Forgotten in equity-heavy portfolios | TIP, SCHP  |
| Small-cap international   | Market-cap weighting underrepresents | VSS, SCZ   |
| India specific            | Often underweight in broad EM        | INDA       |
| China A-shares            | Only partially in VWO/EEM            | ASHR       |
| Infrastructure/MLPs       | Unique return profile                | IGF        |

### Effective Cost Formula

```
Effective Cost = ER / (1 - overlap_with_existing_portfolio)
```

KWEB at 0.70% with ~0% overlap = 0.70% per unit of new exposure
Second S&P 500 fund at 0.03% with 88% overlap = 0.25% per unit of new exposure

KWEB is cheaper per unit of genuinely new exposure.

---

## 4. Algorithmic Universe Construction Pipeline

### 10-Step Pipeline

```
1. SEED: Pull all IBKR-accessible ETFs meeting AUM >$100M and volume >$5M/day
2. FETCH: Get holdings data via OpenBB/FMP/Finnhub
3. OVERLAP: Compute pairwise STRAPSim for all candidates
4. CLUSTER: Hierarchical clustering on returns correlation (skfolio/Riskfolio-Lib)
5. DEDUPLICATE: Within each cluster, eliminate >70% overlap pairs
6. SELECT: From each cluster, pick best on composite score:
   - Expense ratio (adjusted for domicile/WHT)
   - AUM (liquidity)
   - Tracking error
   - Track record length
7. GAP ANALYSIS: Factor regression on selected universe; identify missing dimensions
8. FILL GAPS: Search candidates outside clusters for missing exposures
9. COST OPTIMIZE: For each slot, verify cheapest option (including UCITS alternatives)
10. OUTPUT: Dynamic universe with entry/exit criteria
```

### Entry Criteria

| Criterion       | Threshold                              |
| --------------- | -------------------------------------- |
| AUM             | >$100M (ideally >$500M)                |
| Daily volume    | >$5M                                   |
| Track record    | >3 years                               |
| Unique exposure | <40% overlap with all existing members |
| Factor loading  | Significant on underrepresented factor |
| Expense ratio   | Competitive within exposure category   |

### Exit Criteria

| Signal                  | Threshold                                   |
| ----------------------- | ------------------------------------------- |
| AUM decline             | Below $50M                                  |
| AUM decline rate        | >10% monthly for 2+ months → immediate exit |
| Overlap increase        | >70% with newer, cheaper fund → replace     |
| Tracking error spike    | >2x historical for 3+ months                |
| Liquidity deterioration | Spreads widen >3x historical                |

### Review Cadence

| Review                       | Frequency |
| ---------------------------- | --------- |
| Full universe reconstruction | Quarterly |
| Holdings overlap check       | Monthly   |
| Correlation monitoring       | Weekly    |
| AUM/liquidity screening      | Monthly   |
| New ETF scanning             | Monthly   |

---

## 5. Key Libraries

| Library                     | Purpose                                                           |
| --------------------------- | ----------------------------------------------------------------- |
| `openbb`                    | Unified ETF holdings data API                                     |
| `skfolio`                   | Portfolio optimization with sklearn-style pipelines, HRP/HERC/NCO |
| `riskfolio-lib`             | 35 risk measures, codependence metrics, HRP                       |
| `statsmodels`               | Factor regression, VAR for connectedness                          |
| `networkx`                  | MST visualization of correlation structure                        |
| `arch`                      | DCC-GARCH for dynamic correlations                                |
| `scipy.cluster.hierarchy`   | Hierarchical clustering                                           |
| `sklearn.decomposition.PCA` | Redundancy detection                                              |
