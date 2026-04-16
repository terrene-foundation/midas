# Code Quality Review -- src/midas/

**Branch:** zai
**Date:** 2026-04-16
**Reviewer:** quality-reviewer agent
**Scope:** All Python source under `src/midas/` (~21,000 LOC across 90+ files)

---

## Review Report

### Summary

- Overall Status: **Issues Found**
- Total findings: 19 (4 Critical, 8 Important, 7 Minor)
- Wildcard imports: 0 (clean)
- Unstructured f-string logs: 0 (clean)
- Print statements in production: 0 (clean)

---

### Critical Issues (Must Fix)

#### C-1. TODO markers in production code (ZERO-TOLERANCE Rule 2)

**Location:** `src/midas/fabric/adapters/dataflow_adapter.py:56`
**Location:** `src/midas/evaluation/probes/latent_learnability.py:189`
**Location:** `src/midas/evaluation/probes/latent_learnability.py:267`

Three `TODO` comments exist in production code. Per zero-tolerance Rule 2, TODO/FIXME/HACK/STUB/XXX markers are BLOCKED.

- Line 56: `lookback_days: int = 30,  # TODO (T-00-01): implement lookback window` -- The `lookback_days` parameter is accepted but ignored. The method reads only a single as_of_date worth of data.
- Line 189: `# TODO (T-00-02): wire fabric price read -- placeholder returns NaN` -- The `_realised_return_for_state` method always returns NaN, making the learnability probe non-functional without the `realized_returns_override` parameter.
- Line 267: `# TODO (T-00-01): wire fabric price read once adapters are live` -- Same placeholder method.

**Fix:** Remove TODO comments. Either implement the lookback window or raise NotImplementedError with a clear message. For the learnability probe placeholder, convert to a proper stub that raises a typed error when called without the override, or wire the fabric price read.

#### C-2. Fake data in backtest_scenario tool (ZERO-TOLERANCE Rule 2)

**Location:** `src/midas/agents/tools.py:287-298`

```python
return {
    "weights": weights,
    "period": period,
    "total_return": 0.0,
    "annualized_return": 0.0,
    "max_drawdown": 0.0,
    "sharpe_ratio": 0.0,
    "volatility": 0.0,
    "status": "computed",
}
```

The `backtest_scenario` method fetches price data from the database but discards it entirely, returning hardcoded zero values with `"status": "computed"`. This is fake data presented as real computation. The LLM debate agent receives this and reasons on zero-return assumptions.

**Fix:** Either implement the actual backtest computation using the fetched price data, or return a status of `"status": "no_price_data"` when data is unavailable, and do not fabricate metrics. At minimum, change the status to reflect the data was not computed.

#### C-3. Silent `except Exception: pass` in alt_macro adapters (ZERO-TOLERANCE Rule 3)

**Location:** `src/midas/fabric/adapters/alt_macro.py:113-114` (OECDAdapter)
**Location:** `src/midas/fabric/adapters/alt_macro.py:222-223` (IMFAdapter)
**Location:** `src/midas/fabric/adapters/alt_macro.py:373-374` (TruflationAdapter)

All three alt-macro adapters silently swallow exceptions when writing individual rows to the fabric:

```python
try:
    await db.express.create("macro", row)
    created_rows.append(row)
except Exception:
    pass
```

Per zero-tolerance Rule 3, `except Exception: pass` without logging is BLOCKED. Individual row write failures are silently dropped with zero observability.

**Fix:** Add a `logger.warning(...)` call inside each except block with the series name, date, and error, following the pattern used in the EODHD, FRED, and Yahoo adapters (which already do this correctly).

#### C-4. Silent `except Exception: pass` in universe adapter (ZERO-TOLERANCE Rule 3)

**Location:** `src/midas/fabric/adapters/universe.py:256-257`

The `fetch_constituents` method silently swallows exceptions when writing individual constituent records to the changelog:

```python
try:
    await db.express.create("universe_changelog", ...)
except Exception:
    pass
```

This can silently lose the entire universe membership record without any signal.

**Fix:** Add `logger.warning("fetch_constituents.row_write_failed", ...)` inside the except block.

---

### Important Improvements

#### I-1. ModelRegistry.promote is a no-op

**Location:** `src/midas/ml/__init__.py:102-113`

The `promote` method queries for existing champions, iterates with a `pass` body, and returns True without performing any promotion:

```python
async def promote(self, model_family: str, model_version: str) -> bool:
    try:
        rows = await self._db.express.list(...)
        for row in rows:
            pass  # <-- no-op body
        return True
    except Exception:
        return False
```

The docstring says "Demote existing champion -- in v1 we just register a new version." The method should either implement the promotion (update old champion to non-champion, set new one to champion) or raise a clear error stating the feature is not yet implemented.

**Fix:** Implement the promotion logic: update existing champion's `promotion_status` from "champion" to "retired", then update the target model's `promotion_status` to "champion".

#### I-2. ModelRegistry.retire is a no-op

**Location:** `src/midas/ml/__init__.py:115-123`

