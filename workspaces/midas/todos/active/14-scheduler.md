# M14 — Scheduler & Background Jobs

**Spec anchors:** 11 §7.
**Framework:** Kailash Core SDK workflows + scheduler.

## T-14-01 — Scheduler service backbone

**Objective:** APScheduler-or-equivalent service wrapped as a Kailash workflow; cron + event-driven triggers; heartbeat per job.
**Acceptance:** Tier 2 scheduled job fires, heartbeat visible.

## T-14-02 — 13 scheduled jobs (per `specs/11- §7.1`)

**Objective:** individual workflows for: EOD ingestion, fundamentals refresh, news pipeline, macro ingestion, representation-learner inference, state-inference update, router calibration update, rebalance trigger check, counterfactual computation, PBT (challenger lane), health check, NAV/valuation, paper-trading report generator.
**Acceptance:** each has its own Tier 2 test.

## T-14-03 — Job failure recovery

**Objective:** exponential backoff; persistent failure escalates to user via notification; compliance-gated scheduled trades re-check compliance.
**Acceptance:** injected failure triggers recovery + escalation path.

## T-14-04 — Graceful degradation per source

**Objective:** failure paths per `specs/11- §7.3` (EODHD fallback, IBKR outage, Perplexity outage, frontier LLM outage, DB outage, scheduler outage).
**Acceptance:** Tier 2 per failure path.

## T-14-05 — Orphan-detection scheduled audit (links to T-07-06)

**Objective:** monthly scheduled orphan audit over the full call graph (including shadow lanes) per `rules/orphan-detection.md`.
**Acceptance:** audit runs, reports findings to operator dashboard.

**Gate out:** all 13 jobs heartbeating; degradation paths Tier-2-tested; orphan audit scheduled and running.
