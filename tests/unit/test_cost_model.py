"""Tier 1 tests for the execution cost model.

Ref: specs/13-execution-cost-and-microstructure.md
Ref: src/midas/execution/cost_model.py
"""

import math

import pytest

from midas.execution.cost_model import (
    ExecutionCostModel,
    LiquidityTier,
    TIER_PARAMS,
)


@pytest.fixture
def model():
    return ExecutionCostModel()


# ---------------------------------------------------------------------------
# Almgren-Chriss impact model (spec S2.2)
# ---------------------------------------------------------------------------


class TestEstimateImpact:
    """Verify Almgren-Chriss impact estimation."""

    def test_zero_size_zero_impact(self, model):
        result = model.estimate_impact(0, 1_000_000, 0.02)
        assert result["total_impact"] == 0.0

    def test_basic_impact_positive(self, model):
        result = model.estimate_impact(10_000, 1_000_000, 0.02)
        assert result["total_impact"] > 0
        assert result["temp_impact"] > 0
        assert result["perm_impact"] > 0

    def test_larger_order_more_impact(self, model):
        small = model.estimate_impact(1_000, 1_000_000, 0.02)
        large = model.estimate_impact(100_000, 1_000_000, 0.02)
        assert large["total_impact"] > small["total_impact"]

    def test_higher_vol_more_impact(self, model):
        calm = model.estimate_impact(10_000, 1_000_000, 0.01)
        volatile = model.estimate_impact(10_000, 1_000_000, 0.05)
        assert volatile["total_impact"] > calm["total_impact"]

    def test_zero_adv_returns_inf(self, model):
        result = model.estimate_impact(10_000, 0, 0.02)
        assert result["total_impact"] == float("inf")

    def test_l1_less_impact_than_l4(self, model):
        l1 = model.estimate_impact(10_000, 1_000_000, 0.02, LiquidityTier.L1_DEEP)
        l4 = model.estimate_impact(10_000, 1_000_000, 0.02, LiquidityTier.L4_THIN)
        assert l1["total_impact"] < l4["total_impact"]

    def test_impact_bps_positive(self, model):
        result = model.estimate_impact(10_000, 1_000_000, 0.02)
        assert result["impact_bps"] > 0

    def test_returns_tier_label(self, model):
        result = model.estimate_impact(10_000, 1_000_000, 0.02, LiquidityTier.L3_MODERATE)
        assert result["tier"] == "L3"

    def test_custom_schedule_volume(self, model):
        result = model.estimate_impact(10_000, 1_000_000, 0.02, schedule_volume=500_000)
        assert result["total_impact"] > 0


# ---------------------------------------------------------------------------
# Participation cap (spec S4.3)
# ---------------------------------------------------------------------------


class TestParticipationCap:
    """Verify participation cap checks."""

    def test_small_order_passes(self, model):
        result = model.check_participation_cap(1_000, 1_000_000)
        assert result["passes"] is True

    def test_huge_order_fails(self, model):
        result = model.check_participation_cap(500_000, 1_000_000)
        assert result["passes"] is False

    def test_elevated_tightens_cap(self, model):
        calm = model.check_participation_cap(50_000, 1_000_000, regime="calm")
        elevated = model.check_participation_cap(50_000, 1_000_000, regime="elevated")
        assert elevated["cap_pct"] <= calm["cap_pct"]

    def test_crisis_blocks_all(self, model):
        result = model.check_participation_cap(1, 1_000_000, regime="crisis")
        assert result["cap_pct"] == 0.0
        assert result["passes"] is False

    def test_l4_gets_stricter_cap(self, model):
        l2 = model.check_participation_cap(30_000, 1_000_000, LiquidityTier.L2_LIQUID)
        l4 = model.check_participation_cap(30_000, 1_000_000, LiquidityTier.L4_THIN)
        assert l4["cap_pct"] <= l2["cap_pct"]

    def test_zero_adv_fails(self, model):
        result = model.check_participation_cap(100, 0)
        assert result["passes"] is False


# ---------------------------------------------------------------------------
# Liquidity tiering (spec S5)
# ---------------------------------------------------------------------------


class TestLiquidityTiering:
    """Verify liquidity tier classification."""

    def test_deep_liquidity(self, model):
        assert model.classify_tier(50_000_000) == LiquidityTier.L1_DEEP

    def test_liquid(self, model):
        assert model.classify_tier(5_000_000) == LiquidityTier.L2_LIQUID

    def test_moderate(self, model):
        assert model.classify_tier(800_000) == LiquidityTier.L3_MODERATE

    def test_thin(self, model):
        assert model.classify_tier(100_000) == LiquidityTier.L4_THIN

    def test_all_tiers_have_params(self):
        for tier in LiquidityTier:
            assert tier in TIER_PARAMS
            assert "gamma" in TIER_PARAMS[tier]
            assert "eta" in TIER_PARAMS[tier]
            assert "default_cap" in TIER_PARAMS[tier]


# ---------------------------------------------------------------------------
# Full cost decomposition
# ---------------------------------------------------------------------------


class TestTotalCost:
    """Verify the full cost estimation method."""

    def test_returns_all_components(self, model):
        result = model.estimate_total_cost(10_000, 1_000_000, 0.02, spread=0.001)
        assert "spread_cost" in result
        assert "commission" in result
        assert "impact" in result
        assert "participation_cap" in result
        assert "tier" in result
        assert "regime" in result

    def test_auto_classifies_tier(self, model):
        result = model.estimate_total_cost(10_000, 50_000_000, 0.02)
        assert result["tier"] == "L1"
