"""Tier 1 tests for IBKRAdapter and TWSTFallbackAdapter.

Covers:
- IBKRAdapter: initialization, health_check, priority queue ordering,
  fetch_quote result structure, fetch_positions PIT fields,
  fetch_order_status and order status mapping, fetch_sweep_events,
  write_fill, error handling
- TWSTFallbackAdapter: initialization, health_check when ib_async not installed
- OrderState.from_ibkr() status mapping
- Priority enum values

Mocking strategy:
- _enqueue is mocked to directly invoke the queued function, bypassing
  the priority queue drain infrastructure (avoids hanging async tasks).
- httpx client is mocked to avoid real HTTP calls.
- DataFlow express.create is mocked for audit/fabric writes.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from midas.fabric.adapters.base import (
    AdapterError,
    AuthenticationError,
    RateLimitExceeded,
)
from midas.fabric.adapters.ibkr import (
    IBKR_API_BASE,
    IBKRFallbackError,
    IBKRAdapter,
    OrderState,
    Priority,
    TWS_DEFAULT_PORT,
    TWS_PAPER_PORT,
    TWSTFallbackAdapter,
)
from midas.fabric.engine import create_fabric, reset_fabric


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_enqueue_passthrough(adapter):
    """Replace _enqueue with a passthrough that calls fn directly.

    This bypasses the priority queue drain loop which would otherwise
    hang in unit tests (the drain task never completes).
    """

    async def _enqueue_passthrough(priority, operation, fn, *args, **kwargs):
        return await fn(*args, **kwargs)

    adapter._enqueue = _enqueue_passthrough


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for fabric CRUD tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_ibkr.db")
    db_url = f"sqlite:///{db_path}"
    database = create_fabric(database_url=db_url, auto_migrate=True)
    yield database
    try:
        database.close()
    except Exception:
        pass
    reset_fabric()
    for suffix in ("-wal", "-shm"):
        try:
            os.unlink(db_path + suffix)
        except OSError:
            pass
    try:
        os.unlink(db_path)
    except OSError:
        pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


@pytest.fixture
async def started_db(db):
    """Start the database for async adapter tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


@pytest.fixture
def ibkr_no_creds(db):
    """IBKRAdapter without client credentials."""
    return IBKRAdapter(db=db, client_id=None, client_secret=None)


@pytest.fixture
def ibkr_with_creds(db):
    """IBKRAdapter with dummy client credentials."""
    return IBKRAdapter(
        db=db,
        client_id="test-client-id",
        client_secret="test-client-secret",
    )


@pytest.fixture
def tws_adapter(db):
    """TWSTFallbackAdapter with default parameters."""
    return TWSTFallbackAdapter(db=db)


# ---------------------------------------------------------------------------
# Priority enum tests
# ---------------------------------------------------------------------------


class TestPriorityEnum:
    """Priority enum value and ordering tests."""

    def test_priority_values_are_distinct_integers(self):
        """Each Priority tier has a unique integer value."""
        values = [p.value for p in Priority]
        assert len(values) == len(set(values)), "Priority values must be unique"

    def test_priority_ordering_submit_highest(self):
        """ORDER_SUBMIT has the highest priority value (money at risk)."""
        assert Priority.ORDER_SUBMIT.value > Priority.FRESH_QUOTE.value
        assert Priority.ORDER_SUBMIT.value > Priority.ORDER_STATUS.value
        assert Priority.ORDER_SUBMIT.value > Priority.POSITION_BALANCE.value
        assert Priority.ORDER_SUBMIT.value > Priority.MONITORING.value
        assert Priority.ORDER_SUBMIT.value > Priority.BULK_DATA.value

    def test_priority_ordering_fresh_quote_above_monitoring(self):
        """FRESH_QUOTE is above MONITORING (trade-adjacent compliance gate)."""
        assert Priority.FRESH_QUOTE.value > Priority.MONITORING.value

    def test_priority_ordering_monitoring_above_bulk(self):
        """MONITORING is above BULK_DATA."""
        assert Priority.MONITORING.value > Priority.BULK_DATA.value

    def test_priority_ordering_bulk_data_lowest(self):
        """BULK_DATA has the lowest priority value."""
        assert Priority.BULK_DATA.value == 0

    def test_priority_ordering_submit_above_all(self):
        """ORDER_SUBMIT > FRESH_QUOTE > POSITION_BALANCE > ORDER_STATUS > MONITORING > BULK_DATA."""
        assert Priority.ORDER_SUBMIT.value > Priority.FRESH_QUOTE.value
        assert Priority.FRESH_QUOTE.value > Priority.POSITION_BALANCE.value
        assert Priority.POSITION_BALANCE.value > Priority.ORDER_STATUS.value
        assert Priority.ORDER_STATUS.value > Priority.MONITORING.value
        assert Priority.MONITORING.value > Priority.BULK_DATA.value

    def test_priority_is_int_enum(self):
        """Priority is an IntEnum so it sorts numerically."""
        assert isinstance(Priority.ORDER_SUBMIT, int)
        assert Priority.ORDER_SUBMIT == 5


