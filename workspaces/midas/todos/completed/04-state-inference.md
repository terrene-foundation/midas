# M04 — State Inference Pool

**Spec anchors:** 04 §5.
**Depends on:** M03.

## T-04-01 — Posterior-maintenance service

**Objective:** continuous service that consumes representation-learner outputs and maintains `p(z_t | x_{1:t})` per pool member.
**Invariants:** PIT; posteriors written with timestamps; every update audited.
**Acceptance:** service warm-starts, writes posteriors, replays match on deterministic test data.

## T-04-02 — Deep Bayesian filter champion

**Objective:** one deep-filter inference method as initial champion.
**Acceptance:** posterior updates match expected behavior on synthetic state.

## T-04-03 — Normalizing-flow challenger

**Objective:** NF-based posterior for non-Gaussian structure.
**Acceptance:** challenger registry entry + shadow runs.

## T-04-04 — Neural Kalman challenger

**Objective:** NK variant with explicit linear-Gaussian dynamics + nonlinear emissions.
**Acceptance:** registry + shadow.

## T-04-05 — Energy-based posterior challenger

**Objective:** score-matching implicit posterior.
**Acceptance:** registry + shadow.

## T-04-06 — Out-of-distribution detector

**Objective:** OOD score derived from distance-to-nearest-training-state and posterior width; feeds `a_t` axis and the `state.ood` compliance rule (M12).
**Invariants:** OOD detection is always on; never bypassable.
**Acceptance:** Tier 2 synthetic OOD input triggers detection; in-distribution does not.

## T-04-07 — Change-point posterior (continuous-time)

**Objective:** BOCPD-style continuous change-point head feeding the transition-pressure gauge in UI.
**Acceptance:** Tier 1 synthetic regime flip is detected with calibrated probability.

## T-04-08 — Posterior-combination strategy

**Objective:** strategy for combining multiple pool-member posteriors into the `z_t` delivered to downstream heads (mixture, weighted average, router-selected).
**Depends on:** M06.

**Gate out:** posterior-maintenance service runs continuously, multiple pool members in registry, OOD detector tested.
