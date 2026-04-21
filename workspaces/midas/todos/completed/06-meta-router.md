# M06 — Meta-Router & Three-Loop Adaptation

**Spec anchors:** 05 §3-5.
**Depends on:** M00 (T-00-03, T-00-04), M05.

## T-06-01 — Inner loop: continuous calibration service

**Objective:** per-head calibration service writing live posteriors over local reliability; consumes head predictions and realized outcomes.
**Invariants:** PIT; every calibration record carries (head, z_t neighborhood, horizon, prediction, outcome).
**Acceptance:** Tier 2 soak confirms calibration curves converge on synthetic data with known ground truth.

## T-06-02 — Middle loop: contextual router (champion)

**Objective:** mixture-of-experts / contextual-bandit router that selects or blends pool outputs per `z_t` context.
**Invariants:** PurgedKFold training per T-00-03; parameter-count cap; no outcome leakage.
**Acceptance:** T-00-03 leakage test passes; router beats naive baseline on held-out validation.

## T-06-03 — Router challengers (Bayesian model averaging, stacking)

**Objective:** two router challengers for the router's own champion/challenger lane.
**Acceptance:** registry + shadow.

## T-06-04 — Outer loop: population-based training harness

**Objective:** PBT harness that runs multiple configurations in parallel, propagates winners, retires losers.
**Acceptance:** Tier 2 run with synthetic population converges.

## T-06-05 — Promotion contract evaluator

**Objective:** service that, on a schedule, evaluates each challenger against its promotion contract (per `specs/05- §5.4` + T-00-04).
**Invariants:** Holm-Bonferroni corrected p-values; bootstrap CI lower bound; 12-month primary window per T-00-06.
**Acceptance:** Tier 2 with synthetic noise heads confirms zero false promotions.

## T-06-06 — Demotion / degradation contract evaluator

**Objective:** service that continuously evaluates live champions against degradation thresholds; auto-demotes on breach.
**Invariants:** demotion never requires human approval; writes audit record; reverts to prior champion.
**Acceptance:** Tier 2 asserts demotion fires on injected calibration drift.

## T-06-07 — Promotion proposal surface

**Objective:** on promotion-contract pass, write a decision of type `model_promotion` to `decisions` table for the user to review in the Decisions surface.
**Depends on:** M10, M17, M18.

## T-06-08 — Router per-context audit log

**Objective:** every routing decision writes which heads were consulted, their outputs, and the blend weight — feeds Debate agent.
**Acceptance:** routing decisions queryable by decision_id.

**Gate out:** three loops run continuously, promotion/demotion evaluators pass their Tier 2 tests, audit log complete.