# ---------------------------------------------------------------------------
# OrderState.from_ibkr() status mapping tests
# ---------------------------------------------------------------------------


class TestOrderStateFromIBKR:
    """Tests for OrderState.from_ibkr() classmethod."""

    def test_maps_pending_submit(self):
        assert OrderState.from_ibkr("PendingSubmit") == OrderState.SUBMITTED_PENDING

    def test_maps_pending_cancel(self):
        assert OrderState.from_ibkr("PendingCancel") == OrderState.CANCEL_PENDING

    def test_maps_pre_submitted(self):
        assert OrderState.from_ibkr("PreSubmitted") == OrderState.SUBMITTED_WAITING

    def test_maps_submitted(self):
        assert OrderState.from_ibkr("Submitted") == OrderState.WORKING

    def test_maps_filled(self):
        assert OrderState.from_ibkr("Filled") == OrderState.FILLED

    def test_maps_cancelled(self):
        assert OrderState.from_ibkr("Cancelled") == OrderState.CANCELLED

    def test_maps_api_cancelled(self):
        assert OrderState.from_ibkr("ApiCancelled") == OrderState.CANCELLED_API

    def test_maps_inactive(self):
        assert OrderState.from_ibkr("Inactive") == OrderState.INACTIVE_FLAGGED

    def test_maps_partially_filled(self):
        assert OrderState.from_ibkr("PartiallyFilled") == OrderState.PARTIAL_FILLED

    def test_case_insensitive_mapping(self):
        """Mapping works regardless of input case."""
        assert OrderState.from_ibkr("filled") == OrderState.FILLED
        assert OrderState.from_ibkr("FILLED") == OrderState.FILLED
        assert OrderState.from_ibkr("Filled") == OrderState.FILLED

    def test_unknown_status_returns_rejected(self):
        """Unknown statuses map to REJECTED."""
        result = OrderState.from_ibkr("SomeNewStatus")
        assert result == OrderState.REJECTED

    def test_empty_string_returns_rejected(self):
        """Empty string maps to REJECTED."""
        result = OrderState.from_ibkr("")
        assert result == OrderState.REJECTED

    def test_all_defined_statuses_have_mapping(self):
        """Every known IBKR status maps to a Midas canonical status."""
        known_ibkr_statuses = [
            "PendingSubmit",
            "PendingCancel",
            "PreSubmitted",
            "Submitted",
            "Filled",
            "Cancelled",
            "ApiCancelled",
            "Inactive",
            "PartiallyFilled",
        ]
        for status in known_ibkr_statuses:
            mapped = OrderState.from_ibkr(status)
            assert (
                mapped != OrderState.REJECTED
            ), f"Status '{status}' should have a non-REJECTED mapping"


# ---------------------------------------------------------------------------
# IBKRAdapter initialization tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterInit:
    """IBKRAdapter constructor and initialization tests."""

    def test_default_base_url(self, db):
        """Adapter uses IBKR API base URL by default."""
        adapter = IBKRAdapter(db=db)
        assert adapter._base_url == IBKR_API_BASE

    def test_custom_base_url(self, db):
        """Adapter accepts a custom base URL."""
        adapter = IBKRAdapter(db=db, base_url="https://custom.api.com/")
        assert adapter._base_url == "https://custom.api.com"  # trailing slash stripped

    def test_paper_trading_flag_stored(self, db):
        """Paper trading flag is stored."""
        adapter = IBKRAdapter(db=db, paper_trading=True)
        assert adapter._paper_trading is True

    def test_client_credentials_stored(self, db):
        """Client ID and secret are stored."""
        adapter = IBKRAdapter(
            db=db,
            client_id="cid-123",
            client_secret="csec-456",
        )
        assert adapter._client_id == "cid-123"
        assert adapter._client_secret == "csec-456"

    def test_oauth_tokens_initially_none(self, db):
        """OAuth tokens start as None and expired."""
        adapter = IBKRAdapter(db=db)
        assert adapter._oauth_access_token is None
        assert adapter._oauth_refresh_token is None
        assert adapter._token_expires_at == 0.0

    def test_source_name_is_ibkr(self, db):
        """SOURCE_NAME is 'ibkr'."""
        adapter = IBKRAdapter(db=db)
        assert adapter.SOURCE_NAME == "ibkr"

    def test_priority_queues_initialized(self, db):
        """All priority tiers have queues initialized."""
        adapter = IBKRAdapter(db=db)
        for tier in Priority:
            assert tier in adapter._priority_queues

    def test_default_rate_limit_override(self, db):
        """IBKR adapter overrides the default min_call_interval to 1.5s."""
        adapter = IBKRAdapter(db=db)
        assert adapter._min_call_interval_s == 1.5

    def test_custom_http_timeout(self, db):
        """Custom HTTP timeout is stored."""
        adapter = IBKRAdapter(db=db, http_timeout_s=10.0)
        assert adapter._http_timeout_s == 10.0

    def test_http_client_lazily_created(self, db):
        """HTTP client starts as None and is created on first access."""
        adapter = IBKRAdapter(db=db)
        assert adapter._client is None
        client = adapter._get_client()
        assert client is not None
        assert isinstance(client, httpx.AsyncClient)

    def test_drain_task_initially_none(self, db):
        """Priority queue drain task starts as None."""
        adapter = IBKRAdapter(db=db)
        assert adapter._drain_task is None


