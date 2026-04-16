# Value Audit Report

**Date**: 2026-04-16
**Auditor Perspective**: Enterprise CTO evaluating autonomous investment platform for $500K+ annual spend
**Method**: Source code audit of `zai` branch, cross-referencing specs, briefs, and implementation

---

## Executive Summary

Midas has a **structurally sound spec** and a **genuinely impressive ML architecture** in source code, but the API layer is almost entirely disconnected from that architecture. The backend contains real PyTorch models, real state-inference code, real compliance logic, and real data adapters -- but the API routes return hardcoded zeroes, empty lists, and static strings without ever consulting the fabric or the ML pipeline. A buyer evaluating the live system today would see a working API that delivers zero actionable intelligence. The gap is not in the algorithms; it is in the wiring.

**Top finding**: The API layer (`src/midas/api/routes.py`) contains 12 router classes with zero DataFlow connections. Every endpoint returns static placeholders while the actual computation code sits in `src/midas/ml/`, `src/midas/state_inference/`, `src/midas/router/`, and `src/midas/compliance/` -- completely unwired.

**Single highest-impact fix**: Wire the API routes to the fabric. The PulseRouter should read from `latent_state`, the PortfolioRouter should read from `positions`, the DecisionsRouter should read from `decisions`. The code exists; it just is not connected.

---

## Page-by-Page Audit

### Health Surface (`/api/v1/health`)

**What I See**: Three endpoints (`/`, `/live`, `/ready`). The main health endpoint returns `{"status": "healthy", "dependencies": {"database": "unknown", "ibkr": "unknown", "data_sources": "unknown"}}`. Liveness and readiness return `{"status": "alive"}` and `{"status": "ready"}` respectively. No actual infrastructure checks.

**Value Assessment**:

- Purpose clarity: CLEAR -- health checks are standard
- Data credibility: EMPTY -- `"unknown"` for every dependency means no check is performed
- Value connection: DEAD END -- orchestrators and load balancers cannot make routing decisions
- Action clarity: ABSENT -- no actionable information when something is wrong

**Client Questions**:

1. How do I know if the system is actually working?
2. What does "unknown" mean for my positions?
3. Will you alert me when the database goes down?

**Verdict**: VALUE DRAIN -- fake-healthy endpoint masks real outages (zero-tolerance Rule 2 pattern: "fake health" returning 200 without checking anything)

---

### Pulse Surface (`/api/v1/pulse`)

**What I See**: Three endpoints for the regime-adaptive dashboard. Every response is hardcoded zeroes and empty lists: `"nav": 0.0`, `"attention_score": 0.0`, `"z_t_posterior": []`, `"changepoint_probability": 0.0`.

**Value Assessment**:

- Purpose clarity: CLEAR -- the surface is well-defined in specs 06 and 09
- Data credibility: EMPTY -- all values are zero, no fabric read
- Value connection: DEAD END -- this is the primary user-facing dashboard and it shows nothing
- Action clarity: ABSENT -- user sees an empty dashboard with zero context

**Client Questions**:

1. Why does the dashboard show nothing?
2. Where is the regime detection I was promised?
3. What happened to the attention-load axis?

**Verdict**: VALUE DRAIN -- the most important surface delivers zero of the core value proposition

---

### Decisions Surface (`/api/v1/decisions`)

**What I See**: Six endpoints for decision cards and action handling. `list_decisions` returns `{"decisions": [], "total": 0}`. `get_decision` returns a hardcoded skeleton. `approve` and `decline` log the event but do not update the `decisions` table. `get_brief` returns empty sections.

**Value Assessment**:

- Purpose clarity: CLEAR -- decision workflow is well-designed
- Data credibility: EMPTY -- no fabric reads or writes
- Value connection: DEAD END -- the approval flow is a no-op
- Action clarity: HIDDEN -- buttons exist but do nothing

**Client Questions**:

1. I approve a trade -- what actually happens?
2. Where is the brief that justifies this decision?
3. Can I see the debate that led to this recommendation?

