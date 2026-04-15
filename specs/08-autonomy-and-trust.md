# Autonomy and Trust Boundary

**Status:** GOVERNING. Defines the autonomy ladder, the trust boundary, upgrade/downgrade rules, kill switch, and paper→live gate.

Anchored to FP-14 (track record earns latitude), the owner's Q1 = B (Midas earns its way up), and FP-7 (mandatory paper trading).

---

## 1. The Trust Boundary

The trust boundary is the set of parameters **only the user can change**. Crossing the boundary always requires the user, regardless of autonomy level. The boundary is the user's envelope for the system to operate within.

| Parameter                                             | User-owned                        | Midas may adjust within bounds?                                                                       |
| ----------------------------------------------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Max portfolio drawdown ceiling                        | YES                               | Midas tightens dynamically below, never widens                                                        |
| Volatility target band                                | YES                               | Midas moves within the band, cannot move the band                                                     |
| Concentration cap (per position, per sector)          | YES                               | Midas respects, cannot relax                                                                          |
| Universe exclusions (asset class, sector, instrument) | YES                               | Midas respects                                                                                        |
| Autonomy level                                        | YES (promotion); Midas (demotion) | Downgrades auto; upgrades proposed not applied                                                        |
| Paper / live flag                                     | YES                               | Never                                                                                                 |
| Kill switch                                           | YES                               | Midas may trip the kill switch automatically on a tripped circuit breaker; only the user can clear it |
| Cost budget ceiling                                   | YES                               | Midas allocates within the ceiling                                                                    |
| Debate / brief density preferences                    | YES                               | —                                                                                                     |

The boundary is enforced at the **Pre-Trade Compliance Agent** (see `11-compliance-and-risk.md`). Any envelope-touching action is rejected at the compliance layer before it reaches execution, regardless of which model proposed it.

---

## 2. The Autonomy Ladder

Five levels. Promotion is always user-approved and surfaced as a decision in the Decisions surface. Demotion is automatic when a degradation contract trips.

### 2.1 L0 — Observer (default on install; mandatory during paper trading)

- Midas runs the full pipeline end-to-end
- Midas executes **nothing**
- Every action is a recommendation; every action requires user approval
- User sees the full brief and the evidence for every move
- Paper trading is mandatory (FP-7) — live trading blocked until the 2-week report is reviewed and the user explicitly activates

### 2.2 L1 — Co-Pilot (default after paper→live transition)

- Midas executes **nothing autonomously** still
- But briefs are pre-loaded, the router is live, counterfactuals are tracked
- Approvals are required for every move
- Autonomy upgrade to L2 is gated on: N operating days + positive override-convergence trend + positive early calibration

### 2.3 L2 — Delegated Routine

- Midas may execute **routine rebalances** autonomously under all of:
  - `a_t` is in Calm band
  - Dollar impact is below a user-set threshold X
  - Cost budget check passes
  - Model confidence is above a configurable floor
  - Pool agreement is above a configurable floor
  - No open debate thread on a related decision
- Every other move is escalated to the user
- Upgrade to L3 gated on: M consecutive successful routine rebalances + positive Brinson allocation effect in attribution

### 2.4 L3 — Delegated Tactical

- L2 scope plus: Midas may execute **tactical tilts** autonomously when `a_t` is in Elevated band AND the tilt is within pre-agreed band constraints AND all L2 gating holds
- Urgent and Crisis states still escalate
- Envelope changes still require the user
- Model promotions still require the user
- Upgrade to L4 gated on: sustained track record (months) + user explicit opt-in

### 2.5 L4 — Envelope Autopilot (opt-in only, never reached automatically)

- L3 scope plus: Midas may auto-promote challenger models that meet an extended contract (see `05-model-pool-and-meta-router.md` §5.5)
- Urgent state may execute within pre-configured Urgent-playbook rules; Crisis still escalates
- Envelope changes still require the user; kill switch still user-owned
- This level is a deliberate opt-in and can be revoked instantly by the user

---

## 3. Promotion Protocol

Promotions are decisions like any other. When a level's upgrade contract is satisfied:

1. The system writes a **promotion proposal** to the Decisions surface
2. The proposal contains: the operating history, Brinson attribution, calibration snapshot, model-promotion log, override log, what would change in behavior if upgraded
3. The user reviews the evidence, approves or declines
4. If approved, the new level becomes active on the next decision cycle
5. The promotion decision is audited and recorded

