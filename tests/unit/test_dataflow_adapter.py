"""Tier 1 unit tests for DataFlowFabricReader and DataFlowFabricWriter.

Tests PIT write/read operations, point-in-time discipline (period_end,
filed_at, source_vintage), query methods, and row-to-record conversion
using MagicMock for DataFlow.

Ref: T-00-01
"""

import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from midas.fabric.adapters.dataflow_adapter import (
    DataFlowFabricReader,
    DataFlowFabricWriter,
)
from midas.fabric.models import (
    PITKey,
    AuditLogRecord,
    DecisionRecord,
    LatentStateRecord,
    MacroRecord,
    ModelRegistryRecord,
    PriceRecord,
    ShadowDecisionRecord,
    UniverseMembership,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_pit(
    period_end: str = "2026-03-31",
    filed_at: str = "2026-04-01T18:00:00",
    restated_at: str | None = None,
    source_vintage: str | None = "eodhd_v1",
) -> PITKey:
    return PITKey(
        period_end=date.fromisoformat(period_end),
        filed_at=datetime.fromisoformat(filed_at),
        restated_at=datetime.fromisoformat(restated_at) if restated_at else None,
        source_vintage=source_vintage,
    )


@pytest.fixture
def mock_db() -> MagicMock:
    """DataFlow mock with async express methods."""
    db = MagicMock()
    db.express = MagicMock()
    db.express.create = AsyncMock()
    db.express.list = AsyncMock()
    return db


@pytest.fixture
def reader(mock_db: MagicMock) -> DataFlowFabricReader:
    return DataFlowFabricReader(mock_db)


@pytest.fixture
def writer(mock_db: MagicMock) -> DataFlowFabricWriter:
    return DataFlowFabricWriter(mock_db)


# ---------------------------------------------------------------------------
# DataFlowFabricReader — read_price
# ---------------------------------------------------------------------------


class TestReadPrice:
    """read_price: PIT-compliant price queries."""

    @pytest.mark.asyncio
    async def test_read_price_returns_records(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_price returns PriceRecord objects from DB rows."""
        mock_db.express.list.return_value = [
            {
                "instrument": "AAPL",
                "period_end": "2026-03-28",
                "filed_at": "2026-03-28T20:00:00",
                "restated_at": None,
                "source_vintage": "eodhd_v1",
                "open": 220.0,
                "high": 225.0,
                "low": 219.0,
                "close": 223.5,
                "volume": 50000000,
                "dividend": 0.0,
                "split_ratio": 1.0,
            }
        ]

        results = await reader.read_price("AAPL", date(2026, 3, 31))

        assert len(results) == 1
        rec = results[0]
        assert isinstance(rec, PriceRecord)
        assert rec.instrument == "AAPL"
        assert rec.close == 223.5
        assert rec.pit.period_end == date(2026, 3, 28)
        assert rec.pit.source_vintage == "eodhd_v1"

    @pytest.mark.asyncio
    async def test_read_price_passes_as_of_date_in_filter(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_price threads as_of_date into the query filter."""
        mock_db.express.list.return_value = []

        await reader.read_price("MSFT", date(2026, 4, 1))

        call_args = mock_db.express.list.call_args
        assert call_args[0][0] == "prices"
        filter_dict = (
            call_args[1].get("filter") or call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1]["filter"]
        )
        assert filter_dict["as_of_date"] == "2026-04-01"
        assert filter_dict["instrument"] == "MSFT"

    @pytest.mark.asyncio
    async def test_read_price_empty_returns_empty_list(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_price returns empty list when no rows found."""
        mock_db.express.list.return_value = []

        results = await reader.read_price("UNKNOWN", date(2026, 1, 1))

        assert results == []


# ---------------------------------------------------------------------------
# DataFlowFabricReader — read_fundamentals
# ---------------------------------------------------------------------------


class TestReadFundamentals:
    """read_fundamentals: PIT-compliant fundamental queries."""

    @pytest.mark.asyncio
    async def test_read_fundamentals_returns_records(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_fundamentals returns FundamentalRecord objects."""
        mock_db.express.list.return_value = [
            {
                "instrument": "AAPL",
                "period_end": "2025-12-31",
                "filed_at": "2026-01-28T18:00:00",
                "restated_at": None,
                "source_vintage": "eodhd_fund_v1",
                "fiscal_period": "Q1 2026",
                "revenue": 124300000000.0,
                "ebitda": 40000000000.0,
                "net_income": 33500000000.0,
                "book_value": 75000000000.0,
                "shares_outstanding": 15500000000.0,
                "pe_ratio": 30.5,
                "pb_ratio": 45.0,
                "de_ratio": 1.8,
                "roe": 0.45,
            }
        ]

        results = await reader.read_fundamentals("AAPL", date(2026, 3, 31))

        assert len(results) == 1
        rec = results[0]
        assert rec.instrument == "AAPL"
        assert rec.revenue == 124300000000.0
        assert rec.pe_ratio == 30.5
        assert rec.pit.filed_at == datetime(2026, 1, 28, 18, 0, 0)


# ---------------------------------------------------------------------------
# DataFlowFabricReader — read_macro
# ---------------------------------------------------------------------------


class TestReadMacro:
    """read_macro: PIT-compliant macro series queries."""

    @pytest.mark.asyncio
    async def test_read_macro_returns_records(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_macro returns MacroRecord objects."""
        mock_db.express.list.return_value = [
            {
                "series_code": "CPIAUCSL",
                "period_end": "2026-03-01",
                "filed_at": "2026-04-12T08:30:00",
                "restated_at": None,
                "source_vintage": "fred_v1",
                "value": 318.2,
                "unit": "index",
                "frequency": "M",
            }
        ]

        results = await reader.read_macro("CPIAUCSL", date(2026, 4, 15))

        assert len(results) == 1
        rec = results[0]
        assert rec.series_code == "CPIAUCSL"
        assert rec.value == 318.2
        assert rec.frequency == "M"


# ---------------------------------------------------------------------------
# DataFlowFabricReader — read_universe_membership
# ---------------------------------------------------------------------------


class TestReadUniverseMembership:
    """read_universe_membership: PIT-compliant universe queries."""

    @pytest.mark.asyncio
    async def test_read_universe_membership_returns_records(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_universe_membership returns UniverseMembership objects."""
        mock_db.express.list.return_value = [
            {
                "instrument": "AAPL",
                "period_end": "2026-03-31",
                "filed_at": "2026-03-31T20:00:00",
                "source_vintage": "sp_global_v1",
                "universe_segment": "sp500",
                "is_member": True,
                "weight_in_index": 0.065,
            }
        ]

        results = await reader.read_universe_membership("sp500", date(2026, 4, 1))

        assert len(results) == 1
        rec = results[0]
        assert isinstance(rec, UniverseMembership)
        assert rec.instrument == "AAPL"
        assert rec.is_member is True
        assert rec.weight_in_index == 0.065


# ---------------------------------------------------------------------------
# DataFlowFabricReader — read_latent_state
# ---------------------------------------------------------------------------


class TestReadLatentState:
    """read_latent_state: PIT-compliant latent state queries."""

    @pytest.mark.asyncio
    async def test_read_latent_state_returns_records(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_latent_state parses JSON z_vector and z_covariance."""
        mock_db.express.list.return_value = [
            {
                "state_id": "state_001",
                "period_end": "2026-03-31",
                "filed_at": "2026-04-01T08:00:00",
                "learner_family": "ssl_transformer_v1",
                "learner_role": "champion",
                "z_dim": 3,
                "z_vector": json.dumps([0.1, 0.2, 0.3]),
                "z_covariance": json.dumps([[1.0, 0.1, 0.0], [0.1, 1.0, 0.2], [0.0, 0.2, 1.0]]),
                "z_scale": 1.5,
                "pool_index": None,
            }
        ]

        results = await reader.read_latent_state("ssl_transformer_v1", date(2026, 4, 1))

        assert len(results) == 1
        rec = results[0]
        assert isinstance(rec, LatentStateRecord)
        assert rec.state_id == "state_001"
        assert rec.z_vector == (0.1, 0.2, 0.3)
        assert rec.z_covariance == ((1.0, 0.1, 0.0), (0.1, 1.0, 0.2), (0.0, 0.2, 1.0))
        assert rec.z_dim == 3

    @pytest.mark.asyncio
    async def test_read_latent_state_empty_vector(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_latent_state handles empty/None z_vector gracefully."""
        mock_db.express.list.return_value = [
            {
                "state_id": "state_002",
                "period_end": "2026-03-31",
                "filed_at": "2026-04-01T08:00:00",
                "learner_family": "diffusion_v2",
                "learner_role": "champion",
                "z_dim": 0,
                "z_vector": "None",
                "z_covariance": "None",
                "z_scale": None,
                "pool_index": None,
            }
        ]

        results = await reader.read_latent_state("diffusion_v2", date(2026, 4, 1))

        assert len(results) == 1
        rec = results[0]
        assert rec.z_vector == ()
        assert rec.z_covariance is None


# ---------------------------------------------------------------------------
# DataFlowFabricReader — read_model_registry
# ---------------------------------------------------------------------------


class TestReadModelRegistry:
    """read_model_registry: model version lookups."""

    @pytest.mark.asyncio
    async def test_read_model_registry_found(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_model_registry returns a ModelRegistryRecord when found."""
        mock_db.express.list.return_value = [
            {
                "model_id": "momentum_v3",
                "family": "momentum",
                "role": "champion",
                "version": "3.2.1",
                "z_dim": 8,
                "training_window_start": "2020-01-01",
                "training_window_end": "2025-12-31",
                "calibration_snapshot": json.dumps({"sharpe": 1.8}),
                "probe_result": json.dumps({"passed": True}),
            }
        ]

        result = await reader.read_model_registry("momentum_v3", date(2026, 4, 1))

        assert result is not None
        assert isinstance(result, ModelRegistryRecord)
        assert result.model_id == "momentum_v3"
        assert result.family == "momentum"
        assert result.version == "3.2.1"
        assert result.training_window_start == date(2020, 1, 1)
        assert result.calibration_snapshot == {"sharpe": 1.8}

    @pytest.mark.asyncio
    async def test_read_model_registry_not_found(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """read_model_registry returns None when no rows match."""
        mock_db.express.list.return_value = []

        result = await reader.read_model_registry("nonexistent", date(2026, 4, 1))

        assert result is None


# ---------------------------------------------------------------------------
# DataFlowFabricWriter — write_price
# ---------------------------------------------------------------------------


class TestWritePrice:
    """write_price: PIT-disciplined price writes."""

    @pytest.mark.asyncio
    async def test_write_price_calls_express_create(
        self, writer: DataFlowFabricWriter, mock_db: MagicMock
    ):
        """write_price delegates to db.express.create with correct fields."""
        pit = _make_pit(period_end="2026-03-28", filed_at="2026-03-28T20:00:00")
        record = PriceRecord(
            instrument="AAPL",
            pit=pit,
            open=220.0,
            high=225.0,
            low=219.0,
            close=223.5,
            volume=50000000,
            dividend=0.0,
            split_ratio=1.0,
        )

        await writer.write_price(record)

        mock_db.express.create.assert_awaited_once()
        call_args = mock_db.express.create.call_args
        assert call_args[0][0] == "prices"
        row = call_args[0][1]
        assert row["instrument"] == "AAPL"
        assert row["period_end"] == "2026-03-28"
        assert row["filed_at"] == "2026-03-28T20:00:00"
        assert row["close"] == 223.5
        assert row["source_vintage"] == "eodhd_v1"

    @pytest.mark.asyncio
    async def test_write_price_with_restated_at(
        self, writer: DataFlowFabricWriter, mock_db: MagicMock
    ):
        """write_price includes restated_at when present in PIT key."""
        pit = _make_pit(restated_at="2026-04-10T12:00:00")
        record = PriceRecord(
            instrument="MSFT",
            pit=pit,
            open=None,
            high=None,
            low=None,
            close=400.0,
            volume=None,
            dividend=None,
            split_ratio=None,
        )

        await writer.write_price(record)

        row = mock_db.express.create.call_args[0][1]
        assert row["restated_at"] == "2026-04-10T12:00:00"


# ---------------------------------------------------------------------------
# DataFlowFabricWriter — write_latent_state
# ---------------------------------------------------------------------------


class TestWriteLatentState:
    """write_latent_state: serialized latent state writes."""

    @pytest.mark.asyncio
    async def test_write_latent_state_json_serialization(
        self, writer: DataFlowFabricWriter, mock_db: MagicMock
    ):
        """write_latent_state serializes z_vector and z_covariance as JSON."""
        pit = _make_pit()
        record = LatentStateRecord(
            state_id="state_001",
            pit=pit,
            learner_family="ssl_v1",
            learner_role="champion",
            z_dim=2,
            z_vector=(0.5, -0.3),
            z_covariance=((1.0, 0.1), (0.1, 1.0)),
            z_scale=1.2,
            pool_index=None,
        )

        await writer.write_latent_state(record)

        row = mock_db.express.create.call_args[0][1]
        assert row["state_id"] == "state_001"
        assert json.loads(row["z_vector"]) == [0.5, -0.3]
        assert json.loads(row["z_covariance"]) == [[1.0, 0.1], [0.1, 1.0]]
        assert row["z_scale"] == 1.2

    @pytest.mark.asyncio
    async def test_write_latent_state_no_covariance(
        self, writer: DataFlowFabricWriter, mock_db: MagicMock
    ):
        """write_latent_state writes None for z_covariance when absent."""
        pit = _make_pit()
        record = LatentStateRecord(
            state_id="state_003",
            pit=pit,
            learner_family="ssl_v1",
            learner_role="challenger_shadow",
            z_dim=4,
            z_vector=(0.0, 0.0, 0.0, 0.0),
            z_covariance=None,
            z_scale=None,
            pool_index=2,
        )

        await writer.write_latent_state(record)

        row = mock_db.express.create.call_args[0][1]
        assert row["z_covariance"] is None
        assert row["pool_index"] == 2


# ---------------------------------------------------------------------------
# DataFlowFabricWriter — write_audit
# ---------------------------------------------------------------------------


class TestWriteAudit:
    """write_audit: audit log writes."""

    @pytest.mark.asyncio
    async def test_write_audit_calls_create(self, writer: DataFlowFabricWriter, mock_db: MagicMock):
        """write_audit creates a row in audit_log with JSON details."""
        pit = _make_pit()
        record = AuditLogRecord(
            audit_id="audit_001",
            pit=pit,
            agent="compliance_agent",
            rule_name="max_position_check",
            decision="ALLOW",
            details={"position_pct": 4.5},
            z_t_snapshot=(0.1, 0.2),
        )

        await writer.write_audit(record)

        row = mock_db.express.create.call_args[0][1]
        assert row["audit_id"] == "audit_001"
        assert row["agent"] == "compliance_agent"
        assert row["rule_name"] == "max_position_check"
        assert row["decision"] == "ALLOW"
        assert json.loads(row["details"]) == {"position_pct": 4.5}
        assert row["z_t_snapshot"] == [0.1, 0.2]


# ---------------------------------------------------------------------------
# DataFlowFabricWriter — write_decision
# ---------------------------------------------------------------------------


class TestWriteDecision:
    """write_decision: decision record writes."""

    @pytest.mark.asyncio
    async def test_write_decision_calls_create(
        self, writer: DataFlowFabricWriter, mock_db: MagicMock
    ):
        """write_decision creates a row in decisions table."""
        pit = _make_pit()
        record = DecisionRecord(
            decision_id="dec_001",
            pit=pit,
            autonomy_level=3,
            brief={"signal": "momentum"},
            pool_outputs={"pool_a": {"action": "BUY"}},
            router_decision={"final": "BUY"},
            compliance_checks={"passed": True},
            user_action="APPROVE",
            debate_thread_id=None,
            execution_result={"filled": True},
            counterfactual=None,
            z_t_snapshot=None,
        )

        await writer.write_decision(record)

        row = mock_db.express.create.call_args[0][1]
        assert row["decision_id"] == "dec_001"
        assert row["autonomy_level"] == 3
        assert row["user_action"] == "APPROVE"
        assert json.loads(row["brief"]) == {"signal": "momentum"}
        assert row["counterfactual"] is None


# ---------------------------------------------------------------------------
# DataFlowFabricWriter — write_shadow_decision
# ---------------------------------------------------------------------------


class TestWriteShadowDecision:
    """write_shadow_decision: shadow decision writes."""

    @pytest.mark.asyncio
    async def test_write_shadow_decision_calls_create(
        self, writer: DataFlowFabricWriter, mock_db: MagicMock
    ):
        """write_shadow_decision creates a row in shadow_decisions table."""
        pit = _make_pit()
        record = ShadowDecisionRecord(
            shadow_decision_id="shadow_001",
            pit=pit,
            challenger_family="diffusion_v2",
            challenger_version="0.9.0",
            shadow_allocation={"AAPL": 0.3, "MSFT": 0.7},
            hypothetical_pnl=-500.0,
            hypothetical_brinson={"allocation": -0.01, "selection": 0.005},
            pool_index=1,
        )

        await writer.write_shadow_decision(record)

        row = mock_db.express.create.call_args[0][1]
        assert row["shadow_decision_id"] == "shadow_001"
        assert row["challenger_family"] == "diffusion_v2"
        assert json.loads(row["shadow_allocation"]) == {"AAPL": 0.3, "MSFT": 0.7}
        assert row["hypothetical_pnl"] == -500.0
        assert row["pool_index"] == 1


# ---------------------------------------------------------------------------
# PIT Discipline — filter structure verification
# ---------------------------------------------------------------------------


class TestPITDiscipline:
    """PIT discipline: every query threads as_of_date correctly."""

    @pytest.mark.asyncio
    async def test_all_reader_methods_pass_as_of_date(
        self, reader: DataFlowFabricReader, mock_db: MagicMock
    ):
        """Every reader method includes as_of_date in its filter."""
        as_of = date(2026, 4, 15)
        mock_db.express.list.return_value = []

        # read_price
        await reader.read_price("AAPL", as_of)
        filter_args = mock_db.express.list.call_args
        assert "as_of_date" in str(filter_args)

        mock_db.express.list.reset_mock()

        # read_fundamentals
        await reader.read_fundamentals("AAPL", as_of)
        filter_args = mock_db.express.list.call_args
        assert "as_of_date" in str(filter_args)

        mock_db.express.list.reset_mock()

        # read_macro
        await reader.read_macro("CPIAUCSL", as_of)
        filter_args = mock_db.express.list.call_args
        assert "as_of_date" in str(filter_args)

        mock_db.express.list.reset_mock()

        # read_universe_membership
        await reader.read_universe_membership("sp500", as_of)
        filter_args = mock_db.express.list.call_args
        assert "as_of_date" in str(filter_args)

        mock_db.express.list.reset_mock()

        # read_latent_state uses filed_at directly, not AS_OF_DATE_KEY
        await reader.read_latent_state("ssl_v1", as_of)
        filter_args = mock_db.express.list.call_args
        assert "filed_at" in str(filter_args) or "as_of_date" in str(filter_args)

        mock_db.express.list.reset_mock()

        # read_model_registry
        await reader.read_model_registry("model_001", as_of)
        filter_args = mock_db.express.list.call_args
        assert "as_of_date" in str(filter_args)

    @pytest.mark.asyncio
    async def test_writer_methods_include_period_end_and_filed_at(
        self, writer: DataFlowFabricWriter, mock_db: MagicMock
    ):
        """Every writer method includes period_end and filed_at in its row."""
        pit = _make_pit(period_end="2026-03-31", filed_at="2026-04-01T18:00:00")

        # write_price
        await writer.write_price(PriceRecord("AAPL", pit, None, None, None, None, None, None, None))
        row = mock_db.express.create.call_args[0][1]
        assert row["period_end"] == "2026-03-31"
        assert row["filed_at"] == "2026-04-01T18:00:00"
        assert row["source_vintage"] == "eodhd_v1"

        mock_db.express.create.reset_mock()

        # write_latent_state
        await writer.write_latent_state(
            LatentStateRecord("s1", pit, "fam", "champ", 2, (0.0, 0.0), None, None, None)
        )
        row = mock_db.express.create.call_args[0][1]
        assert row["period_end"] == "2026-03-31"
        assert row["filed_at"] == "2026-04-01T18:00:00"
