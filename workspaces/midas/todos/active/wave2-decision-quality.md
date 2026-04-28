# Wave 2 — Make It Valuable

GAP-3 (Brief Composer Grounding, HIGH) + GAP-4 (Debate Multi-Turn, HIGH) + GAP-6 (ModelRegistry Fix, HIGH)

**Session estimate:** 2 sessions
**Spec anchors:** 05 (model pool), 07 (evidence-first decision)

---

## GROUP D: Brief Composer Grounding (GAP-3)

**Current state:** `AnalystAgent` prompt requests all 10 sections. `BriefComposer` extracts them. The gap: LLM produces generic placeholder text for 4 sections (if_approved, if_rejected, historical_precedent, what_would_change_mind) because the prompt doesn't require evidence-store-backed content and there's no validation enforcing substantive output.

### BUILD Todos

**3A. Build BriefSectionValidator with grounding checks**

- Create `src/midas/brief/validators.py`. Four validators: `validate_if_approved()` checks for dollar amounts + risk metrics; `validate_if_rejected()` checks for position retention + drawdown probability; `validate_historical_precedent()` checks for ≥1 analogue with outcome; `validate_what_would_change_mind()` checks for ≥1 specific numeric threshold. Returns missing-element list for re-prompting.
- **Spec:** 07 S2.3-S2.6
- **LOC:** ~200 load-bearing
- **Invariants:** (1) if_approved must contain ≥1 dollar amount and ≥1 risk metric. (2) if_rejected must reference current position + drawdown probability. (3) historical_precedent must have ≥1 analogue with outcome. (4) what_would_change_mind must contain ≥1 numeric threshold. (5) Failures produce actionable re-prompt messages (not "section missing").
- **Dependencies:** None
- **3 sentences:** Validates that the 4 previously-placeholder brief sections contain spec-required data rather than generic text. Produces actionable re-prompt messages for failures. Catches the gap where LLM could produce "N/A" without signal.

**3B. Build BriefEnricher with fabric data injection**

- Create `src/midas/brief/enricher.py`. Takes DataFlow instance. Before LLM call: fetches current positions/weights for allocation changes, latent state + tail risk for drawdown profiles, historical decisions by latent similarity for precedents. Appends as grounding context to analyst prompt.
- **Spec:** 07 S2.3-S2.6
- **LOC:** ~250 load-bearing
- **Invariants:** (1) Position data from `positions` fabric table. (2) Risk metrics from `latent_state` fabric table. (3) Analogues from `decisions` fabric table filtered by latent similarity. (4) All injected data carries PIT discipline (as_of_date threading). (5) Data fetch failures → WARN log + graceful degradation (empty context, not crash).
- **Dependencies:** None
- **3 sentences:** Fetches real portfolio positions, latent-state risk metrics, and historical decisions from fabric to provide grounding data. The LLM receives this context and produces sections with actual dollar amounts, risk probabilities, and analogue outcomes. Gracefully degrades when fabric data unavailable.

### WIRE Todos

**W3A. Wire enricher + validator into BriefComposer pipeline**

- Modify `BriefComposer.compose()`: (1) call `BriefEnricher` before LLM call, (2) call `BriefSectionValidator` after, (3) if validation fails, re-prompt with specific missing elements (max 1 retry). Log validation failures at WARN.
- **Spec:** 07 S2.3-S2.6
- **Verification:** Compose brief with real context → if_approved has allocation numbers + cost estimates, if_rejected has drawdown probabilities, historical_precedent has analogue references, what_would_change_mind has numeric thresholds.
- **Dependencies:** 3A, 3B

**W3B. Wire retrieve_analogue into historical precedent enrichment**

- `BriefEnricher` for precedent section calls `DebateTools.retrieve_analogue(z_t)` to get top-K analogues by latent similarity, injects as context.
- **Spec:** 07 S2.5, S3.3
- **Verification:** Compose brief with populated `decisions` table → precedent section references actual decision IDs and outcomes.
- **Dependencies:** 3B

**W3C. Wire decision audit record composition per spec 07 S7**