The `retire` method queries for the model but only returns whether it exists, without actually retiring it:

```python
async def retire(self, model_family: str, model_version: str) -> bool:
    try:
        rows = await self._db.express.list(...)
        return len(rows) > 0  # <-- does not retire anything
    except Exception:
        return False
```

**Fix:** Update the matching row's `promotion_status` to "retired" and return the result.

#### I-3. Silent exception swallows in ml/**init**.py (ZERO-TOLERANCE Rule 3)

**Location:** `src/midas/ml/__init__.py:73-74, 80-81, 90-91, 99-100, 112-113, 122-123, 130-131`

Seven `except Exception:` blocks in `ModelRegistry` all silently return empty values (None, [], False) without logging. These are not pass-statements but they achieve the same effect: failures are invisible.

```python
except Exception:
    return None  # no logging
```

**Fix:** Add `logger.error("registry.<method>_failed", ...)` to each except block, following the pattern in `ModelRegistry.register` which already does this correctly on line 62.

#### I-4. Silent exception swallows in credentials.py

**Location:** `src/midas/fabric/credentials.py:95-96` (list_services)
**Location:** `src/midas/fabric/credentials.py:111-112` (is_expired)

Both methods catch `Exception` and return without logging. The `list_services` method returns an empty list, and `is_expired` returns `True` (claiming the credential is expired when the real issue is a query failure). These silent swallows hide infrastructure failures.

**Fix:** Add `logger.warning("credential.<method>_failed", ...)` to each except block.

#### I-5. Silent exception swallows in universe/changelog.py and attribution/nav.py

**Location:** `src/midas/universe/changelog.py:50-51` (get_changelog)
**Location:** `src/midas/attribution/nav.py:34-35` (compute_nav)

Both catch `Exception` and return empty data without logging. NAV computation silently returns 0 when the database is unreachable.

**Fix:** Add logging at WARNING level.

#### I-6. Debate agent JSON parse failure produces fake fallback data

**Location:** `src/midas/agents/debate.py:97-107`

When the LLM returns non-parseable JSON, the debate agent fabricates a fallback result with `"concession_count": 0` and `"final_confidence"` copied from the brief. This is presented as if the debate actually ran, but the steel_man and red_team are just "Parsing failed." strings.

```python
except json.JSONDecodeError:
    logger.warning("debate.result.parse_failed", ...)
    parsed = {
        "recommendation": result["content"],
        "steel_man": "Parsing failed.",
        ...
    }
```

**Fix:** The fallback should clearly mark the result as `"status": "parse_failed"` so the orchestrator can decide whether to retry or escalate, rather than treating fabricated defaults as a real debate outcome.

#### I-7. query_head tool returns placeholder prediction string

**Location:** `src/midas/agents/tools.py:87`

```python
"prediction": "computed_from_z_t",
```

When a model is found, the tool returns the literal string `"computed_from_z_t"` as the prediction value rather than an actual computed prediction. The LLM receives this and must interpret a placeholder string.

**Fix:** Either compute the actual prediction from z_t using the model's calibration, or return `None` with a clear status indicating the prediction requires actual inference.

#### I-8. IBKR adapter \_drain_queue discards exceptions from priority queue items

**Location:** `src/midas/fabric/adapters/ibkr.py:218-225`

The `_drain_queue` method catches exceptions from enqueued operations and stores them in `result` but the caller in `_enqueue` never checks the result -- it just waits on the event. This means adapter errors (auth failures, rate limits) are silently swallowed and the caller gets no error signal.

```python
try:
    result = await fn(*args, **kwargs)
    event.set()
except Exception as exc:
    result = exc
    event.set()  # caller wakes but has no way to see the exception
```

**Fix:** Store the exception in a shared container (e.g., a `Future`) that `_enqueue` can re-raise after `event.wait()`.

---

### Minor Issues

#### M-1. Hardcoded model name in Perplexity adapter

**Location:** `src/midas/fabric/adapters/perplexity.py:139`

```python
"model": "sonar",
```

The model name "sonar" is hardcoded. Per `rules/env-models.md`, model names should come from environment variables.

**Severity rationale:** This is a third-party API model name (not an LLM inference model per the env-models rule), and the Perplexity API does not support the same model routing pattern. Low priority.

#### M-2. Testing fixture uses bare assert

**Location:** `src/midas/testing/fixtures.py:71`

```python
assert self.db is not None, "Call setup() first"
```

While not production code, using `assert` for control flow in fixtures means the check is disabled when Python runs with `-O` (optimized mode). Prefer raising a typed exception.

#### M-3. engine.py uses stdlib logging instead of structlog

**Location:** `src/midas/fabric/engine.py:27`

```python
logger = logging.getLogger(__name__)
```

While engine.py does use structured key-value fields via `extra=`, the rest of the codebase consistently uses structlog. Mixing loggers makes log aggregation inconsistent.

**Fix:** Switch to `structlog.get_logger(__name__)` and pass fields as keyword arguments instead of `extra=` dict.

#### M-4. DataFlowFabricReader.\_row_to_model_registry uses date.today() and datetime.now()

