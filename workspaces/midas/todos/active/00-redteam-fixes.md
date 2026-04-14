# M00 — Redteam Round 1 Critical Fixes

**Blocks:** all other milestones.
**Spec anchors:** 00, 04, 05, 07, 08, 10, 12.
**Why:** Round 1 of redteam (quant-researcher + portfolio-manager) surfaced 9 CRITICAL findings that would render the implementation either overfit or unsafe in live operation. These fixes are written into the specs and into pre-commit gates BEFORE any model or UX code is written.

---

## T-00-01 — Point-in-Time Data Protocol (Quant C1)

**Objective:** every fabric row carrying a time-varying attribute must be addressable by a point-in-time `as_of_date` that can be threaded through every feature computation and backtest.
**Implements:** specs/03-universe-and-data.md §4.3, §2.2.
**Scope (in):** data-model tuple `(period_end, filed_at, restated_at, source_vintage)` on fundamentals / macro / universe-membership / index-constituency; `as_of_date` parameter on every fabric query; ALFRED-style vintage tracking for revised series (FRED CPI, employment, GDP).
**Scope (out):** actual EODHD / FRED ingestion (M01); point-in-time backtest engine (M16).
**Invariants:** (a) any feature at time t reads only rows whose `filed_at ≤ t`; (b) restated data uses the vintage active at t, not the latest restatement; (c) S&P 1500 membership is queried as-of t.
**Acceptance:** Tier 2 test `test_pit_protocol_no_future_leak.py` runs a synthetic restatement + index-add event and asserts every feature computation at the pre-event timestamp sees only pre-event data. Second test intentionally introduces a leak and asserts it is caught.
**Depends on:** none (spec-level).
**Update:** write the protocol as a new section in `specs/03-universe-and-data.md` §4.3 explicitly (replaces the single sentence).

---

## T-00-02 — Latent-State Learnability Probe (Quant C2)

**Objective:** before any representation-learner training runs, commit to a concrete pre-training corpus and run a mutual-information probe that demonstrates `z_t` is learnable from the available data.
**Implements:** specs/04-latent-first-architecture.md §2.2, §4; specs/03-universe-and-data.md §5.1.
**Scope (in):** (a) name the pre-training corpus concretely — candidate: existing TS foundation models (Chronos, TimesFM, Moirai) fine-tuned on Midas fabric, OR public cross-asset corpus (CRSP-equivalent free sources, FRED, Yahoo extended history); (b) define sample-complexity gates — minimum observation count before a latent-learner configuration can exit shadow; (c) build `probe_latent_learnability.py` computing mutual information between `z_t` and realized forward returns vs a scrambled-target null; a family passes only if MI exceeds the null by a statistically significant margin; (d) update spec with the named corpus and the gate.
**Scope (out):** representation-learner training itself (M03).
**Invariants:** (a) no representation learner family is promoted to the model pool without passing the probe; (b) the probe itself is versioned and its output is stored in the model registry.
**Acceptance:** Tier 1 test invokes the probe on synthetic data where latent structure is planted and confirms detection; Tier 2 test confirms probe rejects noise.
**Depends on:** T-00-01.

---

## T-00-03 — Router Overfitting Protocol (Quant C3)

**Objective:** the meta-router is a model and must be trained with overfitting defenses as rigorous as any other head.
**Implements:** specs/05-model-pool-and-meta-router.md §4.2, §4.5.
**Scope (in):** (a) PurgedKFold cross-validation for router training with purge window tied to longest forecast horizon; (b) explicit parameter-count-to-observation ratio cap; (c) minimum observation count before a router is allowed to drive live decisions; (d) naive non-router baseline ("always pick head with highest recent calibration") as a required challenger in the router's own champion/challenger lane; (e) `test_router_does_not_leak_outcome_into_training.py` — mechanical leakage test.
**Scope (out):** router implementation (M06).
**Invariants:** (a) router training data never includes `(t, outcome)` tuples where outcome post-dates `t`; (b) router parameter count stays under the observation-ratio cap; (c) router's own calibration curve is tracked and demotion is automatic if it underperforms the naive baseline.
**Acceptance:** Tier 2 test runs a synthetic leak scenario and confirms the protocol catches it.
**Depends on:** T-00-01.

---

## T-00-04 — Calibration Methodology With Multiple-Comparison Correction (Quant C4)

