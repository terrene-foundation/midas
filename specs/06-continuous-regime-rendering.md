# Continuous Regime Rendering

**Status:** GOVERNING. Defines how the continuous latent state `z_t` is projected into the user interface without ever emitting a discrete regime label.

Anchored to FP-11 (continuous state, no labels) and the owner's turn-4 correction: _"the way you define regimes is too 20th century. In today's AI age, regimes should be probabilistic functions over a continuous state space."_

---

## 1. Principle

The model does not classify market states into buckets. The **rendering layer** translates the continuous posterior `z_t` into a visualization the user can read. The buckets "Calm / Elevated / Urgent / Crisis" live only in the UI and are defined as **bands on a continuous value**, not as states the model reasons about.

> **One-line statement:** _`z_t` is continuous and probabilistic; regime is a visualization, not a classification._

---

## 2. The Attention-Load Axis

The primary rendering projection is a 1-D **attention-load axis** `a_t ∈ [0, 1]`, computed continuously from the full posterior. It answers the single question that matters to the UI: _"how much of the user's attention should this moment demand?"_

`a_t` is a monotonic function of:

- **Risk-head posterior** — expected loss within a horizon under `z_t`
- **Tail-head posterior** — expected shortfall / worst-case under `z_t`
- **Model disagreement** — dispersion across pool members (the less the pool agrees, the more the user needs to see)
- **Posterior width for `z_t` itself** — wide posterior means the system is not sure what state it is in
- **Drawdown velocity** — rate of change of portfolio value over the last N days
- **Distance from training distribution** — how far `z_t` sits from states the pool has been calibrated on

The function is learned (not hand-coded) by regressing historical user-engagement and decision-window-expiry outcomes against historical `z_t`-derived features. It is itself a model in the pool, subject to the same calibration and promotion discipline as any other head.

---

## 3. Visualization Bands

The UI partitions `a_t` into four bands for visualization:

| Band                         | Meaning to the user                                                                                                            | UI behavior                                                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| **Calm** (low `a_t`)         | "Everything is inside the envelope and the system is confident. Nothing needs you."                                            | Pulse shows portfolio value, no approval section, silent notifications, widget sufficient                      |
| **Elevated** (low-mid `a_t`) | "Some drift, some pending decisions, or the system's confidence has narrowed. A glance is warranted."                          | Pulse promotes approval queue, amber accents, structured push notifications                                    |
| **Urgent** (mid-high `a_t`)  | "A tactical response is needed soon. The system wants you to weigh the evidence and decide."                                   | Approval queue dominates, haptic + sound notifications, hard time-to-decide windows                            |
| **Crisis** (high `a_t`)      | "State is far from where the system is calibrated, tail risk is elevated, or a circuit breaker tripped. The system is paused." | Red emergency banner, trading paused by default, kill-switch state visible, all non-essential surfaces demoted |

**Critical rule:** the bands are soft thresholds. The UI interpolates between bands visually so the user perceives gradual change, not discrete flips. A user looking at Pulse as `a_t` drifts upward sees the layout softly reshape, not jump.

---

## 4. Why Continuous Matters

Discrete regime labels introduce three failure modes that the continuous rendering avoids:

| Discrete failure                                                            | Continuous behavior                                                                                                       |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Hard flip at a threshold creates false alarms near the boundary             | Bands are soft; interpolation removes the flip artifact                                                                   |
| Two states labeled the same but latently different route to the same action | `z_t` is the router's input, so different latent states can route differently even inside the same visualization band     |
| The model is forced to classify even when uncertain                         | The posterior width directly contributes to `a_t`; uncertain states are visualized as uncertain, not forced into a bucket |

---

## 5. Transitions Are Continuous, Not Events

There is no "regime change event." Instead there is a **continuous-time change-point posterior** computed by the state-inference pool that estimates `p(transition occurring in next Δt | z_t, history)`. The user sees this as a subtle "transition pressure" gauge in the Pulse surface — not a flash-alert that a regime has changed.

Transitions feed into:

- Approval threshold modulation (closer to a predicted transition = stricter approval threshold, even in Calm)
- Rebalancing cadence (higher transition pressure = shorter review window)
- Notification tier (high transition pressure crossing a floor triggers a proactive "state is shifting" push)

---

## 6. Historical Analogue Retrieval

When `z_t` is close to a historical state, the system retrieves the analogue from the `latent_state` fabric table and surfaces it as a reference point. The Debate agent uses analogues as evidence:

> _"The current latent state is closest to Q4-2018 (similarity 0.84) and March-2020 (similarity 0.71). In both analogues the system responded by reducing equity exposure over the following two weeks. Here is what the Midas policy head proposes for the current state."_

The analogue retrieval is a tool the Debate agent calls; the user can challenge the analogy (_"2018 wasn't this, the Fed path was different"_), and the agent can accept the challenge and re-rank analogues excluding the contested one.

---

## 7. Rendering Contract

What the rendering layer MUST do:

