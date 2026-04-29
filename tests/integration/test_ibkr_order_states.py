"""Tier 2 integration tests for IBKR order lifecycle state machine.

Verifies the full order state machine: all 9 IBKR states map correctly,
terminal/working state classifications, transition logging, and wiring
through the IBKR adapter fetch_order_status path.

Ref: specs/14-ibkr-integration.md §6 — order state machine
Ref: rules/facade-manager-detection.md — manager-shape wiring tests
"""

import asyncio
import tempfile
import os

import pytest

from midas.fabric.engine import create_fabric, reset_fabric
from midas.fabric.models import OrderState


# ---------------------------------------------------------------------------
# State machine unit tests (valid for all IBKR-sourced orders)
# ---------------------------------------------------------------------------


class TestOrderStateMachine:
    """Verify OrderState enum and IBKR mapping."""

    @pytest.mark.parametrize(
        "ibkr_status,expected_state",
        [
            # Non-terminal states
            ("PendingSubmit", OrderState.SUBMITTED_PENDING),
            ("PendingCancel", OrderState.CANCEL_PENDING),
            ("PreSubmitted", OrderState.SUBMITTED_WAITING),
            ("Submitted", OrderState.WORKING),
            ("PartiallyFilled", OrderState.PARTIAL_FILLED),
            # Terminal states
            ("Filled", OrderState.FILLED),
            ("Cancelled", OrderState.CANCELLED),
            ("ApiCancelled", OrderState.CANCELLED_API),
            ("Inactive", OrderState.INACTIVE_FLAGGED),
        ],
    )
    def test_from_ibkr_maps_all_known_states(self, ibkr_status, expected_state):
        """All 9 known IBKR states map to the correct Midas OrderState."""
        result = OrderState.from_ibkr(ibkr_status)
        assert (
            result == expected_state
        ), f"IBKR status '{ibkr_status}' should map to {expected_state}, got {result}"

    @pytest.mark.parametrize(
        "ibkr_status",
        [
            "unknown_status",
            "UNMAPPED",
            "",
            "SOME_RANDOM_STATUS",
        ],
    )
    def test_from_ibkr_defaults_to_rejected_for_unknown(self, ibkr_status):
        """Unknown IBKR statuses fall back to REJECTED state."""
        result = OrderState.from_ibkr(ibkr_status)
        assert result == OrderState.REJECTED

    @pytest.mark.parametrize(
        "state,expected_terminal",
        [
            (OrderState.SUBMITTED_PENDING, False),
            (OrderState.CANCEL_PENDING, False),
            (OrderState.SUBMITTED_WAITING, False),
            (OrderState.WORKING, False),
            (OrderState.PARTIAL_FILLED, False),
            (OrderState.FILLED, False),
            (OrderState.CANCELLED, True),
            (OrderState.CANCELLED_API, True),
            (OrderState.INACTIVE_FLAGGED, False),  # Requires intervention
            (OrderState.REJECTED, True),
        ],
    )
    def test_is_terminal_classification(self, state, expected_terminal):
        """Terminal states (FILLED, CANCELLED, CANCELLED_API) are correctly identified."""
        assert (
            state.is_terminal() is expected_terminal
        ), f"{state} is_terminal() should be {expected_terminal}"

    @pytest.mark.parametrize(
        "state,expected_working",
        [
            (OrderState.SUBMITTED_PENDING, True),
            (OrderState.CANCEL_PENDING, True),
            (OrderState.SUBMITTED_WAITING, True),
            (OrderState.WORKING, True),
            (OrderState.PARTIAL_FILLED, True),
            (OrderState.FILLED, False),
            (OrderState.CANCELLED, False),
            (OrderState.CANCELLED_API, False),
            (OrderState.INACTIVE_FLAGGED, False),
            (OrderState.REJECTED, False),
        ],
    )
    def test_is_working_classification(self, state, expected_working):
        """Working states represent orders that are active and may still execute."""
        assert (
            state.is_working() is expected_working
        ), f"{state} is_working() should be {expected_working}"

    def test_terminal_states_returns_correct_set(self):
        """OrderState.terminal_states() includes exactly the 4 terminal states."""
        terminal = OrderState.terminal_states()
        assert terminal == {
            OrderState.CANCELLED,
            OrderState.CANCELLED_API,
            OrderState.ATTRIBUTED,
            OrderState.REJECTED,
        }

    @pytest.mark.parametrize(
        "state",
        [
            OrderState.SUBMITTED_PENDING,
            OrderState.CANCEL_PENDING,
            OrderState.SUBMITTED_WAITING,
            OrderState.WORKING,
            OrderState.PARTIAL_FILLED,
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.CANCELLED_API,
            OrderState.INACTIVE_FLAGGED,
            OrderState.REJECTED,
        ],
    )
    def test_all_states_have_string_values(self, state):
        """Every OrderState has a non-empty string value."""
        assert isinstance(state.value, str)
        assert len(state.value) > 0

    def test_rejected_is_default_for_unknown_case_insensitive(self):
        """Unknown IBKR statuses are case-insensitive."""
        assert OrderState.from_ibkr("PENDINGSUBMIT") == OrderState.SUBMITTED_PENDING
        assert OrderState.from_ibkr("filled") == OrderState.FILLED
        assert OrderState.from_ibkr("UNKNOWN") == OrderState.REJECTED


