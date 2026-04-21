# RISK: SQLite Threading Causes 500 on Approve/Decline in Test Environment

**Date:** 2026-04-19
**Type:** RISK
**Slug:** sqlite-threading-approve-decline-tests

## Finding

The `approve` and `decline` decision endpoints return HTTP 500 (Internal Server Error) when the decision ID is not found, instead of the expected 404. This is caused by a pre-existing SQLite threading issue in the DataFlow singleton.

**Stack trace:**

```
decision.approve.failed - Exception: RuntimeError('SQLite objects created in a thread can only be used in that same thread')
```

**Root cause:** `get_fabric()` returns the production singleton when `test_mode=False`, but tests call `create_app()` without `test_mode=True`. The singleton's SQLite connection is created in the test client's thread but accessed from the request handler thread.

**Scope:** Affects `Tests/test_api.py::TestDecisionsEndpoint::test_approve_returns_404_when_not_found` and `test_decline_returns_404_when_not_found`.

**Disposition:** Pre-existing, not introduced by zai branch changes. Requires proper test fixture with `test_mode=True` or mock `get_fabric()` in test setup.

## Why This Matters

The endpoints work correctly in production (PostgreSQL) but fail silently in tests, masking real bugs. The 500 instead of 404 means error handling in the request path is bypassed.

## How to Fix

1. Make the test fixture pass `test_mode=True` to the app, or
2. Mock `get_fabric` in the test conftest, or
3. Use the test singleton pattern from `fabric/engine.py`
