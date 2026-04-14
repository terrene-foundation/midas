# Midas Todos — Master Index

**Status:** HUMAN-APPROVED (2026-04-14) — Q1 yes (M00 scope locked), Q2 parallel (paper→live M19 not gated by trader redteam), Q3 yes (M17 → M16 dependency). Ready for /implement in next session.
**Date:** 2026-04-14
**Spec set:** `specs/_index.md` v1 (14 governing files — specs 13 + 14 added this session) + Redteam Round 1 COMPLETE (quant-researcher + portfolio-manager + trader).
**Execution model:** Autonomous. Effort in sessions (1 session ≈ 3-5 human-days equivalent per the 10x multiplier).

---

## Milestones And Gate Dependencies

```
M00 Redteam Fixes (BLOCKING)
       │
       ├─────────────────────────────────────────────────┐
       ▼                                                 ▼
M01 Data Fabric                                M13 Credential Storage
       │                                                 │
       ▼                                                 ▼
M02 Universe                                   M14 Scheduler & Background Jobs
       │                                                 │
       ▼                                                 │
M03 Representation Learner ─┐                           │
       │                     │                           │
       ▼                     │                           │
M04 State Inference ────────┤                           │
       │                     │                           │
       ▼                     │                           │
M05 Model Heads ─────────────┤                           │
       │                     │                           │
       ▼                     │                           │
M06 Meta-Router ─────────────┤                           │
       │                     │                           │
       ▼                     │                           │
M07 Champion/Challenger ────┘                           │
       │                                                 │
       ▼                                                 ▼
M08 Regime Rendering (a_t)        M15 IBKR Integration
       │                                                 │
       │                                                 │
       ▼                                                 ▼
M09 LLM Agents ──────┐         M12 Compliance Agent (PACT)
       │             │                 │
       ▼             │                 │
M10 Brief Composer   │                 │
       │             │                 │
       └─────┬───────┘                 │
             ▼                         ▼
      M11 Autonomy Ladder ─── M16 Performance Attribution
                          │
                          ▼
                   M17 Web App (Nexus)
                          │
                          ▼
                   M18 Mobile App (Flutter)
                          │
                          ▼
                   M19 Paper Trading Flow
                          │
                          ▼
                   M20 Testing (3-tier)
                          │
                          ▼
                   M21 Release & CI/CD
```

---

## Milestone Summary Table

| #   | Milestone                                                         | Blocking?  | Spec anchors       | Est. sessions |
| --- | ----------------------------------------------------------------- | ---------- | ------------------ | ------------- |
| M00 | Redteam Round 1 critical fixes                                    | BLOCKS ALL | 04, 05, 08, 10, 12 | 2-3           |
| M01 | Data fabric + adapters + freshness gates                          | ✓          | 03                 | 3-4           |
| M02 | Universe construction (ETF + S&P 1500)                            | ✓          | 03                 | 2             |
| M03 | Representation learner pool + pre-train & fine-tune               | ✓          | 04, 05             | 4-6           |
| M04 | State inference pool + posterior                                  | ✓          | 04                 | 2-3           |
| M05 | Model heads (return, vol, allocation, execution, cross-sectional) | ✓          | 04, 05             | 5-7           |
| M06 | Meta-router + three-loop calibration                              | ✓          | 05                 | 3-4           |
| M07 | Champion/challenger shadow infrastructure                         | ✓          | 05                 | 2-3           |
| M08 | Continuous regime rendering (a_t)                                 | ✓          | 06                 | 1-2           |
| M09 | Frontier LLM agents (Analyst, Debate, Research) + tools           | ✓          | 07                 | 3-4           |
| M10 | Brief composer + density matrix                                   | ✓          | 07, 09             | 2             |
| M11 | Autonomy ladder + trust boundary                                  | ✓          | 08                 | 2             |
| M12 | Pre-trade compliance agent (PACT rules engine)                    | ✓          | 11                 | 2-3           |
| M13 | Credential storage + API auth                                     | ✓          | 11                 | 1-2           |
| M14 | Scheduler + background jobs + heartbeat                           | ✓          | 11                 | 2             |
| M15 | IBKR integration (Web API v1.0 + TWS fallback)                    | ✓          | 02, 11             | 3-4           |
| M16 | Performance attribution + track record                            | ✓          | 12                 | 2-3           |
| M17 | Web app (Nexus, React)                                            | ✓          | 09                 | 4-5           |
| M18 | Mobile app (Flutter)                                              | ✓          | 09                 | 4-5           |
| M19 | Paper trading flow + report                                       | ✓          | 08, 10             | 1-2           |
| M20 | Testing (Tier 1/2/3 + regression + redteam tests)                 | ✓          | all                | 3-4           |
| M21 | Release + CI/CD + deployment                                      | ✓          | —                  | 2             |

