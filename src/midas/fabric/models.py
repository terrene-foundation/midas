"""
Point-in-Time (PIT) Fabric Models.

Every fabric row carrying a time-varying attribute is addressable by a
point-in-time `as_of_date`.  The PIT tuple is:

    (period_end, filed_at, restated_at, source_vintage)

- period_end   : the business date the record describes
- filed_at     : when the data became available to a reasonable reader
- restated_at  : when the data was last revised (None if never revised)
- source_vintage: the identifier of the data source version (e.g. FRED series_id
  at a specific revision date)

Invariant (a): any feature at time t reads only rows whose filed_at ≤ t
Invariant (b): restated data uses the vintage active at t, not the latest restatement
Invariant (c): S&P 1500 membership is queried as-of t

Ref: specs/03-universe-and-data.md §4.3 (Walk-Forward Discipline)
Ref: T-00-01
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, TypeVar

# ---------------------------------------------------------------------------
# Public Constants
# ---------------------------------------------------------------------------

# Key used to carry as_of_date through query contexts
AS_OF_DATE_KEY = "as_of_date"


class PITVintage(Enum):
    """Known vintage classes for the ALFRED-style tracking."""

    CURRENT = "current"  # latest available
    REVISED = "revised"  # a subsequent revision was published
    PRELIMINARY = "preliminary"  # first release, subject to revision
    CONFIRMED = "confirmed"  # final confirmed value


# ---------------------------------------------------------------------------
# PIT Dataclasses — shared tuple across all time-varying fabric tables
# ---------------------------------------------------------------------------

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PITKey:
    """The canonical four-tuple addressing any time-varying fabric record."""

    period_end: date
    filed_at: datetime
    restated_at: datetime | None = None
    source_vintage: str | None = None

    def is_active_at(self, as_of: datetime | date) -> bool:
        """Return True when this record was the live vintage as of `as_of`."""
        effective_as_of = (
            datetime.combine(as_of, datetime.min.time())
            if isinstance(as_of, date) and not isinstance(as_of, datetime)
            else as_of
        )
        return self.filed_at <= effective_as_of

    def is_superseded_at(self, as_of: datetime | date) -> bool:
        """Return True when a newer vintage was already live as of `as_of`."""
        if self.restated_at is None:
            return False
        effective_as_of = (
            datetime.combine(as_of, datetime.min.time())
            if isinstance(as_of, date) and not isinstance(as_of, datetime)
            else as_of
        )
        return self.restated_at <= effective_as_of

    def fingerprint(self) -> str:
        """Short deterministic hash of the vintage tuple for log-safe IDs."""
        raw = (
            f"{self.period_end.isoformat()}"
            f"{self.filed_at.isoformat()}"
            f"{self.restated_at.isoformat() if self.restated_at else ''}"
            f"{self.source_vintage or ''}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


@dataclass
class PITQueryContext:
    """Carries the point-in-time constraint through every fabric query.

    Ref: T-00-01 Invariant (a) — as_of_date must be threaded through every
    feature computation and backtest.
    """

    as_of_date: date
    vintage_class: PITVintage | None = None
    source_vintage_filter: str | None = None
    _raw: dict[str, Any] = field(default_factory=dict)

    def to_filter(self) -> dict[str, Any]:
        """Build a DataFlow-compatible filter dict for PIT-compliant reads."""
        f = {AS_OF_DATE_KEY: self.as_of_date.isoformat()}
        if self.vintage_class:
            f["vintage_class"] = self.vintage_class.value
        if self.source_vintage_filter:
            f["source_vintage"] = self.source_vintage_filter
        return f


# ---------------------------------------------------------------------------
# Fabric Record Models — each wraps a PIT key + domain payload
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceRecord:
    """OHLCV keyed by (instrument, period_end) with PIT tuple."""

    instrument: str
    pit: PITKey
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    dividend: float | None
    split_ratio: float | None


@dataclass(frozen=True)
class CorporateAction:
    """Splits, dividends, mergers keyed by (instrument, period_end)."""

    instrument: str
    pit: PITKey
    action_type: str  # SPLIT | DIVIDEND | MERGER | SPINOFF
    effective_date: date
    ratio_or_amount: float | None
    ticker_after: str | None


@dataclass(frozen=True)
class FundamentalRecord:
    """Financial statements and ratios keyed by (instrument, period_end, filed_at).

    Ref: specs/03- §2.2 — EODHD Fundamentals primary.
    """

    instrument: str
    pit: PITKey
    # Reported period
    period_end: date
    fiscal_period: str | None  # e.g. "Q3 2024"
    # Statements
    revenue: float | None
    ebitda: float | None
    net_income: float | None
    book_value: float | None
    shares_outstanding: float | None
    # Ratios
    pe_ratio: float | None
    pb_ratio: float | None
    de_ratio: float | None
    roe: float | None


@dataclass(frozen=True)
class MacroRecord:
    """Macro series keyed by (series_code, period_end) with PIT tuple.

    Ref: specs/03- §2.4 — FRED, OECD CLI, IMF WEO.
    """

    series_code: str
    pit: PITKey
    value: float | None
    unit: str | None  # e.g. "percent", "index", "USD billions"
    frequency: str | None  # D | W | M | Q | A


@dataclass(frozen=True)
class UniverseMembership:
    """ETF or index membership as of period_end.

    Invariant (c): S&P 1500 membership is queried as-of t.
    """

    instrument: str
    pit: PITKey
    universe_segment: str  # e.g. "sector_equity", "factor_etf", "sp1500"
    is_member: bool
    weight_in_index: float | None  # None means excluded


@dataclass(frozen=True)
class IndexConstituency:
    """Specific index weight for a constituent on a given rebalance date."""

    index_code: str  # e.g. "SPX", "VTI"
    instrument: str
    pit: PITKey
    weight: float | None
    shares_held: float | None


@dataclass(frozen=True)
class FilingRecord:
    """Raw document references + embedding IDs for SEC EDGAR filings."""

    filing_id: str
    pit: PITKey
    instrument: str | None
    form_type: str  # 10-K | 10-Q | 8-K | S-1 | ...
    filed_date: date
    period_end: date | None
    accession_number: str
    embedding_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NewsRecord:
    """Headlines with embedding IDs and portfolio-impact tags."""

    headline_id: str
    pit: PITKey
    headline: str
    published_at: datetime
    tickers: tuple[str, ...] = field(default_factory=tuple)
    embedding_ids: tuple[str, ...] = field(default_factory=tuple)
    sentiment_score: float | None = None
    impact_tag: str | None = None  # REDUCTION | ADDITION | NEUTRAL | ...


@dataclass(frozen=True)
class AltDataRecord:
    """Alternative data series keyed by (series_id, period_end)."""

    series_id: str
    pit: PITKey
    value: float | None
    source: str | None  # Google Trends | Truflation | ...
    category: str | None  # macro | sentiment | pricing | ...


@dataclass(frozen=True)
class FeatureRecord:
    """Pre-computed features, versioned under features_v{N}.

    Ref: specs/03- §4.1 — features are versioned; old versions stay queryable.
    """

    feature_id: str  # e.g. "momentum_20d_v2"
    version: str  # e.g. "v3"
    pit: PITKey
    instrument: str | None
    value: float | None
    dimensions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EmbeddingRecord:
    """pgvector index entry for text RAG."""

    embedding_id: str
    pit: PITKey
    text_snippet: str
    source_type: str  # filing | news | research | macro_brief
    source_id: str  # filing_id | headline_id | ...
    vector: tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LatentStateRecord:
    """Historical z_t posteriors from champion and challenger learners.

    Ref: specs/04- §2.3 — z_t is a family of candidate posteriors.
    """

    state_id: str
    pit: PITKey
    learner_family: str  # e.g. "ssl_transformer_v1", "diffusion_v2"
    learner_role: str  # champion | challenger_shadow
    z_dim: int
    z_vector: tuple[float, ...]  # center-of-mass of the posterior
    z_covariance: tuple[tuple[float, ...], ...] | None  # full covariance matrix
    z_scale: float | None  # posterior width proxy (mean std across dimensions)
    pool_index: int | None  # position in challenger pool if not champion


@dataclass(frozen=True)
class PositionRecord:
    """Current and historical portfolio positions (IBKR-authoritative)."""

    position_id: str
    pit: PITKey
    instrument: str
    quantity: float
    entry_price: float
    current_price: float
    unrealised_pnl: float
    as_of: datetime


class OrderState(Enum):
    """IBKR order states mapped to Midas canonical states.

    Includes Midas-internal lifecycle states (PENDING, RECONCILED, ATTRIBUTED)
    that extend the IBKR-mapped states for full order lifecycle management.

    Ref: specs/14-ibkr-integration.md S6 (order state table).
    """

    # Midas-internal (not from IBKR)
    PENDING = "pending"  # Pre-submission — order created locally, not yet sent
    RECONCILED = "reconciled"  # Post-fill — fills verified against execution brief
    ATTRIBUTED = "attributed"  # Post-reconciliation — costs attributed, fully terminal

    # IBKR-mapped states per spec 14 S6
    SUBMITTED_PENDING = "submitted_pending"  # PendingSubmit — awaiting initial confirmation
    CANCEL_PENDING = "cancel_pending"  # PendingCancel — cancellation in flight
    SUBMITTED_WAITING = "submitted_waiting"  # PreSubmitted — broker-held, not yet active
    WORKING = "working"  # Submitted — active, working the quote
    PARTIAL_FILLED = "partial_filled"  # Filled (partial) — some quantity filled
    FILLED = "filled"  # Filled (complete) — terminal
    CANCELLED = "cancelled"  # Cancelled — terminal
    CANCELLED_API = "cancelled_api"  # ApiCancelled — terminal, API-initiated
    INACTIVE_FLAGGED = "inactive_flagged"  # Inactive — trap state, requires intervention
    REJECTED = "rejected"  # Rejection taxonomy from IBKR

    @classmethod
    def terminal_states(cls) -> set["OrderState"]:
        """Return the set of terminal states (no further transitions expected)."""
        return {cls.CANCELLED, cls.CANCELLED_API, cls.ATTRIBUTED, cls.REJECTED}

    @classmethod
    def from_ibkr(cls, ibkr_status: str) -> "OrderState":
        """Map IBKR status string to Midas OrderState.

        Ref: specs/14-ibkr-integration.md S6 table.
        """
        mapping = {
            "pendingsubmit": cls.SUBMITTED_PENDING,
            "pendingcancel": cls.CANCEL_PENDING,
            "presubmitted": cls.SUBMITTED_WAITING,
            "submitted": cls.WORKING,
            "filled": cls.FILLED,
            "cancelled": cls.CANCELLED,
            "apicancelled": cls.CANCELLED_API,
            "inactive": cls.INACTIVE_FLAGGED,
            "partiallyfilled": cls.PARTIAL_FILLED,
        }
        return mapping.get(ibkr_status.lower(), cls.REJECTED)

    def is_terminal(self) -> bool:
        """Return True if this state requires no further transitions."""
        return self in self.terminal_states()

    def is_working(self) -> bool:
        """Return True if this state represents an active working order."""
        return self in {
            self.PENDING,
            self.SUBMITTED_PENDING,
            self.CANCEL_PENDING,
            self.SUBMITTED_WAITING,
            self.WORKING,
            self.PARTIAL_FILLED,
        }

    def is_cancellable(self) -> bool:
        """Return True if this state can transition to CANCEL_PENDING."""
        return self in {
            self.PENDING,
            self.SUBMITTED_PENDING,
            self.SUBMITTED_WAITING,
            self.WORKING,
        }


@dataclass(frozen=True)
class OrderRecord:
    """Order state machine history.

    Ref: specs/14-ibkr-integration.md §6 — order state machine.
    """

    order_id: str
    pit: PITKey
    instrument: str
    side: str  # BUY | SELL
    order_type: str  # MARKET | LIMIT | STOP
    quantity: float
    limit_price: float | None
    fill_price: float | None
    fill_quantity: float | None
    status: OrderState
    submitted_at: datetime
    last_updated_at: datetime


@dataclass(frozen=True)
class OrderStateTransition:
    """Immutable record of an order state transition.

    Every order state change (including initial submission) is recorded as
    one of these. Used for audit trail and state machine verification.

    Ref: specs/14-ibkr-integration.md §6.
    """

    transition_id: str
    order_id: str
    pit: PITKey
    from_state: OrderState | None  # None for initial submission
    to_state: OrderState
    transition_reason: str  # e.g. "ibkr_fill", "user_cancel", "risk_reject"
    ibkr_message: str | None  # Raw IBKR message if available
    occurred_at: datetime


@dataclass(frozen=True)
class DecisionRecord:
    """Every decision with full brief + outcome + counterfactual.

    Ref: specs/07- §7 — immutable audit provenance.
    """

    decision_id: str
    pit: PITKey
    autonomy_level: int  # 0-4
    brief: dict[str, Any]
    pool_outputs: dict[str, Any]
    router_decision: dict[str, Any]
    compliance_checks: dict[str, Any]
    user_action: str  # APPROVE | REJECT | MODIFY | DEBATE
    debate_thread_id: str | None
    execution_result: dict[str, Any] | None
    counterfactual: dict[str, Any] | None  # 1d/1w/1m realized paths
    z_t_snapshot: tuple[float, ...] | None


@dataclass(frozen=True)
class ShadowDecisionRecord:
    """Hypothetical decisions from challenger models — never reaches live systems."""

    shadow_decision_id: str
    pit: PITKey
    challenger_family: str
    challenger_version: str
    shadow_allocation: dict[str, float]
    hypothetical_pnl: float | None
    hypothetical_brinson: dict[str, float] | None
    pool_index: int | None


@dataclass(frozen=True)
class ModelRegistryRecord:
    """Model versions, training windows, calibration snapshots."""

    model_id: str
    pit: PITKey
    family: str
    role: str  # champion | challenger | baseline
    version: str
    z_dim: int | None
    training_window_start: date | None
    training_window_end: date | None
    calibration_snapshot: dict[str, Any] | None
    probe_result: dict[str, Any] | None  # T-00-02 output stored here


@dataclass(frozen=True)
class UniverseChangelogRecord:
    """Every universe add/remove with reason."""

    change_id: str
    pit: PITKey
    instrument: str
    action: str  # ADDED | REMOVED
    reason: str
    backtest_impact: str | None
    notified_at: datetime | None


@dataclass(frozen=True)
class AuditLogRecord:
    """Every rule-engine decision, compliance veto, escalation."""

    audit_id: str
    pit: PITKey
    agent: str  # compliance_agent | autonomy_ladder | kill_switch | ...
    rule_name: str
    decision: str  # ALLOW | VETO | ESCALATE | DEMOTE | TRIP | CLEAR
    details: dict[str, Any]
    z_t_snapshot: tuple[float, ...] | None


# ---------------------------------------------------------------------------
# Execution-layer tables (ref: specs/13- §8, specs/14-)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuoteRecord:
    """Bid/ask + size keyed by (instrument, timestamp).

    Ref: specs/13- §8 — feeds spread and cost model.
    """

    quote_id: str
    instrument: str
    timestamp: datetime
    bid_price: float | None
    ask_price: float | None
    bid_size: int | None
    ask_size: int | None
    venue: str | None
    as_of_date: date  # as_of_date for PIT filter


@dataclass(frozen=True)
class FillRecord:
    """IBKR execution record — price, qty, fees, venue, timestamp.

    Ref: specs/13- §8 — feeds slippage calibration.
    """

    fill_id: str
    pit: PITKey
    order_id: str
    instrument: str
    fill_price: float
    fill_quantity: float
    commission: float
    regulatory_fees: float
    venue: str | None
    timestamp: datetime
    is_paper: bool


@dataclass(frozen=True)
class FillSyntheticRecord:
    """Synthesized partial-fill scenarios for order-state-machine testing.

    Ref: specs/14- §9.3 — IBKR partial-fill-during-approval protocol.
    """

    scenario_id: str
    pit: PITKey
    parent_order_id: str
    fills: tuple[dict[str, Any], ...]  # list of partial fill dicts
    total_expected_quantity: float
    description: str


@dataclass(frozen=True)
class FeeScheduleRecord:
    """Versioned IBKR commission + regulatory-fee schedule.

    Ref: specs/13- §2.3.
    """

    schedule_id: str
    pit: PITKey
    effective_from: date
    effective_to: date | None
    commission_per_share: float | None
    minimum_per_order: float | None
    regulatory_fees: dict[str, float] | None


@dataclass(frozen=True)
class CostAttributionRecord:
    """Realized cost decomposition per trade.

    Ref: specs/13- §8 — spread / impact / commission / tax / slippage / gap.
    """

    trade_id: str
    pit: PITKey
    instrument: str
    spread_cost: float
    market_impact_cost: float
    commission_cost: float
    tax_cost: float  # e.g. dividend withholding
    slippage_cost: float
    gap_cost: float
    total_cost: float


@dataclass(frozen=True)
class SweepHistoryRecord:
    """IBKR FX sweep events for SGD/USD accounting.

    Ref: specs/14- §11.
    """

    sweep_id: str
    pit: PITKey
    from_currency: str
    to_currency: str
    amount_converted: float
    exchange_rate: float
    fees: float
    executed_at: datetime


# ---------------------------------------------------------------------------
# Fabric Access Protocol
# ---------------------------------------------------------------------------


class FabricReader(ABC):
    """Abstract reader enforcing PIT discipline on every query.

    Every concrete adapter (DataFlow, direct SQL, etc.) implements this
    interface.  The `as_of` parameter is mandatory on every read method.
    """

    @abstractmethod
    async def read_price(
        self,
        instrument: str,
        as_of: date,
        *,
        lookback_days: int = 30,
    ) -> list[PriceRecord]:
        """Read price history for instrument, respecting as_of_date discipline."""
        ...

    @abstractmethod
    async def read_fundamentals(
        self,
        instrument: str,
        as_of: date,
    ) -> list[FundamentalRecord]:
        """Read fundamentals active as of as_of_date (invariant a)."""
        ...

    @abstractmethod
    async def read_macro(
        self,
        series_code: str,
        as_of: date,
    ) -> list[MacroRecord]:
        """Read macro series using the vintage active as of as_of_date."""
        ...

    @abstractmethod
    async def read_universe_membership(
        self,
        universe_segment: str,
        as_of: date,
    ) -> list[UniverseMembership]:
        """Read universe membership as of as_of_date (invariant c)."""
        ...

    @abstractmethod
    async def read_latent_state(
        self,
        learner_family: str,
        as_of: date,
    ) -> list[LatentStateRecord]:
        """Read z_t posterior from the champion as of as_of_date."""
        ...

    @abstractmethod
    async def read_model_registry(
        self,
        model_id: str,
        as_of: date,
    ) -> ModelRegistryRecord | None:
        """Read model registry entry using the vintage active as of as_of_date."""
        ...

    @abstractmethod
    async def read_positions(
        self,
        instrument: str,
        as_of: date,
    ) -> list[PositionRecord]:
        """Read current portfolio positions for an instrument."""
        ...

    @abstractmethod
    async def read_decisions(
        self,
        instrument: str,
        as_of: date,
        lookback_days: int = 730,
        limit: int = 5,
    ) -> list[DecisionRecord]:
        """Read historical decision records for an instrument within a lookback window."""
        ...


class FabricWriter(ABC):
    """Abstract writer for fabric records."""

    @abstractmethod
    async def write_price(self, record: PriceRecord) -> None: ...

    @abstractmethod
    async def write_latent_state(self, record: LatentStateRecord) -> None: ...

    @abstractmethod
    async def write_audit(self, record: AuditLogRecord) -> None: ...

    @abstractmethod
    async def write_decision(self, record: DecisionRecord) -> None: ...

    @abstractmethod
    async def write_shadow_decision(self, record: ShadowDecisionRecord) -> None: ...