**Verdict**: VALUE DRAIN -- the co-decision protocol (spec 07) is unimplemented at the API level

---

### Debate Surface (`/api/v1/debate`)

**What I See**: Five endpoints for debate threads. `create_thread` returns a hardcoded `"thread_id": "thread_1"`. `add_message` echoes the input. `invoke_tool` returns an empty `tool_result`. None of these connect to the DebateAgent or the evidence store.

**Value Assessment**:

- Purpose clarity: CLEAR -- debate is the core differentiator
- Data credibility: EMPTY -- no LLM calls, no evidence queries
- Value connection: DEAD END -- the debate surface is a chat facade
- Action clarity: ABSENT -- user cannot actually argue with the system

**Client Questions**:

1. Can I actually challenge a recommendation and get a reasoned response?
2. Where is the "what would change my mind" evidence?
3. Does the system actually re-run the optimizer when I propose alternatives?

**Verdict**: VALUE DRAIN -- the single most differentiating feature is a stub

---

### Portfolio Surface (`/api/v1/portfolio`)

**What I See**: Five endpoints returning hardcoded zeroes: `"nav": 0.0`, `"positions": []`, `"allocation": []`, `"attribution": {all zeros}`, `"risk": {all zeros}`.

**Value Assessment**:

- Purpose clarity: CLEAR -- portfolio monitoring is table stakes
- Data credibility: EMPTY -- no connection to the positions table
- Value connection: DEAD END -- user cannot see their portfolio
- Action clarity: ABSENT -- no actionable data

**Client Questions**:

1. Where is my money?
2. What is my current allocation?
3. How has the portfolio performed?

**Verdict**: VALUE DRAIN -- the user's primary concern (their money) is invisible

---

### Backtest Surface (`/api/v1/backtest`)

**What I See**: Three endpoints. `run_backtest` returns a fake `run_id`. `get_results` returns `"status": "pending"`. No backtesting logic is invoked.

**Value Assessment**:

- Purpose clarity: CLEAR -- backtesting is critical for trust
- Data credibility: EMPTY -- no computation occurs
- Value connection: DEAD END
- Action clarity: ABSENT

**Verdict**: VALUE DRAIN

---

### Signal Surface (`/api/v1/signal`)

**What I See**: Two endpoints returning `{"signals": []}` and `{"results": []}`.

**Value Assessment**:

- Purpose clarity: CLEAR
- Data credibility: EMPTY
- Value connection: DEAD END
- Action clarity: ABSENT

**Verdict**: VALUE DRAIN

---

### Settings Surface (`/api/v1/settings`)

**What I See**: Seven endpoints. The envelope endpoint returns hardcoded default values (not from the fabric). The autonomy endpoint returns L0 with `days_at_level: 0`. The kill switch logs a warning but does not call `ExecutionAgent.cancel_all_pending()`. The paper/live state returns static data.

**Value Assessment**:

- Purpose clarity: CLEAR -- settings are well-structured
- Data credibility: EMPTY -- hardcoded, not fabric-backed
- Value connection: ISOLATED -- kill switch does not actually cancel orders
- Action clarity: PARTIAL -- the surface exists but actions are no-ops

**Client Questions**:

1. If I hit the kill switch, are my orders actually cancelled?
2. Where are my actual envelope settings stored?
3. Can I change my autonomy level?

**Verdict**: NEUTRAL -- the structure is right, the kill switch is a safety concern

---

### Compliance Surface (`/api/v1/compliance`)

**What I See**: Three endpoints returning `{"rules": []}` and `{"evaluations": []}`. The compliance rules engine (16 blocking rules in `blocking_rules.py`) exists and is real -- but the API does not connect to it.

**Value Assessment**:

- Purpose clarity: CLEAR
- Data credibility: EMPTY at API, REAL in backend
- Value connection: DISCONNECTED
- Action clarity: ABSENT

**Verdict**: VALUE DRAIN -- real compliance exists but is invisible

---

## Value Flow Analysis

### Flow 1: Data Ingestion -> Latent State -> Portfolio Allocation

**Steps Traced**:

