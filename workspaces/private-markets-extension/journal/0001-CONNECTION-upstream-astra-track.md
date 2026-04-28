---
name: Connection to upstream Astra private-markets extension track
date: 2026-04-22
type: CONNECTION
author: co-authored
project: training-midas-private-markets-extension-mirror
topic: cross-repo connection
phase: analyze
tags: [astra, midas, private-markets, product-track, mirror]
---

## Connection

A product-track initiative in the Astra repo — extending autonomous portfolio-management to private-market investment workflows — is catalysed by an atelier workshop for a sovereign growth-stage investor. This workspace mirrors the track in the training Midas instance for educational / learner awareness.

## The three connected artefacts

1. **Originating workshop.** `atelier/workspaces/sggc-ai-transformation-workshop/journal/0005-CONNECTION-astra-private-product-track.md` — workshop-side anchor where the opportunity was named.
2. **Authoritative product track.** `dev/astra/workspaces/private-markets-extension/` — where the product direction is set.
3. **Authoritative spec.** `dev/astra/specs/13-private-markets-extension.md` — where the extension is specified at the same rigour as Astra's public-markets specs (`specs/00`–`specs/12`).

This mirror (here at `training/midas/workspaces/private-markets-extension/`) is the fourth artefact — a reference anchor for the training instance so learners, exercises, and training-side agents know the track exists without needing to read the product workspace.

## What transfers across the connection

- Shared-core primitives unchanged: decision-brief contract, debate agent interface, graduated autonomy L0–L4, automatic demotion, forensic audit, pre-action compliance gating interface
- Engine swap: factor overlays / regime inference / IB execution → thesis-based exposure tracking / event-based state inference / pre-commitment gates
- New primitives: deal-flow triage, DD orchestration, KPI monitoring, Level-3 mark-to-model, cap-table evolution, stage-transition gates, thesis-drift detection, exit-pathway reasoning
- Compliance rule set adapted: sovereign nexus, KYC, export control, co-invest fair-dealing, insider-information handling, portfolio-IP protection

## What does NOT transfer to this mirror

- Design-partner identities — not discussed in identifying form in either the upstream workspace or this mirror
- Implementation commits — happen in `dev/astra/`, not here
- Spec authority — this mirror does not amend the authoritative spec

## Why the mirror is useful

- **Cross-repo orientation.** Training-midas agents encounter a session-start awareness that a parallel production track exists upstream; they don't invent private-markets primitives in isolation or build educational content that contradicts the production specification.
- **Learner referenceability.** Training content referencing the Astra pattern in private domains can cite the authoritative spec here, keeping educational material synchronised with production specification.

## Follow-up

- [x] Mirror workspace created
- [x] Cross-reference captured
- [ ] When upstream Astra private track produces learner-relevant artefacts (worked examples, reference test-portfolios), mirror them here for educational use

## For Discussion

1. The mirror is an awareness artefact, not an authority artefact. If a training-side agent drifts from the authoritative spec during an exercise, what mechanism catches the drift — or is it accepted as fair for educational simplification?
2. If Astra's public-markets engine and private-markets engine later converge into a unified trunk, does this mirror persist as a historical artefact, or does it get retired?
3. The value of this mirror depends on the training midas using it. If no learner project ever references the private-markets track, the mirror decays to noise. What's the shortest path to demonstrating value — a single worked example, or waiting for learner pull?