1. **Never emit a regime label as model output.** Labels live in the visualization, not the reasoning. If a model's output field is a string like `"Elevated"`, the field is wrong.
2. **Always carry `z_t` posterior + `a_t` band together.** The UI never renders a band without the underlying continuous value being available for drill-through.
3. **Interpolate between bands.** No hard flips. CSS/animation transitions on band changes are long (hundreds of milliseconds) so the user perceives drift, not events.
4. **Show transition pressure as a gauge.** Not a badge, not an alert — a gauge the user can watch climb.
5. **Expose the full `z_t` posterior through Debate.** A user who asks _"why are you in Elevated?"_ gets the `z_t` projection onto the factor basis, the risk head's posterior, the pool disagreement measurement, and the distance-from-training value — each as a data point the Debate agent can explain.
6. **Never suppress escalation because the band "shouldn't" change.** Out-of-distribution `z_t` escalates to Crisis regardless of recent trajectory. Safety first.

What the rendering layer MUST NOT do:

1. **No model calls a "regime classifier."** There is no regime classifier. The model pool has no head that emits a discrete state.
2. **No hardcoded VIX thresholds for band assignment.** The mapping is learned and continuous. VIX is an input to `a_t`, not the source of truth.
3. **No caching the band and routing decisions against the cached value.** Router decisions read `z_t` directly.
4. **No downgrading the band silently.** Going from Urgent to Elevated still writes an entry to the audit log and surfaces in Pulse's recent-activity feed.

---

## 8. Examples

### 8.1 Soft Drift

Over a week, `a_t` drifts from 0.15 (Calm) to 0.32 (still Calm, but climbing). The Pulse layout is unchanged in band but the regime gauge visibly moves. No notification fires. On day 5, `a_t` crosses 0.40 (Elevated band). The Pulse smoothly reshapes: approval queue returns to the top, amber accent appears. A single structured push notification fires: _"Midas is in an Elevated state. Two pending tactical decisions."_

### 8.2 OOD Escalation

A sudden unprecedented policy announcement moves `z_t` to a region the pool has not been calibrated on. Distance-from-training shoots up. `a_t` jumps to 0.82 (Urgent) despite VIX and spreads still being modest. The user sees the gauge climb hard, the Pulse reshapes to Urgent, and the brief in the Decisions surface says: _"The state has moved to a region where Midas's confidence is low. Trading in this state is escalated to you until the model recalibrates."_

### 8.3 Bimodal Posterior

The state-inference pool produces a bimodal posterior — one mode consistent with a continuation of the current environment, one with a regime transition. The router blends cautiously; the brief shows both modes with their respective action implications. `a_t` is computed with the full posterior, not the mode, so the user sees elevated attention load even though the point estimate is in Calm.

### 8.4 Model Disagreement Escalation

The allocation pool members disagree strongly about what to do — DRL policies want to reduce equity, classical baselines want to hold. Disagreement contributes to `a_t`; the band shifts toward Elevated even though the risk heads are calm. The brief surfaces the disagreement explicitly: _"My heads disagree about this move. Here are their rationales."_

---

## 9. Implementation Boundaries

| Component                    | Writes band?                                                  | Reads band?                                              |
| ---------------------------- | ------------------------------------------------------------- | -------------------------------------------------------- |
| State inference pool         | Writes `z_t` posterior; never writes a band                   | —                                                        |
| Risk / tail heads            | Write posteriors; never write a band                          | —                                                        |
| `a_t` computer               | Reads `z_t` + head outputs; writes `a_t`                      | Writes band membership to the rendering layer            |
| UI / Pulse                   | —                                                             | Reads `a_t` + band; reshapes layout                      |
| Notification router          | —                                                             | Reads `a_t` + band; tiers notifications                  |
| Meta-router (`05-`)          | Reads `z_t` posterior directly, NOT the band                  | Band is for the UI; routing uses the continuous value    |
| Pre-trade compliance (`11-`) | Reads `a_t` as one input to the approval-threshold modulation | Band is a secondary signal; primary gate is the envelope |

---

## 10. Migration From Phase 01 Discrete Regimes

Phase 01 specified:

- **Market regime** (HMM 3-state): Bull-LowVol / Bull-HighVol / Sideways / Bear-Deflationary / Bear-Inflationary
- **Operational regime** (VIX/spread/curve thresholds): Calm / Elevated / Urgent / Crisis

Under the reframe:

- **Market regime is gone.** Replaced by `z_t` posterior. The "market" is whatever `z_t` currently is; no labels.
- **Operational regime is preserved as a visualization** (Calm / Elevated / Urgent / Crisis) but is now derived from the continuous `a_t` axis rather than hand-coded thresholds.
- The **concept** of two layers (a strategy-facing view and a UX-facing view) is preserved: the strategy layer reads `z_t` directly (continuous, rich); the UX layer reads `a_t` (low-D, human-readable). But nothing in the strategy layer ever consumes a label.

Phase 01 red-team finding FIX-1 (the market-vs-operational regime split) was correct in spotting the conflation. This reframe resolves it by putting the strategy view on `z_t` and the UX view on `a_t`.

---

## 11. Relationship To Other Specs

- `04-latent-first-architecture.md` — defines `z_t` itself
- `05-model-pool-and-meta-router.md` — consumes `z_t` for routing, never a band
- `09-surfaces-and-attention.md` — uses `a_t` to drive UI reshape and notification tiers
- `07-evidence-first-decision.md` — uses `a_t` as one input to approval-threshold modulation
- `11-compliance-and-risk.md` — uses `a_t` alongside envelope enforcement