# ---------------------------------------------------------------------------
# IBKRAdapter health_check tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterHealthCheck:
    """Health check tests for IBKRAdapter."""

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_without_credentials(self, ibkr_no_creds):
        """Health check reports unhealthy when client credentials are missing."""
        result = await ibkr_no_creds.health_check()
        assert result["source"] == "ibkr"
        assert result["healthy"] is False
        assert "credentials" in result["detail"].lower()

    @pytest.mark.asyncio
    async def test_health_check_returns_source_name(self, ibkr_no_creds):
        """Health check always includes the source name."""
        result = await ibkr_no_creds.health_check()
        assert result["source"] == "ibkr"

    @pytest.mark.asyncio
    async def test_health_check_healthy_on_successful_token(self, started_db):
        """Health check reports healthy when OAuth token is acquired."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )

        async def mock_fetch_initial_token():
            adapter._oauth_access_token = "mock-token-123"
            adapter._token_expires_at = 9999999999.0
            adapter._oauth_refresh_token = "mock-refresh"
            return "mock-token-123"

        adapter._fetch_initial_token = mock_fetch_initial_token

        result = await adapter.health_check()
        assert result["source"] == "ibkr"
        assert result["healthy"] is True
        assert "OAuth" in result["detail"]

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_on_auth_error(self, started_db):
        """Health check reports unhealthy on AuthenticationError."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )

        async def mock_fetch_raises_auth():
            raise AuthenticationError("ibkr", "oauth2_initial", status_code=401)

        adapter._fetch_initial_token = mock_fetch_raises_auth

        result = await adapter.health_check()
        assert result["healthy"] is False
        assert "authentication" in result["detail"].lower()

    @pytest.mark.asyncio
    async def test_health_check_signals_fallback_on_503(self, started_db):
        """Health check reports fallback_required when IBKR returns 503."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )

        async def mock_fetch_raises_fallback():
            raise IBKRFallbackError("Web API returned 503")

        adapter._fetch_initial_token = mock_fetch_raises_fallback

        result = await adapter.health_check()
        assert result["healthy"] is False
        assert result.get("fallback_required") is True


# ---------------------------------------------------------------------------
# IBKRAdapter fetch_quote tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterFetchQuote:
    """fetch_quote result structure tests."""

    @pytest.mark.asyncio
    async def test_fetch_quote_result_structure(self, started_db):
        """fetch_quote returns a dict with required fields."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(ticker):
            return {"bid": 150.25, "ask": 150.30, "bid_size": 100, "ask_size": 200}

        adapter._do_fetch_quote = mock_do_fetch

        result = await adapter.fetch_quote("AAPL")

        # Verify required fields are present
        assert "ticker" in result
        assert "bid" in result
        assert "ask" in result
        assert "mid" in result
        assert "spread_bps" in result
        assert "timestamp" in result
        assert "source_vintage" in result

    @pytest.mark.asyncio
    async def test_fetch_quote_calculates_mid_correctly(self, started_db):
        """fetch_quote calculates mid price as (bid + ask) / 2."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        # Mock _do_fetch_quote to return specific data
        async def mock_do_fetch(ticker):
            return {"bid": 100.0, "ask": 102.0}

        adapter._do_fetch_quote = mock_do_fetch

        result = await adapter.fetch_quote("TEST")
        assert result["mid"] == 101.0

    @pytest.mark.asyncio
    async def test_fetch_quote_calculates_spread_bps(self, started_db):
        """fetch_quote calculates spread in basis points."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        # bid=100, ask=101 -> spread = 1 -> bps = (1/100.5)*10000 ~ 99.5025
        async def mock_do_fetch(ticker):
            return {"bid": 100.0, "ask": 101.0}

        adapter._do_fetch_quote = mock_do_fetch

        result = await adapter.fetch_quote("TEST")

        expected_bps = ((101.0 - 100.0) / 100.5) * 10000
        assert abs(result["spread_bps"] - round(expected_bps, 4)) < 0.01

    @pytest.mark.asyncio
    async def test_fetch_quote_source_vintage_format(self, started_db):
        """source_vintage follows ibkr:TICKER:TIMESTAMP format."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(ticker):
            return {"bid": 50.0, "ask": 51.0}

        adapter._do_fetch_quote = mock_do_fetch

        result = await adapter.fetch_quote("MSFT")
        assert result["source_vintage"].startswith("ibkr:MSFT:")

    @pytest.mark.asyncio
    async def test_fetch_quote_returns_empty_on_empty_data(self, started_db):
        """fetch_quote returns empty dict when API returns no data."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(ticker):
            return {}

        adapter._do_fetch_quote = mock_do_fetch

        result = await adapter.fetch_quote("UNKNOWN")
        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_quote_handles_zero_bid_ask(self, started_db):
        """fetch_quote returns mid=0 when bid or ask is zero."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(ticker):
            return {"bid": 0, "ask": 100.0}

        adapter._do_fetch_quote = mock_do_fetch

        result = await adapter.fetch_quote("TEST")
        # When bid is 0, mid should be 0 (both bid and ask must be non-zero)
        assert result["mid"] == 0.0
        assert result["spread_bps"] == 0.0

    @pytest.mark.asyncio
    async def test_fetch_quote_includes_bid_size_ask_size(self, started_db):
        """fetch_quote result includes bid_size and ask_size."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(ticker):
            return {"bid": 100.0, "ask": 101.0, "bid_size": 500, "ask_size": 300}

        adapter._do_fetch_quote = mock_do_fetch

        result = await adapter.fetch_quote("AAPL")
        assert result["bid_size"] == 500.0
        assert result["ask_size"] == 300.0


