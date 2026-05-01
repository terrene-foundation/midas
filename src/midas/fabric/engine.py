"""
Fabric engine — creates and manages the DataFlow instance for all fabric tables.

Provides a single DataFlow instance with all 23 fabric models registered.
Callers use ``get_fabric()`` to obtain the initialized database.

The engine supports two modes:

* **Production** — reads ``DATABASE_URL`` from config, connects to PostgreSQL.
* **Test** — pass ``test_mode=True`` for an in-memory SQLite instance suitable
  for Tier 1 unit tests.

Ref: specs/03-universe-and-data.md S3.3 (Fabric Layout)
Ref: T-01-01
"""

import logging
from typing import TYPE_CHECKING, List, Dict, Any

from dataflow import DataFlow, DataFlowConfig, FilterCondition

from midas import config

if TYPE_CHECKING:
    from midas.ml import ModelRegistry

logger = logging.getLogger(__name__)


class _DataFlowExpressAsync:
    """Thin adapter exposing DataFlowExpress async CRUD methods.

    DataFlowExpress methods are already ``async def``, so this wrapper simply
    delegates with the ``model_name`` → ``model`` kwarg renaming the midas
    codebase expects (``express.create("orders", data)`` vs
    ``express.create(model="orders", data=data)``).
    """

    __slots__ = ("_inner",)

    def __init__(self, inner):
        self._inner = inner

    async def create(self, model_name: str, data: Dict) -> Dict:
        return await self._inner.create_async(model_name, data)

    async def read(self, model_name: str, id: int | str) -> Dict:
        return await self._inner.read_async(model_name, id)

    async def list(self, model_name: str, filter: Dict | None = None) -> List[Dict]:
        if not filter:
            fc_list: List[FilterCondition] = []
        else:
            fc_list = [FilterCondition.eq(str(col), val) for col, val in filter.items()]
        return await self._inner.list_async(model_name, fc_list)

    async def update(self, model_name: str, id: int | str, fields: Dict) -> Dict:
        return await self._inner.update_async(model_name, id, fields)

    async def delete(self, model_name: str, id: int | str) -> Dict:
        return await self._inner.delete_async(model_name, id)

    async def upsert(self, model_name: str, data: Dict) -> Dict:
        return await self._inner.upsert_async(model_name, data)

    async def bulk_create(self, model_name: str, rows: List[Dict]) -> List[Dict]:
        return await self._inner.bulk_create_async(model_name, rows)

    async def bulk_update(self, model_name: str, rows: List[Dict]) -> List[Dict]:
        return self._inner.bulk_update(model_name, rows)

    async def bulk_delete(self, model_name: str, ids: List[int | str]) -> List[Dict]:
        return self._inner.bulk_delete(model_name, ids)

    async def bulk_upsert(self, model_name: str, rows: List[Dict]) -> List[Dict]:
        return self._inner.bulk_upsert(model_name, rows)

    async def count(self, model_name: str, filter: Dict | None = None) -> int:
        if not filter:
            fc_list: List[FilterCondition] = []
        else:
            fc_list = [FilterCondition.eq(str(col), val) for col, val in filter.items()]
        return await self._inner.count_async(model_name, fc_list)

    async def count_by(self, model_name: str, field: str, value: Any) -> int:
        return self._inner.count_by(model_name, field, value)

    async def sum_by(self, model_name: str, field: str, value: Any) -> float:
        return self._inner.sum_by(model_name, field, value)

    async def aggregate(
        self, model_name: str, aggs: List[Dict], group_by: List[str] | None = None
    ) -> List[Dict]:
        return self._inner.aggregate(model_name, aggs, group_by)


class MidasFabric(DataFlow):
    """DataFlow subclass that exposes the ModelRegistry facade and express CRUD."""

    _midas_model_registry: "ModelRegistry | None" = None
    _express_async: _DataFlowExpressAsync | None = None

    @property
    def model_registry(self) -> "ModelRegistry":
        """Lazy-loaded ModelRegistry facade for model pool management."""
        if self._midas_model_registry is None:
            from midas.ml import ModelRegistry

            self._midas_model_registry = ModelRegistry(self)
        return self._midas_model_registry

    @property
    def express(self) -> _DataFlowExpressAsync:
        """Async express CRUD interface (create, read, list, update, delete, etc.)."""
        if self._express_async is None:
            self._express_async = _DataFlowExpressAsync(self._inner.express)
        return self._express_async

    async def start(self) -> None:
        """Start the database (no-op; connection is established in __init__)."""
        pass