Autonomy upgrade is never silent. FP-14's violation test is: "if an autonomy level can be silently increased by the system without the user seeing the evidence in a Decisions surface event, the track-record contract is broken."

---

## 4. Demotion Protocol

Demotions are automatic and fast. Triggers:

| Trigger                                                         | Demotion                                                                                                 |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Drawdown breaches a configured fraction of the envelope ceiling | L3 → L1                                                                                                  |
| Live champion model demoted (`05-` degradation contract)        | L3 → L2 (until the new champion proves calibration)                                                      |
| User override rate exceeds a threshold over a trailing window   | L3 → L2 or L2 → L1 depending on magnitude                                                                |
| Calibration drift on any load-bearing head                      | Held at current level, new promotions paused                                                             |
| Stale-data gate trips                                           | All levels temporarily paused (not demoted, but no new autonomous actions until data freshness recovers) |
| Crisis band entered                                             | L3/L4 → L2 for the duration of Crisis                                                                    |
| OOD `z_t` detected                                              | L3/L4 → L2 for the duration                                                                              |
| User trips kill switch                                          | All → L0 until user clears                                                                               |

Every demotion writes an audit record and surfaces in Pulse. The user sees what happened and why.

---

## 5. Kill Switch

### 5.1 Purpose

The kill switch is the user's last-resort control. It halts all trading and reverts to a safe posture without requiring the user to reason about the market.

### 5.2 Access

- From Pulse (any regime band)
- From Settings
- From the decision detail screen if a decision is pending
- From the Debate surface

Always one tap (plus biometric) away. Never buried in a menu.

### 5.3 Effect When Tripped

- All pending orders cancelled
- All autonomous decisioning halted (router continues reading but no new actions propose)
- Monitoring continues (the system still updates `z_t`, still writes calibration, still generates briefs as decisions that will require manual approval to act on)
- Pulse shows a persistent "KILL SWITCH ACTIVE" banner
- No trade will execute until the switch is cleared
- All autonomy levels revert to L0

### 5.4 Clearing (Process-Lock, not Time-Lock)

Per Redteam Round 1 PM-C4, the time-based 15-minute cool-down is replaced by a **process lock** — time locks cannot distinguish "user is right" from "user is panicking"; process locks can.

- Requires biometric
- Requires explicit user action from Settings or Pulse
- Clear always reverts autonomy to L1 regardless of prior level
- Mandatory state-of-the-world brief before clear — `z_t` posterior, drawdown state, pool disagreement, any compliance events — user must read and acknowledge
- 60-second dwell on the first post-clear decision (enforced at the compliance layer AND the UI)
- First post-clear decision is user-approved regardless of autonomy level
- Clearing is audited

### 5.5 Auto-Trip Conditions

Midas trips the switch automatically when:

- Drawdown crosses the hard circuit-breaker threshold (a fraction of the envelope ceiling that is itself a user setting with a safe default)
- An OOD `z_t` state coincides with a rapid NAV move
- IBKR integration reports a severe error class
- The PACT rules engine reports a policy breach the system cannot resolve

Auto-trip is logged and surfaces as an immediate notification.

---

## 6. Paper → Live Gate

### 6.1 Flow (summary; full UX in `09-surfaces-and-attention.md`)

1. Install + configure envelope → paper trading begins immediately
2. Paper trading runs at least 2 weeks end-to-end with real data
3. Paper trading report is generated — every subsystem pass/fail, simulated P&L, any anomalies, comparison to backtest expectations
4. User reviews the report in a dedicated review surface
5. User taps "Go Live" — biometric + explicit confirmation
6. System transitions to live; first live decision is logged prominently

### 6.2 What The Report Covers

- Data pipeline health (all sources green, no stale gates tripped)
- Representation learner calibration snapshot
- State inference pool calibration
- Return heads + vol heads + tail heads calibration
- Router behavior log
- Allocation policy simulated P&L and Brinson attribution
- Compliance agent record (every veto logged)
- Order state machine record
- Approval workflow record (decisions presented, time-to-decide, modify/reject rates)
- Any anomalies, warnings, or degradation events
- At least one simulated regime transition the system handled
- **Both raw-paper costs AND PLAF-adjusted costs** (Paper-to-Live Adjustment Factor per `13- §6`) — IBKR paper fills are optimistic (instant mid fills, no impact, stale NBBO); the user reviews both to understand the degradation expected when going live

