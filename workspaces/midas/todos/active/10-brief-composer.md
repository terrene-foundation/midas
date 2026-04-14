# M10 — Brief Composer & Density Matrix

**Spec anchors:** 07 §2, 09 §4, T-00-08.
**Depends on:** M09.

## T-10-01 — Top-of-fold decide-in-10s card component

**Objective:** schema + renderer for the universal card per T-00-08. Action line, one counter-evidence, one "what would change my mind", three spatially-separated buttons.
**Acceptance:** T-00-08 usability gate passes.

## T-10-02 — Density matrix templating

**Objective:** matrix over `(a_t band × dollar-impact tier × confidence tier)` → brief density template.
**Acceptance:** unit tests render each cell from a fixture.

## T-10-03 — Compressed brief template (low-weight)

**Objective:** compressed brief used for routine low-weight approvals.
**Acceptance:** golden-test render.

## T-10-04 — Full structured brief template (medium-to-high weight)

**Objective:** seven-section full brief template per `specs/07- §2`.
**Acceptance:** golden-test render with all sections present.

## T-10-05 — Extreme-weight brief with honesty banner

**Objective:** full brief + OOD / Crisis honesty banner + required review before action.
**Acceptance:** Tier 2 confirms banner fires on synthetic OOD state.

## T-10-06 — Brief composer service

**Objective:** composer that consumes decision context, selects template from density matrix, calls Analyst agent, produces final brief.
**Acceptance:** end-to-end produces briefs for the three density tiers.

## T-10-07 — Provenance pointer rendering

**Objective:** every claim in every brief links to a fabric row / model version / tool call; UI surfaces as drill-through.
**Acceptance:** click-through on any claim reaches the source row.

**Gate out:** briefs render in all density tiers, usability gate passes, provenance click-through works end-to-end.
