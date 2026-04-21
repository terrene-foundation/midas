# M09 — Frontier LLM Agents (Analyst, Debate, Research)

**Spec anchors:** 07, FP-12.
**Framework:** Kaizen (multi-agent + signatures + tools + A2A), Kailash MCP (tool exposure).
**Depends on:** M01-M08, M12 (compliance).

## T-09-01 — Frontier-LLM provider abstraction

**Objective:** Kaizen-backed provider abstraction wiring to frontier models (Opus-class, GPT-5-class) with automatic fallback between frontier tiers when primary is unavailable.
**Invariants:** no cost-saving substitution to non-frontier for decision-adjacent work; fallback escalates, never degrades silently.
**Acceptance:** Tier 2 demonstrates seamless failover between two frontier providers.

## T-09-02 — Analyst agent (brief composer)

**Objective:** Kaizen signature-based agent that consumes decision context + evidence store and produces the structured brief per `specs/07- §2`.
**Invariants:** every claim carries provenance; sections 1-7 mandatory; "what would change my mind" non-optional; section 2.7 confidence is a distribution.
**Acceptance:** T-00-08 usability gate passes on a synthetic decision set.

## T-09-03 — Debate agent (argument + tool use)

**Objective:** Kaizen A2A agent with steelman/red-team sub-role split per T-00-10; accesses the full evidence store + tool suite.
**Invariants:** `update_decision` tool invocation requires preceding new-evidence tool call; sycophancy counter audited; disagreement-floor metric monitored.
**Acceptance:** Tier 2 sycophantic-user simulation confirms concession rate stays in bounds.

## T-09-04 — Debate tools suite

**Objective:** the 10 tools in `specs/07- §3.3` as Kailash MCP tools:

- `query_fabric`, `query_head`, `query_calibration`, `retrieve_analogue`, `propose_alternative_allocation`, `recompute_with_constraint`, `backtest_scenario`, `update_decision`, `generate_counterfactual`, `surface_override_pattern`.
  **Invariants:** MCP governance (PACT-backed) applies — default-deny tool policy, audit every call; `update_decision` re-enters the compliance layer.
  **Acceptance:** each tool has a Tier 2 test.

## T-09-05 — Research Assistant agent (RAG)

**Objective:** Kaizen + Kailash MCP agent over the `embeddings` pgvector store; retrieves filings, news, academic papers, broker notes.
**Acceptance:** test queries return relevant documents with citations.

## T-09-06 — RAG corpus ingestion pipeline

**Objective:** batch pipeline for filings (SEC), academic papers (arXiv q-fin curated), broker notes (manual drop), user research (personal store).
**Depends on:** M01 (EDGAR adapter).

## T-09-07 — Multi-provider embedding pool (T-05-17 completion)

**Objective:** multiple text encoders in parallel; router picks per query/document type.
**Acceptance:** registry contains at least 3 embedding candidates with calibration.

## T-09-08 — Latent-to-factor-language projection service

**Objective:** frontier LLM call that consumes `z_t` evidence + factor overlay and produces human-readable explanation for the brief.
**Invariants:** honesty banner appears when projection is weak.
**Acceptance:** Tier 2 confirms banner fires on synthetic weak-projection inputs.

## T-09-09 — Agent runtime orchestrator

**Objective:** Nexus-exposed orchestrator for Analyst, Debate, Research agents; routing via Kaizen.
**Depends on:** M17 (Nexus backbone).

## T-09-10 — Debate thread persistence

**Objective:** threads persist with full context; resumable across sessions; linked to decisions.
**Acceptance:** close and resume a thread; full context returns.

**Gate out:** three agents running, 10 tools Tier-2-tested, frontier failover works, debate thread persistence end-to-end.