# ---------------------------------------------------------------------------
# IBKRAdapter fetch_positions PIT field tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterFetchPositions:
    """fetch_positions PIT (point-in-time) field tests."""

    @pytest.mark.asyncio
    async def test_fetch_positions_pit_fields_present(self, started_db):
        """Each position row has period_end, filed_at, restated_at, source_vintage."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [
                {
                    "symbol": "AAPL",
                    "position": 100,
                    "avg_cost": 145.50,
                    "marketPrice": 150.25,
                    "marketValue": 15025.0,
                    "unrealizedPnl": 475.0,
                },
            ]

        adapter._do_fetch_positions = mock_do_fetch

        rows = await adapter.fetch_positions("U1234567")

        assert len(rows) == 1
        row = rows[0]

        # PIT fields
        assert "period_end" in row
        assert "filed_at" in row
        assert "restated_at" in row
        assert "source_vintage" in row

        # period_end should be today's date
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).date().isoformat()
        assert row["period_end"] == today

        # filed_at should be an ISO timestamp
        assert "T" in row["filed_at"]

        # restated_at should be empty string (initial filing)
        assert row["restated_at"] == ""

    @pytest.mark.asyncio
    async def test_fetch_positions_source_vintage_format(self, started_db):
        """source_vintage follows ibkr:positions:ACCOUNT_ID:DATE format."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [{"symbol": "GOOG", "position": 50, "avg_cost": 2800.0}]

        adapter._do_fetch_positions = mock_do_fetch

        rows = await adapter.fetch_positions("U9876543")
        assert rows[0]["source_vintage"].startswith("ibkr:positions:U9876543:")

    @pytest.mark.asyncio
    async def test_fetch_positions_extracts_quantity_from_position_field(self, started_db):
        """Position quantity is extracted from 'position' key."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [{"symbol": "TSLA", "position": "250.5", "avg_cost": 200.0}]

        adapter._do_fetch_positions = mock_do_fetch

        rows = await adapter.fetch_positions("U1111111")
        assert rows[0]["quantity"] == 250.5

    @pytest.mark.asyncio
    async def test_fetch_positions_empty_list_on_no_data(self, started_db):
        """fetch_positions returns empty list when API returns no data."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return []

        adapter._do_fetch_positions = mock_do_fetch

        rows = await adapter.fetch_positions("U0000000")
        assert rows == []

    @pytest.mark.asyncio
    async def test_fetch_positions_falls_back_to_conid(self, started_db):
        """When symbol and ticker are missing, falls back to conid."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [{"conid": "265598", "position": 10, "avg_cost": 100.0}]

        adapter._do_fetch_positions = mock_do_fetch

        rows = await adapter.fetch_positions("U1111111")
        assert rows[0]["ticker"] == "265598"


# ---------------------------------------------------------------------------
# IBKRAdapter fetch_order_status tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterFetchOrderStatus:
    """fetch_order_status and order status mapping tests."""

    @pytest.mark.asyncio
    async def test_fetch_order_status_maps_status(self, started_db):
        """IBKR order statuses are mapped to Midas canonical statuses."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [
                {
                    "symbol": "AAPL",
                    "side": "BUY",
                    "order_type": "LMT",
                    "quantity": 100,
                    "limit_price": 150.0,
                    "status": "Filled",
                    "filled_qty": 100,
                    "filled_price": 149.95,
                    "order_id": "ORD-001",
                },
            ]

        adapter._do_fetch_orders = mock_do_fetch

        rows = await adapter.fetch_order_status("U1234567")

        assert len(rows) == 1
        assert rows[0]["status"] == "filled"
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["side"] == "BUY"
        assert rows[0]["quantity"] == 100.0

    @pytest.mark.asyncio
    async def test_fetch_order_status_pit_fields(self, started_db):
        """Order rows include PIT fields."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [
                {"symbol": "MSFT", "status": "Submitted", "order_id": "ORD-002"},
            ]

        adapter._do_fetch_orders = mock_do_fetch

        rows = await adapter.fetch_order_status("U1234567")

        row = rows[0]
        assert "period_end" in row
        assert "filed_at" in row
        assert "restated_at" in row
        assert "source_vintage" in row
        assert row["restated_at"] == ""

    @pytest.mark.asyncio
    async def test_fetch_order_status_source_vintage_format(self, started_db):
        """source_vintage follows ibkr:orders:ACCOUNT_ID:TIMESTAMP format."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [
                {"symbol": "TSLA", "status": "PreSubmitted", "order_id": "ORD-003"},
            ]

        adapter._do_fetch_orders = mock_do_fetch

        rows = await adapter.fetch_order_status("U5555555")
        assert rows[0]["source_vintage"].startswith("ibkr:orders:U5555555:")

    @pytest.mark.asyncio
    async def test_fetch_order_status_multiple_orders(self, started_db):
        """fetch_order_status processes multiple orders."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [
                {"symbol": "AAPL", "status": "Filled", "order_id": "ORD-010"},
                {"symbol": "MSFT", "status": "Cancelled", "order_id": "ORD-011"},
                {"symbol": "GOOG", "status": "Submitted", "order_id": "ORD-012"},
            ]

        adapter._do_fetch_orders = mock_do_fetch

        rows = await adapter.fetch_order_status("U9999999")
        assert len(rows) == 3

        statuses = {r["ticker"]: r["status"] for r in rows}
        assert statuses["AAPL"] == "filled"
        assert statuses["MSFT"] == "cancelled"
        assert statuses["GOOG"] == "working"


# ---------------------------------------------------------------------------
# IBKRAdapter fetch_sweep_events tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterFetchSweepEvents:
    """fetch_sweep_events tests."""

    @pytest.mark.asyncio
    async def test_fetch_sweep_events_result_structure(self, started_db):
        """Sweep event rows have the expected fields."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [
                {
                    "base_currency": "USD",
                    "target_currency": "SGD",
                    "amount": 10000.0,
                    "rate": 1.34,
                    "fee": 2.0,
                    "sweep_id": "SWEEP-001",
                    "timestamp": "2024-06-15T10:30:00Z",
                },
            ]

        adapter._do_fetch_sweeps = mock_do_fetch

        rows = await adapter.fetch_sweep_events("U1234567")

        assert len(rows) == 1
        row = rows[0]
        assert row["base_currency"] == "USD"
        assert row["target_currency"] == "SGD"
        assert row["amount"] == 10000.0
        assert row["rate"] == 1.34
        assert row["fee"] == 2.0
        assert row["broker_sweep_id"] == "SWEEP-001"

    @pytest.mark.asyncio
    async def test_fetch_sweep_events_pit_fields(self, started_db):
        """Sweep events include PIT fields."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return [
                {
                    "base_currency": "USD",
                    "target_currency": "EUR",
                    "amount": 5000.0,
                    "rate": 0.92,
                },
            ]

        adapter._do_fetch_sweeps = mock_do_fetch

        rows = await adapter.fetch_sweep_events("U1234567")

        row = rows[0]
        assert "period_end" in row
        assert "filed_at" in row
        assert "restated_at" in row
        assert "source_vintage" in row
        assert row["source_vintage"].startswith("ibkr:sweeps:U1234567:")

    @pytest.mark.asyncio
    async def test_fetch_sweep_events_empty_on_no_data(self, started_db):
        """fetch_sweep_events returns empty list when no sweeps exist."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        _make_enqueue_passthrough(adapter)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        async def mock_do_fetch(account_id):
            return []

        adapter._do_fetch_sweeps = mock_do_fetch

        rows = await adapter.fetch_sweep_events("U0000000")
        assert rows == []


