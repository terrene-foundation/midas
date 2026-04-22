# Data Fabric and Universe

The investable universe, data source catalog, fabric layout, freshness rules, and feature store contract. Any implementation touching `fabric/`, `universe/`, or data ingestion must read this first.

**Specs authority:** `specs/03-universe-and-data.md` (governing)

---

## The Fabric Rule

> Every raw source lands in the fabric. Every model reads only from the fabric. No model calls an external API directly.

Enforcement: adapter layer (`fabric/adapters/`) is the only place making outbound calls. Stale-data gate in Pre-Trade Compliance blocks trades with stale upstream data. One exception: execution-time fresh IBKR quote pull before trade submission.

---

## Universe Composition

| Segment               | v1.0 | v1.1                                       |
| --------------------- | ---- | ------------------------------------------ |
| US sector ETFs        | ✓    | ✓                                          |
| Asset-class ETFs      | ✓    | ✓                                          |
| Style/factor ETFs     | ✓    | ✓                                          |
| S&P 1500 constituents | —    | ✓ (after v1.0 positive Brinson allocation) |

### 8 ETF Inclusion Criteria (Algorithmic, Not Curated)

1. Liquidity floor (min avg daily dollar volume)
2. AUM floor (reduces closure risk)
3. Expense ratio cap (adapted from cost budget)
4. Tracking error vs index (passive ETFs)
5. Holdings overlap analysis (>80% overlap → dedup to better liquidity/expense)
6. Fund age (min history for backtest validity)
7. Missing-exposure detection (factor regression identifies gaps)
8. Ireland-domiciled UCITS evaluation (15% WHT vs 30% for Singapore residents)

---

## Data Source Catalog

### Price & Market Data

| Source           | Role                                                   | Authority           |
| ---------------- | ------------------------------------------------------ | ------------------- |
| EODHD All-in-One | Primary prices, dividends, splits                      | Primary             |
| Yahoo Finance    | Fallback + anomaly cross-check                         | Secondary           |
| IBKR Web API     | Real-time quotes at execution; positions/account truth | Truth for positions |

### Fundamentals & Filings

| Source             | Role                                         |
| ------------------ | -------------------------------------------- |
| EODHD Fundamentals | Primary fundamentals (v1.1 S&P 1500)         |
| SEC EDGAR          | Deep document ingestion into research corpus |

### News, Sentiment & Research

| Source            | Role                                   |
| ----------------- | -------------------------------------- |
| Perplexity API    | Debate context, research synthesis     |
| EODHD News        | Headline stream for sentiment          |
| RSS/curated feeds | Macro commentary ingestion             |
| arXiv q-fin, SSRN | Academic papers (monthly curated pull) |

No single sentiment classifier is pre-picked (FP-9: multiple candidates run in parallel).

### Macro & Alternative

| Source        | Role                                  |
| ------------- | ------------------------------------- |
| FRED          | Yield curve, PMI, CPI, credit spreads |
| OECD CLI      | Composite leading indicators          |
| IMF WEO       | Macro forecasts                       |
| Google Trends | Alt-data search demand                |
| Truflation    | Alt inflation measure                 |

### Derived Signals

VIX, term structure (10Y-2Y), credit spreads (HYG-Treasury), correlation structure, realized vol — all auxiliary inputs. Primary representation is the latent learner.

---

## Fabric Table Catalog (29 Tables)

| Table                | Purpose                                                      |
| -------------------- | ------------------------------------------------------------ |
| `prices`             | OHLCV keyed by (instrument, date)                            |
| `corporate_actions`  | Splits, dividends, mergers                                   |
| `fundamentals`       | Statements, ratios per reporting period                      |
| `filings`            | Raw document refs + embedding IDs                            |
| `news`               | Headlines + embedding IDs + portfolio-impact tags            |
| `macro`              | Macro series keyed by (series, date)                         |
| `alt_data`           | Alternative data series                                      |
| `features`           | Pre-computed features, versioned (feature_v1, feature_v2...) |
| `embeddings`         | pgvector index of text embeddings for RAG                    |
| `latent_state`       | Historical z_t posteriors from champion and challengers      |
| `positions`          | Current/historical positions (IBKR-authoritative)            |
| `orders`             | Order state machine history                                  |
| `decisions`          | Every decision with full brief + outcome + counterfactual    |
| `shadow_decisions`   | Hypothetical decisions from challenger models                |
| `model_registry`     | Model versions, training windows, calibration snapshots      |
| `universe_changelog` | Every universe add/remove with reason                        |
| `audit_log`          | Every rule-engine decision, compliance veto, escalation      |
| `quotes`             | Bid/ask + size for spread and cost model                     |
| `fills`              | IBKR execution records (price, qty, fees, venue)             |
| `fills_synthetic`    | Synthesized partial-fill scenarios for testing               |
| `fee_schedule`       | Versioned IBKR commission + regulatory fees                  |
| `cost_attribution`   | Realized cost decomposition per trade                        |
| `sweep_history`      | IBKR FX sweep events for SGD/USD                             |
| `decisions`          | Full brief + outcome + counterfactual                        |
| `compliance_rules`   | PACT rules engine config                                     |
| `users`              | User accounts and preferences                                |
| `sessions`           | Auth sessions                                                |
| `debate_threads`     | Debate agent conversation history                            |
| `research_queries`   | Research assistant query log                                 |

---

## Freshness Rules

| Mode                  | Polling                | What                                                   |
| --------------------- | ---------------------- | ------------------------------------------------------ |
| Active (user in app)  | 1-min                  | Quotes and portfolio values                            |
| Active                | Once daily after close | EOD data                                               |
| Inactive (background) | 15-min                 | Regime-relevant inputs (VIX, SPX, DXY, credit spreads) |
| Inactive              | After close            | Full EOD pipeline                                      |
| Never                 | —                      | Tick data, streaming market data (v1)                  |

Every market data view shows `as of [timestamp]`. No pretense of real-time.

---

## Feature Store

Features are versioned. Refactoring mints a new version; old versions remain queryable until last consuming model is retired.

Categories: latent features (primary), econometric overlays (attribution), technical, fundamental (v1.1+), text-derived, macro.

Walk-forward discipline: feature value at time t depends only on data known at time t. Retroactive revisions tracked as separate records.

---

## Source Failure Modes

| Source Fails | Impact                                                                        |
| ------------ | ----------------------------------------------------------------------------- |
| EODHD        | Yahoo fallback; stale-data gate after threshold; rebalancing paused           |
| Yahoo        | EODHD continues; anomaly detection degraded                                   |
| IBKR         | All trading halts; portfolio state read-only; pending orders cancelled/queued |
| Perplexity   | Debate continues with RAG-only context                                        |
| FRED         | Cached last value; auxiliary input only                                       |

Fabric marks affected features stale; compliance agent enforces stale-data gate.