1. `fabric/adapters/eodhd.py` -- **REAL**: Makes actual HTTP calls to EODHD API with httpx, writes to fabric tables via DataFlow. Handles pagination, auth errors, rate limits. REAL code.
2. `fabric/engine.py` -- **REAL**: Creates DataFlow with 24 fabric models registered. Singleton pattern, test mode support. REAL code.
3. `ml/models/representation.py` -- **REAL**: Five PyTorch architectures (SSLTransformer, ContrastiveEncoder, MAE, VAE, DeepSSM). Proper encode/forward interfaces. Untrained but architecturally correct.
4. `ml/online_inference.py` -- **REAL**: Runs all pool members, writes z_t to fabric with PIT discipline. Checkpoint loading. REAL code.
5. `state_inference/bayesian_filter.py` -- **REAL**: Three architectures (DeepBayesianFilter, NormalizingFlowChallenger, NeuralKalmanChallenger). Proper posterior sampling. REAL code.
6. `state_inference/posterior_service.py` -- **REAL**: Writes posteriors to fabric latent_state table with in-memory cache. REAL code.
7. `heads/allocation.py` -- **REAL**: DRL champions (CVaRPPO, SAC, TD3) and classical baselines (MVO, BL, HRP, RiskParity). Proper softmax output. REAL code.
8. `router/contextual_router.py` -- **REAL**: Mixture-of-experts routing with softmax, blending, audit logging. Uses deterministic sin-based scoring (placeholder for a learned router, but structurally correct).
9. `api/routes.py` -> PortfolioRouter -- **BROKEN**: Returns `{"nav": 0.0}` without reading from fabric.

**Flow Assessment**:

- Completeness: **BROKEN AT STEP 9** -- the entire ML pipeline produces real outputs, but the API never asks for them
- Narrative coherence: STRONG in the backend, BROKEN at the API boundary
- Evidence of value: DEMONSTRATED in backend code, ABSENT at user-facing surface

**Where It Breaks**: The fabric has the data. The ML pipeline produces real z_t vectors. The heads produce real allocations. The router blends them. And then the API returns zeroes.

---

### Flow 2: Decision Pipeline (Research -> Brief -> Debate -> Recommendation)

**Steps Traced**:

1. `agents/research.py` -- **REAL**: Queries fabric tables (news, filings, embeddings), computes cosine similarity for RAG retrieval, calls frontier LLM for synthesis. One concern: similarity is hardcoded at `0.5` in `_retrieve_from_db` lines 172, 187 with a comment "Placeholder; real impl uses embeddings."
2. `agents/analyst.py` -- **REAL**: Calls frontier LLM with a structured 7-section prompt, parses JSON response, handles parse failures gracefully. REAL LLM reasoning.
3. `agents/debate.py` -- **REAL**: Steelman/red-team structured debate with separate LLM calls for each position. Tracks concessions and confidence. REAL LLM reasoning.
4. `agents/orchestrator.py` -- **REAL**: Coordinates the full pipeline (research -> brief -> debate -> recommendation). REAL orchestration.
5. `api/routes.py` -> DecisionsRouter -- **BROKEN**: Returns hardcoded empty decisions. Does not call the orchestrator.

**Flow Assessment**:

- Completeness: **BROKEN AT STEP 5** -- the agent pipeline works, but the API does not trigger it
- Narrative coherence: STRONG in the agent layer, BROKEN at the API boundary
- Evidence of value: DEMONSTRATED in agent code, ABSENT at user-facing surface

---

### Flow 3: Compliance Veto

**Steps Traced**:

1. `compliance/rules_engine.py` -- **REAL**: Data-driven rules engine with typed predicates, default-deny on exceptions, audit logging. REAL and well-designed.
2. `compliance/blocking_rules.py` -- **REAL**: 16 blocking rules covering envelope, data freshness, state, autonomy, model, execution, and API health. All with proper predicate logic. REAL.
3. `compliance/warning_rules.py` -- EXISTS but not read (likely similar quality).
4. `compliance/escalation_rules.py` -- EXISTS.
5. `compliance/kill_switch.py` -- EXISTS.
6. `api/routes.py` -> ComplianceRouter -- **BROKEN**: Returns `{"rules": []}`. Does not register or evaluate rules.