# ---------------------------------------------------------------------------
# Module-level state — lazy singleton pattern
# ---------------------------------------------------------------------------

_fabric: MidasFabric | None = None
_fabric_test: MidasFabric | None = None


# ---------------------------------------------------------------------------
# Model registration
# ---------------------------------------------------------------------------


def _register_models(db: DataFlow) -> None:
    """Register all 31 fabric table models on the given DataFlow instance.

    Every model follows the DataFlow conventions:

    * PK field is named ``id`` (int, auto-managed).
    * Timestamps (``created_at``, ``updated_at``) are NOT declared — DataFlow
      adds them automatically.
    * Optional fields use simple assignment defaults (not ``field()``).

    Ref: specs/03-universe-and-data.md S3.3
    """

    # -- 1. prices -----------------------------------------------------------
    @db.model
    class prices:
        id: int
        ticker: str
        period_end: str
        open: float = 0.0
        high: float = 0.0
        low: float = 0.0
        close: float = 0.0
        adj_close: float = 0.0
        volume: float = 0.0
        source: str = "eodhd"
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 2. corporate_actions ------------------------------------------------
    @db.model
    class corporate_actions:
        id: int
        ticker: str
        period_end: str
        action_type: str
        value: float = 0.0
        description: str = ""
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 3. fundamentals -----------------------------------------------------
    @db.model
    class fundamentals:
        id: int
        ticker: str
        period_end: str
        filed_at: str
        restated_at: str = ""
        source_vintage: str = ""
        revenue: float = 0.0
        earnings: float = 0.0
        book_value: float = 0.0
        debt: float = 0.0
        cash: float = 0.0
        shares_outstanding: float = 0.0
        pe_ratio: float = 0.0
        pb_ratio: float = 0.0
        roe: float = 0.0
        source: str = "eodhd"

    # -- 4. filings ----------------------------------------------------------
    @db.model
    class filings:
        id: int
        ticker: str
        filing_type: str
        filed_at: str
        document_url: str = ""
        title: str = ""
        embedding_id: str = ""
        source: str = "sec_edgar"

    # -- 5. news -------------------------------------------------------------
    @db.model
    class news:
        id: int
        ticker: str = ""
        headline: str
        summary: str = ""
        source: str = ""
        published_at: str
        url: str = ""
        embedding_id: str = ""
        portfolio_impact: str = ""
        sentiment_score: float = 0.0

    # -- 6. macro ------------------------------------------------------------
    @db.model
    class macro:
        id: int
        series_name: str
        period_end: str
        value: float = 0.0
        vintage: str = ""
        source: str = "fred"
        unit: str = ""
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 7. alt_data ---------------------------------------------------------
    @db.model
    class alt_data:
        id: int
        series_name: str
        period_end: str
        value: float = 0.0
        source: str = ""
        metadata_json: str = ""
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 8. features ---------------------------------------------------------
    @db.model
    class features:
        id: int
        instrument: str
        feature_name: str
        feature_version: str = "feature_v1"
        as_of_date: str
        value: float = 0.0
        computation_hash: str = ""
        filed_at: str = ""
        status: str = "active"

    # -- 9. embeddings -------------------------------------------------------
    @db.model
    class embeddings:
        id: int
        source_type: str
        source_id: str = ""
        content_hash: str
        embedding_blob: str = ""
        model_name: str = ""

    # -- 10. latent_state ----------------------------------------------------
    @db.model
    class latent_state:
        id: int
        state_id: str = ""
        period_end: str = ""
        filed_at: str = ""
        learner_family: str = ""
        learner_role: str = ""  # champion | challenger_shadow
        z_dim: int = 0
        z_vector: str = ""  # JSON-encoded list of floats
        z_covariance: str = ""  # JSON-encoded diagonal covariance
        z_scale: float = 0.0
        pool_index: int = 0

    # -- 11. positions -------------------------------------------------------
    @db.model
    class positions:
        id: int
        ticker: str
        quantity: float = 0.0
        avg_cost: float = 0.0
        current_price: float = 0.0
        market_value: float = 0.0
        unrealized_pnl: float = 0.0
        as_of_date: str
        source: str = "ibkr"
        account_id: str = ""

    # -- 12. orders ----------------------------------------------------------
    @db.model
    class orders:
        id: int
        ticker: str
        side: str
        order_type: str
        quantity: float = 0.0
        limit_price: float = 0.0
        status: str = "pending"
        filled_qty: float = 0.0
        filled_price: float = 0.0
        submitted_at: str = ""
        filled_at: str = ""
        broker_order_id: str = ""
        parent_decision_id: str = ""

    # -- 13. decisions -------------------------------------------------------
    @db.model
    class decisions:
        id: int
        decision_type: str
        instruments: str = ""
        action: str = ""
        rationale: str = ""
        brief_json: str = ""
        outcome_json: str = ""
        counterfactual_json: str = ""
        confidence: float = 0.0
        autonomy_level: int = 0
        model_version: str = ""
        z_t_snapshot: str = ""
        created_at_day: str = ""
        user_id: str = ""  # Owner of the decision; required for authorization

    # -- 14. shadow_decisions ------------------------------------------------
    @db.model
    class shadow_decisions:
        id: int
        model_family: str
        model_version: str
        decision_type: str
        instruments: str = ""
        action: str = ""
        rationale: str = ""
        confidence: float = 0.0
        z_t_snapshot: str = ""
        created_at_day: str = ""
        diverges_from_champion: bool = False

    # -- 15. model_registry --------------------------------------------------
    @db.model
    class model_registry:
        id: int
        model_family: str
        model_version: str
        model_type: str = ""
        training_window_start: str = ""
        training_window_end: str = ""
        calibration_json: str = ""
        promotion_status: str = "shadow"
        sample_count: int = 0
        parameter_count: int = 0
        trained_at: str = ""
        config_hash: str = ""
        parent_version: str = ""
        pool_layer: str = ""
        metrics_json: str = ""

    # -- 16. universe_changelog ----------------------------------------------
    @db.model
    class universe_changelog:
        id: int
        ticker: str
        action: str
        reason: str = ""
        effective_date: str
        backtest_impact: str = ""

    # -- 17. audit_log -------------------------------------------------------
    @db.model
    class audit_log:
        id: int
        audit_id: str = ""
        rule_name: str
        action: str
        details: str = ""
        severity: str = "info"
        instrument: str = ""
        decision_id: str = ""
        agent: str = ""
        period_end: str = ""
        filed_at: str = ""
        z_t_snapshot: str = ""

    # -- 18. quotes ----------------------------------------------------------
    @db.model
    class quotes:
        id: int
        ticker: str
        bid_price: float = 0.0
        ask_price: float = 0.0
        bid_size: float = 0.0
        ask_size: float = 0.0
        mid_price: float = 0.0
        spread_bps: float = 0.0
        timestamp: str
        period_end: str = ""
        source: str = "ibkr"
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 19. fills -----------------------------------------------------------
    @db.model
    class fills:
        id: int
        order_id: str = ""
        ticker: str
        fill_price: float = 0.0
        fill_qty: float = 0.0
        commission: float = 0.0
        exchange_fee: float = 0.0
        regulatory_fee: float = 0.0
        venue: str = ""
        fill_timestamp: str
        broker_fill_id: str = ""
        period_end: str = ""
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 20. fills_synthetic -------------------------------------------------
    @db.model
    class fills_synthetic:
        id: int
        scenario_name: str
        ticker: str = ""
        fill_price: float = 0.0
        fill_qty: float = 0.0
        expected_partial: bool = False
        scenario_json: str = ""
        period_end: str = ""
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 21. fee_schedule ----------------------------------------------------
    @db.model
    class fee_schedule:
        id: int
        fee_type: str
        tier_min: float = 0.0
        tier_max: float = 0.0
        rate_per_share: float = 0.0
        min_commission: float = 0.0
        max_commission_pct: float = 0.0
        effective_date: str
        source: str = "ibkr"

    # -- 22. cost_attribution ------------------------------------------------
    @db.model
    class cost_attribution:
        id: int
        trade_id: str
        ticker: str = ""
        spread_cost: float = 0.0
        impact_cost: float = 0.0
        commission: float = 0.0
        tax: float = 0.0
        slippage: float = 0.0
        gap_cost: float = 0.0
        total_cost: float = 0.0
        timestamp: str
        period_end: str = ""
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 23. sweep_history ---------------------------------------------------
    @db.model
    class sweep_history:
        id: int
        base_currency: str = "USD"
        target_currency: str = "SGD"
        amount: float = 0.0
        rate: float = 0.0
        fee: float = 0.0
        sweep_timestamp: str
        broker_sweep_id: str = ""
        period_end: str = ""
        filed_at: str = ""
        restated_at: str = ""
        source_vintage: str = ""

    # -- 24. credentials ------------------------------------------------------
    @db.model
    class credentials:
        id: int
        service: str
        key_name: str
        encrypted_value: str
        expires_at: str = ""
        last_rotated_at: str = ""
        active: bool = True

    # -- 25. compliance_rules ------------------------------------------------
    @db.model
    class compliance_rules:
        id: int
        rule_id: str
        rule_name: str
        category: str  # block | escalate | warn
        severity: str
        description: str
        predicate_config: str = ""  # JSON config, NOT eval-able code
        is_active: bool = True
        created_at: str = ""
        updated_at: str = ""

    # -- 26. users -----------------------------------------------------------
    @db.model
    class users:
        id: int
        email: str
        password_hash: str

    # -- 27. sessions --------------------------------------------------------
    @db.model
    class sessions:
        id: int
        user_id: int
        refresh_token_hash: str
        expires_at: str = ""
        revoked_at: str = ""

    # -- 28. notification_settings --------------------------------------------
    @db.model
    class notification_settings:
        id: int
        user_id: int  # 0 for global default settings
        tiers_json: str = "{}"  # JSON-serialized notification tiers
        quiet_hours_start: str = "22:00"
        quiet_hours_end: str = "07:00"
        quiet_hours_timezone: str = "Asia/Singapore"
        daily_attention_ceiling_minutes: int = 30

    # -- 29. paper_live_settings -----------------------------------------------
    @db.model
    class paper_live_settings:
        id: int
        user_id: int  # 0 for global settings
        paper_trading_active: bool = True
        live_start_date: str = ""  # ISO date string when live mode began
        report_acknowledged_at: str = ""  # ISO datetime user acknowledged the report
        report_acknowledged_by: str = ""  # user identifier

    # -- 30. notifications ----------------------------------------------------
    @db.model
    class notification:
        id: int
        user_id: str = ""  # string to match user_id type in decisions table
        notification_type: str = (
            "PORTFOLIO_ALERT"  # PORTFOLIO_ALERT | REGIME_CHANGE | TRADE_CONFIRMATION
        )
        title: str = ""
        body: str = ""
        read: bool = False
        metadata_json: str = "{}"  # extra context (instrument, decision_id, etc.)

    # -- 31. debate_threads ----------------------------------------------------
    @db.model
    class debate_threads:
        id: int
        thread_id: str = ""  # UUID string for external reference
        decision_id: str = ""
        status: str = "open"  # open | updated | maintained | closed
        turns_json: str = "[]"  # JSON-encoded list of debate turns
        portfolio_context_json: str = "{}"  # JSON-encoded live portfolio snapshot
        created_at: str = ""

    # -- 32. briefs -----------------------------------------------------------
    @db.model
    class briefs:
        id: int
        title: str
        hypothesis: str = ""
        constraints: str = ""
        regime_assumptions: str = ""
        metrics: str = ""
        status: str = "draft"  # draft | active | archived
        version: int = 1

    # -- 33. brief_versions ----------------------------------------------------
    @db.model
    class brief_versions:
        id: int
        brief_id: int
        version: int
        title: str = ""
        hypothesis: str = ""
        constraints: str = ""
        regime_assumptions: str = ""
        metrics: str = ""
        status: str = "draft"
        created_at: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# All fabric table names for reference and validation.
