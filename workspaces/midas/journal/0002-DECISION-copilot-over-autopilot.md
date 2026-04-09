---
type: DECISION
date: 2026-04-09
created_at: 2026-04-09T21:30:00+08:00
author: agent
project: midas
topic: Reframed product identity from autopilot to co-pilot with graduated autonomy
phase: analyze
tags: [product-identity, trust, regulatory, user-persona]
---

## Decision

Reframed Midas from "autonomous AI that makes investment decisions for you" to "AI investment co-pilot with graduated autonomy." The brief describes full autonomy; we recommend building toward it through a trust ladder: Observer → Co-Pilot → Autopilot.

## Alternatives Considered

1. **Full Autopilot from v1** — per the brief's stated intent. Rejected because: (a) no AI has demonstrated auditable market-beating returns, (b) regulatory exposure is maximized, (c) user trust cannot be earned without track record, (d) the credible target user (self-directed IBKR investor) wants augmented decisions, not delegation.

2. **Pure research/analytics tool** — no execution at all. Rejected because: execution integration is a real differentiator, and the brief explicitly requires it.

3. **Co-Pilot with graduated autonomy** — chosen. Starts as decision support + debate. Users opt into increasing autonomy as trust accrues. Full autopilot is a v3 feature, not a v1 promise.

## Rationale

- The most credible target user ($100K-$500K self-directed IBKR investor) already makes decisions — they want a sounding board, not a replacement
- "AI makes the best decisions" is an indefensible claim; "AI applies disciplined, systematic strategy" is honest and more compelling
- Regulatory exposure scales with autonomy: tools < advice < management. Co-pilot sits at the lower end
- The AI debate feature (the primary differentiator) is inherently a co-pilot interaction, not an autopilot one
- Trust is earned through track record + counterfactual tracking, not claimed upfront

## Consequences

- v1 architecture must support the full autonomy pathway (don't build walls)
- Onboarding includes explicit autonomy level selection
- Counterfactual tracking is essential from day 1 (builds the evidence base for graduating to autopilot)
- Marketing language must avoid "best decisions" and "fully autonomous" — focus on discipline, transparency, and debate

## For Discussion

- The brief's author explicitly wants "I don't want to monitor it" — does the co-pilot model honor that intent, or does it water down the vision? At what point does caution become failure to execute the brief?
- If the graduated autonomy model is adopted, what specific metrics should gate the transition from Co-Pilot to Autopilot? (e.g., 6 months of positive alpha, user override rate below 10%, etc.)
- Is there a middle ground where the system is autonomous for routine rebalancing (small, low-risk trades) but co-pilot for everything else — satisfying both the "don't make me monitor" intent and the trust concern?