**Flow Assessment**:

- Completeness: **BROKEN AT STEP 6**
- Narrative coherence: STRONG in compliance layer
- Evidence of value: DEMONSTRATED in backend, ABSENT at API

---

## Mock Data Findings

### Critical Mock Data (Zero-Tolerance Violations)

1. **API routes -- hardcoded zeroes everywhere** (`src/midas/api/routes.py`):
   - `PulseRouter.get_pulse`: returns `nav: 0.0`, `attention_score: 0.0`, empty lists
   - `PulseRouter.get_regime`: returns `z_t_posterior: []`, `ood_score: 0.0`
   - `PortfolioRouter.get_portfolio`: returns `nav: 0.0`, `cash: 0.0`, `positions: []`
   - `PortfolioRouter.get_risk`: returns all zeroes for vol, sharpe, sortino, etc.
   - `DecisionsRouter.list_decisions`: returns `decisions: []`
   - `SettingsRouter.get_envelope`: returns hardcoded default values, not from fabric
   - These are the zero-tolerance Rule 2 "frontend mock data" pattern -- fake data presented as real

2. **Research agent -- hardcoded similarity** (`src/midas/agents/research.py` lines 172, 187):
   - `row["similarity"] = 0.5  # Placeholder; real impl uses embeddings`
   - Every retrieved document gets the same relevance score. This defeats the purpose of RAG.

3. **Health check -- fake healthy** (`src/midas/api/routes.py` HealthRouter):
   - Returns `"healthy"` with `"unknown"` dependencies. This is the zero-tolerance Rule 2 "fake health" anti-pattern documented explicitly in the project's own rules.

### Acceptable Placeholder Patterns

1. `random.choice` in `pbt_harness.py` line 76 -- PBT champion selection uses random choice. This is correct for a population-based training harness.
2. `random.uniform` in `pbt_harness.py` line 99 -- Mutation perturbation. Correct for PBT.
3. `np.random.default_rng(42)` in `latent_learnability.py` line 219 -- Seeded RNG for reproducible probe. Correct.

### The Good News

No `MOCK_`, `FAKE_`, `DUMMY_`, or `SAMPLE_` constants were found in source code. No `Math.random()` equivalents. The ML code, adapter code, and compliance code contain genuine implementation. The mock data problem is concentrated in the API layer.

---

## Value Delivery Score Per Milestone