**Location:** `src/midas/fabric/adapters/dataflow_adapter.py:260-261`

```python
period_end=date.today(),
filed_at=datetime.now(),
```

The PITKey for model_registry records read from the database uses "now" timestamps instead of the actual filed_at from the database row. This violates PIT invariant (a) because it makes the record appear to have been filed at the current time rather than when it was actually filed.

**Fix:** Use the `filed_at` and `period_end` values from the database row, not the current time.

#### M-5. IBKR Web API base URL appears to have a typo

**Location:** `src/midas/fabric/adapters/ibkr.py:46`

```python
IBKR_API_BASE = "https://api.interactivebrokererc.com"
```

The domain `interactivebrokererc.com` appears to be a typo (extra 'r' and 'c'). The correct domain for IBKR Web API is typically `interactivebrokers.com`. This URL would fail in production.

**Fix:** Verify the correct IBKR API endpoint and update. The likely correct URL is `https://api.interactivebrokers.com`.

#### M-6. GoogleTrendsAdapter.fetch_trend does not fetch real data

**Location:** `src/midas/fabric/adapters/alt_macro.py:263-295`

The method hits an RSS endpoint that provides trending searches (not interest over time), acknowledges this in a comment, and returns an empty list with `success=True`. The audit log records success even though no data was retrieved.

**Fix:** Either return status reflecting partial/no data, or mark as a known v1 limitation with a clear audit detail indicating the adapter returns empty results pending full implementation.

#### M-7. TWSTFallbackAdapter.\_get_ib performs synchronous blocking call

**Location:** `src/midas/fabric/adapters/ibkr.py:1091-1092`

```python
self._ib.connect(self._host, self._port, clientId=self._client_id)
```

The `ib_async.IB.connect()` is a synchronous blocking call inside a method called from async code paths. This blocks the event loop during TWS connection establishment.

**Fix:** Wrap in `asyncio.get_event_loop().run_in_executor(None, ...)` to avoid blocking the event loop, following the pattern already used in the Yahoo adapter for synchronous yfinance calls.

---

### Code Example Validation

No executable code examples were found in the reviewed source (this is application code, not documentation). The review focused on production code quality rather than doc snippet correctness.

---

### Structured Logging Compliance

- **Passed:** All 90+ files use structlog consistently
- **Passed:** Zero `print()` statements in production code
- **Passed:** Zero unstructured f-string log messages (`logger.xxx(f"...")` patterns)
- **Note:** `engine.py` is the sole file using stdlib `logging` instead of structlog (see M-3)

---

### Import Hygiene

- **Passed:** Zero wildcard imports (`from X import *`)
- **Passed:** All imports use absolute paths
- **Passed:** `TYPE_CHECKING` guard used correctly for type-only imports (e.g., ibkr.py, dataflow_adapter.py)

---

### Financial Calculation Safety

- **Passed:** `brinson.py` validates array lengths match before computation
- **Passed:** `metrics.py` guards against division by zero in Sharpe (std == 0), Sortino (downside_std == 0), Calmar (mdd == 0), Information Ratio (te == 0), Jensen's Alpha (var_b == 0)
- **Passed:** `posterior_combination.py` validates inputs (empty list, length mismatch, shape mismatch, weight sum)
- **Passed:** `ood_detector.py` guards against degenerate covariance matrices and zero training variance
- **Note:** `tools.py:propose_alternative_allocation` does guard division by zero (`equity_weight > 0`) and (`non_equity_total > 0`)

---

### Async Correctness

- **Issue I-8:** IBKR priority queue discards exceptions (see above)
- **Issue M-7:** TWS fallback uses synchronous connect in async context (see above)
- **Passed:** Yahoo adapter correctly wraps synchronous yfinance calls in `run_in_executor`
- **Passed:** Resource cleanup uses `async with` and `try/finally` patterns in cache, adapters, and fixtures

---

### Overall Quality Assessment

**Architecture:** Well-structured. Clean separation between fabric layer (data), agents (reasoning), compliance (rules), and ML (inference). The PIT (point-in-time) discipline is consistently enforced across all fabric reads. Adapter pattern is well-implemented with shared retry, rate-limiting, and audit infrastructure in `BaseAdapter`.

**Observability:** Strong baseline. Structured logging with structlog is used throughout. Entry/exit/error logging is present on most integration points. The `engine.py` stdlib logger is the only outlier.

**Compliance engine:** Clean implementation. 16 blocking rules and 7 escalation rules are data-driven (lambda predicates registered at startup), not hardcoded if-else chains. Default-deny posture on evaluation failures is correct.

**Main risks:**

1. The three TODO markers and two no-op methods (promote, retire) represent unfinished work that will fail silently in production.
2. The 7 silent exception swallows in `ml/__init__.py` and 3 in `alt_macro.py` will hide infrastructure failures from operators.
3. The fake backtest data in `tools.py` will feed false information to the LLM debate agent.
4. The IBKR adapter priority queue silently drops exceptions, which could hide broker connectivity failures during live trading.