FABRIC_TABLES: list[str] = [
    "prices",
    "corporate_actions",
    "fundamentals",
    "filings",
    "news",
    "macro",
    "alt_data",
    "features",
    "embeddings",
    "latent_state",
    "positions",
    "orders",
    "decisions",
    "shadow_decisions",
    "model_registry",
    "universe_changelog",
    "audit_log",
    "quotes",
    "fills",
    "fills_synthetic",
    "fee_schedule",
    "cost_attribution",
    "sweep_history",
    "credentials",
    "compliance_rules",
    "users",
    "sessions",
    "notification_settings",
    "paper_live_settings",
    "notification",
    "debate_threads",
    "briefs",
    "brief_versions",
]


def create_fabric(
    database_url: str | None = None,
    *,
    test_mode: bool = False,
    auto_migrate: bool = True,
) -> MidasFabric:
    """Create a new MidasFabric instance with all fabric models registered.

    Parameters
    ----------
    database_url:
        Database connection string.  Defaults to ``config.DATABASE_URL``.
        Ignored when ``test_mode=True`` (in-memory SQLite is used instead).
    test_mode:
        Use in-memory SQLite.  Intended for Tier 1 unit tests only.
    auto_migrate:
        Let DataFlow auto-generate tables from the ``@db.model`` definitions.
        Set to ``False`` only if you are managing migrations yourself.

    Returns
    -------
    DataFlow
        A fully-initialised DataFlow instance with all 33 fabric tables
        registered and (unless ``auto_migrate=False``) schema created.
    """
    url = "sqlite:///:memory:" if test_mode else (database_url or config.DATABASE_URL)

    # Convert SQLAlchemy SQLite URL format to Rust dataflow format.
    # SQLAlchemy:  sqlite:///relative   (3 slashes = relative path)
    #              sqlite:////absolute  (4 slashes = absolute path)
    #              sqlite:///:memory:   (special in-memory)
    # Rust dataflow: sqlite::memory:  (in-memory)
    #                sqlite:path?mode=rwc  (file, read-write-create)
    if url.startswith("sqlite:///"):
        if url == "sqlite:///:memory:":
            url = "sqlite::memory:"
        else:
            path = url[len("sqlite:///") :]
            url = f"sqlite:{path}?mode=rwc"

    logger.info(
        "fabric.create_fabric",
        extra={
            "test_mode": test_mode,
            "auto_migrate": auto_migrate,
            "database_type": "sqlite_memory" if test_mode else url.split(":")[0],
        },
    )

    db = MidasFabric(
        url, config=DataFlowConfig(database_url=url, auto_migrate=auto_migrate, test_mode=test_mode)
    )
    _register_models(db)

    logger.info(
        "fabric.create_fabric.ok",
        extra={"tables_registered": len(FABRIC_TABLES)},
    )

    return db


