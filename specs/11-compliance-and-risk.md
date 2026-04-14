# Compliance and Risk

**Status:** GOVERNING. Defines the Pre-Trade Compliance Agent (rules engine), envelope enforcement, hard safety limits, and the compliance veto over model outputs.

Anchored to the owner's value chain map (Block 3 — Risk, Compliance, Reporting), PACT governance framework (see `rules/pact-governance.md`), and Phase 01 red-team finding A-C1 (API security and compliance were underspecified).

---

## 1. Principle

> **The compliance layer has veto power over every proposed trade, at every autonomy level, regardless of which model produced it.**

No model output — DRL policy, classical baseline, LLM suggestion — reaches execution without passing through the Pre-Trade Compliance Agent. The veto is structural. A bypass would be a rule violation of this spec.

---

## 2. The Pre-Trade Compliance Agent

### 2.1 What It Is

A **PACT-governed rules engine** that evaluates every proposed trade and every envelope-touching action before it reaches the order manager or the user-facing Decisions surface.

### 2.2 Architecture

- Rules are **data**, not code. A rule registry table (`compliance_rules`) stores each rule's predicate, severity, action, and metadata.
- Each proposed action is a typed message: trade proposal, envelope change, autonomy promotion, model promotion, universe change.
- The engine evaluates all applicable rules for the action type.
- Rule outcomes: `pass`, `warn`, `escalate_to_user`, `block`.
- The engine writes an audit record for every evaluation.

### 2.3 The Default-Deny Posture

Any action whose compliance rule set raises an exception — rule evaluation fails, rule set is incomplete, rule engine is in maintenance — is **blocked by default**. Errors on the side of inaction. Aligned with PACT default-deny.

---

## 3. The Rule Set (v1 Minimum)

Rules are data, so this is a starting set. The registry can add rules without a release.

### 3.1 Blocking Rules (Hard Gates)

| Rule ID                       | Predicate                                                                                 | Reason                                 |
| ----------------------------- | ----------------------------------------------------------------------------------------- | -------------------------------------- |
| `env.drawdown_ceiling`        | Action would take portfolio past envelope drawdown ceiling                                | Envelope is the trust boundary (`08-`) |
| `env.vol_target`              | Action would breach vol target band                                                       | Envelope                               |
| `env.concentration.position`  | Action would exceed per-position concentration cap                                        | Envelope                               |
| `env.concentration.sector`    | Action would exceed per-sector concentration cap                                          | Envelope                               |
| `env.universe`                | Action targets an instrument not in approved universe                                     | Envelope                               |
| `env.cost_budget`             | Action's estimated cost exceeds the remaining cost budget                                 | Envelope                               |
| `data.stale_price`            | Price data for target instrument is older than a freshness threshold                      | Correctness — FP-3, Phase 01 A-H2      |
| `data.stale_fundamental`      | (v1.1+) Fundamentals for target are older than freshness threshold                        | Correctness                            |
| `state.kill_switch`           | Kill switch is active                                                                     | Safety (`10-`)                         |
| `state.paper_trading`         | Paper flag is on; action is a real trade                                                  | Safety (FP-7, `10-`)                   |
| `state.ood`                   | `z_t` is detected as OOD and action is not manually approved                              | Safety (`10-` §8)                      |
| `autonomy.level_breach`       | Action exceeds the current autonomy level's scope                                         | `08-`                                  |
| `model.confidence_floor`      | Model's posterior confidence on the decision is below a floor                             | Model quality                          |
| `model.pool_disagreement`     | Pool disagreement on the action is above a ceiling without manual approval                | Model quality                          |
| `exec.freshness_at_execution` | Fresh price pull at execution time differs from the cached price by more than a threshold | Execution safety — Phase 01 A-H2       |
| `api.ibkr_health`             | IBKR integration reports an unhealthy state                                               | Infrastructure                         |

### 3.2 Escalation Rules (User-Facing)

| Rule ID                     | Predicate                                                                 | Action                                                                                    |
| --------------------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `escalate.urgent_band`      | Action is in the Urgent `a_t` band and current autonomy level is below L3 | Present in Decisions surface with full brief                                              |
| `escalate.crisis_band`      | Action is in the Crisis `a_t` band                                        | Present in Decisions surface unless explicitly a kill-switch clear or envelope tightening |
| `escalate.envelope_change`  | Action is an envelope change                                              | Present with biometric gate (`10-`)                                                       |
| `escalate.model_promotion`  | Action is a challenger promotion                                          | Present with full evidence package (`05-` §5.5)                                           |
| `escalate.autonomy_upgrade` | Action is an autonomy-level upgrade                                       | Present with track record + Brinson attribution (`08-`)                                   |
| `escalate.debate_open`      | Action relates to a pending decision with an open Debate thread           | Routed to the Debate thread                                                               |
| `escalate.first_seven_days` | System is in the first 7 live days post paper→live                        | Every action is user-facing regardless of autonomy level                                  |