| Milestone                   | Component                                                                            | Real Logic?                                     | Wired to API?         | Score |
| --------------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------- | --------------------- | ----- |
| M01 Data Fabric             | Fabric engine, 24 models, adapters (EODHD, Yahoo, FRED, IBKR, SEC Edgar, Perplexity) | YES -- real HTTP adapters, real DataFlow writes | NO                    | 6/10  |
| M02 Universe                | ETF selection, filters, overlap, constraints                                         | YES -- structural logic present                 | NO                    | 5/10  |
| M03 Representation Learner  | SSL Transformer, Contrastive, MAE, VAE, Deep SSM                                     | YES -- real PyTorch models                      | NO                    | 7/10  |
| M04 State Inference         | Bayesian filter, normalizing flow, neural Kalman, OOD detector                       | YES -- real posteriors with sampling            | NO                    | 8/10  |
| M05 Model Heads             | Allocation (DRL + classical), return, vol, tail risk, execution                      | YES -- real PyTorch heads + classical baselines | NO                    | 7/10  |
| M06 Meta-Router             | Contextual router, calibration, PBT harness                                          | YES -- real routing with audit logging          | NO                    | 7/10  |
| M07 Champion/Challenger     | Shadow lane, promotion contracts                                                     | YES -- real shadow infrastructure               | NO                    | 6/10  |
| M08 Regime Rendering        | Attention-load axis, changepoint detection                                           | PARTIAL -- OOD and changepoint are real         | NO                    | 4/10  |
| M09 LLM Agents              | Analyst, Debate, Research, Orchestrator                                              | YES -- real LLM reasoning with tool access      | NO                    | 7/10  |
| M10 Brief Composer          | Density matrix, templates, top-of-fold card                                          | YES -- real composition pipeline                | NO                    | 6/10  |
| M11 Autonomy Ladder         | L0-L4 state machine, upgrade contracts                                               | YES -- real state machine with audit trail      | NO                    | 7/10  |
| M12 Compliance Agent        | Rules engine, 16 blocking rules, kill switch                                         | YES -- real predicates with default-deny        | NO                    | 8/10  |
| M13 Credential Storage      | Credential model in fabric                                                           | MINIMAL -- model exists only                    | NO                    | 2/10  |
| M14 Scheduler               | 13 job definitions, scheduler service                                                | PARTIAL -- jobs exist but are mostly no-ops     | NO                    | 4/10  |
| M15 IBKR Integration        | IBKR adapter (1500+ lines)                                                           | YES -- comprehensive order management           | NO                    | 6/10  |
| M16 Performance Attribution | Brinson, NAV, metrics, track record                                                  | YES -- real attribution math                    | NO                    | 6/10  |
| M17 Web App                 | API routes, FastAPI app                                                              | YES (structure) but ALL STUBS                   | N/A (this IS the API) | 2/10  |
| M18 Mobile App              | Not found                                                                            | NO                                              | NO                    | 0/10  |
| M19 Paper Trading           | Paper manager with 14-day gate                                                       | YES -- real state management                    | NO                    | 5/10  |
| M20 Testing                 | 44 test files across tiers                                                           | YES -- comprehensive test coverage              | N/A                   | 7/10  |
| M21 Release                 | Version, changelog                                                                   | YES -- basic release tooling                    | N/A                   | 5/10  |

**Average value delivery score: 5.5/10** -- the backend is strong, the API is a facade.

---

## Cross-Cutting Issues

### CRITICAL: API-Fabric Disconnection

**Severity**: CRITICAL
**Impact**: Every user-facing surface returns zeroes and empty lists. The entire ML pipeline, agent system, and compliance engine are invisible to the user.
**Fix Category**: WIRING
**Evidence**: `src/midas/api/routes.py` contains 12 router classes. Zero of them import or reference DataFlow. Zero of them call `get_fabric()`. Zero of them read from fabric tables.

The fix is not algorithmic -- it is mechanical. Each router needs:

1. A `DataFlow` instance injected via constructor
2. Read queries from the appropriate fabric table
3. Calls to the appropriate service classes (RepresentationInferenceService, ContextualRouter, AgentOrchestrator, RulesEngine, etc.)

### CRITICAL: Scheduler Jobs Are No-Ops

**Severity**: CRITICAL
**Impact**: The 13 scheduled jobs that should drive the daily ML pipeline (data ingestion, representation inference, state inference, rebalance check, etc.) are mostly `return {"success": True}` with no actual work. Only `health_check` and `nav_valuation` call real code.
**Fix Category**: WIRING
**Evidence**: `src/midas/scheduler/jobs.py` lines 87-179 -- 10 of 13 jobs log "started" and immediately return success with no computation.

### HIGH: Research Agent Placeholder Similarity

**Severity**: HIGH
**Impact**: Every document retrieved by the research agent gets `similarity = 0.5`, making the RAG system unable to distinguish relevant from irrelevant documents.
**Fix Category**: DATA
**Evidence**: `src/midas/agents/research.py` lines 172, 187 -- `row["similarity"] = 0.5  # Placeholder`

### HIGH: Health Endpoint Is Fake

**Severity**: HIGH
**Impact**: Load balancers, orchestrators, and monitoring systems cannot detect real failures. A dead database, a broken IBKR connection, and stale data are all reported as "healthy."
**Fix Category**: WIRING
**Fix**: Wire `HealthRouter.health()` to `HealthCheckOrchestrator` which already exists in `src/midas/fabric/health.py`.