# ---------------------------------------------------------------------------
# IBKRAdapter write_fill tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterWriteFill:
    """write_fill tests."""

    @pytest.mark.asyncio
    async def test_write_fill_returns_row_with_all_fields(self, started_db):
        """write_fill returns a dict with all fill fields."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        result = await adapter.write_fill(
            order_id="ORD-001",
            ticker="AAPL",
            fill_price=150.25,
            fill_qty=100.0,
            commission=1.0,
            exchange_fee=0.05,
            regulatory_fee=0.01,
            venue="SMART",
            fill_timestamp="2024-06-15T10:30:00Z",
            broker_fill_id="FILL-001",
        )

        assert result["order_id"] == "ORD-001"
        assert result["ticker"] == "AAPL"
        assert result["fill_price"] == 150.25
        assert result["fill_qty"] == 100.0
        assert result["commission"] == 1.0
        assert result["exchange_fee"] == 0.05
        assert result["regulatory_fee"] == 0.01
        assert result["venue"] == "SMART"
        assert result["fill_timestamp"] == "2024-06-15T10:30:00Z"
        assert result["broker_fill_id"] == "FILL-001"

    @pytest.mark.asyncio
    async def test_write_fill_pit_fields(self, started_db):
        """write_fill includes PIT fields."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        result = await adapter.write_fill(
            order_id="ORD-002",
            ticker="MSFT",
            fill_price=300.0,
            fill_qty=50.0,
            commission=0.5,
            exchange_fee=0.03,
            regulatory_fee=0.01,
            venue="ISLAND",
            fill_timestamp="2024-06-15T11:00:00Z",
            broker_fill_id="FILL-002",
        )

        assert "period_end" in result
        assert "filed_at" in result
        assert "restated_at" in result
        assert result["restated_at"] == ""
        assert result["source_vintage"].startswith("ibkr:fill:FILL-002")

    @pytest.mark.asyncio
    async def test_write_fill_returns_empty_on_db_error(self, started_db):
        """write_fill returns empty dict when database write fails."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )

        async def mock_create_fail(table, row):
            raise RuntimeError("database connection lost")

        started_db.express.create = mock_create_fail

        result = await adapter.write_fill(
            order_id="ORD-003",
            ticker="GOOG",
            fill_price=2800.0,
            fill_qty=10.0,
            commission=2.0,
            exchange_fee=0.1,
            regulatory_fee=0.02,
            venue="NYSE",
            fill_timestamp="2024-06-15T12:00:00Z",
            broker_fill_id="FILL-003",
        )

        assert result == {}


# ---------------------------------------------------------------------------
# IBKRAdapter error handling tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterErrorHandling:
    """Error handling tests for IBKRAdapter."""

    @pytest.mark.asyncio
    async def test_oauth_request_raises_auth_error_on_401(self, started_db):
        """_oauth_request raises AuthenticationError on 401."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
            max_retries=1,
            base_delay_s=0.01,
        )

        # Pre-set a token so _ensure_token does not try to fetch
        adapter._oauth_access_token = "valid-token"
        adapter._token_expires_at = 9999999999.0

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}

        # Create a mock client where _get_client returns a mock with .get()
        # that returns our mock_response
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        with pytest.raises(AuthenticationError) as exc_info:
            await adapter._oauth_request("/v1/test", {}, "test_op")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_oauth_request_raises_rate_limit_on_429(self, started_db):
        """_oauth_request detects 429 and raises RateLimitExceeded."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
            max_retries=1,
            base_delay_s=0.01,
        )

        adapter._oauth_access_token = "valid-token"
        adapter._token_expires_at = 9999999999.0

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "5"}
        mock_response.text = "rate limited"

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        # Bypass _retry so the specific exception type is preserved
        async def _retry_passthrough(operation, fn, *args, **kwargs):
            return await fn(*args, **kwargs)

        adapter._retry = _retry_passthrough

        with pytest.raises(RateLimitExceeded) as exc_info:
            await adapter._oauth_request("/v1/test", {}, "test_op")

        assert exc_info.value.retry_after_s == 5.0

    @pytest.mark.asyncio
    async def test_oauth_request_raises_fallback_on_503(self, started_db):
        """_oauth_request detects 503 and raises IBKRFallbackError."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
            max_retries=1,
            base_delay_s=0.01,
        )

        adapter._oauth_access_token = "valid-token"
        adapter._token_expires_at = 9999999999.0

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.headers = {}

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        # Bypass _retry so the specific exception type is preserved
        async def _retry_passthrough(operation, fn, *args, **kwargs):
            return await fn(*args, **kwargs)

        adapter._retry = _retry_passthrough

        with pytest.raises(IBKRFallbackError):
            await adapter._oauth_request("/v1/test", {}, "test_op")

    @pytest.mark.asyncio
    async def test_oauth_request_raises_adapter_error_on_500(self, started_db):
        """_oauth_request raises AdapterError on 500."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
            max_retries=1,
            base_delay_s=0.01,
        )

        adapter._oauth_access_token = "valid-token"
        adapter._token_expires_at = 9999999999.0

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        with pytest.raises(AdapterError) as exc_info:
            await adapter._oauth_request("/v1/test", {}, "test_op")

        assert "server error" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_fetch_initial_token_raises_without_credentials(self, started_db):
        """_fetch_initial_token raises AuthenticationError without credentials."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id=None,
            client_secret=None,
        )

        with pytest.raises(AuthenticationError):
            await adapter._fetch_initial_token()

    @pytest.mark.asyncio
    async def test_ensure_token_refreshes_when_expired(self, started_db):
        """_ensure_token attempts refresh when token is expired."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )

        # Set token as expired
        adapter._oauth_access_token = "old-token"
        adapter._oauth_refresh_token = "old-refresh"
        adapter._token_expires_at = 0.0  # expired

        refresh_called = False

        async def mock_refresh():
            nonlocal refresh_called
            refresh_called = True
            adapter._oauth_access_token = "new-token"
            return "new-token"

        adapter._refresh_token = mock_refresh

        token = await adapter._ensure_token()
        assert refresh_called
        assert token == "new-token"


# ---------------------------------------------------------------------------
# IBKRAdapter close tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterClose:
    """Resource cleanup tests."""

    @pytest.mark.asyncio
    async def test_close_closes_http_client(self, started_db):
        """close() closes the httpx client."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )

        client = adapter._get_client()
        assert not client.is_closed

        await adapter.close()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_close_handles_no_client(self, started_db):
        """close() is safe when no client was created."""
        adapter = IBKRAdapter(
            db=started_db,
            client_id="test-id",
            client_secret="test-secret",
        )
        assert adapter._client is None
        await adapter.close()  # should not raise