**Objective:** calibration is a statistical procedure, not a checklist. Specify the neighborhood estimator, the minimum-sample gate, and the multiple-comparison correction.
**Implements:** specs/05-model-pool-and-meta-router.md §3.2; specs/12-performance-and-track-record.md §4.
**Scope (in):** (a) define `z_t`-neighborhood estimator concretely — k-NN with k tied to dimensionality and sample size, or kernel-weighted with bandwidth from cross-validation; (b) minimum observation count per bin before a calibration claim is publishable; (c) Holm-Bonferroni correction across the promotion-contract criteria in `05-` §5.4 (6 criteria → family-wise α control); (d) Deflated Sharpe Ratio and PBO (Probability of Backtest Overfitting) for the promotion gate; (e) spec update explicit.
**Scope (out):** calibration infrastructure build (M06-M07).
**Invariants:** (a) no promotion decision fires without Holm-Bonferroni-corrected p-values above threshold; (b) no calibration curve is displayed without its sample-size annotation; (c) every promotion event writes the full corrected test output to the audit log.
**Acceptance:** Tier 2 test spins up a pool of 20 random-noise "heads" and asserts the promotion mechanism certifies ZERO of them as champion (family-wise Type I control verified).
**Depends on:** T-00-01.

---

## T-00-05 — Shadow-Lane Isolation Contract (Quant C5)

**Objective:** the shadow lane must be structurally isolated from the champion, not merely conventionally separated by table name.
**Implements:** specs/05-model-pool-and-meta-router.md §5.2, §5.3.
**Scope (in):** (a) dedicated `features_shadow_v{N}` namespace; (b) shadow lane has its own inference pool (no shared `z_t` with champion); (c) shadow decisions cannot write to `positions`, `orders`, or the execution agent — enforced at the PACT compliance layer, not in code comments; (d) monthly `/redteam` audit that walks the shadow-lane call graph and asserts no production call sites; (e) Tier 2 test `test_shadow_decision_does_not_reach_order_manager.py` — reaches into a shadow-decision flow and asserts no IBKR adapter call fires.
**Scope (out):** shadow infrastructure build (M07).
**Invariants:** (a) shadow lane never writes positions; (b) shadow lane never calls the IBKR adapter; (c) shadow lane features are namespaced and cannot pollute the champion's features.
**Acceptance:** the Tier 2 test passes; orphan-detection audit (`rules/orphan-detection.md`) runs and finds shadow components have no production call sites.
**Depends on:** T-00-01.

---

## T-00-06 — Track-Record Window Extension (PM C1)

**Objective:** extend Brinson / attribution windows for autonomy-promotion contracts beyond 3 months. 3-month Brinson is ~12 data points — cannot distinguish 30-bps-per-quarter skill from zero skill.
**Implements:** specs/08-autonomy-and-trust.md §7; specs/12-performance-and-track-record.md §3.4, §6.1.
**Scope (in):** (a) promote 12-month rolling as the primary window for L3 / L4 contracts; 3-month is a secondary context signal only; (b) require bootstrap-derived confidence interval lower bound to exceed floor, not point estimate; (c) pool-consistency gate — e.g. positive in 8 of 12 trailing months, not just aggregate; (d) minimum-activity gate — number of rebalance events must exceed floor before promotion is proposable; (e) spec updates to `08-` §7 and `12-` §3.4, §6.1.
**Scope (out):** attribution engine build (M16).
**Invariants:** (a) no promotion proposal fires without the 12-month window being populated and the bootstrap lower bound exceeding floor; (b) the short-window metrics are visible in UI but never trigger autonomy transitions.
**Acceptance:** Tier 2 test injects a short-run lucky streak and asserts no promotion proposal fires.
**Depends on:** T-00-04.

---

## T-00-07 — Envelope-Widening Cooldown And Drawdown Lockout (PM C2)

**Objective:** the user can widen their envelope only under structured conditions. Biometric is not a defense against panic.
**Implements:** specs/08-autonomy-and-trust.md §1; specs/10-moments-of-truth.md §7; specs/11-compliance-and-risk.md.
**Scope (in):** (a) drawdown-conditional lockout — widening is blocked while portfolio drawdown exceeds a configurable fraction of current envelope ceiling (default 70%); (b) 24-hour cooldown between any two envelope widenings; (c) 72-hour minimum since the last drawdown event above a threshold; (d) Debate agent must be invoked before the widening action is even presentable, and must attempt to push back with evidence; (e) rule added to PACT rules engine: `env.widening.cooldown`, `env.widening.drawdown_lockout`.
**Scope (out):** the compliance rules engine build itself (M12); Debate push-back implementation (M09).
**Invariants:** (a) no envelope widening executes under drawdown lockout; (b) every widening writes an audit record including the Debate transcript that preceded it.
**Acceptance:** Tier 2 test simulates a user widening during drawdown and asserts the widening is blocked; second test confirms widening succeeds after cooldown and no recent drawdown.
**Depends on:** M12 (for enforcement), but the spec update lands in M00.

---

## T-00-08 — Top-Of-Fold Decide-In-10-Seconds Card (PM C3)

