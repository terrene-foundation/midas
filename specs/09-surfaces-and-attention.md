# Surfaces and Attention

**Status:** GOVERNING. Defines the seven UI surfaces, how they reshape with `a_t`, and the attention budget contract.

Anchored to FP-13 (attention is sacred) and the owner's Q3 answer: _"humans have cognitive load; work with AI UX specialists to ensure my attention is well spent."_

---

## 1. The Seven Surfaces

Each surface does one job. Features that don't fit one of these jobs are in the wrong place.

| Surface       | One-sentence job                                                                             |
| ------------- | -------------------------------------------------------------------------------------------- |
| **Pulse**     | "Is everything okay?" in 5 seconds — the daily read that lets the user close the app.        |
| **Decisions** | Hands the user the approval tap with enough context to say yes/no without second-guessing.   |
| **Debate**    | A joint evidence review where the user can argue with Midas and actually change the outcome. |
| **Portfolio** | Lets the user inspect what they actually own, what's drifting, what rebalancing cost them.   |
| **Backtest**  | Builds (or rebuilds) trust that the strategy survives the conditions the user fears.         |
| **Signal**    | Filters news and research down to items that actually touch the user's book.                 |
| **Settings**  | Lets the user retune envelope, autonomy, and preferences after they learn about themselves.  |

The Debate surface is uniquely **universally accessible** — it is overlayable from every other surface so the user can challenge any recommendation or any position without losing context.

---

## 2. Regime-Adaptive Reshape

The Pulse surface reshapes with `a_t`. This is the defining UX move of Midas. Layouts interpolate — they never hard-flip.

| `a_t` band   | Pulse layout                                                                                                                                 | Promoted surfaces                      | Demoted surfaces              | Notification tier       |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | ----------------------------- | ----------------------- |
| **Calm**     | Portfolio value hero, regime gauge small, no approval section, recent-actions feed                                                           | Pulse                                  | Decisions hidden (no pending) | Silent in-app           |
| **Elevated** | Approval queue returns to top; amber accents; regime gauge prominent; decision windows shown                                                 | Decisions, Debate                      | Signal muted                  | Standard push           |
| **Urgent**   | Approval queue dominates; single-decision focus mode for highest-weight pending; window timers shown as progress bars (not countdown timers) | Decisions (full-width), Debate         | Portfolio, Backtest secondary | Prominent push + haptic |
| **Crisis**   | Red emergency banner; trading-paused state unmistakable; kill-switch state visible; all non-essential demoted                                | Pulse (status), kill-switch visibility | Everything else               | Emergency notification  |

The layout interpolation is animated over hundreds of milliseconds. The user sees a drift, not an event. This is critical — hard-flips create false alarms at band boundaries and the owner explicitly rejected the discrete-regime framing.

---

## 3. Attention Budget

The user has finite attention. Midas tracks it as a first-class concept.

### 3.1 What Is Tracked

- **Decision-seconds per day** — cumulative time spent on Decision and Debate surfaces
- **Decision volume per day / week** — count of pending decisions presented
- **Notification volume by tier** — how many pushes fired, by band
- **Time-to-decide distributions** — how long the user takes on approvals, by `a_t` band and dollar impact tier
- **Fatigue signals** — time-to-decide trending up, approve-without-reading heuristics (e.g. tap-immediately rate on Urgent), deferred decisions accumulating

### 3.2 What The Budget Does

The attention budget is consumed by decisions, not by browsing. When the system detects fatigue, it:

- Compresses routine briefs further
- Batches routine approvals into digest forms
- Raises the threshold for proactively starting a Debate
- Surfaces a "you are approving without reading the full brief" pattern warning if the heuristic trips
- Suggests an autonomy level upgrade if the override pattern is stable and positive (see FP-14, `08-autonomy-and-trust.md`)

The budget does **not** silently hide decisions. It changes how they are presented.