### 6.2.1 Paper-Fill Realism Disclaimer

Per Redteam Round 1 Trader H-3: a clean paper-trading report does **not** prove safety in live. It proves every subsystem is wired and no obvious failure mode fires on optimistic fills. The paper-to-live transition is therefore framed as "safe to begin carefully calibrated live trading with conservative sizing and L1 approval on every decision for the first seven days" — not "safe to trade at full autonomy." First-seven-days L1 enforcement (§6.4) + PLAF recalibration (`13- §6`) are the honest bridge.

### 6.3 Blocking Conditions

A paper→live transition cannot be requested if any of:

- Fewer than 14 operating days
- Any subsystem marked fail
- Any critical anomaly in the report
- User has not opened the report and acknowledged

These are not UI hints — they are enforced by the Pre-Trade Compliance Agent.

### 6.4 Post-Transition

First live decision ships with an extended brief and a confirmation step even if autonomy level L1 would otherwise auto-present. The first seven days live run at L1 regardless of paper-trading performance — track record has to exist in live data before L2 is proposable.

---

## 7. Upgrade Contracts (Concrete)

> **T-00-06 Update:** 3-month windows are too noisy for autonomy decisions. A 3-month Brinson attribution yields ~12 data points — insufficient to distinguish 30-bps-per-quarter skill from zero. All L3/L4 promotion contracts require a 12-month primary window.

### 7.1 Window Hierarchy

| Window          | Role                                                          |
| --------------- | ------------------------------------------------------------- |
| 1-week          | Context signal only — never triggers autonomy decisions       |
| 1-month         | Primary reporting window                                      |
| 3-month         | Context signal only — NOT a promotion trigger                 |
| 12-month        | **Primary track-record window for L3/L4 promotion contracts** |
| Since inception | Lifetime context                                              |

### 7.2 Track-Record Gates For L3/L4

A promotion proposal to L3 or L4 fires only when ALL of the following are true:

1. **12-month bootstrap lower bound** — the 90% confidence interval lower bound of the 12-month Sharpe ratio exceeds the floor, not the point estimate. Bootstrap with 1,000 resamples minimum.
2. **Pool-consistency gate** — the strategy was positive in at least 8 of the 12 trailing monthly periods (not just the aggregate). A strategy that won 12% in aggregate but was negative in 7 of 12 months is not consistent.
3. **Minimum-activity gate** — at least M (default: 6) routine rebalance events occurred in the 12-month window. A strategy with low turnover cannot be evaluated on outcome quality.
4. **Aggregate 12-month Sharpe ratio** — point estimate exceeds the champion's 12-month Sharpe in the same latent region.

### 7.3 Concrete Promotion Table

| Transition | Minimum contract                                                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| L0 → L1    | Paper trading complete + report reviewed + user Go-Live                                                                                       |
| L1 → L2    | N live operating days + positive override-convergence + no degradation events + positive early calibration on at least one allocation head    |
| L2 → L3    | M ≥ 6 rebalances in 12-month window + bootstrap lower bound Sharpe > floor + positive in ≥ 8/12 trailing months + no compliance vetoes        |
| L3 → L4    | 12-month primary window (same gates as L2, extended track record) + user explicit opt-in + user has experienced ≥ 1 Elevated state transition |

Concrete values for N, M, and the various thresholds are set in `11-compliance-and-risk.md` §rules registry, not hardcoded here — they are data, and the user may adjust them (within reason) in Settings. Starting defaults are conservative.

> **Why bootstrap CI lower bound, not point estimate?** A point estimate of Sharpe = 0.8 could be Sharpe = 0.2 with 90% confidence. Requiring the lower bound to exceed the floor prevents promotions where the apparent skill is entirely within the noise band.

---

## 8. Relationship To Other Specs

- `07-evidence-first-decision.md` — autonomy controls which decisions are user-facing vs autonomous
- `10-moments-of-truth.md` — paper→live transition is a moment of truth (cannot be skipped)
- `11-compliance-and-risk.md` — envelope enforcement, stale-data gate, kill switch auto-trip
- `12-performance-and-track-record.md` — Brinson attribution is the substrate for upgrade contracts