**Objective:** solve the structural tension between 7-section briefs and a 30-second attention budget. Universal top-of-fold card on every approval screen that renders an actionable decision in 10 seconds.
**Implements:** specs/07-evidence-first-decision.md §2; specs/09-surfaces-and-attention.md §4.
**Scope (in):** (a) define the top-of-fold card schema — action (one line), single strongest counter-evidence (one line), "what would change my mind" one-liner, three buttons: Approve (biometric-gated) / Debate / Decline; (b) buttons spatially separated per `10-` §2; (c) forced 3-second dwell before biometric unlock on high-weight briefs; (d) measurable usability gate — test rig simulates a user reading only the top-of-fold and asserts correct decline on backtested bad recommendations exceeds a threshold; (e) spec updates to `07-` §2 and `09-` §4.
**Scope (out):** brief generator build (M10); UI implementation (M17, M18).
**Invariants:** (a) every approval screen ships with the card; (b) full brief is tap-to-expand below the card, never default-open on high-frequency low-weight decisions; (c) the card's counter-evidence is always sourced from a real pool-disagreement or calibration signal, not a synthetic warning.
**Acceptance:** usability gate passes on a synthetic decision set where 20% are backtested bad recommendations.
**Depends on:** none at spec level; enforcement depends on M10, M17, M18.

---

## T-00-09 — Kill-Switch Process-Lock (PM C4)

**Objective:** replace the 15-minute time cool-down on kill-switch clear with a structured re-engagement process. Time locks cannot distinguish "user is right" from "user is panicking"; process locks can.
**Implements:** specs/08-autonomy-and-trust.md §5.4; specs/10-moments-of-truth.md §5.
**Scope (in):** (a) kill-switch clear always reverts autonomy to L1 regardless of prior level; (b) mandatory state-of-the-world brief before clear — `z_t` posterior, drawdown state, pool disagreement, any compliance events — user must read and acknowledge; (c) 60-second dwell on the first post-clear decision (cannot approve faster than this); (d) first post-clear decision is user-approved regardless of autonomy level; (e) remove the 15-minute timer; (f) spec updates.
**Scope (out):** UI build (M17, M18); compliance rule wiring (M12).
**Invariants:** (a) kill-switch clear cannot bypass the state-of-the-world brief; (b) first decision post-clear requires L1 approval; (c) the 60-second dwell is enforced at the compliance layer and the UI both.
**Acceptance:** Tier 2 test asserts the clear flow cannot be bypassed.
**Depends on:** M12 (enforcement).

---

## T-00-10 — Debate Concession-With-Evidence Rule (PM H3)

**Objective:** prevent long-context sycophancy drift in the Debate agent. Concession must be backed by evidence, not rhetoric.
**Implements:** specs/07-evidence-first-decision.md §3; specs/10-moments-of-truth.md §4.
**Scope (in):** (a) concession protocol — the Debate agent can only mutate a pending decision if a new evidence tuple has been produced (a tool call returning new data, not just user rhetoric); (b) concession audit counter — every concession without evidence is logged and counts against the agent's audit signal; (c) steelman/red-team sub-role split — two internal roles alternate in long threads to avoid single-agent drift; (d) disagreement-floor metric — over a thread window, the agent is expected to disagree at a minimum rate; sustained agreement drift flags the thread for re-calibration; (e) spec updates.
**Scope (out):** LLM agent implementation (M09).
**Invariants:** (a) `update_decision` tool invocation requires a preceding new-evidence tool call within N turns; (b) concession-without-evidence counter is public and visible in the decision audit; (c) the two sub-roles share the evidence store but not the system prompt.
**Acceptance:** Tier 2 test runs a simulated sycophantic user against the agent and asserts concession rate stays within bounds.
**Depends on:** M09.

---

## T-00-11 — Trader Redteam Completion ✅ COMPLETE

**Status:** Done. Findings in `workspaces/midas/04-validate/round-1-trader.md`.
**Owner direction:** Q2 — paper→live (M19) runs in parallel with trader-redteam findings, NOT gated by them. Track-record contract (FP-14) and first-seven-days L1 enforcement provide the live bridge.
**Result:** 4 CRITICAL + 2 HIGH findings → T-00-12 through T-00-16 below.

---

## T-00-12 — Transaction Cost Model Spec ✅ SPEC-LEVEL DONE

**Objective:** formal cost decomposition (spread, impact, commission, tax, slippage, gap) with functional forms and calibration loop.
**Implements:** `specs/13-execution-cost-and-microstructure.md` (written this session).
**Implementation todos live in:** M05 (T-05-14 execution head reads this spec), M12 (compliance rules `env.cost_budget`, `exec.participation_cap`, `data.stale_cost_inputs`, `warn.event_adjacent`, `warn.wide_spread`), M15 (execution agent implements selection + child-order scheduler per spec).
**Acceptance:** the three compliance rules + execution-algorithm selection are exercised end-to-end in Tier 2 against IBKR paper.

