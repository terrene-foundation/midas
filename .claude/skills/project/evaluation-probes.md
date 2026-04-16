# Evaluation Probe Suite — Acceptance Contracts

**Source:** `tests/evaluation/probes/` (10 probe files)
**Purpose:** Live specification of what "safe to operate" means; each probe encodes an acceptance contract as a Tier 2 test

---

## Probe Index

| Probe                                | Domain                   | Spec Anchor                  | Red Team Task |
| ------------------------------------ | ------------------------ | ---------------------------- | ------------- |
| `test_calibration_protocol.py`       | Calibration              | specs/05 §5.4, specs/12 §4   | T-00-04       |
| `test_router_overfitting.py`         | Router overfitting       | specs/05 §4.2, §4.5          | T-00-03       |
| `test_shadow_lane_isolation.py`      | Shadow lane isolation    | specs/05 §5.2, §5.3          | T-00-05       |
| `test_track_record_protocol.py`      | Track record / promotion | specs/08 §7, specs/12 §3.4   | T-00-06       |
| `test_kill_switch_process_lock.py`   | Kill switch              | specs/08 §5.4, specs/10 §5   | T-00-09       |
| `test_envelope_widening_protocol.py` | Envelope widening        | specs/08 §1, §7, specs/10 §7 | T-00-07       |
| `test_debate_concession_rules.py`    | Debate concession        | specs/07 §3, specs/10 §4     | T-00-10       |
| `test_quote_moved_protocol.py`       | Quote-moved              | specs/10 §6.4, specs/14 §8.2 | T-00-18       |
| `test_top_of_fold_card.py`           | Top-of-fold card         | specs/07 §2, specs/09 §4     | T-00-08       |
| `test_latent_learnability.py`        | Latent learnability      | specs/04 §2.2                | T-00-02       |

---

## Calibration Probe

**File:** `test_calibration_protocol.py`
**Domain:** Holm-Bonferroni multiple-comparison correction

Tests three layers:

1. **Holm-Bonferroni correction** — adjusted alphas strictly increasing; all-pass only when all p-values clear corrected thresholds
2. **Adaptive k-NN neighborhood** — k bounded [5, min(n/4, 50)]; monotonic in sample count, inverse-monotonic in dimensionality
3. **DSR + PBO** — Deflated Sharpe Ratio and Probability of Backtest Overfitting for promotion gate

**Integration:** 20 random-noise heads → zero certified champions (family-wise Type I error controlled).

**Failure signals:**

- Alpha adjustment not ordered → family-wise error rate not controlled
- k fixed (no adaptive) → meaningless calibration in high dimensions
- Random-noise head certified → PBO/DSR gate missing

---

## Router Overfitting Probe

**File:** `test_router_overfitting.py`
**Domain:** Meta-router overfitting defenses

Four structural defenses tested:

1. **Temporal leakage detection** — any `outcome_ts < pit_ts` → `training_leak_detected = True`, `passes = False`
2. **Parameter-count cap** — router params ≤ 10% of training observations; 50 params / 100 obs → fails
3. **Minimum 504 observations** — below threshold → `passes_min_observations = False`
4. **Naive baseline required** — "always pick highest recent calibration" is a required challenger; router must outperform it

**Failure signals:**

- Temporal leakage in training data → block
- Parameter bloat → `passes_param_ratio = False`
- Insufficient history → `passes_min_observations = False`
- No naive challenger → `has_naive_baseline = False`
- Router beaten by naive on noise → `naive_outperforms = True`

---

## Shadow Lane Isolation Probe

**File:** `test_shadow_lane_isolation.py`
**Domain:** Structural isolation of shadow challenger from production

Three isolation boundaries enforced:

1. **Namespace isolation** — shadow features must use `features_shadow_v{N}`, not `features_v{N}` (champion namespace)
2. **No IBKR adapter calls** — shadow flow cannot contain `ibkr_adapter.submit_order`, `order_manager.submit`, `positions.write`, `orders.write`
3. **Schema contract** — `ShadowDecisionRecord.hypothetical_pnl` must be populated (None = live execution contamination)

**Integration:** full synthetic shadow flow (8 steps: router through `shadow_decisions.write`) contains zero IBKR/order-manager/positions/orders calls.

**Violation types:**

- `ShadowPollutedChampionFeatures` — shadow uses champion namespace
- `ShadowCalledIBKRAdapter` — shadow flow calls IBKR
- `ShadowRecordHypotheticalPnlNone` — schema violation

---

## Track Record / Promotion Gate Probe

**File:** `test_track_record_protocol.py`
**Domain:** L3/L4 autonomy promotion gates

Four independent gates — ALL must pass:

| Gate                  | Threshold                                     | Signal                            |
| --------------------- | --------------------------------------------- | --------------------------------- |
| 12-month window       | ≥ 12 monthly records                          | `window_sufficient`               |
| Bootstrap lower bound | CI lower bound **strictly exceeds** 0.3 floor | `bootstrap_pass` — at-floor fails |
| Pool consistency      | ≥ 8/12 trailing months positive               | `consistency_pass`                |
| Activity              | ≥ 6 rebalance events                          | `activity_pass`                   |

**Lucky streak test:** 3 months of perfect data → `window_sufficient = False` regardless of metric quality.

**Boundary:** CI lower bound = 0.300 → fails (must be > 0.300); CI lower bound = 0.301 → passes.

---

## Kill Switch Process Lock Probe

**File:** `test_kill_switch_process_lock.py`
**Domain:** Kill-switch clear flow cannot be bypassed

State machine enforces mandatory step sequence:

```
ACTIVE → begin_clear_flow → BRIEF_READ → acknowledge_brief → BRIEF_ACKNOWLEDGED
→ complete_clear → CLEARED
```