### HIGH: Kill Switch Does Not Cancel Orders

**Severity**: HIGH
**Impact**: User activates kill switch, no orders are actually cancelled.
**Fix Category**: WIRING
**Fix**: Wire `SettingsRouter.activate_kill_switch()` to `ExecutionAgent.cancel_all_pending()`.

### MEDIUM: Contextual Router Uses Deterministic Scoring

**Severity**: MEDIUM
**Impact**: The meta-router does not actually learn from outcomes. It uses `math.sin` of position-dependent weights, which is deterministic and not learned from data.
**Fix Category**: DATA
**Evidence**: `src/midas/router/contextual_router.py` lines 56-62
**Note**: This is architecturally acknowledged -- the spec calls for a contextual bandit or MoE layer "trained on historical (context, head outputs, realized outcome) tuples." The current implementation is a structurally correct placeholder.

### MEDIUM: Models Are Untrained

**Severity**: MEDIUM
**Impact**: All PyTorch models (representation learners, state inference, allocation heads) have architecturally correct code but random weights. They will not produce meaningful outputs until trained.
**Fix Category**: DATA
**Note**: This is expected at this stage -- the training infrastructure exists (`ml/training.py`) and the checkpoint loading exists (`ml/online_inference.py`). Training requires actual financial data and compute resources.

### LOW: No Mobile App Implementation

**Severity**: LOW
**Impact**: Brief specifies iOS and Android interfaces. No mobile code exists.
**Fix Category**: MISSING
**Note**: Expected to be addressed in M18.

---

## Severity Table

| Issue                                         | Severity | Impact                                | Fix Category |
| --------------------------------------------- | -------- | ------------------------------------- | ------------ |
| API returns hardcoded zeroes for all surfaces | CRITICAL | User sees nothing real                | WIRING       |
| Scheduler jobs are no-ops                     | CRITICAL | ML pipeline never runs automatically  | WIRING       |
| Research agent hardcoded similarity           | HIGH     | RAG cannot rank documents             | DATA         |
| Health endpoint fake-healthy                  | HIGH     | Outages invisible to monitoring       | WIRING       |
| Kill switch does not cancel orders            | HIGH     | Safety mechanism is a no-op           | WIRING       |
| API not connected to fabric                   | HIGH     | All computation invisible             | WIRING       |
| Contextual router uses sin-based scoring      | MEDIUM   | Routing not learned from data         | DATA         |
| Models have random weights                    | MEDIUM   | Outputs are meaningless until trained | DATA         |
| No mobile app                                 | LOW      | Brief requirement not met             | MISSING      |

---

## Brief Fulfillment Audit

| Brief Requirement                                   | Status     | Evidence                                                                                                                                                                 |
| --------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| "I don't want to monitor it"                        | PARTIAL    | Autonomy ladder exists (L0-L4), but API returns L0 with zero context. Scheduling infrastructure exists but jobs are no-ops.                                              |
| "Make the best investment decisions"                | STRUCTURAL | The ML pipeline (representation learners -> state inference -> model heads -> meta-router) is architecturally complete. But models are untrained and the API is unwired. |
| "Turbulent markets, don't trade without permission" | YES        | Compliance rules engine with OOD detection, kill switch, and envelope enforcement exist. The autonomy ladder enforces approval gates.                                    |
| "ETFs for diversification and sector rotation"      | STRUCTURAL | Universe module with ETF selection, overlap analysis, and constraints exists.                                                                                            |
| "Go big or go home" risk profile                    | PARTIAL    | Envelope parameters exist but are hardcoded in the API.                                                                                                                  |
| "Backtest comprehensively"                          | NO         | Backtest API returns stub data. No backtesting logic found.                                                                                                              |
| "Web, iOS, Android interface"                       | PARTIAL    | Web API structure exists (stubs). No mobile app.                                                                                                                         |
| "Debate with the AI"                                | STRUCTURAL | DebateAgent, DebateRouter, and Orchestrator exist with real LLM reasoning. API is unwired.                                                                               |
| "Fabric instead of pulling data all the time"       | YES        | Data fabric with 24 models, cache layer, freshness gates, and real adapters (EODHD, Yahoo, FRED, IBKR).                                                                  |
| "Aggressive caching"                                | YES        | `fabric/cache.py` exists with TTL-based caching.                                                                                                                         |
| "News is important, use perplexity"                 | YES        | Perplexity adapter exists in `fabric/adapters/perplexity.py`.                                                                                                            |
| "Transaction fees, price impact, slippage"          | STRUCTURAL | `execution/execution_agent.py`, `fills`, `fee_schedule`, and `cost_attribution` models exist. IBKR adapter has order management.                                         |

