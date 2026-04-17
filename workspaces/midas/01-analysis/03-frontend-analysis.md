# Frontend Analysis — Gap Summary

**Scope**: Web frontend (React/Next.js). Mobile (Flutter) deferred to separate cycle.

## Existing Foundation

- Detailed plan at `02-plans/05-frontend.md` — tech stack, page structure, design system, regime-adaptive layouts
- 5 user flows covering all critical paths
- Backend API with 10 router classes covering 8 domains
- All specs are GOVERNING status with FE-relevant sections

## Findings

### HIGH (blocks implementation)

1. **No auth system** — Static API key only; FE needs login/session/token-refresh for biometric gating
2. **No WebSocket endpoint** — Real-time surfaces (Pulse, Decisions, Debate) need WS transport
3. **No onboarding endpoints** — Brokerage connect, risk seed, paper-trading activation
4. **Attention budget UI missing** — Decision-seconds/day, fatigue warnings, approval-without-reading alert (spec 09 S3)
5. **Brief density matrix not implemented** — 4-level template over (a_t × dollar × confidence) (spec 09 S4)
6. **7-section brief contract missing from components** — Thesis, Evidence, If Approved/Rejected, Precedent, WWCM, Confidence (spec 07 S2)
7. **Kill-switch UX absent** — Unmissable "trading paused" state, clear affordance (spec 10 S5)
8. **Paper→live transition missing** — Multi-step gate with 2-week minimum (spec 10 S3)
9. **Quote-moved-since-brief guard missing** — Fresh quote at confirmation, drift dialog (spec 10 S6.4)
10. **Continuous a_t gauge missing** — Soft band visualization, not discrete badges (spec 06 S3)
11. **Transition-pressure gauge absent** — `p(transition)` on Pulse (spec 06 S5)
12. **Debate tools not surfaced** — 10 agent tools need UI affordances (spec 07 S3.3)
13. **No WCAG plan** — Regime restructure traps screen readers; colorblind users; focus management (spec 09 S10)
14. **Regime interpolation mechanism undefined** — `useMemo` switch is discrete; prose says continuous (spec 06 S3)
15. **Settings surface incomplete** — Missing attention ceiling, quiet hours, notification tiers, weekly report (spec 09 S9.4)

### MEDIUM (needs clarification)

1. Missing component states (loading, error, empty, skeleton)
2. Debate resolution states not shown (spec 07 S3.5)
3. Debate action toolbar absent (spec 07 S3.3)
4. Notification batching logic for Calm (spec 09 S7.2)
5. Web re-auth flow for Urgent/Crisis approvals (spec 10 S2.3)
6. Historical analogue rendering in briefs (spec 06 S6)
7. Override-pattern dashboard (spec 07 S5)
8. Dark-mode only — no light tokens (should document as v1 constraint)
9. Easing curves undefined for animations
10. Debate panel interaction spec incomplete (width, resize, keyboard, focus trap)

### Backend API Gaps

- Auth: login, refresh, logout (all missing)
- WebSocket: endpoint + message types (missing)
- Onboarding: connect-brokerage, risk-profile, activate (missing)
- Decisions: modify endpoint (missing)
- Debate: resolution endpoint (missing)
- Notifications: preferences, history (missing)
- Backtest: scorecard, regime-breakdown, consistency, cost-sensitivity views (missing)
- Portfolio: position history endpoint (missing)

## Decision: Web-First, Mobile Deferred

The plan correctly splits web (Next.js) from mobile (Flutter). Web is primary; mobile is a future cycle. Min-width 1024px is justified for a financial co-pilot managing six-figure portfolios.

## Tech Stack Confirmed

- Next.js App Router + React Query + Shadcn/ui + Tailwind CSS + Geist
- WebSocket for real-time (regime, prices, decisions, debate)
- No state library beyond React Query (server state) + React context (regime, auth)
