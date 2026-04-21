# M01 — Data Fabric

**Spec anchors:** 03 (universe-and-data).
**Framework:** DataFlow (primary), Kailash Core SDK (workflow orchestration).
**Depends on:** M00 (T-00-01 point-in-time protocol).

---

## T-01-01 — DataFlow schema for fabric tables

**Objective:** create the DataFlow models for every fabric table in `specs/03-universe-and-data.md §3.3`: `prices`, `corporate_actions`, `fundamentals`, `filings`, `news`, `macro`, `alt_data`, `features`, `embeddings`, `latent_state`, `positions`, `orders`, `decisions`, `shadow_decisions`, `model_registry`, `universe_changelog`, `audit_log`.
**Invariants:** all time-varying tables carry `(period_end, filed_at, restated_at, source_vintage)` per T-00-01; tenant isolation primitives present even though v1 is single-user (multi-tenant-ready); every write is verifiable with a read-back.
**Acceptance:** DataFlow models generate, migrations apply cleanly, `db.express.read` returns rows with the PIT tuple.
**Depends on:** T-00-01.

## T-01-02 — Adapter for EODHD (prices + fundamentals + news)

**Objective:** single adapter module that is the only code path with outbound EODHD calls; writes to fabric tables; handles pagination, retries, rate limits.
**Invariants:** no caller of this adapter ever sees a raw response — always a fabric row; failures write a health-check entry, not an exception to the caller.
**Acceptance:** Tier 2 test hits EODHD sandbox, writes rows, verifies read-back.

## T-01-03 — Adapter for Yahoo Finance (fallback)

**Objective:** adapter with the same interface as EODHD; cross-check mode that flags discrepancies vs EODHD into `audit_log`.
**Acceptance:** Tier 2 test triggers EODHD failure and confirms Yahoo fallback.

## T-01-04 — Adapter for IBKR Web API v1.0

**Objective:** adapter for account state, positions, order status, and real-time quotes. OAuth 2.0 handshake.
**Invariants:** every call is audited; rate-limit aware with priority queue (trades > monitoring > data per Phase 01 A-H4); fresh-price path bypasses cache.
**Acceptance:** Tier 2 against IBKR paper; positions read-back matches.
**Depends on:** M13 (credentials).

## T-01-05 — Adapter for IBKR TWS fallback

**Objective:** fallback adapter via `ib_async` for when Web API is unavailable.
**Acceptance:** Tier 2 confirms identical behavior shape between both adapters.

## T-01-06 — Adapter for FRED (macro)

**Objective:** ingest series with ALFRED-style vintage tracking per T-00-01.
**Acceptance:** ingest CPI at two vintages and confirm the fabric stores both.

## T-01-07 — Adapter for Perplexity (news/research)

**Objective:** on-demand adapter for debate-agent context and research queries; write results to `news` + `embeddings`.
**Acceptance:** Tier 2 returns portfolio-tagged news.

## T-01-08 — Adapter for SEC EDGAR (filings)

**Objective:** ingest 10-K / 10-Q / 8-K filings with `filed_at` and document IDs; stage for embedding pipeline.
**Acceptance:** Tier 2 ingests a recent 10-K and indexes it.

## T-01-09 — Adapter for OECD CLI + IMF WEO + Google Trends + Truflation

**Objective:** four lightweight adapters for alt-macro sources; same contract as FRED.
**Acceptance:** Tier 2 ingests a sample series from each.

## T-01-10 — Redis hot cache layer

**Objective:** Redis-backed cache for latest prices, `z_t` state, session data; TTLs per `specs/03- §3.4` (1-min active, 15-min inactive).
**Invariants:** execution-time price pull bypasses cache (T-00-01 + A-H2); stale-data gate uses cache timestamp.
**Acceptance:** Tier 2 asserts cache and bypass both work.

## T-01-11 — Stale-data gate (compliance rule input)

**Objective:** computes freshness per feature and emits a stale-data flag consumed by the Pre-Trade Compliance Agent (M12).
**Acceptance:** Tier 2 asserts gate trips when a fabric row exceeds threshold.

## T-01-12 — Feature store layer (versioned features)

**Objective:** versioned feature computation with PIT discipline; features tagged `feature_v{N}`.
**Invariants:** no feature reads data whose `filed_at > as_of`; version bumps never overwrite prior versions while a model references them.
**Acceptance:** Tier 2 asserts a backtest using `feature_v1` and a live decision using `feature_v2` produce different outputs when expected.

## T-01-13 — pgvector embedding store

**Objective:** pgvector-backed index over news/filings/research embeddings; supports the Research Assistant RAG.
**Acceptance:** Tier 2 queries return top-K by cosine similarity with expected results.

## T-01-14 — Data source dependency health check

**Objective:** health-check job per adapter; surfaces status to the Pulse surface and to compliance.
**Acceptance:** health endpoint returns status per source.

## T-01-15 — Adapter for Universe membership (S&P 1500 as-of date)

**Objective:** PIT S&P 500/400/600 constituents; source: S&P (or FTSE alternative); feeds universe construction in M02.
**Invariants:** membership queried by `as_of_date` always.
**Acceptance:** Tier 2 asserts membership as of 2020-03-01 is not the same as 2024-03-01.

---

**Gate out:** M01 is complete when every adapter passes its Tier 2 test against real infrastructure, all fabric tables have verified PIT discipline, and the health check reports all sources green in a 24-hour soak.
