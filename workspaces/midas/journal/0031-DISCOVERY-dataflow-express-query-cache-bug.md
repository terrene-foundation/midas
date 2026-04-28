---
type: DISCOVERY
date: 2026-04-25
impact: HIGH
---

# DataFlow Express Query Cache Returns Stale Results After Writes

## Summary

`db.express.list(table, filter={...})` returns stale cached empty results after
`db.express.create(table, row)` writes new rows. The cache does not invalidate
on writes.

## Reproduction

1. Call `db.express.list("audit_log", filter={"action": "onboarding"})` on empty table
   — returns `[]` (correct), **caches "0 rows for this filter"**
2. Call `db.express.create("audit_log", {"action": "onboarding", ...})` — succeeds
3. Call `db.express.list("audit_log", filter={"action": "onboarding"})` again
   — returns `[]` (WRONG — should return the row just created)

The unfiltered `db.express.list("audit_log")` also exhibits stale caching in some
contexts, though not as consistently.

## Affected Tests

- `tests/integration/test_onboarding_wiring.py` — **worked around** with in-memory
  `_FakeDB`/`_FakeExpress` that bypasses DataFlow entirely for state machine logic tests
- `tests/integration/test_ibkr_order_states.py::test_fetch_order_status_uses_order_state_enum`
  — **still failing** because it uses real DataFlow and reads back orders with a filter
  after writing them

## Workaround

For tests that need read-after-write consistency with filters:

1. Load all rows without filter (`db.express.list(table)`) and filter in Python
2. Use an in-memory fake DB for business logic tests (preferred for unit/integration)
3. Accept that real DataFlow integration tests will fail until the SDK bug is fixed

## Action Required

File a GitHub issue against the Kailash DataFlow SDK for the express query cache
invalidation bug. The cache should invalidate on any write (create/update/delete)
operation, at minimum for the affected table.