### 3.3 Warning Rules (Non-Blocking)

| Rule ID                        | Predicate                                                                                 | Action                                                                           |
| ------------------------------ | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `warn.turnover_high`           | Action would push weekly turnover above a soft ceiling                                    | Surface in brief                                                                 |
| `warn.fee_intensity`           | Cost ratio vs expected alpha is in a yellow zone                                          | Surface in brief                                                                 |
| `warn.model_calibration_drift` | The head producing the recommendation has shown calibration drift in the last N decisions | Surface in brief, trigger challenger evaluation                                  |
| `warn.user_override_pattern`   | The user has overridden similar recommendations recently                                  | Surface in brief as "you overrode similar decisions — here's the counterfactual" |
| `warn.fx_exposure`             | Currency exposure is outside a soft band                                                  | Surface in brief                                                                 |

---

## 4. Hard Safety Limits (Non-Dynamic)

These do not self-tune. They are circuit breakers. They are the one exception to FP-3 (dynamic over static) — deliberately.

| Limit                             | Value                                                                        | Behavior                                                                                 |
| --------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **Emergency stop drawdown**       | A fraction of the envelope ceiling (user-configurable, conservative default) | Kill switch auto-trips; all trading halted; 100% cash/short bonds; human review required |
| **Kill switch**                   | Manual + auto-trip                                                           | See `10-` §5                                                                             |
| **Paper trading gate**            | 2 weeks minimum                                                              | Enforced in `env.paper_trading` + `state.paper_trading` rules                            |
| **Freshness floor for execution** | A threshold in seconds                                                       | Enforced in `exec.freshness_at_execution`                                                |

---

## 5. Envelope Enforcement

The envelope (user-owned; see `08-` §1) is not a preference — it is a binding constraint that the Pre-Trade Compliance Agent enforces on every action.

### 5.1 Flow

1. Allocator / router proposes an action with a target weight change
2. Action is passed to the compliance agent with:
   - Target weight change
   - Estimated cost
   - `z_t` posterior context
   - Data freshness snapshot
   - Current autonomy level
   - Current envelope snapshot
3. Compliance agent evaluates all applicable rules in order
4. First blocking rule short-circuits
5. Warnings accumulate into the brief
6. Escalation rules determine whether the action goes to execution or to Decisions surface

### 5.2 Time-Varying Envelope Tightening

Midas may **tighten** the envelope dynamically within bounds the user has pre-approved (per PC-1, PC-8 — continuous risk response). Example: as drawdown approaches the ceiling, position limits tighten via a continuous response function. The widening direction is always user-owned.

The tightening function is itself part of the state — it is not a hardcoded curve but a dynamic response governed by `z_t` posterior, tail head, and pool disagreement. The response function is monitored for calibration like any other head.

---

## 6. Credential Storage And API Security

Phase 01 red-team finding A-H6 flagged missing credential storage architecture. This spec resolves it.

### 6.1 IBKR Credentials

- OAuth tokens and API keys are stored encrypted in the `credentials` fabric table
- Application-level encryption key is loaded from `.env` at process start
- Tokens never appear in logs; log redaction is enforced in the adapter layer
- Token refresh is a background job with its own audit trail
- On token failure, all trading is paused (`api.ibkr_health` rule)

### 6.2 API Authentication

Phase 01 red-team A-C1: the API layer had no auth specification. This spec resolves it.

- Every Nexus endpoint requires authentication — JWT minimum for v1
- Session management with configurable inactivity timeout
- Biometric re-auth on mobile for high-stakes actions (see `10-`)
- CORS configured restrictively
- Rate limiting per session / IP

### 6.3 Secrets Lifecycle

- No hardcoded secrets in code (per `rules/security.md`)
- `.env` is the only source of truth for secrets in development
- In production-like deployments, a secrets manager (KMS-backed) replaces `.env`
- `.env` is in `.gitignore`; `.env.example` documents required keys

---

## 7. Background Jobs And Infrastructure Health

Phase 01 red-team A-C2: the background job architecture was missing. This spec resolves it.