# ---------------------------------------------------------------------------
# TWSTFallbackAdapter initialization tests
# ---------------------------------------------------------------------------


class TestTWSTFallbackAdapterInit:
    """TWSTFallbackAdapter constructor and initialization tests."""

    def test_default_host_and_port(self, db):
        """Default host is 127.0.0.1, default port is TWS_DEFAULT_PORT."""
        adapter = TWSTFallbackAdapter(db=db)
        assert adapter._host == "127.0.0.1"
        assert adapter._port == TWS_DEFAULT_PORT

    def test_paper_trading_uses_paper_port(self, db):
        """Paper trading flag switches port to TWS_PAPER_PORT."""
        adapter = TWSTFallbackAdapter(db=db, paper_trading=True)
        assert adapter._port == TWS_PAPER_PORT

    def test_live_trading_uses_default_port(self, db):
        """Live trading uses the default TWS port."""
        adapter = TWSTFallbackAdapter(db=db, paper_trading=False)
        assert adapter._port == TWS_DEFAULT_PORT

    def test_custom_host_and_port(self, db):
        """Custom host and port are stored."""
        adapter = TWSTFallbackAdapter(db=db, host="192.168.1.100", port=4001)
        assert adapter._host == "192.168.1.100"
        assert adapter._port == 4001

    def test_source_name(self, db):
        """SOURCE_NAME is 'ibkr_tws'."""
        adapter = TWSTFallbackAdapter(db=db)
        assert adapter.SOURCE_NAME == "ibkr_tws"

    def test_account_id_stored(self, db):
        """account_id is stored when provided."""
        adapter = TWSTFallbackAdapter(db=db, account_id="U1234567")
        assert adapter._account_id == "U1234567"

    def test_ib_connection_initially_none(self, db):
        """IB connection starts as None."""
        adapter = TWSTFallbackAdapter(db=db)
        assert adapter._ib is None


