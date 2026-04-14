# M12 — Pre-Trade Compliance Agent (PACT Rules Engine)

**Spec anchors:** 11.
**Framework:** PACT (governance, D/T/R, default-deny), Kailash Core SDK (workflow).
**Depends on:** M01, M11.

## T-12-01 — Rules engine core (data-driven)

**Objective:** rule registry with typed predicates, severities (pass/warn/escalate/block), actions; rule evaluation pipeline; default-deny on exception.
**Invariants:** rules are data not code; add rule without a release; audit every evaluation.
**Acceptance:** Tier 2 adds rule via registry and rule evaluates without code change.

## T-12-02 — Blocking rules (v1 set)

**Objective:** 16 blocking rules from `specs/11- §3.1`: `env.drawdown_ceiling`, `env.vol_target`, `env.concentration.position`, `env.concentration.sector`, `env.universe`, `env.cost_budget`, `data.stale_price`, `data.stale_fundamental`, `state.kill_switch`, `state.paper_trading`, `state.ood`, `autonomy.level_breach`, `model.confidence_floor`, `model.pool_disagreement`, `exec.freshness_at_execution`, `api.ibkr_health`.
**Acceptance:** every rule has a Tier 2 test that fires on a synthetic breach.

## T-12-03 — Escalation rules

**Objective:** 7 escalation rules from `specs/11- §3.2`: `escalate.urgent_band`, `escalate.crisis_band`, `escalate.envelope_change`, `escalate.model_promotion`, `escalate.autonomy_upgrade`, `escalate.debate_open`, `escalate.first_seven_days`.
**Acceptance:** Tier 2 test per rule.

## T-12-04 — Warning rules

**Objective:** 5 warning rules from `specs/11- §3.3`.
**Acceptance:** warnings accumulate in brief composer input.

## T-12-05 — Envelope-widening rules (T-00-07)

**Objective:** `env.widening.cooldown`, `env.widening.drawdown_lockout`, `env.widening.debate_required`.
**Acceptance:** T-00-07 Tier 2 test passes.

## T-12-06 — Kill-switch process-lock enforcement (T-00-09)

**Objective:** kill-switch clear workflow (state-of-the-world brief, 60-second dwell, L1 reversion, first post-clear decision user-approved).
**Acceptance:** T-00-09 Tier 2 test passes.

## T-12-07 — Re-entry of Debate `update_decision` into compliance

**Objective:** every mutation of a pending decision via the Debate `update_decision` tool re-enters the compliance pipeline from the top.
**Invariants:** no bypass; router / scheduler / Debate all enter through the same gate.
**Acceptance:** Tier 2 confirms re-entry.

## T-12-08 — Audit log

**Objective:** append-only `audit_log` with immutable records for every rule evaluation and decision.
**Acceptance:** verify immutability; query by (rule_id, decision_id).

## T-12-09 — Compliance rule viewer (read-only UI)

**Objective:** surface the rule set in Settings as read-only for v1 per `specs/09- §9.4`.
**Depends on:** M17, M18.

**Gate out:** all rules in registry, each with a Tier 2 test; audit log immutable; re-entry structural.
