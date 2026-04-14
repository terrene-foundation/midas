# M17 — Web App (Nexus + React/Next.js)

**Spec anchors:** 09, 10.
**Framework:** Nexus (multi-channel backbone), React/Next.js, Shadcn, React Query.
**Depends on:** M10, M11, M12, M16.

## T-17-01 — Nexus API backbone

**Objective:** Nexus deployment exposing all decision / debate / portfolio / backtest / signal / settings endpoints.
**Acceptance:** OpenAPI generated; smoke-test per endpoint.

## T-17-02 — Design system foundation

**Objective:** dark-mode primary; color tokens per (superseded Phase 01 `03-uiux`) — updated where needed for attention-load rendering; Geist + Geist Mono; 8px radius cards; no drop shadows.
**Acceptance:** Storybook renders.

## T-17-03 — Build Pulse surface (7.1 Calm + 7.2 Elevated + 7.3 Urgent + 7.4 Crisis)

**Objective:** Pulse with regime-adaptive reshape per `specs/06-` + `09- §6`.
**Invariants:** interpolation between bands is smooth; kill-switch always visible.
**Acceptance:** playback fixture moves `a_t` across bands; reshape visually correct.

## T-17-04 — Wire Pulse to backend

**Objective:** live data bindings — NAV, positions, `a_t`, pending decisions, recent actions; React Query.
**Acceptance:** zero mocked data; all data flows end-to-end from fabric to UI.

## T-17-05 — Build Decisions surface

**Objective:** list of pending decisions; card renders top-of-fold (T-10-01) with approve/debate/decline; batch-review mode for multiple pending.
**Acceptance:** approve path triggers re-auth + backend call.

## T-17-06 — Wire Decisions surface to backend

**Objective:** live decision events + brief rendering + action handling.
**Acceptance:** end-to-end approval flows.

## T-17-07 — Build Debate surface

**Objective:** slide-in panel overlay, thread list, composer with tool-action buttons; inline visualization rendering.
**Acceptance:** T-09-10 thread persistence works through UI.

## T-17-08 — Wire Debate to agents + tools

**Objective:** messages flow through Kaizen runtime; tool invocations surface in UI; `update_decision` triggers mutation and re-compliance.
**Acceptance:** debate can actually mutate a pending decision.

## T-17-09 — Build Portfolio surface

**Objective:** horizontal allocation bars (not pie), position list, drift highlighting, per-position risk contribution.
**Acceptance:** live data from M16.

## T-17-10 — Wire Portfolio to backend

**Objective:** live IBKR positions + attribution.

## T-17-11 — Build Backtest surface

**Objective:** scorecard-first layout, regime breakdown, "what if" panels, cost sensitivity, sub-horizon consistency view.
**Acceptance:** renders fixture backtest output.

## T-17-12 — Wire Backtest to engine

**Objective:** connect to backtest service (light scenarios interactive, heavy jobs queued).

## T-17-13 — Build Signal surface

**Objective:** news feed filtered by portfolio impact per `specs/09- §9.3`.

## T-17-14 — Wire Signal to Perplexity + embeddings

**Objective:** Perplexity + RAG surfaces portfolio-tagged items.

## T-17-15 — Build Settings surface

**Objective:** envelope parameters, autonomy view, notification tiers, kill switch, paper/live state, data source status, compliance rule viewer (read-only).

## T-17-16 — Wire Settings to envelope + autonomy services

**Objective:** envelope-widening flow triggers T-00-07 enforcement.

## T-17-17 — Attention-budget tracking UI

**Objective:** session decision-seconds counter; fatigue signals surfaced; weekly attention report.

## T-17-18 — Notification delivery (web push + in-app)

**Objective:** tiered notifications per `specs/09- §7` via Nexus middleware.

## T-17-19 — Accessibility + responsiveness audit

**Objective:** WCAG AA; min 1024px.

## T-17-20 — Anti-patterns guard

**Objective:** lint-style check preventing pie charts, countdown timers, modals for critical financial actions, adjacent approve/reject buttons.
**Acceptance:** CI lint rule fails on violation.

**Gate out:** web app runs end-to-end against real backend; all 7 surfaces function with live data; no mock data remaining; attention metrics collected.