### 3.3 Attention Is A User Setting Too

In Settings the user can:

- Set their own daily attention ceiling and see how the system responds
- Configure notification tiers per band
- Define quiet hours (during which Elevated-band notifications are batched)
- Review a weekly attention-usage report

---

## 4. Brief Density Matrix

Briefs are not one template. They are a matrix over `(a_t band × dollar-impact tier × confidence tier)`. The frontier LLM generates the brief; the density template is enforced by the brief composer.

| Decision weight                                              | Brief density                                                                                      |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| Low (Calm band, small dollar, high confidence)               | Compressed: thesis + key number + "what would change my mind" + tap-to-expand                      |
| Medium (Elevated band OR medium dollar OR medium confidence) | Structured: all seven sections from `07-evidence-first-decision.md`, concise                       |
| High (Urgent band OR large dollar OR wide confidence)        | Full structured + pinned summary card + visible calibration history + pool disagreement callout    |
| Extreme (Crisis band OR OOD `z_t` OR envelope-touching)      | Full brief + honesty banner ("I am less calibrated in this state") + required review before action |

A routine $500 rebalance and a $50K tactical shift never share a template. If they do, attention is being wasted.

---

## 5. Navigation

### 5.1 Web

- Left rail with icons + labels, collapsible to icons only
- Six items visible (Pulse, Decisions, Debate, Portfolio, Backtest, Signal) + Settings in a footer
- Debate opens as a slide-in panel from the right, overlayable on any screen
- Minimum width: 1024px — this is a desktop/tablet product, phone users use the mobile app

### 5.2 Mobile

- Bottom tab bar with five items: Pulse, Decisions, Debate, Portfolio, More
- Debate also available as a bottom sheet from any screen
- Biometric gating on trade approvals, envelope changes, kill-switch clear, paper→live transition

---

## 6. The Pulse Surface In Detail

Pulse is the single most-opened surface. It must answer "is everything okay?" in under 5 seconds for the Calm case.

### 6.1 Calm Layout

- **Hero:** portfolio value, daily change, YTD change
- **Regime gauge:** small, unobtrusive, showing `a_t` position
- **Recent actions feed:** last 3-5 autonomous actions with one-line rationale each; tap to expand
- **Market context strip:** VIX, SPX, DXY at bottom, all in normal ranges

### 6.2 Elevated Layout

- **Top section:** approval queue — 1-3 pending decisions shown as cards with thesis + dollar impact + decision window
- **Hero:** portfolio value (smaller)
- **Regime gauge:** prominent, amber-accented
- **Recent actions:** collapsed to two lines

### 6.3 Urgent Layout

- **Full-width:** the single highest-weight pending decision, with summary card, countdown/window bar (not a countdown timer — a progress bar), approve/modify/reject/debate buttons with spatial separation
- **Secondary:** other pending decisions as a list below
- **Minimal:** portfolio value as a sidebar
- **Kill-switch:** always visible in the header

### 6.4 Crisis Layout

- **Emergency banner:** red, full-width, "trading paused" state unmistakable
- **Kill-switch state:** visible and accessible
- **Portfolio:** value shown for reference but not hero
- **Decisions:** deferred except for envelope changes, kill-switch clear, and explicit user-initiated actions

---

## 7. Notifications

### 7.1 Tiering By Band

| Band     | Notification behavior                                                                 |
| -------- | ------------------------------------------------------------------------------------- |
| Calm     | Silent in-app; no push unless weekly digest or milestone (all-time high)              |
| Elevated | Standard push with rich content (decision summary, dollar impact, confidence, window) |
| Urgent   | Prominent push + haptic + sound on mobile; banner notification even when locked       |
| Crisis   | Emergency notification; sound + haptic; wakes device                                  |

### 7.2 Batching In Calm

Routine rebalances fire no notifications individually. They appear in the recent-actions feed in Pulse and accumulate into a weekly summary push: _"Weekly summary: +1.8% ($50,423). 3 trades, $127 fees. State: Calm all week."_

