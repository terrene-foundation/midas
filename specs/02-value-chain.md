# Value Chain and Operating Model

**Status:** GOVERNING. Defines the full buy-side operating model Midas implements and the v1 scope boundary within it.

Derived from the owner's value chain map (turn 3) and FP-1 (institutional infrastructure, democratized). Where Phase 01 narrowed scope to ETF-based portfolio management, the owner's value chain map put the full front/middle/back office back on the table. This spec reconciles the two and sets the v1 boundary explicitly.

---

## 1. The Operating Model

Midas implements a complete buy-side investment management operating model organized into five blocks. Every block has a concrete v1 deliverable. Blocks marked `[SCOPE: v1]` are required for paper-trading launch. Blocks marked `[SCOPE: v1.5+]` are specified here so the system is not designed to preclude them.

```
┌─────────────────────────────────────────────────────────────────────┐
│                  BLOCK 1 — INTELLIGENCE & RESEARCH                  │
│  Data Ingestion │ News & Alt-Data │ Knowledge Base │ Research Agent  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────┴─────────────────────────────────────┐
│               BLOCK 2 — INVESTMENT MANAGEMENT (3 layers)             │
│                                                                      │
│    Strategic Asset Allocation (SAA)  →  Strategic Asset Mix          │
│    Tactical Asset Allocation (TAA)   →  Tactical Asset Mix           │
│    Security Selection                →  Target Positions             │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────┴─────────────────────────────────────┐
│          BLOCK 3 — RISK, COMPLIANCE, VALUATION (cross-cutting)       │
│   Pre-Trade Compliance │ Continuous Risk │ Valuation/NAV │ Reporting  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────┴─────────────────────────────────────┐
│             BLOCK 4 — PORTFOLIO CONSTRUCTION & EXECUTION              │
│   Portfolio Construction │ Trade Execution │ Allocation Adjustment    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────┴─────────────────────────────────────┐
│                 BLOCK 5 — PERFORMANCE & OPERATIONS                    │
│   Performance Measurement │ Attribution │ Order Ops │ Settlement      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Block 1 — Intelligence and Research

### 2.1 Data Ingestion `[SCOPE: v1]`

All raw sources land in the data fabric first; every downstream component reads _only_ from the fabric. See `03-universe-and-data.md` for the full data source catalog.

Consumers:

- Representation learner (latent state)
- Econometric factor computer (overlay)
- News/sentiment pipeline
- Research assistant RAG

### 2.2 News and Alternative Data Analysis `[SCOPE: v1]`

- News: EODHD news + Perplexity-sourced research + RSS feeds for macro commentary
- Alt-macro: FRED, OECD CLI, Google Trends
- Pipeline: ingest → embedding → vector index (pgvector) → consumed by LLM analyst, LLM debate, and latent learner as auxiliary inputs

**No one-off sentiment classifier is picked ahead of time.** Per FP-9, multiple embedding candidates run in parallel and the meta-router decides which is trusted for the current context. Frontier LLMs handle the decision-adjacent synthesis.

### 2.3 Knowledge Base and Research Assistant `[SCOPE: v1]`

A RAG-backed research corpus that the Analyst agent and Debate agent both query:

- Filings (SEC EDGAR 10-K/10-Q/8-K, insider transactions)
- Academic papers (arXiv q-fin, SSRN — curated ingestion)
- Broker notes and macro commentary (manual ingestion)
- User's own saved research (personal store)

Implementation: Kailash RAG nodes over pgvector; frontier LLMs for synthesis.

### 2.4 LLM Analyst vs Classical AI Split `[SCOPE: v1]`

The owner's value chain map separates "LLM Agents" from "Classical AI." In Midas this distinction maps to:

- **LLM Agents (frontier):** Analyst brief writer, Debate agent, Research assistant, latent-state-to-factor-language projection. FP-12 applies — frontier only.
- **Classical AI (DL models + classical ML in the model pool):** Representation learners, state-inference networks, return-prediction heads, allocator policy nets, cross-sectional CNN/GNNs. See `05-model-pool-and-meta-router.md`.

The two are not competing — they are different layers. LLMs interface with the user; DL models drive the decision.

---

## 3. Block 2 — Investment Management (Three Layers)

The three-layer IM structure is the backbone of the value chain. Each layer has a distinct job, a distinct update frequency, and a distinct model pool.

### 3.1 Strategic Asset Allocation (SAA) `[SCOPE: v1]`

**Job:** determine the long-term strategic mix across asset classes (equity / bonds / real assets / cash) within the user's risk envelope.

**Update frequency:** slow — monthly review, quarterly re-optimization, bound by envelope.

**Model pool (per FP-9, pools not picks):**

- Champion candidates: DRL policies trained on long-horizon objectives with path-dependent transaction costs, risk-aware RL
- Challenger baselines: Mean-Variance Optimization, Black-Litterman, Hierarchical Risk Parity, Risk Parity
- Stress testing: scenario generation under synthesized adverse latent states
- Ensemble via the meta-router (05-model-pool-and-meta-router.md)

**Output:** target strategic mix with confidence posterior.

### 3.2 Tactical Asset Allocation (TAA) `[SCOPE: v1]`

**Job:** short/medium-term tilts around the strategic mix based on current latent state and market outlook.

**Update frequency:** weekly max, regime-conditional — more frequent when the state-transition posterior is high.

**Model pool:**

- Champion candidates: tactical heads conditioned on `z_t` posterior, state-space-conditioned policy nets, temporal DL models (transformer / Mamba / TCN families)
- Challenger baselines: momentum-and-carry signal framework, investment clock, Black-Litterman with signal views
- Market outlook rubrics: structured prompts to the frontier LLM analyst produce qualitative market-outlook factors that feed the TAA head as auxiliary context

**Output:** tactical tilt vector relative to SAA target.

### 3.3 Security Selection `[SCOPE: v1]`

**Job:** choose specific securities within each allocation bucket.

**v1 universe:** ETF sector rotation first (naturally diversified, high liquidity, cheap), then S&P 1500 US equities as latent-learners earn their keep. See `03-universe-and-data.md` for universe specification.

**Update frequency:** ETF sector rotation weekly max; single-name selection bi-weekly max.

**Model pool:**

- Champion candidates: cross-sectional CNNs over the universe (spatial structure), Graph Neural Networks over asset-relationship graphs (correlation, co-holding, sector), cross-sectional transformers
- Challenger baselines: factor-ranked long-only (quality + low-vol + momentum composite), fundamental screens
- Liquidity and cost gating: every proposed trade must clear expected-alpha > expected-cost with cost estimated by the execution pool

**Output:** target position list (ticker, weight, conviction posterior).

---

## 4. Block 3 — Risk, Compliance, Valuation, Reporting (Cross-Cutting)

This block runs continuously and has veto power over the entire IM block.

### 4.1 Pre-Trade Compliance Agent `[SCOPE: v1]`

A **PACT-governed rules engine** that evaluates every proposed trade before it touches the order manager. See `11-compliance-and-risk.md`.

Minimum rule set for v1:

- Envelope breach (drawdown, volatility, concentration, universe) — blocking
- Cost budget breach (estimated cost vs expected alpha ratio) — blocking
- Stale-data gate (data freshness below threshold) — blocking
- Kill switch active — blocking
- Paper-trading gate (if live flag off, no real orders) — blocking
- Universe constraint (instrument not in approved universe) — blocking
- Model confidence floor (`z_t` in a region below calibration threshold) — escalates to user
- Autonomy-level breach (action exceeds current level's scope) — escalates to user

Rules are data, not code. New rules can be added without a release.

### 4.2 Continuous Risk Monitoring `[SCOPE: v1]`

Real-time (daily EOD, polling-refreshed when user is active) monitoring of:

- Portfolio drawdown vs envelope, with continuous response function (no step ladders)
- Volatility vs target band
- Correlation breakdown detection (derived from `z_t` — no hard-coded DCC threshold)
- Position-level contribution to portfolio tail risk
- Model head calibration drift

Triggers: degradation contracts, autonomy downgrades, escalations to the Decisions surface.

### 4.3 Valuation and NAV `[SCOPE: v1]`

Daily NAV computation from positions × marks. Produces the time series on which Brinson attribution is computed in Block 5. Uses IBKR end-of-day marks with EODHD cross-check.

### 4.4 Client Reporting and Communications `[SCOPE: v1]`

Even for a single user, the system produces:

- Weekly summary (push)
- Monthly statement (P&L, attribution, model calibration snapshot, override log)
- Ad-hoc exports when the user asks

For v1.5+ multi-tenant: generalizes to per-tenant reports.

---

## 5. Block 4 — Portfolio Construction and Execution

### 5.1 Portfolio Construction `[SCOPE: v1]`

Translates (SAA target + TAA tilt + Security Selection list) into an orderable trade list. This is where:

- Current holdings are reconciled with the target
- Trade list is generated subject to the cost budget
- Turnover cap is enforced
- Fractional/whole share constraints applied
- Trade list is handed to the Pre-Trade Compliance Agent for veto

### 5.2 Trade Execution `[SCOPE: v1]`

- Orders routed to IBKR Web API v1.0 (primary) or TWS bridge (fallback)
- **Fresh price pull at execution time** (bypasses the cache — FP-3 on dynamic, and the Phase 01 red-team finding A-H2)
- Execution agent tracks partial fills, reroutes or cancels as needed
- Post-execution reconciliation against the Compliance Agent's expectations

### 5.3 Allocation Adjustment `[SCOPE: v1]`

Ongoing drift monitoring. When drift exceeds tolerance and the regime state and autonomy level permit, the rebalance is triggered. Otherwise it becomes a pending decision in the Decisions surface.

---

## 6. Block 5 — Performance and Operations

### 6.1 Performance Measurement `[SCOPE: v1]`

Daily NAV, daily / weekly / monthly return, rolling Sharpe, Sortino, Calmar, max drawdown. Benchmark comparison against: SAA-static baseline, 60/40 passive, S&P 500 total return.

### 6.2 Performance Attribution `[SCOPE: v1]`

**Brinson-Fachler decomposition** into Allocation Effect + Selection Effect + Interaction:

- **Allocation effect** = credit/blame for SAA and TAA decisions
- **Selection effect** = credit/blame for Security Selection decisions
- **Interaction** = joint effect

Why this matters for v1 beyond reporting: the attribution is the **substrate for track-record-earns-latitude** (FP-14). Autonomy upgrades require positive attribution at the layer being delegated.

### 6.3 Operations Management `[SCOPE: v1 (partial)]`

IBKR handles the primary order lifecycle for v1. Midas owns:

- Order state machine (pending → submitted → partial → filled → reconciled → attributed)
- Settlement reconciliation (verify filled quantities match executed orders)
- Failure recovery (API timeouts, rejected orders, partial fills)

IBKR handles clearing and custody. Midas does not reimplement these.

---

## 7. Kailash Framework Mapping

The value chain maps cleanly onto the Kailash stack. This is by design — FP-1 says Midas puts the institutional stack into individual hands, and the Kailash framework family exists to make that feasible.

| Value chain block                                                     | Kailash framework                                                                               |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Data Ingestion, Feature Fabric, Feature Store                         | **DataFlow** — zero-config database, Redis cache, PostgreSQL store                              |
| Representation learning, model pool, meta-router, champion/challenger | **Kailash ML** + Core SDK — model registry, training pipeline, drift monitor, ensemble combiner |
| LLM analyst, debate agent, research assistant, RAG                    | **Kaizen** — signature-based programming, multi-agent coordination, tool use                    |
| Fine-tuning domain models (if required)                               | **Kailash Align** — LoRA adapters, DPO/SFT, model serving                                       |
| Pre-Trade Compliance Agent, envelope enforcement, audit trail         | **PACT** — D/T/R accountability grammar, operating envelope, default-deny policy                |
| Workflow orchestration (daily pipelines, regime monitor, rebalancer)  | **Core SDK** — workflows, nodes, scheduled jobs                                                 |
| Multi-channel delivery (Web + Mobile + local CLI)                     | **Nexus** — unified API/CLI/MCP deployment                                                      |
| MCP tools exposed to frontier LLMs                                    | **Kailash MCP** — tools, resources, governance                                                  |

This is not a "we should use Kailash" preference — it is the natural shape. Any component built outside this framework needs a reason.

---

## 8. v1 Scope Boundary (Explicit)

**In scope for v1 paper-trading launch:**

- All of Block 1 (Intelligence & Research)
- All three layers of Block 2 (SAA + TAA + Security Selection) operating on ETF + S&P 1500 universe
- All of Block 3 (Risk, Compliance, Valuation, Reporting) with minimum rule set
- All of Block 4 (Portfolio Construction, Execution, Allocation Adjustment) with IBKR paper
- Block 5 Performance Measurement + Brinson Attribution + IBKR-backed operations

**Phase within v1:**

- v1.0 — ETF sector rotation only (validates representation learning + model pool + router on a bounded universe before single-name adds noise)
- v1.1 — ETF sector rotation + S&P 1500 single-name selection (only after v1.0 shows positive Brinson allocation effect in paper trading)

**Out of v1, kept in spec so the system is not designed to preclude them:**

- Options, leverage, derivatives
- Multi-tenant / multi-user
- Commercialization (regulatory path)
- Real-time streaming market data (EOD + polling is sufficient for investing-not-trading)
- Dedicated transparency/explainability module (deferred until working models earn it — owner direction turn 4)
- US / foreign single names beyond S&P 1500
- Tax-lot accounting

---

## 9. Change Management

This spec is updated at first instance when a scope boundary moves. The change is logged in this file with a date and reason. Plans and todos that contradict the current boundary are wrong and must be reconciled in the same action.