async def get_fabric(
    database_url: str | None = None,
    *,
    test_mode: bool = False,
) -> MidasFabric:
    """Return the lazily-initialised, singleton fabric MidasFabric instance.

    On first call the instance is created and all models are registered.
    Subsequent calls return the cached instance.

    Parameters
    ----------
    database_url:
        Override the database URL.  Only takes effect on the first call.
    test_mode:
        Use in-memory SQLite.  Separate singleton from the production
        instance so that tests do not pollute the real database.

    Returns
    -------
    MidasFabric
        The shared fabric MidasFabric instance with model_registry facade.
    """
    global _fabric, _fabric_test

    if test_mode:
        if _fabric_test is None:
            _fabric_test = create_fabric(test_mode=True)
        return _fabric_test

    if _fabric is None:
        _fabric = create_fabric(database_url=database_url)
    return _fabric


def reset_fabric() -> None:
    """Reset the cached fabric instances.

    Primarily for use in test teardown.  After calling this, the next
    ``get_fabric()`` invocation creates a fresh MidasFabric instance.
    """
    global _fabric, _fabric_test

    if _fabric is not None:
        try:
            _fabric.close()
        except Exception:
            pass
        _fabric = None

    if _fabric_test is not None:
        try:
            _fabric_test.close()
        except Exception:
            pass
        _fabric_test = None