### 7.3 Never Cry Wolf

An Urgent notification that turns out to be a false alarm consumes user trust more expensively than almost any other failure. The attention budget tracks "Urgent notifications followed by no significant action by the user" as a fatigue signal; persistent false-urgents trigger a recalibration of `a_t` thresholds.

---

## 8. The Debate Surface

### 8.1 Universal Accessibility

Debate is available from every other surface as an overlay (web) or bottom sheet (mobile). Entering Debate never loses the originating context — the Debate thread pre-loads with the pending decision, position, news item, or backtest run that was open.

### 8.2 Thread List

The dedicated Debate tab shows a list of recent and active threads with:

- Originating context (decision ID, position, news item)
- Resolution state (updated / maintained / open / envelope-change)
- Last activity timestamp
- Tap to resume

### 8.3 Composition Affordances

Within a thread:

- Free-text input for the user
- Agent messages grounded in data, with every claim showing a provenance pointer
- Inline visualizations generated by tool calls
- A toolbar of **action buttons** the agent can surface: "Update decision to 8%", "Keep at 15%", "Run alt-backtest", "Show calibration curve"
- Thread memory persists across sessions

### 8.4 Sycophancy Prohibition

See `10-moments-of-truth.md` §4. The Debate agent must disagree when evidence warrants. A Debate that always concedes is worse than no Debate.

---

## 9. Other Surfaces (Brief)

### 9.1 Portfolio

- Horizontal allocation bars (not pie charts) with target vs current and drift highlighted
- Position list sortable by weight, P&L, drift
- Each position links to its history, its contribution to portfolio risk, and the debate thread (if any) that led to its current weight

### 9.2 Backtest

- Scorecard first (numbers), equity curve second (chart)
- Regime breakdown using historical `z_t` analogues
- Sub-horizon consistency view
- Cost sensitivity
- "What-if" scenarios for envelope changes

### 9.3 Signal (News)

- Items filtered by portfolio impact (computed by the research agent)
- None = deprioritized; High = promoted
- Tap to drill into how the item would or would not affect pending decisions

### 9.4 Settings

- Envelope parameters (trust-boundary settings)
- Autonomy level viewer and upgrade proposals
- Notification tier preferences
- Kill-switch access
- Paper/live state
- Data source status
- Compliance rule viewer (read-only in v1)

---

## 10. Working With UX Specialists

The owner explicitly asked for collaboration with AI UX specialists (Q3). For v1 that means:

- The attention-budget visual design (gauge, fatigue warnings, digest formats) is delegated to a UX specialist agent
- The brief density matrix is co-designed: the templates are specified here; the visual/interaction design is the UX specialist's domain
- Animation timings for regime-reshape interpolation are set by the UX specialist in collaboration with this spec
- The mobile/web split of Debate affordances is the specialist's domain
- The attention-budget report format is co-designed

This spec sets the attention contract; the specialist's role is to realize it in pixels and interactions.

---

## 11. Anti-Patterns (Blocked)

- Pie charts for allocation
- Countdown timers (use progress bars)
- Modals for critical financial actions
- Purple-to-blue gradients, neon accents, glassmorphism
- Generic chatbot sidebar for Debate
- Notification spam in Calm
- Hard-flip band transitions
- Decision buttons adjacent on mobile (Approve and Reject must be spatially separated — see `10-moments-of-truth.md`)
- Same template for a $500 rebalance and a $50K tactical shift

---

## 12. Relationship To Other Specs

- `06-continuous-regime-rendering.md` — provides `a_t` that drives reshape
- `07-evidence-first-decision.md` — defines the brief contract that the density matrix composes
- `10-moments-of-truth.md` — defines the inviolable UX safety rules
- `08-autonomy-and-trust.md` — defines paper→live and kill-switch affordances