- After each decision completes (approve/reject/debate), compose an immutable audit record to `decision_audit` fabric table containing: full brief, pool members consulted + outputs, router blending decision, compliance checks passed, user action, debate thread reference, execution result, counterfactual outcome placeholder. Existing code has pieces (provenance pointers in debate.py, audit_log in tools.py) but no single composition point.
- **Spec:** 07 S7 (audit and provenance — all 8 fields)
- **Verification:** Process a decision through orchestrator → `decision_audit` row exists with all 8 spec-required fields populated.
- **Dependencies:** W3A (brief enrichment must produce grounded brief first)

### Regression Tests

**R5. Regression: Brief sections must be data-grounded**

- File: `tests/regression/test_brief_section_grounding.py`
- Tests: if_approved contains cost estimate, if_rejected contains drawdown reference, historical_precedent contains analogue, what_would_change_mind contains numeric threshold, "N/A" fails validation, re-prompt fixes missing sections.
- **Marker:** `@pytest.mark.regression`

---

## GROUP E: Debate Multi-Turn (GAP-4)

**Current state:** `DebateAgent.debate()` runs single LLM call despite `debate_rounds` parameter. `AgentOrchestrator` instantiates `DebateAgent` without tools, so `_build_live_context()` never fires. Frontend has polished multi-turn UI (InlineVisualization, ToolActionBar, ThreadView) but backend doesn't ground debate in portfolio data.

### BUILD Todos

**4A. Build multi-turn debate execution loop**

- Rewrite `DebateAgent.debate()` to execute actual multi-turn debate. Each round: (1) steelman prompt with accumulated context, (2) red-team prompt with accumulated context + steelman output, (3) moderation prompt for concessions + confidence update. Thread history accumulates. After 10+ exchanges, generate summary to bound tokens. Final result includes all rounds.
- **Spec:** 07 S3.2, S3.5, S3.6
- **LOC:** ~300 load-bearing
- **Invariants:** (1) Each round produces distinct steelman + red-team pair. (2) Thread history accumulates and persists via `store_thread()`. (3) After 10+ exchanges, summary generated and prepended to context. (4) Resolution state is one of: updated, maintained, open, envelope_change. (5) Concession tracking cumulative across rounds.
- **Dependencies:** None
- **3 sentences:** Replaces single-shot LLM call with real multi-turn loop where steelman and red-team arguments alternate across rounds. Thread history persists and summarizes when >10 exchanges to bound token usage. Final output reflects full multi-round debate, not a single synthesis.

**4B. Build DebateSession with 10-tool dispatch**

- Create `src/midas/agents/debate_session.py`. Wraps `DebateAgent` + `DebateTools`. Each turn, LLM may request tool calls (all 10 from spec 07 S3.3: query_fabric, query_head, query_calibration, retrieve_analogue, backtest_scenario, update_decision, generate_counterfactual, surface_override_pattern, propose_alternative_allocation, recompute_with_constraint). Dispatches tools, injects results into LLM context, continues turn. Tool calls logged with audit entries.
- **Spec:** 07 S3.3 (10-tool table), S3.5
- **LOC:** ~350 load-bearing
- **Invariants:** (1) All 10 tools registered and dispatchable. (2) Tool results injected as assistant messages. (3) `update_decision` triggers "decision updated" resolution. (4) Tool calls logged at INFO with name, latency, status. (5) Failed tools → WARN + reported to LLM as errors. (6) LLM decides which tools to call (agent-reasoning rule).
- **Dependencies:** 4A
- **3 sentences:** Wraps debate agent with 10-tool dispatch layer so each turn the LLM can call query_fabric, backtest_scenario, update_decision, etc. Tool results inject back into context for genuine evidence-grounded conversation. The `update_decision` tool is the critical differentiator — it lets debate actually mutate the pending decision.

### WIRE Todos

**W4A. Wire DebateTools into AgentOrchestrator constructor**

- Modify `AgentOrchestrator.__init__()` to pass `self.tools` (DebateTools) to `DebateAgent(provider, tools=self.tools)`. Enables `_build_live_context()` to fetch live portfolio data.
- **Spec:** 07 S3.5
- **Verification:** `process_decision()` with position reference → debate result references actual position data.
- **Dependencies:** None (quick wire fix)

**W4B. Wire DebateSession into orchestrator pipeline**

