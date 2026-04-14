# Performance and Track Record

**Status:** GOVERNING. Defines how performance is measured, decomposed via Brinson attribution, and converted into the track record that earns autonomy.

Anchored to FP-14 (track record earns latitude), the owner's Q1 = B answer, and the owner's value chain map (Block 5 — Performance Measurement + Attribution).

---

## 1. Principle

> **Autonomy is a currency earned through demonstrated performance, decomposed into allocation effect, selection effect, and calibration quality — not a setting the user flips.**

Performance is not a vanity metric. It is the substrate for the autonomy ladder (`08-`), model promotion contracts (`05-`), and the user's trust calibration over time.

---

## 2. Primary Metrics

All metrics computed daily from the NAV time series (Block 5 §6.1 of `02-`). Benchmarks: SAA-static baseline (the user's envelope with no TAA or security selection applied), 60/40 passive, S&P 500 total return.

| Metric                                    | Computed                                         | Used for                                       |
| ----------------------------------------- | ------------------------------------------------ | ---------------------------------------------- |
| Total return                              | Daily / weekly / monthly / YTD / since inception | Reporting                                      |
| Risk-adjusted return — Sharpe             | Rolling windows                                  | Reporting + promotion contracts                |
| Risk-adjusted return — Sortino            | Rolling windows                                  | Reporting                                      |
| Risk-adjusted return — Calmar             | Rolling windows                                  | Promotion contracts                            |
| Max drawdown                              | Rolling                                          | Reporting + compliance                         |
| Recovery time                             | Per drawdown episode                             | Reporting                                      |
| Annualized volatility                     | Rolling                                          | Reporting + envelope monitoring                |
| Tracking error vs SAA baseline            | Daily                                            | Attribution                                    |
| Turnover                                  | Weekly / monthly                                 | Cost monitoring                                |
| Transaction cost as fraction of return    | Monthly                                          | Cost monitoring                                |
| Information Ratio (IR)                    | Rolling windows vs SAA baseline                  | Active-management quality; promotion contracts |
| Alpha (Jensen's α)                        | Rolling windows vs SAA baseline and vs benchmark | Active-return skill net of beta                |
| M² (Modigliani risk-adjusted performance) | Rolling windows                                  | Benchmark-comparable return at benchmark risk  |
| Treynor Ratio                             | Rolling windows                                  | Return per unit of systematic (beta) risk      |

### 2.1 Metric Roles and Interpretation

- **Information Ratio** — active return / active risk vs the SAA baseline. Primary signal of TAA + selection skill net of tracking risk. Used as a core promotion input alongside Brinson attribution; a strategy with positive Brinson allocation effect but poor IR is statistically indistinguishable from noise.
- **Alpha (Jensen's α)** — regression-based risk-adjusted excess return. Computed against the SAA baseline AND the passive benchmark (60/40, S&P 500) for triangulation. Alpha that survives multiple-comparison correction is real skill; alpha that vanishes under Deflated Sharpe / PBO is not.
- **M² Measure** — translates Sharpe into a direct return comparison at the benchmark's risk level. Useful in user-facing reporting because it renders "risk-adjusted outperformance" in percent rather than a dimensionless ratio — the user reads "Midas returned X% more than 60/40 at equivalent risk."
- **Treynor Ratio** — return per unit of systematic risk (β). Primary use: evaluating whether excess returns are earned via idiosyncratic skill vs via leveraged market beta. A high Sharpe with a high Treynor-to-Sharpe ratio means the edge is mostly beta — relevant for the honesty layer on earned autonomy.

### 2.2 Statistical Discipline

All metrics above are **distributions, not point estimates**. Reporting shows the rolling value AND the bootstrapped confidence interval. Promotion contracts (see `08-` and `05-`) require the metric's bootstrap lower bound to exceed the floor, not just the point estimate. This is a direct response to the Redteam Round 1 Quant finding C4 (calibration methodology without multiple-comparison correction); the same discipline applies here.

Benchmarks for IR / alpha / M² / Treynor:

- **Primary:** SAA-static baseline (measures active Midas decisions net of the user's envelope)
- **Secondary:** 60/40 passive (multi-asset reference)
- **Tertiary:** S&P 500 total return (equity-only reference for the equity-tilt components)

---

## 3. Brinson–Fachler Attribution

The core attribution decomposition. Required because the autonomy ladder promotes per-layer — L2 requires positive **allocation effect**, L3 requires positive **selection effect**.

### 3.1 Decomposition

For each reporting period and each asset class bucket:

- **Allocation effect** = (portfolio weight in bucket − benchmark weight in bucket) × (benchmark return of bucket − total benchmark return). Credit for asset-class tilts.
- **Selection effect** = benchmark weight in bucket × (portfolio return of bucket − benchmark return of bucket). Credit for picking winners within the bucket.
- **Interaction** = (portfolio weight − benchmark weight) × (portfolio return of bucket − benchmark return of bucket). Joint credit.

Total excess return = allocation + selection + interaction.

### 3.2 Buckets

- **Asset class** — equity / fixed income / real assets / cash
- **Sector** (within equity) — the 11 GICS sectors
- **Duration** (within fixed income) — short / intermediate / long / credit
- **Style** (within equity) — growth / value / momentum / quality / low-vol tilts

Attribution is computed at each level; dashboards show the decomposition hierarchically.

### 3.3 Benchmark For Attribution

The attribution benchmark is the **SAA-static baseline** — the portfolio the envelope would produce with no TAA and no security selection, rebalanced to envelope targets at the same cadence. This isolates TAA's contribution (allocation) and security selection's contribution (selection).

Secondary benchmarks (60/40, S&P 500) are reported but not used for the attribution split.

### 3.4 Time Windows

Attribution is computed on a rolling basis:

- 1-week (noisy, context only)
- 1-month (primary reporting window)
- 3-month (promotion contract window)
- 12-month (track record summary)
- Since inception (lifetime)

Short windows are shown for context but do not drive autonomy decisions — they are too noisy. Promotion contracts read 3-month and 12-month windows.

---

## 4. Calibration Tracking

Performance is not just returns. It is also how well the model's stated confidence matched reality.

### 4.1 Per-Head Calibration Curves

Every head in the model pool (return, vol, tail, allocation, cross-sectional) maintains a calibration curve: when the head says 70% confidence, how often is it actually right?

Curves are computed over rolling windows and conditional on `z_t` neighborhood (a head can be well-calibrated in some latent regions and poorly in others — the router uses this).

### 4.2 Aggregate Calibration

System-level calibration is tracked as the weighted average of head-level calibration, weighted by how much each head contributed to actual decisions over the window.

### 4.3 User-Facing Calibration View

In the Backtest or Portfolio surface, the user can view:

- Aggregate calibration curve
- Per-head breakdown
- Trend over time (is the system improving or drifting?)
- Calibration conditioned on `z_t` band (are some states harder to calibrate?)

This is the answer to "fake confidence" (user failure mode §5.3 of `01-`). Visible calibration lets the user verify that Midas's confidence claims are earned.

---

## 5. Counterfactual Tracking

Every decision — executed or rejected — has a counterfactual computed after its horizon closes.

### 5.1 What Counterfactual Means In v1

Per Phase 01 red-team A-H3, the counterfactual is **not** a full portfolio simulation. It is the realized return of the alternative path at 1d, 1w, and 1m horizons:

- **Executed decisions** — counterfactual = what would have happened if held instead of traded
- **Rejected decisions** — counterfactual = what the recommendation would have produced
- **Modified decisions** — counterfactual = the original (pre-modification) recommendation

These are approximations — they do not account for downstream portfolio effects. They are honest, computable, and useful.

### 5.2 Where Counterfactuals Go

- Into the `decisions` fabric table alongside the decision
- Into the user's override pattern view
- Into the Debate agent's evidence store (the agent can reference them: _"you overrode three similar; the counterfactual cost of those holds was X"_)
- Into the router's context (not directly retraining, but informing routing decisions)
- Into the promotion/demotion contracts (a model whose recommendations consistently lose to their counterfactuals degrades fast)

### 5.3 v1.5+ Extension

Full portfolio-path counterfactual simulation is deferred. The approximation is sufficient for v1.

---

## 6. The Track Record Score

### 6.1 What It Is

A composite score the autonomy ladder reads when evaluating upgrade contracts. It is not a single number shown to the user — it is an internal signal composed of:

| Component                                   | Contribution                                                                           |
| ------------------------------------------- | -------------------------------------------------------------------------------------- |
| Brinson allocation effect (3-month rolling) | Primary for L2 / L3 upgrades                                                           |
| Brinson selection effect (3-month rolling)  | Primary for L3 / L4 upgrades (selection layer)                                         |
| Calmar ratio (3-month rolling)              | Balances return vs drawdown                                                            |
| Calibration quality                         | Down-weights good returns achieved with over-confidence                                |
| Override convergence                        | User override rate trending down indicates increasing trust; up indicates the opposite |
| Degradation event count                     | Each degradation event penalizes                                                       |
| Turnover / cost drag                        | Excessive turnover penalizes                                                           |
| Worst-case rolling window                   | A bad window disqualifies regardless of aggregate                                      |

### 6.2 How It Is Used

- The autonomy ladder (`08-` §7) reads the track record score as part of evaluating upgrade contracts
- When the score crosses a threshold, the upgrade proposal surfaces in Decisions
- The score does not silently raise or lower autonomy — all transitions are either user-approved (upgrades) or compliance-triggered (downgrades)

### 6.3 What The User Sees

A user-friendly summary in the Portfolio or Backtest surface:

- Current score in human-readable form
- Contributing factors in plain language
- Current standing vs the next autonomy upgrade threshold
- History of upgrades and demotions with dates and reasons

---

## 7. Reporting Surfaces

### 7.1 Weekly Summary (Push Notification + In-App)

- Return + benchmark comparison for the week
- Trades executed + fees
- `a_t` band distribution over the week
- Any notable events (regime transitions, degradation, override patterns)

### 7.2 Monthly Statement

- Full Brinson attribution for the month
- Calibration snapshot
- Track record score movement
- Performance vs all three benchmarks
- Override log
- Compliance events (vetoes, warnings, escalations)
- Any model promotions or demotions

### 7.3 Paper Trading Report (Generated once, at end of paper period)

- See `08-` §6.2 for the full contract
- This is the blocking report for the paper→live transition

### 7.4 On-Demand Exports

- User can request any time-range export via Settings or the Debate agent
- Exports are CSV + PDF
- No external data in exports — only the user's own data

---

## 8. Performance Is Not Enough By Itself

A final important rule: positive performance by itself does not earn an autonomy upgrade. The composite score requires positive performance **plus** good calibration **plus** low override friction **plus** no degradation events.

A system that made money while being over-confident is not a system the user should delegate more to. The calibration component prevents "right for the wrong reasons" from earning autonomy.

---

## 9. Relationship To Other Specs

- `05-model-pool-and-meta-router.md` — promotion / demotion contracts read calibration curves and Brinson decomposition
- `08-autonomy-and-trust.md` — autonomy ladder reads the track record score
- `07-evidence-first-decision.md` — decisions table and counterfactual store feed the Debate agent
- `09-surfaces-and-attention.md` — reporting surfaces (weekly summary, monthly statement) render this data
- `11-compliance-and-risk.md` — compliance events are one input to the track record score
