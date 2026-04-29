"""Tier 1 tests for the fabric engine and DataFlow model registration."""

import os
import tempfile

import pytest

from midas.fabric.engine import create_fabric, FABRIC_TABLES, reset_fabric


@pytest.fixture
def db():
    """Create an in-memory test DataFlow instance with all fabric models."""
    database = create_fabric(test_mode=True)
    yield database
    reset_fabric()


@pytest.fixture
async def adb():
    """Async fixture: create DataFlow on a temp file SQLite for CRUD tests.

    In-memory SQLite causes DataFlow's migration system to hang.
    A temp file avoids that while staying fully local.
    """
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_fabric.db")
    db_url = f"sqlite:///{db_path}"
    database = create_fabric(database_url=db_url, auto_migrate=True)
    await database.start()
    yield database
    try:
        await database.close_async()
    except Exception:
        pass
    reset_fabric()
    # Cleanup temp file
    try:
        os.unlink(db_path)
    except OSError:
        pass
    # Remove WAL/SHM files DataFlow may create
    for suffix in ("-wal", "-shm"):
        try:
            os.unlink(db_path + suffix)
        except OSError:
            pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


class TestFabricEngine:
    """Tests for fabric engine creation and model registration."""

    def test_all_tables_registered(self, db):
        """T-01-01: All fabric tables must be registered."""
        models = db.list_models()
        assert len(models) == len(FABRIC_TABLES)

    def test_expected_tables_present(self, db):
        """T-01-01: Every table from the spec must exist."""
        models = set(db.list_models())
        for table in FABRIC_TABLES:
            assert table in models, f"Missing fabric table: {table}"

    def test_fabric_tables_constant_matches(self):
        """T-01-01: FABRIC_TABLES constant has correct count."""
        assert len(FABRIC_TABLES) == 33

    def test_duplicate_free_table_list(self):
        """T-01-01: No duplicate table names."""
        assert len(FABRIC_TABLES) == len(set(FABRIC_TABLES))