- Replace direct `self.debate.debate(brief)` call in `AgentOrchestrator.process_decision()` with `DebateSession` wrapping agent + tools. Pass `decision_id` for `update_decision` targeting.
- **Spec:** 07 S3.3, S3.5
- **Verification:** Full orchestrator pipeline → debate stage executes multiple turns with tool calls in logs, `update_decision` invocable.
- **Dependencies:** 4A, 4B

**W4C. Wire thread persistence to fabric**

- Replace in-memory `self._thread_store` dict with fabric-backed persistence. `store_thread()` writes to `debate_threads` fabric table. `retrieve_thread()` reads from fabric. Fallback to in-memory when fabric unavailable (test mode).
- **Spec:** 07 S3.6
- **Verification:** Store thread with 5 messages → new `DebateAgent` instance → retrieve thread → all 5 messages present with correct role/content/timestamp.
- **Dependencies:** 4A

### Regression Tests

**R6. Regression: Multi-turn debate produces multiple rounds**

- File: `tests/regression/test_debate_multi_turn.py`
- Tests: debate produces multiple rounds, live context injected when tools present, thread persistence across sessions, resolution state valid (4 spec values), concession count accumulates, summary generated after 10 exchanges, orchestrator passes tools, update_decision triggers "updated" resolution.
- **Marker:** `@pytest.mark.regression`

---

## GROUP F: ModelRegistry Fix (GAP-6)

**Current state:** `promote()` (ml/**init**.py:106-121) demotes existing champions but never writes "champion" on target. `retire()` (ml/**init**.py:123-132) checks existence but never updates status. Classic orphan pattern.

### BUILD Todos

**6A. Fix promote() to actually promote target model**

- Modify `promote()`: (1) demote existing champions to "challenger", (2) promote target to "champion" via `db.express.update()`, (3) write audit log with previous/new champion metadata, (4) return updated record.
- **Spec:** 05 (champion/challenger lifecycle)
- **LOC:** ~80 load-bearing
- **Invariants:** (1) After promote(), exactly 1 champion per family. (2) Previous champion demoted before new promoted. (3) Promotion audited with previous/new metadata. (4) Target not found → typed error, not silent True.
- **Dependencies:** None

**6B. Fix retire() to actually retire target model**

- Modify `retire()`: (1) update status to "retired", (2) if retired was champion → trigger re-promotion of best challenger, (3) write audit log, (4) return updated record. Prevent retiring last active model in pool.
- **Spec:** 05 (model lifecycle)
- **LOC:** ~120 load-bearing
- **Invariants:** (1) Target status becomes "retired". (2) Champion retirement triggers auto re-promotion. (3) Retiring last model in pool → typed error. (4) Retirement audited.
- **Dependencies:** 6A (re-promotion uses promote())

### WIRE Todos

**W6A. Wire promotion/retirement events to audit_log**

- After each promote/retire, write structured audit entry to `audit_log` fabric table: agent_id, action ("model_promoted"/"model_retired"), target family/version, previous/new champion, timestamp.
- **Spec:** 05, 07 S7
- **Verification:** Promote model → audit_log row with action="model_promoted" + correct metadata.

**W6B. Wire ModelRegistry to meta-router for live pool updates**

- After promote/retire, notify meta-router that pool composition changed so next inference uses updated champion/challenger set. Simple invalidation flag or event.
- **Spec:** 05 (three-loop adaptation)
- **Verification:** Promote model → next `list_by_pool()` returns updated champion.

### Regression Tests

**R7. Regression: ModelRegistry lifecycle**

- File: `tests/regression/test_model_registry_lifecycle.py`
- Tests: promote sets champion, promote demotes previous, exactly 1 champion per family, retire sets retired, retire champion triggers re-promotion, retire last model raises error, promote nonexistent raises error, audit log on promotion, audit log on retirement.
- **Marker:** `@pytest.mark.regression`

---

## Execution Order

All three groups (D, E, F) are independent — can run in parallel across 3 agents:

- Agent 1: GROUP D (3A → 3B → W3A → W3B → R5) — ~1 session
- Agent 2: GROUP E (W4A, 4A → 4B → W4B → W4C → R6) — ~1 session
- Agent 3: GROUP F (6A → 6B → W6A → W6B → R7) — ~0.5 session (smallest group)

Group F is small enough to pair with review/red-team work in the same session.