**Total:** 21 milestones, estimated 55-75 autonomous sessions.

---

## Per-Session Capacity Discipline

Every todo in every milestone file conforms to the per-session capacity budget (`rules/autonomous-execution.md` § Per-Session Capacity Budget):

- ≤ 500 LOC load-bearing logic per todo
- ≤ 5-10 simultaneous invariants per todo
- ≤ 3-4 call-graph hops
- Describable in ≤ 3 sentences

Todos that exceeded the budget at planning were sharded here, not deferred.

---

## Redteam Round 1 Summary — COMPLETE

Three expert personas pressure-tested the spec set:

| Persona           | Outcome                                                                     | File                                       |
| ----------------- | --------------------------------------------------------------------------- | ------------------------------------------ |
| Quant researcher  | 5 CRITICAL + 7 HIGH + 6 MEDIUM + 6 LOW + 10 missing-entirely                | `04-validate/round-1-quant-researcher.md`  |
| Buy-side trader   | 4 CRITICAL + 2 HIGH — resolved via specs 13 + 14 + inline edits to 03/08/10 | `04-validate/round-1-trader.md`            |
| Portfolio manager | 4 CRITICAL + 1 HIGH noted + more in file                                    | `04-validate/round-1-portfolio-manager.md` |

**All CRITICAL findings have spec-level resolutions written (see M00 T-00-01 through T-00-18).** Implementation of the enforcement (tests, compliance rules, UI affordances) is distributed across M01/M05/M09/M12/M15/M16/M17/M18/M19/M20.

**Owner directive Q2:** trader-redteam findings are fixed IN PARALLEL with M19 paper→live, NOT gating it. The first-seven-days L1 enforcement (`specs/08- §6.4`) + PLAF recalibration (`specs/13- §6`) are the live bridge.

---

## Approval Gate — APPROVED 2026-04-14

| Question                                         | Owner answer                |
| ------------------------------------------------ | --------------------------- |
| Q1 — M00 scope correct (PM redteam 4 CRITICALs)? | **YES**                     |
| Q1b — Quant redteam 5 CRITICALs at M00?          | **YES** (implicit under Q1) |
| Q2 — Trader redteam blocks M19 paper→live?       | **NO — run in parallel**    |
| Q3 — M17 (web) gated behind M16 (attribution)?   | **YES**                     |

All answers locked. `/implement` is authorized to begin at M00 in the next session.

**Trader redteam completed this session** (rate limit lifted); 4 CRITICAL + 2 HIGH findings resolved at spec level via new `specs/13-execution-cost-and-microstructure.md` + `specs/14-ibkr-integration.md` + inline edits to `specs/03`, `specs/08`, `specs/10`. Implementation enforcement distributed across the relevant milestones (see M00 T-00-12 through T-00-18).

---

## File Naming Convention

- `00-redteam-fixes.md` through `21-release.md` — one file per milestone
- Each file contains all todos for that milestone, numbered T-NN
- Each todo references the spec file(s) it implements
- Each todo states: objective, scope (in/out), invariants, acceptance criteria, dependencies, test tier requirements
