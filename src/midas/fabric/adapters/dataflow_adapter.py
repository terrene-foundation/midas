"""
DataFlow adapter for the Midas fabric.

Implements FabricReader / FabricWriter against DataFlow's express API,
enforcing the PIT discipline on every query.

Ref: specs/03-universe-and-data.md §3.2 — DataFlow is the fabric substrate.
Ref: T-00-01
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from dataflow import DataFlow

from midas.fabric.models import (
    AS_OF_DATE_KEY,
    AuditLogRecord,
    DecisionRecord,
    FabricReader,
    FabricWriter,
    FundamentalRecord,
    LatentStateRecord,
    MacroRecord,
    ModelRegistryRecord,
    PITKey,
    PITQueryContext,
    PriceRecord,
    ShadowDecisionRecord,
    UniverseMembership,
)

if TYPE_CHECKING:
    pass


class DataFlowFabricReader(FabricReader):
    """DataFlow-backed fabric reader.

    Enforces Invariant (a): any feature at time t reads only rows
    whose filed_at ≤ t.
    """

    _df: DataFlow

    def __init__(self, df: DataFlow) -> None:
        self._df = df

    async def read_price(
        self,
        instrument: str,
        as_of: date,
        *,
        lookback_days: int = 30,
    ) -> list[PriceRecord]:
        ctx = PITQueryContext(as_of_date=as_of)
        rows = await self._df.express.list(
            "prices",
            filter={
                "instrument": instrument,
                AS_OF_DATE_KEY: ctx.as_of_date.isoformat(),
            },
            order_by="period_end",
        )
        if lookback_days and rows:
            from datetime import timedelta

            cutoff = as_of - timedelta(days=lookback_days)
            rows = [
                r
                for r in rows
                if date.fromisoformat(r.get("period_end", as_of.isoformat())) >= cutoff
            ]
        return [self._row_to_price(r) for r in rows]

    async def read_fundamentals(
        self,
        instrument: str,
        as_of: date,
    ) -> list[FundamentalRecord]:
        ctx = PITQueryContext(as_of_date=as_of)
        rows = await self._df.express.list(
            "fundamentals",
            filter={
                "instrument": instrument,
                AS_OF_DATE_KEY: ctx.as_of_date.isoformat(),
            },
        )
        return [self._row_to_fundamental(r) for r in rows]

    async def read_macro(
        self,
        series_code: str,
        as_of: date,
    ) -> list[MacroRecord]:
        ctx = PITQueryContext(as_of_date=as_of)
        rows = await self._df.express.list(
            "macro",
            filter={
                "series_code": series_code,
                AS_OF_DATE_KEY: ctx.as_of_date.isoformat(),
            },
        )
        return [self._row_to_macro(r) for r in rows]

    async def read_universe_membership(
        self,
        universe_segment: str,
        as_of: date,
    ) -> list[UniverseMembership]:
        ctx = PITQueryContext(as_of_date=as_of)
        rows = await self._df.express.list(
            "universe_membership",
            filter={
                "universe_segment": universe_segment,
                AS_OF_DATE_KEY: ctx.as_of_date.isoformat(),
            },
        )
        return [self._row_to_universe_membership(r) for r in rows]

    async def read_latent_state(
        self,
        learner_family: str,
        as_of: date,
    ) -> list[LatentStateRecord]:
        ctx = PITQueryContext(as_of_date=as_of)
        rows = await self._df.express.list(
            "latent_state",
            filter={
                "learner_family": learner_family,
                "learner_role": "champion",
                "filed_at": ctx.as_of_date.isoformat(),
            },
        )
        return [self._row_to_latent_state(r) for r in rows]

    async def read_model_registry(
        self,
        model_id: str,
        as_of: date,
    ) -> ModelRegistryRecord | None:
        ctx = PITQueryContext(as_of_date=as_of)
        rows = await self._df.express.list(
            "model_registry",
            filter={
                "model_id": model_id,
                AS_OF_DATE_KEY: ctx.as_of_date.isoformat(),
            },
        )
        if not rows:
            return None
        return self._row_to_model_registry(rows[0])

    # ------------------------------------------------------------------
    # Row -> Record helpers
    # ------------------------------------------------------------------

    def _row_to_price(self, row: dict) -> PriceRecord:
        return PriceRecord(
            instrument=row["instrument"],
            pit=PITKey(
                period_end=date.fromisoformat(row["period_end"]),
                filed_at=datetime.fromisoformat(row["filed_at"]),
                restated_at=(
                    datetime.fromisoformat(row["restated_at"]) if row.get("restated_at") else None
                ),
                source_vintage=row.get("source_vintage"),
            ),
            open=row.get("open"),
            high=row.get("high"),
            low=row.get("low"),
            close=row.get("close"),
            volume=row.get("volume"),
            dividend=row.get("dividend"),
            split_ratio=row.get("split_ratio"),
        )

    def _row_to_fundamental(self, row: dict) -> FundamentalRecord:
        return FundamentalRecord(
            instrument=row["instrument"],
            pit=PITKey(
                period_end=date.fromisoformat(row["period_end"]),
                filed_at=datetime.fromisoformat(row["filed_at"]),
                restated_at=(
                    datetime.fromisoformat(row["restated_at"]) if row.get("restated_at") else None
                ),
                source_vintage=row.get("source_vintage"),
            ),
            period_end=date.fromisoformat(row["period_end"]),
            fiscal_period=row.get("fiscal_period"),
            revenue=row.get("revenue"),
            ebitda=row.get("ebitda"),
            net_income=row.get("net_income"),
            book_value=row.get("book_value"),
            shares_outstanding=row.get("shares_outstanding"),
            pe_ratio=row.get("pe_ratio"),
            pb_ratio=row.get("pb_ratio"),
            de_ratio=row.get("de_ratio"),
            roe=row.get("roe"),
        )

    def _row_to_macro(self, row: dict) -> MacroRecord:
        return MacroRecord(
            series_code=row["series_code"],
            pit=PITKey(
                period_end=date.fromisoformat(row["period_end"]),
                filed_at=datetime.fromisoformat(row["filed_at"]),
                restated_at=(
                    datetime.fromisoformat(row["restated_at"]) if row.get("restated_at") else None
                ),
                source_vintage=row.get("source_vintage"),
            ),
            value=row.get("value"),
            unit=row.get("unit"),
            frequency=row.get("frequency"),
        )

    def _row_to_universe_membership(self, row: dict) -> UniverseMembership:
        return UniverseMembership(
            instrument=row["instrument"],
            pit=PITKey(
                period_end=date.fromisoformat(row["period_end"]),
                filed_at=datetime.fromisoformat(row["filed_at"]),
                restated_at=None,
                source_vintage=row.get("source_vintage"),
            ),
            universe_segment=row["universe_segment"],
            is_member=row.get("is_member", False),
            weight_in_index=row.get("weight_in_index"),
        )

    def _row_to_latent_state(self, row: dict) -> LatentStateRecord:
        import json

        z_vector_raw = row.get("z_vector", "")
        z_vector = (
            tuple(json.loads(z_vector_raw)) if z_vector_raw and z_vector_raw != "None" else ()
        )
        z_cov = None
        z_cov_raw = row.get("z_covariance", "")
        if z_cov_raw and z_cov_raw != "None":
            z_cov = tuple(tuple(r) for r in json.loads(z_cov_raw))

        return LatentStateRecord(
            state_id=row["state_id"],
            pit=PITKey(
                period_end=date.fromisoformat(row["period_end"]),
                filed_at=datetime.fromisoformat(row["filed_at"]),
                restated_at=None,
                source_vintage=None,
            ),
            learner_family=row["learner_family"],
            learner_role=row["learner_role"],
            z_dim=row.get("z_dim", len(z_vector)),
            z_vector=z_vector,
            z_covariance=z_cov,
            z_scale=row.get("z_scale"),
            pool_index=row.get("pool_index"),
        )

    def _row_to_model_registry(self, row: dict) -> ModelRegistryRecord:
        import json

        return ModelRegistryRecord(
            model_id=row["model_id"],
            pit=PITKey(
                period_end=date.today(),
                filed_at=datetime.now(),
                restated_at=None,
                source_vintage=None,
            ),
            family=row["family"],
            role=row["role"],
            version=row["version"],
            z_dim=row.get("z_dim"),
            training_window_start=(
                date.fromisoformat(row["training_window_start"])
                if row.get("training_window_start")
                else None
            ),
            training_window_end=(
                date.fromisoformat(row["training_window_end"])
                if row.get("training_window_end")
                else None
            ),
            calibration_snapshot=(
                json.loads(row["calibration_snapshot"]) if row.get("calibration_snapshot") else None
            ),
            probe_result=(json.loads(row["probe_result"]) if row.get("probe_result") else None),
        )


class DataFlowFabricWriter(FabricWriter):
    """DataFlow-backed fabric writer."""

    _df: DataFlow

    def __init__(self, df: DataFlow) -> None:
        self._df = df

    async def write_price(self, record: PriceRecord) -> None:
        await self._df.express.create(
            "prices",
            {
                "instrument": record.instrument,
                "period_end": record.pit.period_end.isoformat(),
                "filed_at": record.pit.filed_at.isoformat(),
                "restated_at": (
                    record.pit.restated_at.isoformat() if record.pit.restated_at else None
                ),
                "source_vintage": record.pit.source_vintage,
                "open": record.open,
                "high": record.high,
                "low": record.low,
                "close": record.close,
                "volume": record.volume,
                "dividend": record.dividend,
                "split_ratio": record.split_ratio,
            },
        )

    async def write_latent_state(self, record: LatentStateRecord) -> None:
        import json

        await self._df.express.create(
            "latent_state",
            {
                "state_id": record.state_id,
                "period_end": record.pit.period_end.isoformat(),
                "filed_at": record.pit.filed_at.isoformat(),
                "learner_family": record.learner_family,
                "learner_role": record.learner_role,
                "z_dim": record.z_dim,
                "z_vector": json.dumps(list(record.z_vector)),
                "z_covariance": (
                    json.dumps([list(row) for row in record.z_covariance])
                    if record.z_covariance
                    else None
                ),
                "z_scale": record.z_scale,
                "pool_index": record.pool_index,
            },
        )

    async def write_audit(self, record: AuditLogRecord) -> None:
        import json

        await self._df.express.create(
            "audit_log",
            {
                "audit_id": record.audit_id,
                "period_end": record.pit.period_end.isoformat(),
                "filed_at": record.pit.filed_at.isoformat(),
                "agent": record.agent,
                "rule_name": record.rule_name,
                "decision": record.decision,
                "details": json.dumps(record.details),
                "z_t_snapshot": list(record.z_t_snapshot) if record.z_t_snapshot else None,
            },
        )

    async def write_decision(self, record: DecisionRecord) -> None:
        import json

        await self._df.express.create(
            "decisions",
            {
                "decision_id": record.decision_id,
                "period_end": record.pit.period_end.isoformat(),
                "filed_at": record.pit.filed_at.isoformat(),
                "autonomy_level": record.autonomy_level,
                "brief": json.dumps(record.brief),
                "pool_outputs": json.dumps(record.pool_outputs),
                "router_decision": json.dumps(record.router_decision),
                "compliance_checks": json.dumps(record.compliance_checks),
                "user_action": record.user_action,
                "debate_thread_id": record.debate_thread_id,
                "execution_result": (
                    json.dumps(record.execution_result) if record.execution_result else None
                ),
                "counterfactual": (
                    json.dumps(record.counterfactual) if record.counterfactual else None
                ),
                "z_t_snapshot": list(record.z_t_snapshot) if record.z_t_snapshot else None,
            },
        )

    async def write_shadow_decision(self, record: ShadowDecisionRecord) -> None:
        import json

        await self._df.express.create(
            "shadow_decisions",
            {
                "shadow_decision_id": record.shadow_decision_id,
                "period_end": record.pit.period_end.isoformat(),
                "filed_at": record.pit.filed_at.isoformat(),
                "challenger_family": record.challenger_family,
                "challenger_version": record.challenger_version,
                "shadow_allocation": json.dumps(record.shadow_allocation),
                "hypothetical_pnl": record.hypothetical_pnl,
                "hypothetical_brinson": (
                    json.dumps(record.hypothetical_brinson) if record.hypothetical_brinson else None
                ),
                "pool_index": record.pool_index,
            },
        )
