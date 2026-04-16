---
type: DISCOVERY
date: 2026-04-16
---

# Red Team Findings — Security and Quality Issues

## Summary

Three rounds of red team validation on the zai branch (commits 04b1125, bbc6668, f031cf4, ee8fe28) surfaced and resolved findings across security, code quality, and financial safety.

## Findings Resolved

### CRITICAL (resolved in Round 1)

1. **Kill switch spoofable** — `clear_kill_switch` accepted `{"user_approved": true}` body boolean with no verification. Fixed: now requires `confirmation_code` + `user_approved`.
2. **IBKR credential leak** — Two `AdapterError` constructions included `response.text[:200]` which could contain OAuth tokens. Fixed: removed response body from error messages.
3. **Health endpoint fake** — Always returned `{"status": "healthy"}` without checking anything. Fixed: now checks DATABASE_URL, IBKR_CLIENT_ID, and data source API keys.

### HIGH (resolved in Rounds 1-3)

4. **No API authentication** — All endpoints were publicly accessible. Fixed: added Bearer/ApiKey middleware with env-configurable MIDAS_API_KEY.
5. **Debate agent fabricated text on parse failure** — JSON parse failure returned fake steel_man/red_team text. Fixed: returns `parse_failed` with `parse_error: true` flag.
6. **query_head placeholder** — Returned `"computed_from_z_t"` string as prediction. Fixed: lazy import of `midas.heads.prediction.predict_from_latent`.
7. **backtest_scenario fake metrics** — Returned all zeros for sharpe, drawdown, volatility. Fixed: computes real returns from price data.
8. **NaN/Inf not guarded** — Brinson decomposition and NAV computation could return NaN without warning. Fixed: `math.isfinite()` checks with warning logs.
9. **Division by near-zero** — IBKR spread calculation used `if mid` instead of `if mid > 1e-10`. Fixed: threshold guard.
10. **Silent exceptions in universe modules** — Changelog writes and membership fetches swallowed all exceptions. Fixed: added logger calls.

## Remaining LOW Items (acceptable)

- `autonomy/ladder.py:283` — JSON parse of optional evidence field, `pass` acceptable
- `fabric/adapters/base.py:189` — Rate limit timing, `pass` acceptable
- `testing/fixtures.py` (3 sites) — Cleanup paths, `pass` acceptable per Rule 3 exception
- `fabric/engine.py:542,549` — Module-level cleanup, `pass` acceptable
