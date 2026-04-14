# Universe and Data Fabric

**Status:** GOVERNING. Defines the investable universe, all data sources, and the fabric pattern that governs how data flows through Midas.

---

## 1. Universe (v1)

The owner's directive (turn 4): start with ETF sector rotation because ETFs are naturally diversified, highly liquid, cheap, and cover asset classes cleanly. Add S&P 1500 US equities once the latent learners earn their keep on the ETF universe.

### 1.1 Universe Composition

| Segment                   | v1.0 | v1.1 | Selection criteria                                                                                                                                                             |
| ------------------------- | ---- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **US sector ETFs**        | ✓    | ✓    | SPDR Select Sector (11), Vanguard VIPERS (11), iShares sector ETFs — algorithmically chosen per sector                                                                         |
| **Asset-class ETFs**      | ✓    | ✓    | Broad equity (VTI, SPY), international (VEA, VWO), fixed income by duration (SHY, IEF, TLT), credit (HYG, LQD), real assets (GLD, IAU, DBC, VNQ), cash-equivalents (BIL, SGOV) |
| **Style / factor ETFs**   | ✓    | ✓    | Momentum (MTUM), quality (QUAL), low-vol (USMV), value (VTV), size (IWM, VB)                                                                                                   |
| **S&P 1500 constituents** | —    | ✓    | S&P 500 + MidCap 400 + SmallCap 600                                                                                                                                            |

### 1.2 Algorithmic Selection (not human-curated, per FP-2)

Every instrument in the universe is present because the data says it belongs. Inclusion criteria are evaluated and logged:

**ETF inclusion criteria** (all checked per FP-2, PC-2):

1. **Liquidity floor** — minimum average daily dollar volume over a rolling window
2. **AUM floor** — minimum fund size (reduces closure risk)
3. **Expense ratio cap** — below a threshold that is itself adapted based on the cost-budget constraint
4. **Tracking error vs index** — for passive ETFs, below a tolerance
5. **Holdings overlap analysis** — ETFs with >80% holdings overlap are deduped to the one with better liquidity/expense
6. **Fund age** — minimum history for backtesting validity
7. **Missing-exposure detection** — factor regression identifies gaps; adding an instrument that fills a gap is preferred
8. **Ireland-domiciled UCITS alternatives** — for US ETFs, a UCITS equivalent is evaluated against the US version on dividend-withholding-adjusted net return (30% US WHT vs 15% Ireland for Singapore residents, per FP-6)

**S&P 1500 inclusion criteria** (v1.1):

1. **Index membership** — current S&P 500 / 400 / 600 constituent
2. **Liquidity floor** — minimum average daily dollar volume
3. **Price floor** — avoids penny-stock microstructure noise
4. **Fundamental data availability** — full fundamentals available from EODHD + SEC EDGAR
5. **Trading halt history** — no recent extended halt or delisting warning

### 1.3 Dynamic Maintenance

The universe changes over time, logged in a `universe_changelog` table (per Phase 01 red-team fix). Every addition and removal carries a reason + backtest impact + timestamp. The user is notified in the Signal / Pulse surface when composition changes.

Review cadence:

- **ETFs:** monthly review, quarterly full re-evaluation
- **S&P 1500:** quarterly index rebalance window + ad-hoc on corporate actions

---

## 2. Data Sources Catalog

Every source lands in the fabric first. No model calls an external API directly. This is the brief's "fabric, not pull-every-time" rule made enforceable.

### 2.1 Price and Market Data

| Source                | Coverage                                                    | Frequency                                    | Role                                                               | Authority                                 |
| --------------------- | ----------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------- |
| **EODHD All-in-One**  | EOD OHLCV for 150K+ tickers, 70+ exchanges                  | Daily + on-demand                            | Primary prices, dividends, splits, corporate actions               | Primary                                   |
| **Yahoo Finance**     | EOD OHLCV, basic fundamentals                               | On failure / cross-check                     | Fallback + anomaly detection vs EODHD                              | Secondary                                 |
| **IBKR Web API v1.0** | Real-time bid/ask, positions, account balance, order status | Real-time when user is active; EOD otherwise | Execution-time price pull (bypasses cache); account state of truth | Truth for positions; secondary for quotes |

### 2.2 Fundamentals and Filings

| Source                 | Coverage                                                | Frequency      | Role                                               |
| ---------------------- | ------------------------------------------------------- | -------------- | -------------------------------------------------- |
| **EODHD Fundamentals** | Financial statements, ratios, ownership, insider trades | Daily          | Primary fundamentals for S&P 1500 selection (v1.1) |
| **SEC EDGAR**          | 10-K/10-Q/8-K filings, insider transactions             | On-publication | Deep-document ingestion into research corpus       |

### 2.3 News, Sentiment, and Research