class TestFabricCRUD:
    """Tier 1 tests for basic CRUD on fabric models via DataFlow express."""

    @pytest.mark.asyncio
    async def test_prices_create_and_list(self, adb):
        """T-01-01: Prices table supports create and list read-back."""
        result = await adb.express.create(
            "prices",
            {
                "ticker": "SPY",
                "period_end": "2024-01-02",
                "open": 470.0,
                "high": 475.0,
                "low": 469.0,
                "close": 474.0,
                "volume": 1000000.0,
                "filed_at": "2024-01-03T00:00:00+00:00",
            },
        )
        assert result is not None
        assert result.get("rows_affected", 0) >= 1

        rows = await adb.express.list("prices", filter={"ticker": "SPY"})
        assert len(rows) >= 1
        assert rows[0]["ticker"] == "SPY"
        assert rows[0]["close"] == 474.0

    @pytest.mark.asyncio
    async def test_fundamentals_pit_fields(self, adb):
        """T-01-01: Fundamentals carry PIT tuple (period_end, filed_at, restated_at, source_vintage)."""
        await adb.express.create(
            "fundamentals",
            {
                "ticker": "AAPL",
                "period_end": "2024-03-31",
                "filed_at": "2024-04-26",
                "restated_at": "",
                "source_vintage": "eodhd:2024-04-26",
                "revenue": 90753.0,
                "earnings": 23636.0,
            },
        )
        rows = await adb.express.list("fundamentals", filter={"ticker": "AAPL"})
        assert len(rows) >= 1
        row = rows[0]
        assert row["period_end"] == "2024-03-31"
        assert row["filed_at"] == "2024-04-26"
        assert row["source_vintage"] == "eodhd:2024-04-26"

    @pytest.mark.asyncio
    async def test_features_versioned(self, adb):
        """T-01-01: Features are versioned with feature_version field."""
        await adb.express.create(
            "features",
            {
                "instrument": "SPY",
                "feature_name": "momentum_20d",
                "feature_version": "feature_v1",
                "as_of_date": "2024-01-15",
                "value": 0.032,
            },
        )
        await adb.express.create(
            "features",
            {
                "instrument": "SPY",
                "feature_name": "momentum_20d",
                "feature_version": "feature_v2",
                "as_of_date": "2024-01-15",
                "value": 0.028,
            },
        )
        rows = await adb.express.list("features", filter={"instrument": "SPY"})
        assert len(rows) >= 2
        versions = {r["feature_version"] for r in rows}
        assert "feature_v1" in versions
        assert "feature_v2" in versions

    @pytest.mark.asyncio
    async def test_orders_create(self, adb):
        """T-01-01: Orders table accepts new orders with status field."""
        result = await adb.express.create(
            "orders",
            {
                "ticker": "SPY",
                "side": "buy",
                "order_type": "limit",
                "quantity": 100.0,
                "limit_price": 470.0,
                "status": "pending",
            },
        )
        assert result.get("rows_affected", 0) >= 1
        rows = await adb.express.list("orders", filter={"ticker": "SPY"})
        assert len(rows) >= 1
        assert rows[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_decisions_with_context(self, adb):
        """T-01-01: Decisions carry z_t_snapshot and autonomy_level."""
        await adb.express.create(
            "decisions",
            {
                "decision_type": "rebalance",
                "instruments": "SPY,TLT,GLD",
                "action": "overweight SPY +5%",
                "rationale": "Latent state shift to risk-on",
                "confidence": 0.72,
                "autonomy_level": 2,
                "model_version": "router_v3",
                "z_t_snapshot": "[0.12, -0.03, 0.87]",
            },
        )
        rows = await adb.express.list("decisions", filter={"decision_type": "rebalance"})
        assert len(rows) >= 1
        assert rows[0]["z_t_snapshot"] == "[0.12, -0.03, 0.87]"
        assert rows[0]["autonomy_level"] == 2

    @pytest.mark.asyncio
    async def test_shadow_decisions_isolated(self, adb):
        """T-01-01: Shadow decisions store diverges_from_champion flag."""
        await adb.express.create(
            "shadow_decisions",
            {
                "model_family": "transformer_v2",
                "model_version": "shadow_v2.3",
                "decision_type": "rebalance",
                "action": "hold",
                "diverges_from_champion": True,
            },
        )
        rows = await adb.express.list("shadow_decisions", filter={"model_family": "transformer_v2"})
        assert len(rows) >= 1
        # SQLite stores booleans as integers (0/1)
        assert bool(rows[0]["diverges_from_champion"]) is True

    @pytest.mark.asyncio
    async def test_quotes_spread_bps(self, adb):
        """T-01-01: Quotes carry spread in basis points."""
        await adb.express.create(
            "quotes",
            {
                "ticker": "SPY",
                "bid_price": 470.10,
                "ask_price": 470.15,
                "mid_price": 470.125,
                "spread_bps": 1.06,
                "timestamp": "2024-01-15T10:30:00Z",
            },
        )
        rows = await adb.express.list("quotes", filter={"ticker": "SPY"})
        assert len(rows) >= 1
        assert rows[0]["spread_bps"] == 1.06

    @pytest.mark.asyncio
    async def test_cost_attribution_decomposition(self, adb):
        """T-01-01: Cost attribution decomposes into 6 cost components."""
        await adb.express.create(
            "cost_attribution",
            {
                "trade_id": "T-001",
                "ticker": "SPY",
                "spread_cost": 1.06,
                "impact_cost": 2.50,
                "commission": 1.00,
                "tax": 0.0,
                "slippage": 0.50,
                "gap_cost": 0.0,
                "total_cost": 5.06,
                "timestamp": "2024-01-15T10:30:00Z",
            },
        )
        rows = await adb.express.list("cost_attribution", filter={"trade_id": "T-001"})
        assert len(rows) >= 1
        assert rows[0]["total_cost"] == 5.06
        assert rows[0]["tax"] == 0.0  # No capital gains tax (FP-6)

    @pytest.mark.asyncio
    async def test_audit_log_entries(self, adb):
        """T-01-01: Audit log records rule evaluations."""
        await adb.express.create(
            "audit_log",
            {
                "rule_name": "stale_data_gate",
                "action": "blocked",
                "severity": "warn",
                "instrument": "SPY",
                "details_json": '{"staleness_seconds": 86401}',
            },
        )
        rows = await adb.express.list("audit_log", filter={"rule_name": "stale_data_gate"})
        assert len(rows) >= 1
        assert rows[0]["severity"] == "warn"

    @pytest.mark.asyncio
    async def test_universe_changelog(self, adb):
        """T-01-01: Universe changelog tracks additions/removals with reason."""
        await adb.express.create(
            "universe_changelog",
            {
                "ticker": "XYZ",
                "action": "added",
                "reason": "liquidity_floor_met",
                "effective_date": "2024-03-01",
                "backtest_impact": "+2bps_annualized",
            },
        )
        rows = await adb.express.list("universe_changelog", filter={"ticker": "XYZ"})
        assert len(rows) >= 1
        assert rows[0]["action"] == "added"
        assert rows[0]["reason"] == "liquidity_floor_met"