# ---------------------------------------------------------------------------
# TWSTFallbackAdapter health_check tests
# ---------------------------------------------------------------------------


class TestTWSTFallbackAdapterHealthCheck:
    """Health check tests for TWSTFallbackAdapter."""

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_when_ib_async_not_installed(self, db):
        """Health check reports unhealthy when ib_async is not installed."""
        adapter = TWSTFallbackAdapter(db=db)

        with patch("midas.fabric.adapters.ibkr.ib_async", None):
            result = await adapter.health_check()

        assert result["source"] == "ibkr_tws"
        assert result["healthy"] is False
        assert "ib_async" in result["detail"]

    @pytest.mark.asyncio
    async def test_health_check_returns_source_name(self, db):
        """Health check always includes source name."""
        adapter = TWSTFallbackAdapter(db=db)

        with patch("midas.fabric.adapters.ibkr.ib_async", None):
            result = await adapter.health_check()

        assert result["source"] == "ibkr_tws"


# ---------------------------------------------------------------------------
# TWSTFallbackAdapter fetch_sweep_events tests
# ---------------------------------------------------------------------------


class TestTWSTFallbackAdapterSweepEvents:
    """Sweep events are not available via TWS in v1."""

    @pytest.mark.asyncio
    async def test_fetch_sweep_events_returns_empty(self, started_db):
        """TWS adapter returns empty list for sweep events (not supported in v1)."""
        adapter = TWSTFallbackAdapter(db=started_db)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        rows = await adapter.fetch_sweep_events("U1234567")
        assert rows == []