| Source                  | Coverage                                              | Frequency            | Role                                                                     |
| ----------------------- | ----------------------------------------------------- | -------------------- | ------------------------------------------------------------------------ |
| **Perplexity API**      | Portfolio-tagged news + research synthesis            | On-demand            | Debate agent context, research assistant, market-outlook rubrics         |
| **EODHD News**          | Headline stream tagged to tickers                     | Continuous           | Sentiment and event ingestion into the latent learner's auxiliary inputs |
| **RSS / curated feeds** | Macro commentary, broker notes, central bank speeches | Continuous           | Research corpus ingestion                                                |
| **arXiv q-fin, SSRN**   | Academic papers                                       | Monthly curated pull | Research corpus for the research assistant                               |

**No sentiment classifier is pre-picked.** Per FP-9, multiple embedding and classification candidates run in parallel. Frontier LLMs (FP-12) handle decision-adjacent synthesis.

### 2.4 Macro and Alternative Data

| Source                         | Coverage                                                                 | Frequency                           | Role                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------ | ----------------------------------- | --------------------------------------------------------------------------------------------- |
| **FRED (Federal Reserve)**     | Yield curve, PMI, CPI, unemployment, credit spreads, monetary aggregates | Daily to monthly (source-dependent) | Auxiliary inputs to the latent learner; rendering inputs for the continuous-regime projection |
| **OECD CLI**                   | Composite leading indicators (G20 + selected economies)                  | Monthly                             | Macro-regime priors for the latent learner                                                    |
| **IMF WEO**                    | Macroeconomic forecasts and outlook                                      | Quarterly                           | Auxiliary inputs                                                                              |
| **Google Trends**              | Search demand for financial topics, tickers                              | Weekly                              | Alternative-data lane                                                                         |
| **Truflation (or equivalent)** | Alternative inflation measurement                                        | Daily                               | Alternative-data lane                                                                         |

### 2.5 Derived / Computed

| Signal                             | Inputs                     | Role                                                                 |
| ---------------------------------- | -------------------------- | -------------------------------------------------------------------- |
| VIX                                | Ingested from EODHD        | Auxiliary to the continuous regime projection                        |
| Term structure (10Y–2Y)            | FRED                       | Auxiliary                                                            |
| Credit spreads (HYG–Treasury)      | Computed from prices       | Auxiliary                                                            |
| Correlation structure              | Computed daily from prices | Auxiliary; primary correlation representation is the latent learner  |
| Realized vol (multiple estimators) | Computed from OHLCV        | Auxiliary; primary vol representation is a DL head in the model pool |

### 2.6 Explicitly Not In v1

- Options chain / implied vol surface (Tier-1 frontier, flagged as Phase 01 gap — added in v1.5+ once working models demand it)
- Tick / minute-level data (investing-not-trading, per FP-4)
- Satellite / credit-card / transaction alt-data (revisit after v1 models earn it)
- Fine-grained earnings transcripts for full-coverage NLP (v1.5+; v1 uses Perplexity summaries + filings RAG)

---

## 3. Data Fabric Pattern

### 3.1 The Rule

> Every raw source lands in the fabric. Every model reads only from the fabric. No model calls an external API directly.

This is the brief's explicit ask ("Always use a fabric instead of pulling data all the time, store whatever you have collected and re-use") and it is enforced architecturally, not by convention.

### 3.2 Implementation

- **DataFlow** is the fabric substrate. PostgreSQL for durable storage, Redis for hot cache. Generated nodes per model (see `02-value-chain.md` §7).
- **Adapter layer** — a dedicated `adapters/` module is the only place that makes outbound calls. Every adapter writes to a standard fabric table and never returns raw responses to callers.
- **Stale-data gate** — the Pre-Trade Compliance Agent blocks any trade whose upstream data is stale beyond a freshness threshold.
- **Execution-time price pull** — the one exception to "read from fabric only": when a trade is about to execute, the execution agent pulls a fresh IBKR quote through the adapter and compares to the cached price before submission. If the discrepancy exceeds a threshold, the decision is returned to the user.

### 3.3 Fabric Layout (logical)

| Table / namespace    | Purpose                                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------- |
| `prices`             | OHLCV keyed by `(instrument, date)`                                                                      |
| `corporate_actions`  | Splits, dividends, mergers                                                                               |
| `fundamentals`       | Statements, ratios per reporting period                                                                  |
| `filings`            | Raw document references + embedding IDs                                                                  |
| `news`               | Headlines + embedding IDs + portfolio-impact tags                                                        |
| `macro`              | Macro series keyed by `(series, date)`                                                                   |
| `alt_data`           | Alternative data series                                                                                  |
| `features`           | Pre-computed features, versioned (`feature_v1`, `feature_v2`, …)                                         |
| `embeddings`         | pgvector index of text embeddings for RAG                                                                |
| `latent_state`       | Historical `z_t` posteriors from champion and challengers                                                |
| `positions`          | Current and historical portfolio positions (IBKR-authoritative)                                          |
| `orders`             | Order state machine history                                                                              |
| `decisions`          | Every decision with full brief + outcome + counterfactual                                                |
| `shadow_decisions`   | Hypothetical decisions from challenger models                                                            |
| `model_registry`     | Model versions, training windows, calibration snapshots                                                  |
| `universe_changelog` | Every universe add/remove with reason                                                                    |
| `audit_log`          | Every rule-engine decision, compliance veto, escalation                                                  |
| `quotes`             | Bid/ask + size, keyed by `(instrument, timestamp)`; feeds spread and cost model per `13-`                |
| `fills`              | IBKR execution records (price, qty, fees, venue, timestamp); feeds slippage calibration per `13-`        |
| `fills_synthetic`    | Synthesized partial-fill scenarios for order-state-machine testing per `14- §9.3`                        |
| `fee_schedule`       | Versioned IBKR commission + regulatory-fee schedule per `13- §2.3`                                       |
| `cost_attribution`   | Realized cost decomposition per trade (spread / impact / commission / tax / slippage / gap) per `13- §8` |
| `sweep_history`      | IBKR FX sweep events for SGD/USD accounting per `14- §11`                                                |

