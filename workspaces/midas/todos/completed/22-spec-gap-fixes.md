# Spec Gap Fixes — Round 4 Implementation

Source: spec-to-code gap analysis (2026-04-17)
Status: COMPLETE (2026-04-20)

## Group A: High — Spec Compliance Gaps

### A1. Wire API routes to fabric (specs 09, 07)

Remove hardcoded returns from `api/routes.py`. PulseRouter reads regime state from fabric. DecisionsRouter reads/writes decisions. PortfolioRouter reads positions/allocation from fabric. BacktestRouter delegates to shadow lane. SignalRouter reads z_t posterior.

- Implements: specs/09-surfaces-and-attention.md, specs/07-evidence-first-decision.md
- Invariants: fabric query, PIT discipline, no mock data

### A2. Compliance rules stored in DB table (spec 11 §S3)

Add `compliance_rules` DataFlow model. RulesEngine loads rules from DB at startup, falls back to code factory. Admin API endpoint to add/modify rules without release.

- Implements: specs/11-compliance-and-risk.md §S3 "Rules are data, not code"
- Invariants: default-deny, append-only audit, typed errors

### A3. Performance metrics as distributions (spec 12 §S1)

Replace point-estimate RiskMetrics methods with bootstrap resampling. Each metric returns (point, ci_lower, ci_upper). Sharpe, Sortino, Calmar, max_drawdown, IR, alpha, M-squared, Treynor.

- Implements: specs/12-performance-and-track-record.md §S1
- Invariants: bootstrap n>=1000, seed=42, ci at 95%

### A4. L3/L4 promotion requires 12-month window + bootstrap CI (spec 08 §S4)

AutonomyLadder.evaluate_upgrade_contract must compute 12-month track record score with bootstrap CI. Reject if CI lower bound < floor. 3-month is context signal only.

- Implements: specs/08-autonomy-and-trust.md §S4
- Invariants: 12-month lookback, bootstrap CI, floor parameter

### A5. Debate tools wired to real services (spec 07 §S3.5)

Replace stub implementations in `agents/tools.py`. propose_alternative_allocation calls allocation head. recompute_with_constraint calls optimizer. backtest_scenario calls shadow lane. generate_counterfactual calls counterfactual engine.

- Implements: specs/07-evidence-first-decision.md §S3.5
- Invariants: write to pending decisions, audit trail

## Group B: Medium — Stub Replacement

### B1. Fix research agent similarity placeholder

Replace `row["similarity"] = 0.5` with actual cosine similarity using EmbeddingStore.

- File: `agents/research.py:172`

### B2. Fix counterfactual engine to use price paths

Replace outcome_json field reads with actual fabric price queries for 1d/5d/21d horizons.

- File: `attribution/counterfactual.py`

### B3. Fix NAV cash/unsettled stubs

Add cash tracking fields to NAV computation. Remove hardcoded 0 values.

- File: `attribution/nav.py`

### B4. Fix paper trading subsystem evaluation

`_evaluate_subsystem` must check actual subsystem health (fabric connectivity, model pool status, compliance engine status, IBKR health) instead of always returning "pass".

- File: `paper_trading/report.py`

### B5. Fix shadow PNL placeholder

Replace `+/- confidence * 0.01` heuristic with actual price-based PNL computation using fabric price reads.

- File: `shadow/shadow_lane.py`

### B6. Fix SP1500 filter placeholder

Replace price=0, volume=0 placeholders with fabric queries for actual market data.

- File: `universe/filters.py`

### B7. Fix ModelRegistry demotion loop

Replace `pass` in promote() demotion loop with actual demotion logic (demote old champion to challenger).

- File: `ml/__init__.py:114`

### B8. Remove dataflow_adapter TODO

Implement lookback window parameter in DataFlowFabricReader.read_price.

- File: `fabric/adapters/dataflow_adapter.py:56`

## Group C: Low — Structural Debt

### C1. Deduplicate OODDetector, PosteriorMaintenanceService, DeepBayesianFilter

Consolidate duplicate implementations across ml/ and state_inference/. Keep ml/ as canonical, re-export from state_inference/.

- Files: ml/ood_detector.py, state_inference/ood_detector.py, ml/posterior_state.py, state_inference/posterior_service.py, ml/deep_bayesian_filter.py, state_inference/bayesian_filter.py

### C2. Remove empty scaffolded directories

Remove core/, models/, ux/, agents/debate/ if they serve no purpose.

### C3. Remove no-op GoogleTrendsAdapter

Either implement or remove. Current state (0 rows) violates zero-tolerance.

- File: `fabric/adapters/alt_macro.py`