# ---------------------------------------------------------------------------
# TWSTFallbackAdapter write_fill tests
# ---------------------------------------------------------------------------


class TestTWSTFallbackAdapterWriteFill:
    """write_fill tests for TWS adapter."""

    @pytest.mark.asyncio
    async def test_write_fill_returns_row_with_fields(self, started_db):
        """TWS write_fill returns a row with all expected fields."""
        adapter = TWSTFallbackAdapter(db=started_db)

        async def mock_create(table, row):
            return {"rows_affected": 1}

        started_db.express.create = mock_create

        result = await adapter.write_fill(
            order_id="ORD-TWS-001",
            ticker="AAPL",
            fill_price=151.0,
            fill_qty=200.0,
            commission=1.5,
            exchange_fee=0.07,
            regulatory_fee=0.02,
            venue="SMART",
            fill_timestamp="2024-06-15T14:00:00Z",
            broker_fill_id="FILL-TWS-001",
        )

        assert result["order_id"] == "ORD-TWS-001"
        assert result["ticker"] == "AAPL"
        assert result["fill_price"] == 151.0
        assert result["fill_qty"] == 200.0
        assert result["source_vintage"].startswith("ibkr_tws:fill:FILL-TWS-001")

    @pytest.mark.asyncio
    async def test_write_fill_returns_empty_on_db_error(self, started_db):
        """TWS write_fill returns empty dict on database error."""
        adapter = TWSTFallbackAdapter(db=started_db)

        async def mock_create_fail(table, row):
            raise RuntimeError("connection lost")

        started_db.express.create = mock_create_fail

        result = await adapter.write_fill(
            order_id="ORD-TWS-002",
            ticker="MSFT",
            fill_price=300.0,
            fill_qty=50.0,
            commission=0.5,
            exchange_fee=0.03,
            regulatory_fee=0.01,
            venue="ISLAND",
            fill_timestamp="2024-06-15T15:00:00Z",
            broker_fill_id="FILL-TWS-002",
        )

        assert result == {}


# ---------------------------------------------------------------------------
# IBKRFallbackError tests
# ---------------------------------------------------------------------------


class TestIBKRFallbackError:
    """IBKRFallbackError exception tests."""

    def test_fallback_error_is_adapter_error(self):
        """IBKRFallbackError inherits from AdapterError."""
        err = IBKRFallbackError("Web API returned 503")
        assert isinstance(err, AdapterError)

    def test_fallback_error_preserves_detail(self):
        """IBKRFallbackError stores the detail message."""
        err = IBKRFallbackError("Web API returned 503")
        assert "503" in err.detail

    def test_fallback_error_source_is_ibkr(self):
        """IBKRFallbackError sets source to 'ibkr'."""
        err = IBKRFallbackError("test detail")
        assert err.source == "ibkr"

    def test_fallback_error_operation_is_web_api(self):
        """IBKRFallbackError sets operation to 'web_api'."""
        err = IBKRFallbackError("test detail")
        assert err.operation == "web_api"


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    """IBKR adapter constants tests."""

    def test_api_base_url_is_https(self):
        """IBKR API base URL uses HTTPS."""
        assert IBKR_API_BASE.startswith("https://")

    def test_tws_default_port_is_7496(self):
        """Default TWS port is 7496."""
        assert TWS_DEFAULT_PORT == 7496

    def test_tws_paper_port_is_7497(self):
        """Paper trading TWS port is 7497."""
        assert TWS_PAPER_PORT == 7497

    def test_priority_has_six_tiers(self):
        """Priority enum defines exactly six tiers."""
        assert len(Priority) == 6
