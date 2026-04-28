# 0027-HIGH-ibkr-order-filter-isolation

**Severity:** HIGH
**Status:** Open
**Date:** 2026-04-26
**Component:** `midas.fabric.adapters.ibkr`, `dataflow.express`

## Finding

Orders written to the `orders` table via `IBKRAdapter.fetch_order_status()` are persisted to SQLite (confirmed via raw SQL). However, subsequent calls to `db.express.list("orders", filter={"broker_order_id": "ORD001"})` return 0 rows for those orders.

Orders written directly via `db.express.create("orders", row)` followed by `db.express.list("orders", filter={"broker_order_id": "ORD001"})` work correctly and return 1 row.

All orders appear in unfiltered `db.express.list("orders", filter={})` queries regardless of write path.

## Impact

- `test_fetch_order_status_uses_order_state_enum` fails at the assertion verifying DB persistence
- Integration tests that rely on filtered reads after adapter writes will give false negatives
- The data IS in the DB; the bug is in the read path after these specific writes

## Root Cause Hypothesis

The IBKR adapter's `fetch_order_status` method calls `self._get_db()` to obtain the DataFlow instance, then writes via `db.express.create()`. The write succeeds and commits. However, the same `db` instance used for the subsequent filtered `express.list` call may be using a different underlying connection/transaction context than the one that served the write.

Evidence:

- Raw SQL via `sqlite3.connect(db_path)` shows the rows are actually in the DB
- Direct create + filtered list in the same async context works
- The bug only manifests after writes through `fetch_order_status`

Likely cause: The `IBKRAdapter._get_db()` or the DataFlow's connection pool is creating a new connection for the filtered read that doesn't see the uncommitted (or incorrectly committed) data from the adapter's connection.

Alternative: The `filter={"broker_order_id": "ORD001"}` dict is being handled differently depending on which execution path wrote the data — possibly a field-name/column-map mismatch that only surfaces after certain writes.

## Reproduction

```python
# This works:
await db.express.create("orders", row)
rows = await db.express.list("orders", filter={"broker_order_id": "ORD001"})  # returns 1

# This fails (data IS in DB per raw SQL):
adapter = IBKRAdapter(db=db)
adapter._enqueue = mock_enqueue  # returns synthetic_orders
await adapter.fetch_order_status("ACC123")
rows = await db.express.list("orders", filter={"broker_order_id": "ORD001"})  # returns 0
all_rows = await db.express.list("orders", filter={})  # returns the order
```

## Required Fix

1. Investigate whether `fetch_order_status` uses a different DB connection than the caller's `started_db` fixture
2. Check if the `orders` table `broker_order_id` column has any index or constraint that could cause filtered reads to miss rows written by the adapter
3. Verify transaction isolation: ensure the write in `fetch_order_status` is committed before the read in the test proceeds
4. Check whether `_get_db()` in the adapter returns the same singleton as the test fixture's `started_db`

## Files Affected

- `src/midas/fabric/adapters/ibkr.py` — `fetch_order_status` write path
- `src/midas/fabric/adapters/base.py` — `_get_db()` lazy initialization
- `tests/integration/test_ibkr_order_states.py` — blocked test at line 334
