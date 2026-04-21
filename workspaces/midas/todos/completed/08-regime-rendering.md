# M08 — Continuous Regime Rendering

**Spec anchors:** 06.
**Depends on:** M04, M05.

## T-08-01 — Attention-load axis `a_t` computer

**Objective:** service that computes `a_t ∈ [0,1]` from (risk head posterior, tail head posterior, pool disagreement, `z_t` posterior width, drawdown velocity, distance-from-training).
**Invariants:** `a_t` is itself a tracked pool member with calibration; no hardcoded VIX/spread thresholds; computed live per `z_t` update.
**Acceptance:** Tier 2 replay against historical crises asserts `a_t` rose at least N days before the major drawdown.

## T-08-02 — Band projection (Calm/Elevated/Urgent/Crisis)

**Objective:** projection of `a_t` into the four UI bands with soft-threshold interpolation.
**Invariants:** bands are a rendering decision; the model layer never consumes bands, only `a_t` or `z_t`.
**Acceptance:** interpolation works across band boundaries without flip artifacts.

## T-08-03 — Transition-pressure gauge

**Objective:** continuous-time change-point posterior (from T-04-07) rendered as a gauge the user can watch climb.
**Acceptance:** gauge updates in realtime; historical playback matches expected pressure during known transitions.

## T-08-04 — OOD escalation override

**Objective:** when OOD detector trips (T-04-06), `a_t` → Crisis band regardless of other inputs.
**Acceptance:** Tier 2 synthetic OOD input forces Crisis.

## T-08-05 — Historical analogue retriever

**Objective:** tool that returns top-K historical `z_t` analogues for a given current state; consumed by the Debate agent.
**Acceptance:** replay test — known analogues retrievable with expected similarity.

## T-08-06 — Factor overlay projector

**Objective:** post-hoc projection of `z_t` onto the econometric factor basis for user-facing explanation (tool for the frontier LLM).
**Acceptance:** projection produces interpretable narrative on synthetic data.

**Gate out:** `a_t` runs continuously, band transitions are smooth, OOD escalation is structural, analogue and factor projections queryable.