Post-clear rules:

- **60-second dwell** enforced before first post-clear decision
- **Autonomy reverts to L1** on clear regardless of prior level
- **No 15-minute timer** — `hasattr(protocol, "_clear_cooldown_seconds") = False` is an assertion

**Failure signals:**

- Skipping steps → raises `ValueError`
- Empty brief acknowledged → raises `ValueError("brief has no content")`
- Dwelling < 60s before first decision → `post_clear_dwell_incomplete` in failures
- 15-minute timer present → attribute exists (banned pattern)

---

## Envelope Widening Protocol Probe

**File:** `test_envelope_widening_protocol.py`
**Domain:** Envelope widening blocked under drawdown, cooldown, without Debate

Four independent gates:

| Gate               | Rule                                                          | Signal                           |
| ------------------ | ------------------------------------------------------------- | -------------------------------- |
| Drawdown lockout   | Current drawdown **strictly below** 70% of ceiling            | `FAIL_DRAWDOWN_LOCKOUT` if ≥ 70% |
| 24-hour cooldown   | Widening blocked within 24h of prior widening                 | `FAIL_COOLDOWN`                  |
| 72h drawdown event | Widening blocked within 72h of drawdown event ≥ 50% threshold | `FAIL_DRAWDOWN_EVENT_WINDOW`     |
| Debate invocation  | Debate agent must be invoked before widening is presentable   | `FAIL_NO_DEBATE_INVOKED`         |

**Boundary:** drawdown = 0.699 → passes; drawdown = 0.70 → fails (must be strictly below).

---

## Debate Concession Rules Probe

**File:** `test_debate_concession_rules.py`
**Domain:** Debate agent concession backed by evidence, not rhetoric

Four structural constraints:

1. **Evidence gate** — `update_decision` requires new evidence tuple (from tool call returning new data) within N turns; rhetoric alone cannot mutate
2. **Evidence recency** — evidence must be within `concession_lookback_turns` (default 3); stale evidence does not authorize mutation
3. **Disagreement floor** — agent must take REDTEAM position in ≥ 30% of turns within thread window
4. **Concession counter** — every concession without evidence is logged and counted against the agent's audit signal

**Failure signals:**

- Mutation without evidence → `can_mutate_decision = False`
- Mutation with stale evidence → `can_mutate_decision = False`
- Disagreement < 30% → `disagreement_floor_met = False`
- Unknown thread → `thread_not_found` in failures

---

## Quote-Moved-Since-Brief Probe

**File:** `test_quote_moved_protocol.py`
**Domain:** Market moves between brief composition and biometric approval

Regime-adaptive thresholds — move must be **strictly below** threshold to auto-execute:

| Regime   | Threshold | Strictness     |
| -------- | --------- | -------------- |
| CALM     | 0.5%      | strictly below |
| ELEVATED | 0.3%      | strictly below |
| URGENT   | 0.2%      | strictly below |

At or above threshold → `QuoteMovedError` raised, auto-execute blocked, modal surfaced for user re-confirm.

**Boundary:** exactly 0.2% in URGENT → `threshold_exceeded = False` (must be strictly below).

**T-00-18 acceptance:** 0.4% move in ELEVATED → `threshold_exceeded = True`, `auto_execute_permitted = False`.

---

## Top-of-Fold Card Probe

**File:** `test_top_of_fold_card.py`
**Domain:** Usable decision card within 10-second attention window

Required schema:

- **Action** — one line, non-empty
- **Counter-evidence** — ≤ 100 characters, exactly one line
- **What would change my mind** — ≤ 100 characters, exactly one line
- **Buttons** — APPROVE (biometric-gated), DEBATE, DECLINE (all three required)
- **Biometric required** — `biometric_required=True` mandatory
- **3-second dwell** on high-weight decisions

**Failure signals:**

- Empty action → `action_missing_or_empty`
- Counter-evidence > 100 chars → `counter_evidence_not_one_line`
- Missing any button → specific missing button identified
- `biometric_required=False` → `biometric_not_required_on_approve`
- High-weight without 3s dwell → `high_weight_missing_dwell`

---

## Latent Learnability Probe

**File:** `test_latent_learnability.py`
**Domain:** z_t is learnable from available data before promotion

Mutual information probe:

1. Plant synthetic latent structure correlated with returns
2. Estimate MI between z and realized forward returns
3. Compare to null distribution (scrambled-target permutation)
4. Family passes only if MI **significantly exceeds** null

**Integration:**

- 20 random-noise heads → zero pass (null correctly absorbs Type I error)
- Planted structure (sin/cos manifold) → `passes = True`
- Insufficient observations (< 252) → `passes = False`, `math.isnan(mu_actual)`

---

## Structural vs. Behavioral Enforcement

| Structural (bypass impossible)  | Behavioral (audit signal)                         |
| ------------------------------- | ------------------------------------------------- |
| Kill switch step sequence       | Concession without evidence (logged but allowed)  |
| Shadow lane IBKR call detection | Disagreement floor drift (triggers recalibration) |
| Envelope widening gates (all 4) | Concession-without-evidence counter               |
| Quote-moved threshold           | Latent learnability probe record in registry      |
| Top-of-fold card schema         |                                                   |

---

## Probe Design Principles

- **Synthetic injection** — inject the failure mode directly into test data/flow
- **Single top-level assertion** — `passes`, `promotion_proposal_fires`, `is_isolation_verified`
- **Detailed subordinate assertions** — each gate has its own boolean so failure is immediately localized
- **Boundary testing** — thresholds tested at exactly-boundary and one-unit-past to catch off-by-one