### 7.1 Scheduled Jobs

The following jobs run on schedules and are essential to autonomous operation:

| Job                                         | Frequency                                             | Purpose                                |
| ------------------------------------------- | ----------------------------------------------------- | -------------------------------------- |
| EOD data ingestion                          | Daily after close                                     | Prices, dividends, splits from EODHD   |
| Fundamentals refresh                        | Daily                                                 | Statements, ratios                     |
| News pipeline                               | Continuous                                            | EODHD news + Perplexity + RSS          |
| Macro ingestion                             | Daily to monthly                                      | FRED, OECD, alt-data                   |
| Representation learner inference            | Daily (per `z_t` update); continuous when user active | Updates `z_t` posterior                |
| State inference update                      | Continuous on new data                                | Posterior maintenance                  |
| Router calibration update                   | Hourly to daily                                       | Inner loop of `05-`                    |
| Rebalance trigger check                     | Daily + event-driven                                  | Triggers proposals per TAA/SAA cadence |
| Counterfactual computation                  | Daily batch                                           | Feeds `12-` attribution                |
| Population-based training (challenger lane) | Continuous during training phase                      | Outer loop of `05-`                    |
| Health check / heartbeat                    | Every minute                                          | IBKR, data sources, model heads        |
| NAV + valuation                             | Daily EOD                                             | Block 5 of `02-`                       |
| Paper trading report generator              | On request + at end of paper period                   | FP-7                                   |

### 7.2 Scheduler Architecture

- Kailash Core SDK workflows with a scheduler service (APScheduler or equivalent)
- Every scheduled job writes a heartbeat entry; the health check detects stalled jobs
- Failed jobs retry with exponential backoff; persistent failure escalates to the user
- A job that would execute a trade checks the compliance agent before running — even scheduled rebalances are compliance-gated

### 7.3 Graceful Degradation

If a subsystem fails, trading pauses automatically. Never execute with stale or missing data. Specific degradation paths:

| Failure             | Behavior                                                                                                                                                                                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| EODHD outage        | Yahoo fallback; if both fail, `data.stale_price` trips                                                                                                                                                                                     |
| IBKR outage         | `api.ibkr_health` blocks all actions; monitoring continues; queued actions held                                                                                                                                                            |
| Perplexity outage   | Debate continues with RAG-only context                                                                                                                                                                                                     |
| Frontier LLM outage | Fall back to the next-best frontier model; if all frontier models are unavailable, the Debate surface shows a degraded banner and the decisions surface warns briefs may be less polished; no decisions execute silently on a degraded LLM |
| Database outage     | Full system halt; the compliance agent cannot run; everything blocks                                                                                                                                                                       |
| Scheduler outage    | No new decisions propose; existing pending decisions still visible                                                                                                                                                                         |

---

## 8. Audit Trail

Every rule evaluation, every compliance decision, every escalation writes to an **immutable audit log** table. The log is:

- Append-only
- Indexed by (timestamp, rule_id, action_type, decision_id)
- Queryable by the Debate agent and by the user (via an audit viewer in Settings)
- The authoritative record for any dispute, reconciliation, or regulatory audit (if Midas is ever commercialized)

---

## 9. Compliance Agent In The Critical Path

```
[Action proposed by router / user / scheduler]
               │
               ▼
[Compliance Agent evaluates rules in order]
               │
               ├── blocking rule fails → BLOCK + audit
               │
               ├── escalation rule fires → ESCALATE to Decisions / Debate / user
               │
               └── all pass → return with warnings accumulated
                              │
                              ▼
               [Brief composer adds warnings to brief]
                              │
                              ▼
               [Execution agent executes against IBKR]
                              │
                              ▼
               [Reconciliation agent verifies fills]
                              │
                              ▼
               [Audit record closes]
```

At no point in this flow is the compliance agent bypassable. The router is **not allowed** to short-circuit. The scheduler is **not allowed** to bypass. The Debate agent, when it mutates a pending decision via `update_decision`, re-enters this flow from the top.

---

## 10. Relationship To Other Specs

- `08-autonomy-and-trust.md` — defines the envelope; compliance enforces it
- `07-evidence-first-decision.md` — brief composer receives warnings from compliance
- `10-moments-of-truth.md` — defines UX rules that compliance enforces at the backend
- `05-model-pool-and-meta-router.md` — model promotion is a compliance-gated decision
- `12-performance-and-track-record.md` — audit trail feeds attribution
- Root `rules/pact-governance.md` — governance framework this spec implements
