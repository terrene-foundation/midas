# 0013-RISK — Spec Compliance Gaps From Full Red Team Audit

**Date:** 2026-04-16
**Phase:** 04 Red Team (full spec audit)
**Status:** 10 of 12 HIGH findings fixed, 2 deferred to milestone implementation

## Findings

### Fixed (10)

1. **06/S2 — a_t missing 2 inputs**: RegimeRenderer used 4 weights; spec requires 6. Added model_disagreement (0.10) and drawdown_velocity (0.05), rebalanced to sum=1.0.

2. **07/S2.3-2.5 — Missing brief sections**: AnalystAgent brief lacked "If Approved", "If Rejected", and "Historical Precedent" sections. Added all three to prompt schema and fallback.

3. **07/S3.5 — No debate resolution states**: DebateAgent returned raw JSON without tracking resolution. Added `resolution_state` field (updated/maintained/open/envelope_change).

4. **07/S3.6 — No thread persistence**: Debate threads were stateless. Added `_thread_store` with store/retrieve/list methods.

5. **10/S4.3 — Missing non-sycophancy directive**: DebateAgent prompt lacked explicit "disagree when evidence warrants" instruction. Added to DEBATE_SYSTEM_PROMPT.

6. **11/S3.3 — Warning rule IDs mismatch**: 4 of 5 warning rule IDs differed from spec. Replaced with spec-required IDs: turnover_high, fee_intensity, user_override_pattern, fx_exposure.

7. **14/S12 — 5 compliance rules missing**: Added api.ibkr_rate_limit, api.ibkr_session_invalid, exec.quote_moved_since_brief (blocking) and warn.halted, warn.auction_window (warning).

8. **14/S7 — No rejection taxonomy**: Created execution/rejection_codes.py with 6 categories (INSUFFICIENT_MARGIN, ORDER_LIMIT_EXCEEDED, MARKET_DATA_MISSING, INSTRUMENT_HALTED, INVALID_ORDER, UNKNOWN).

9. **12/S2 — M-squared and Treynor missing**: Added m_squared() and treynor_ratio() static methods to RiskMetrics.

10. **12/S6.1 — TrackRecordScorer weights mismatch**: Replaced sharpe/sortino/drawdown/win_rate/avg_return with spec-required 8 components (brinson_allocation, brinson_selection, calmar, calibration_quality, override_convergence, degradation_events, turnover_cost_drag, worst_case_window).

### Deferred to Milestone Implementation (2)

1. **Spec 13 cost model**: Full transaction cost decomposition (spread/impact/commission/tax/slippage/gap), PLAF, child order scheduler, liquidity tiering. Spec written (T-00-12 marked SPEC-LEVEL DONE); implementation distributed to M05/M12/M15/M16/M19.

2. **Spec 03 UCITS evaluation**: Ireland-domiciled UCITS alternative comparison. Marked v1.1 in spec.

### MEDIUM (behavioral gaps in autonomy, not blocking)

- First-seven-days L1 enforcement in autonomy module (currently escalation-only)
- Envelope widening guard not wired into EnvelopeStore
- Missing 5 of 8 demotion triggers (stale_data, crisis_band, ood, calibration_drift, kill_switch)
- Paper-to-live report acknowledgment not verified