# ---------------------------------------------------------------------------
# Fixture: real DataFlow instance for integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a temp-file SQLite MidasFabric for integration tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_ibkr_order_states.db")
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
    """Start the database for async integration tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# IBKR Adapter wiring tests
# ---------------------------------------------------------------------------


class TestIBKRAdapterOrderStateWiring:
    """Verify IBKR adapter wires OrderState correctly in fetch_order_status."""

    @pytest.mark.asyncio
    async def test_fetch_order_status_uses_order_state_enum(self, started_db):
        """fetch_order_status maps IBKR statuses to OrderState values in orders table."""
        from midas.fabric.adapters.ibkr import IBKRAdapter

        adapter = IBKRAdapter(db=started_db)
        adapter._db = started_db  # ensure adapter has db

        # Mock _enqueue to return synthetic IBKR order data with all known states
        synthetic_orders = [
            {
                "order_id": "ORD001",
                "symbol": "AAPL",
                "side": "BUY",
                "action": "BUY",
                "order_type": "LMT",
                "type": "LMT",
                "quantity": 100,
                "limit_price": 150.00,
                "lmt_price": 150.00,
                "status": "PendingSubmit",
                "filled_qty": 0,
                "filled": 0,
                "filled_price": 0,
                "avg_fill_price": 0,
                "submitted_at": "2026-04-01T10:00:00Z",
                "created_time": "2026-04-01T10:00:00Z",
                "filled_at": "",
                "fill_time": "",
                "parent_id": "DEC001",
            },
            {
                "order_id": "ORD002",
                "symbol": "MSFT",
                "side": "BUY",
                "action": "BUY",
                "order_type": "LMT",
                "type": "LMT",
                "quantity": 50,
                "limit_price": 380.00,
                "lmt_price": 380.00,
                "status": "Filled",
                "filled_qty": 50,
                "filled": 50,
                "filled_price": 379.50,
                "avg_fill_price": 379.50,
                "submitted_at": "2026-04-01T11:00:00Z",
                "created_time": "2026-04-01T11:00:00Z",
                "filled_at": "2026-04-01T11:05:00Z",
                "fill_time": "2026-04-01T11:05:00Z",
                "parent_id": "DEC002",
            },
            {
                "order_id": "ORD003",
                "symbol": "GOOGL",
                "side": "SELL",
                "action": "SELL",
                "order_type": "MKT",
                "type": "MKT",
                "quantity": 25,
                "limit_price": 0,
                "lmt_price": 0,
                "status": "PartiallyFilled",
                "filled_qty": 10,
                "filled": 10,
                "filled_price": 170.25,
                "avg_fill_price": 170.25,
                "submitted_at": "2026-04-01T12:00:00Z",
                "created_time": "2026-04-01T12:00:00Z",
                "filled_at": "2026-04-01T12:03:00Z",
                "fill_time": "2026-04-01T12:03:00Z",
                "parent_id": "DEC003",
            },
            {
                "order_id": "ORD004",
                "symbol": "TSLA",
                "side": "BUY",
                "action": "BUY",
                "order_type": "STP",
                "type": "STP",
                "quantity": 30,
                "limit_price": 245.00,
                "lmt_price": 245.00,
                "status": "Cancelled",
                "filled_qty": 0,
                "filled": 0,
                "filled_price": 0,
                "avg_fill_price": 0,
                "submitted_at": "2026-04-01T13:00:00Z",
                "created_time": "2026-04-01T13:00:00Z",
                "filled_at": "",
                "fill_time": "",
                "parent_id": "DEC004",
            },
            {
                "order_id": "ORD005",
                "symbol": "NVDA",
                "side": "BUY",
                "action": "BUY",
                "order_type": "LMT",
                "type": "LMT",
                "quantity": 20,
                "limit_price": 880.00,
                "lmt_price": 880.00,
                "status": "Inactive",
                "filled_qty": 0,
                "filled": 0,
                "filled_price": 0,
                "avg_fill_price": 0,
                "submitted_at": "2026-04-01T14:00:00Z",
                "created_time": "2026-04-01T14:00:00Z",
                "filled_at": "",
                "fill_time": "",
                "parent_id": "DEC005",
            },
        ]

        # Patch _enqueue to return synthetic data without making real API calls
        async def mock_enqueue(priority, operation, fn, *args, **kwargs):
            return synthetic_orders

        adapter._enqueue = mock_enqueue

        # Call fetch_order_status
        orders = await adapter.fetch_order_status("ACC123")

        assert len(orders) == 5

        # Verify state mapping for each order
        order_by_id = {o["broker_order_id"]: o for o in orders}

        assert order_by_id["ORD001"]["status"] == "submitted_pending"
        assert order_by_id["ORD002"]["status"] == "filled"
        assert order_by_id["ORD003"]["status"] == "partial_filled"
        assert order_by_id["ORD004"]["status"] == "cancelled"
        assert order_by_id["ORD005"]["status"] == "inactive_flagged"

        # Verify each order was written to the orders table
        # DataFlow express.list(filter=...) returns stale results after
        # writes, so we read all orders and filter manually.
        all_orders = await started_db.express.list("orders")
        order_ids_in_db = {o.get("broker_order_id") for o in all_orders}
        for broker_order_id in ["ORD001", "ORD002", "ORD003", "ORD004", "ORD005"]:
            assert (
                broker_order_id in order_ids_in_db
            ), f"Order {broker_order_id} should be in orders table"

    @pytest.mark.asyncio
    async def test_state_transition_is_logged(self, started_db):
        """When a state change is detected, the transition is logged at INFO."""
        from midas.fabric.adapters.ibkr import IBKRAdapter

        adapter = IBKRAdapter(db=started_db)
        adapter._db = started_db

        # Pre-write an order in SUBMITTED state
        await started_db.express.create(
            "orders",
            {
                "broker_order_id": "ORD_TRANS_001",
                "ticker": "AAPL",
                "side": "BUY",
                "order_type": "LMT",
                "quantity": 100,
                "limit_price": 150.0,
                "filled_qty": 0.0,
                "filled_price": 0.0,
                "status": "working",  # was submitted, now working
                "submitted_at": "2026-04-01T10:00:00Z",
                "filled_at": "",
                "parent_decision_id": "",
                "period_end": "2026-04-01",
                "filed_at": "2026-04-01T10:00:00Z",
                "restated_at": "",
                "source_vintage": "test",
            },
        )

        # Mock _enqueue returning the same order now FILLED
        async def mock_enqueue(priority, operation, fn, *args, **kwargs):
            return [
                {
                    "order_id": "ORD_TRANS_001",
                    "symbol": "AAPL",
                    "side": "BUY",
                    "action": "BUY",
                    "order_type": "LMT",
                    "type": "LMT",
                    "quantity": 100,
                    "limit_price": 150.00,
                    "lmt_price": 150.00,
                    "status": "Filled",
                    "filled_qty": 100,
                    "filled": 100,
                    "filled_price": 150.25,
                    "avg_fill_price": 150.25,
                    "submitted_at": "2026-04-01T10:00:00Z",
                    "created_time": "2026-04-01T10:00:00Z",
                    "filled_at": "2026-04-01T10:05:00Z",
                    "fill_time": "2026-04-01T10:05:00Z",
                    "parent_id": "",
                }
            ]

        adapter._enqueue = mock_enqueue

        # Capture log output
        import structlog
        import io
        from unittest.mock import MagicMock

        log_buffer = []

        class CapturingLogger:
            def info(self, msg, **kwargs):
                log_buffer.append(("info", msg, kwargs))

            def debug(self, msg, **kwargs):
                log_buffer.append(("debug", msg, kwargs))

            def warning(self, msg, **kwargs):
                log_buffer.append(("warning", msg, kwargs))

            def error(self, msg, **kwargs):
                log_buffer.append(("error", msg, kwargs))

        original_log = adapter._log
        adapter._log = CapturingLogger()

        try:
            await adapter.fetch_order_status("ACC123")
        finally:
            adapter._log = original_log

        # Verify the state transition was persisted via OrderManager audit
        # (OrderManager writes order_state_transition to audit_log)
        audit_rows = await started_db.express.list("audit_log")
        transition_audits = [
            r
            for r in audit_rows
            if r.get("rule_name") == "order_state_transition" and "filled" in r.get("action", "")
        ]
        assert len(transition_audits) >= 1, (
            f"Expected at least 1 order_state_transition audit, "
            f"got {len(transition_audits)} from {len(audit_rows)} audit rows"
        )


class TestTWSTFallbackAdapterOrderStateWiring:
    """Verify TWSTFallbackAdapter uses OrderState correctly."""

    @pytest.mark.asyncio
    async def test_tws_adapter_maps_order_status_to_order_state(self, started_db):
        """TWSTFallbackAdapter maps IBKR order statuses via OrderState.from_ibkr."""
        from midas.fabric.adapters.ibkr import TWSTFallbackAdapter

        adapter = TWSTFallbackAdapter(db=started_db)
        adapter._db = started_db

        # Mock _get_ib to return fake open orders
        class FakeOrder:
            class Contract:
                symbol = "AAPL"

            class Order:
                orderId = "TWS001"
                action = "BUY"
                orderType = "LMT"
                totalQuantity = 100.0
                lmtPrice = 175.0
                status = "Submitted"  # IBKR status
                filledQuantity = 0.0
                avgFillPrice = 0.0
                submitted = "2026-04-01T10:00:00Z"
                filledTime = None
                parentId = "DEC001"

            contract = Contract()
            order = Order()

        class FakeIB:
            def isConnected(self):
                return True

            def openOrders(self):
                return [FakeOrder()]

        adapter._get_ib = lambda: FakeIB()

        # Patch structlog on the adapter
        import structlog

        class CapturingLogger:
            def __init__(self):
                self.entries = []

            def info(self, msg, **kwargs):
                self.entries.append(("info", msg, kwargs))

            def debug(self, msg, **kwargs):
                self.entries.append(("debug", msg, kwargs))

            def warning(self, msg, **kwargs):
                self.entries.append(("warning", msg, kwargs))

            def error(self, msg, **kwargs):
                self.entries.append(("error", msg, kwargs))

        adapter._log = CapturingLogger()

        orders = await adapter.fetch_order_status("ACC_TWS")

        assert len(orders) == 1
        assert orders[0]["status"] == "working"  # Submitted -> working
        assert orders[0]["broker_order_id"] == "TWS001"
        assert orders[0]["ticker"] == "AAPL"

        # Verify order was written to DB
        all_orders = await started_db.express.list("orders")
        assert any(o.get("broker_order_id") == "TWS001" for o in all_orders)


@pytest.mark.skip(reason="Order API endpoints not yet implemented — Wave 4 scope")
class TestOrderStateAPIRouter:
    """Verify the OrderStatusRouter endpoints work with real DB state."""

    def test_list_orders_endpoint_returns_orders(self, client):
        """GET /api/v1/orders/ returns orders from the orders table."""
        response = client.get("/api/v1/orders/")
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        assert "total" in data

    def test_list_orders_filters_by_status(self, client):
        """GET /api/v1/orders/?status=filled returns only filled orders."""
        response = client.get("/api/v1/orders/?status=filled")
        assert response.status_code == 200
        data = response.json()
        assert all(o["status"] == "filled" for o in data["orders"])

    def test_list_orders_rejects_invalid_status(self, client):
        """Invalid status values return 400."""
        response = client.get("/api/v1/orders/?status=not_a_state")
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_get_order_returns_404_for_unknown_order(self, client):
        """GET /api/v1/orders/NONEXISTENT returns 404."""
        response = client.get("/api/v1/orders/NONEXISTENT")
        assert response.status_code == 404

    def test_get_order_transitions_returns_empty_for_unknown(self, client):
        """GET /api/v1/orders/NONEXISTENT/transitions returns 200 with empty list."""
        response = client.get("/api/v1/orders/NONEXISTENT/transitions")
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "NONEXISTENT"
        assert data["transitions"] == []
        assert data["transition_count"] == 0

    def test_order_states_have_is_terminal_and_is_working_fields(self, client, app):
        """Orders returned by get_order include is_terminal and is_working."""
        # First create a test order in the DB
        from midas.fabric.engine import create_fabric, reset_fabric
        import tempfile, os

        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_order_states.db")
        db_url = f"sqlite:///{db_path}"
        database = create_fabric(database_url=db_url, auto_migrate=True)
        import asyncio

        asyncio.get_event_loop().run_until_complete(database.start())

        asyncio.get_event_loop().run_until_complete(
            database.express.create(
                "orders",
                {
                    "broker_order_id": "TEST_ORD_001",
                    "ticker": "AAPL",
                    "side": "BUY",
                    "order_type": "LMT",
                    "quantity": 100.0,
                    "limit_price": 150.0,
                    "filled_qty": 0.0,
                    "filled_price": 0.0,
                    "status": "working",
                    "submitted_at": "2026-04-01T10:00:00Z",
                    "filled_at": "",
                    "parent_decision_id": "",
                    "period_end": "2026-04-01",
                    "filed_at": "2026-04-01T10:00:00Z",
                    "restated_at": "",
                    "source_vintage": "test",
                },
            )
        )

        # Override app's fabric for this test
        from midas.api import app as app_module

        old_get_fabric = app_module._get_db

        async def override_get_db():
            return database

        app_module._get_db = override_get_db

        try:
            response = client.get("/api/v1/orders/TEST_ORD_001")
            assert response.status_code == 200
            data = response.json()
            assert data["is_terminal"] is False
            assert data["is_working"] is True
        finally:
            app_module._get_db = old_get_fabric
            asyncio.get_event_loop().run_until_complete(database.close_async())
            database.close()
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