### 3.4 Polling and Freshness

Per the brief ("Data latency is critical so do aggressive caching... activate polling when screen is active"):

- **Active (user in app):** 1-minute polling for quotes and portfolio values; EOD data pulled once per day after close
- **Inactive (background):** 15-minute polling for regime-relevant inputs only (VIX, SPX, DXY, credit spreads); full EOD pipeline after close
- **Never:** intraday ingestion of tick data, continuous streaming market data for v1

### 3.5 Freshness Display

Every market data view shows `as of [timestamp]`. No pretense of real-time. The user always knows how old the number is.

---

## 4. Feature Store

### 4.1 Role

Features are computed from the fabric and stored under versioned identifiers. Every model reads features by version. Refactoring a feature mints a new version; old versions remain queryable until the last model that uses them is retired.

### 4.2 Feature Categories

1. **Latent features** — outputs of the representation learners (the primary drivers, per FP-10)
2. **Econometric overlays** — momentum, value, carry, quality, volatility — computed for attribution and LLM-facing explanation (not as primary decision inputs)
3. **Technical** — rolling statistics, drawdown, spread-to-moving-average
4. **Fundamental** — ratios, growth rates, quality scores (v1.1+)
5. **Text-derived** — sentiment scores, topic distributions, embedding similarity to reference corpora
6. **Macro** — FRED / OECD / alt-data transforms

### 4.3 Walk-Forward Discipline

Every feature computation respects the point-in-time rule: feature value at time `t` may depend only on data known at time `t`. Retroactive feature revisions (e.g., restated fundamentals) are tracked as separate revision records; backtests use the revision active as-of each backtest date.

### 4.4 Retraining Cadence

- **Latent learners:** weekly full retrain during active training phase; monthly after stabilization
- **Return heads:** weekly retrain during training phase; bi-weekly after
- **Covariance / tail models:** daily update
- **LLM prompts / signatures:** versioned alongside model-registry entries; no silent prompt edits

Training cadence is allowed to expand when population-based training is running multiple challengers in parallel.

---

## 5. Data Depth Strategy

The owner's directive: `(a) + (b)` — pre-train on a large public corpus and fine-tune on our universe, plus aggressive alt-data. Noted also: financial data is very noisy because trades happen for many reasons; treat noise as a first-class concern.

### 5.1 Pre-training Corpora

- Public financial time-series corpora (cross-market, cross-asset-class, cross-frequency) for the representation learner
- Large text corpora for language embeddings (domain + general)
- Synthetic market data from generative models for tail-regime augmentation (reserved for stress testing, not primary training)

### 5.2 Fine-tuning on Midas Universe

- Representation learners fine-tune on the Midas fabric after pre-training
- Econometric features are used as auxiliary targets (multi-task loss) to stabilize latent geometry

### 5.3 Noise Handling (Owner Note)

Financial data is noisy because people trade for many reasons — some rational, some not. Principles:

- **Denoising in the representation layer, not in the target.** Contrastive learning and denoising autoencoders are the first line of defense.
- **Multi-horizon consistency.** A signal that only works at one horizon is suspect; the model pool evaluates every head at 1, 3, and 6-month horizons.
- **Robust loss functions.** Quantile losses, Huber losses, and distributional losses over point losses where appropriate.
- **Regime-conditional validation.** A model that looks good in aggregate but fails in specific `z_t` regions is not promotion-ready.

---

## 6. Data Source Dependencies and Failure Modes

| Source     | If source fails                                         | Impact                                                 |
| ---------- | ------------------------------------------------------- | ------------------------------------------------------ |
| EODHD      | Yahoo Finance fallback; stale-data gate after threshold | Rebalancing paused, monitoring continues               |
| Yahoo      | EODHD continues; only a cross-check is lost             | Minor; anomaly detection degraded                      |
| IBKR       | All trading halts; portfolio state goes read-only       | Major; pending orders cancelled or queued per decision |
| Perplexity | Debate agent continues with RAG-only context            | Minor; news-driven context narrower                    |
| FRED       | Cached last value used; auxiliary input only            | Minor                                                  |

The fabric's job during a source outage is to mark affected features stale and let the compliance agent enforce the stale-data gate.
