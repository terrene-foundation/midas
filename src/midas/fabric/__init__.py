"""Midas Data Fabric.

Every raw source lands in the fabric. Every model reads only from the fabric.
No model calls an external API directly.

Ref: specs/03-universe-and-data.md section 3 (Data Fabric Pattern)
"""

from midas.fabric.cache import FabricCache
from midas.fabric.engine import (
    FABRIC_TABLES,
    create_fabric,
    get_fabric,
    reset_fabric,
)
from midas.fabric.features import FeatureStore
from midas.fabric.freshness import FreshnessGate, FreshnessResult
from midas.fabric.models import (
    AS_OF_DATE_KEY,
    PITVintage,
    FundamentalRecord,
    MacroRecord,
    UniverseMembership,
    IndexConstituency,
    PriceRecord,
    CorporateAction,
    FilingRecord,
    NewsRecord,
    AltDataRecord,
    FeatureRecord,
    EmbeddingRecord,
    LatentStateRecord,
    PositionRecord,
    OrderRecord,
    DecisionRecord,
    ShadowDecisionRecord,
    ModelRegistryRecord,
    UniverseChangelogRecord,
    AuditLogRecord,
    QuoteRecord,
    FillRecord,
    FillSyntheticRecord,
    FeeScheduleRecord,
    CostAttributionRecord,
    SweepHistoryRecord,
    PITQueryContext,
    FabricReader,
    FabricWriter,
)

__all__ = [
    # Engine
    "FABRIC_TABLES",
    "create_fabric",
    "get_fabric",
    "reset_fabric",
    # Cache layer (T-01-10)
    "FabricCache",
    # Stale-data gate (T-01-11)
    "FreshnessGate",
    "FreshnessResult",
    # Feature store (T-01-12)
    "FeatureStore",
    # PIT constants & types
    "AS_OF_DATE_KEY",
    "PITVintage",
    "PITQueryContext",
    # Domain records
    "FundamentalRecord",
    "MacroRecord",
    "UniverseMembership",
    "IndexConstituency",
    "PriceRecord",
    "CorporateAction",
    "FilingRecord",
    "NewsRecord",
    "AltDataRecord",
    "FeatureRecord",
    "EmbeddingRecord",
    "LatentStateRecord",
    "PositionRecord",
    "OrderRecord",
    "DecisionRecord",
    "ShadowDecisionRecord",
    "ModelRegistryRecord",
    "UniverseChangelogRecord",
    "AuditLogRecord",
    "QuoteRecord",
    "FillRecord",
    "FillSyntheticRecord",
    "FeeScheduleRecord",
    "CostAttributionRecord",
    "SweepHistoryRecord",
    # Abstract interfaces
    "FabricReader",
    "FabricWriter",
]