---

## Bottom Line

As a CTO evaluating this platform, I would tell my board:

"The architecture is genuinely differentiated. The latent-first design, the continuous state inference, the champion/challenger infrastructure, and the evidence-based debate system are not vaporware -- they exist as real, working code. The compliance engine with its 16 blocking rules and default-deny posture is production-grade thinking. The data fabric with 24 tables and real adapters for six data sources is serious infrastructure.

However, the system is currently a laboratory, not a product. Every surface a user would interact with returns zeroes and empty lists. The API layer is disconnected from the substantial backend. The scheduler does not run the pipeline. The kill switch does not cancel orders. A user deploying this today would get a beautiful API that tells them nothing.

The gap is mechanical, not conceptual. Every missing connection is a wiring problem, not a design problem. The highest-impact investment is one to two sessions connecting the API routes to the fabric, wiring the scheduler jobs to the service classes, and making the health endpoint actually check things. After that, training the representation learners on real financial data converts the system from 'architecturally correct' to 'operationally valuable.'

Score: 6/10 for architecture, 2/10 for delivery, 4/10 overall. The distance from 4 to 9 is wiring, not invention."

---

## Appendix: Evidence Paths

### Real Implementation (Value-Generating Code)

- `/Users/esperie/repos/training/midas/src/midas/ml/models/representation.py` -- 5 PyTorch architectures
- `/Users/esperie/repos/training/midas/src/midas/state_inference/bayesian_filter.py` -- 3 posterior architectures with sampling
- `/Users/esperie/repos/training/midas/src/midas/state_inference/ood_detector.py` -- Mahalanobis OOD detection
- `/Users/esperie/repos/training/midas/src/midas/state_inference/posterior_service.py` -- Fabric-backed posterior persistence
- `/Users/esperie/repos/training/midas/src/midas/heads/allocation.py` -- DRL champions + classical baselines
- `/Users/esperie/repos/training/midas/src/midas/router/contextual_router.py` -- MoE routing with audit
- `/Users/esperie/repos/training/midas/src/midas/compliance/rules_engine.py` -- Data-driven rules engine
- `/Users/esperie/repos/training/midas/src/midas/compliance/blocking_rules.py` -- 16 blocking rules
- `/Users/esperie/repos/training/midas/src/midas/agents/orchestrator.py` -- Full decision pipeline
- `/Users/esperie/repos/training/midas/src/midas/agents/debate.py` -- Steelman/red-team debate
- `/Users/esperie/repos/training/midas/src/midas/agents/analyst.py` -- Structured brief generation
- `/Users/esperie/repos/training/midas/src/midas/fabric/engine.py` -- 24 fabric models
- `/Users/esperie/repos/training/midas/src/midas/fabric/adapters/eodhd.py` -- Real HTTP adapter
- `/Users/esperie/repos/training/midas/src/midas/autonomy/ladder.py` -- L0-L4 state machine
- `/Users/esperie/repos/training/midas/src/midas/paper_trading/paper_manager.py` -- Paper/live gate
- `/Users/esperie/repos/training/midas/src/midas/execution/execution_agent.py` -- Order management

### Disconnected Stubs (Value Drains)

- `/Users/esperie/repos/training/midas/src/midas/api/routes.py` -- All 12 routers return hardcoded data
- `/Users/esperie/repos/training/midas/src/midas/scheduler/jobs.py` -- 10 of 13 jobs are no-ops