---

## T-00-13 — IBKR Integration Spec ✅ SPEC-LEVEL DONE

**Objective:** IBKR Web API v1.0 operational contract — rate limits, order states, rejection taxonomy, partial-fill-during-approval, halts, auctions, FX sweep.
**Implements:** `specs/14-ibkr-integration.md` (written this session).
**Implementation todos live in:** M15 (order state machine, rate-limit back-pressure, rejection handling, TWS fallback), M18 (biometric quote-moved re-confirm modal), M12 (rules `api.ibkr_rate_limit`, `api.ibkr_session_invalid`, `exec.quote_moved_since_brief`, `warn.halted`, `warn.auction_window`).
**Acceptance:** IBKR ops rules exercised in Tier 2; partial-fill-during-approval test passes against a synthesised fabric scenario.

---

## T-00-14 — Fabric Schema Additions ✅ SPEC-LEVEL DONE

**Objective:** add `quotes`, `fills`, `fills_synthetic`, `fee_schedule`, `cost_attribution`, `sweep_history` to the fabric layout.
**Implements:** `specs/03-universe-and-data.md §3.3` (updated this session).
**Implementation todos:** add a new task in M01 — T-01-16 — create DataFlow models for the six new tables; adapters update accordingly (quotes ingested from IBKR / EODHD; fills from IBKR; fee_schedule versioned ingestion).
**Acceptance:** Tier 2 write + read-back for all six new tables.

---

## T-00-15 — Paper-Fill Realism In Paper→Live Gate ✅ SPEC-LEVEL DONE

**Objective:** honest treatment of IBKR paper-trading fill optimism.
**Implements:** `specs/08-autonomy-and-trust.md §6.2` adds both-costs reporting (raw-paper + PLAF-adjusted); §6.2.1 adds the paper-fill disclaimer (updated this session); PLAF mechanics in `specs/13- §6`.
**Implementation todos live in:** M19 (paper-trading report generator surfaces both cost views; PLAF recalibration weekly for first N live days), M16 (PLAF integrated into attribution).
**Acceptance:** paper-trading report renders both raw and adjusted costs; PLAF update job heartbeats.

---

## T-00-16 — Kill-Switch Process-Lock ✅ SPEC-LEVEL DONE

**Objective:** replace the 15-minute time-lock with a process-lock on kill-switch clear.
**Implements:** `specs/08-autonomy-and-trust.md §5.4` (updated this session).
**Implementation todos live in:** M12 (compliance enforcement), M17/M18 (UI: state-of-the-world brief + 60-second dwell + L1 reversion).
**Acceptance:** Tier 2 confirms clear flow cannot be bypassed; T-00-09 superseded by this (same fix, now spec-level).

---

## T-00-17 — Debate Concession-With-Evidence Enforcement (cross-ref)

**Objective:** enforce T-00-10 at implementation. Spec is already written.
**Implements:** `specs/07- §3`, `specs/10- §4`.
**Implementation todos live in:** M09 (Debate agent implementation with steelman/red-team sub-roles + concession counter + evidence-tuple gate on `update_decision`).
**Acceptance:** T-00-10 Tier 2 sycophancy simulation passes.

---

## T-00-18 — Quote-Moved-Since-Brief Protocol (Trader H-4)

**Objective:** detect and act on market moves between brief composition and biometric approval.
**Implements:** `specs/10-moments-of-truth.md §6.4` (added this session); `specs/14- §8.2`.
**Implementation todos live in:** M12 (rule `exec.quote_moved_since_brief`), M17/M18 (UI modal on fresh-quote mismatch), M15 (fresh-quote pull at execution time wired).
**Acceptance:** Tier 2 synthesises a 0.4% mid move between brief and approval in Elevated band; modal surfaces; user confirmation required before submit.

---

## Gate Out Of M00

M00 is complete when:

1. All 18 CRITICAL-level spec updates are written into `specs/` — ✅ done this session.
2. T-00-11 complete (trader redteam ran) — ✅ done this session; findings are T-00-12 through T-00-18.
3. The pre-commit hook runs the M00 test rig (leakage test, probe, shadow-isolation test, multiple-comparison test, cost-model test, IBKR-ops test, quote-moved test) on a trivial example and passes. **Implementation of the test rig lives in M20.**
4. Implementation todos in M01/M05/M12/M15/M16/M17/M18/M19 that reference T-00-12 through T-00-18 are executed under /implement — this is autonomous work after approval.

**Note (owner directive, Q2):** trader-redteam findings are fixed in parallel with M19 paper→live; they do NOT block paper→live. The first-seven-days L1 enforcement (§6.4 of spec 08) + PLAF recalibration (`13- §6`) are the live bridge that compensates for any residual gap.
