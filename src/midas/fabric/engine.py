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
from typing import TYPE_CHECKING

from dataflow import DataFlow

from midas import config

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state — lazy singleton pattern
# ---------------------------------------------------------------------------

_fabric: DataFlow | None = None
_fabric_test: DataFlow | None = None


# ---------------------------------------------------------------------------
# Model registration
# ---------------------------------------------------------------------------


def _register_models(db: DataFlow) -> None:
    """Register all 23 fabric table models on the given DataFlow instance.

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
]


def create_fabric(
    database_url: str | None = None,
    *,
    test_mode: bool = False,
    auto_migrate: bool = True,
) -> DataFlow:
    """Create a new DataFlow instance with all fabric models registered.

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
        A fully-initialised DataFlow instance with all 23 fabric tables
        registered and (unless ``auto_migrate=False``) schema created.
    """
    url = "sqlite:///:memory:" if test_mode else (database_url or config.DATABASE_URL)

    logger.info(
        "fabric.create_fabric",
        extra={
            "test_mode": test_mode,
            "auto_migrate": auto_migrate,
            "database_type": "sqlite_memory" if test_mode else url.split("://")[0],
        },
    )

    db = DataFlow(url, auto_migrate=auto_migrate)
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
) -> DataFlow:
    """Return the lazily-initialised, singleton fabric DataFlow instance.

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
    DataFlow
        The shared fabric DataFlow instance.
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
    ``get_fabric()`` invocation creates a fresh DataFlow instance.
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
