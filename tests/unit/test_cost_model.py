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
    DEFAULT_TAX_DRAG_BPS,
    TIME_OF_DAY_MULTIPLIERS,
    SLIPPAGE_REGIME_MULTIPLIERS,
    SLIPPAGE_TIER_MULTIPLIERS,
    GAP_TYPE_MULTIPLIERS,
    GAP_REGIME_MULTIPLIERS,
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

    def test_total_cost_includes_new_terms(self, model):
        result = model.estimate_total_cost(
            10_000, 1_000_000, 0.02, spread=0.001,
            position_value=500_000, gap_type="overnight",
        )
        assert "tax" in result
        assert "slippage" in result
        assert "gap" in result
        assert "total_cost" in result
        assert "total_cost_p90" in result
        assert result["total_cost"] > 0
        assert result["total_cost_p90"] >= result["total_cost"]

    def test_no_gap_when_type_is_none(self, model):
        result = model.estimate_total_cost(10_000, 1_000_000, 0.02)
        assert result["gap"]["gap_bps"] == 0.0
        assert result["gap"]["gap_dollars"] == 0.0

    def test_tax_advantaged_zero_tax(self, model):
        result = model.estimate_total_cost(
            10_000, 1_000_000, 0.02, tax_advantaged=True,
        )
        assert result["tax"]["tax_drag_bps"] == 0.0
        assert result["tax"]["tax_drag_dollars"] == 0.0


# ---------------------------------------------------------------------------
# Tax / dividend withholding drag (spec S2.4)
# ---------------------------------------------------------------------------


class TestTaxDrag:
    def test_positive_position_generates_drag(self, model):
        result = model.estimate_tax_drag(100_000)
        assert result["tax_drag_bps"] > 0
        assert result["tax_drag_dollars"] > 0

    def test_tax_advantaged_zero(self, model):
        result = model.estimate_tax_drag(100_000, tax_advantaged=True)
        assert result["tax_drag_bps"] == 0.0
        assert result["tax_drag_dollars"] == 0.0
        assert result["tax_advantaged"] is True

    def test_zero_position_zero_drag(self, model):
        result = model.estimate_tax_drag(0)
        assert result["tax_drag_dollars"] == 0.0

    def test_longer_holding_higher_drag(self, model):
        short = model.estimate_tax_drag(100_000, holding_period_days=30)
        long = model.estimate_tax_drag(100_000, holding_period_days=365)
        assert long["tax_drag_bps"] > short["tax_drag_bps"]

    def test_default_drag_bps_is_0_5(self):
        assert DEFAULT_TAX_DRAG_BPS == 0.5


# ---------------------------------------------------------------------------
# Execution slippage (spec S2.5)
# ---------------------------------------------------------------------------


class TestSlippage:
    def test_basic_slippage(self, model):
        result = model.estimate_slippage(0.02, 10_000, 1_000_000)
        assert result["slippage_bps"] > 0
        assert result["slippage_bps_p90"] > result["slippage_bps"]

    def test_zero_vol_zero_slippage(self, model):
        result = model.estimate_slippage(0.0, 10_000, 1_000_000)
        assert result["slippage_bps"] == 0.0

    def test_zero_adv_zero_slippage(self, model):
        result = model.estimate_slippage(0.02, 10_000, 0)
        assert result["slippage_bps"] == 0.0

    def test_higher_regime_more_slippage(self, model):
        calm = model.estimate_slippage(0.02, 10_000, 1_000_000, regime="calm")
        crisis = model.estimate_slippage(0.02, 10_000, 1_000_000, regime="crisis")
        assert crisis["slippage_bps"] > calm["slippage_bps"]

    def test_thin_tier_more_slippage(self, model):
        l1 = model.estimate_slippage(0.02, 10_000, 1_000_000, tier=LiquidityTier.L1_DEEP)
        l4 = model.estimate_slippage(0.02, 10_000, 1_000_000, tier=LiquidityTier.L4_THIN)
        assert l4["slippage_bps"] > l1["slippage_bps"]

    def test_pre_open_wider_slippage(self, model):
        normal = model.estimate_slippage(0.02, 10_000, 1_000_000, time_of_day="normal")
        pre_open = model.estimate_slippage(0.02, 10_000, 1_000_000, time_of_day="pre_open")
        assert pre_open["slippage_bps"] > normal["slippage_bps"]

    def test_returns_tier_and_regime(self, model):
        result = model.estimate_slippage(0.02, 10_000, 1_000_000, tier=LiquidityTier.L2_LIQUID, regime="elevated")
        assert result["tier"] == "L2"
        assert result["regime"] == "elevated"

    def test_participation_rate_computed(self, model):
        result = model.estimate_slippage(0.02, 10_000, 1_000_000)
        assert abs(result["participation_rate"] - 0.01) < 1e-6


# ---------------------------------------------------------------------------
# Gap risk (spec S2.6)
# ---------------------------------------------------------------------------


class TestGapRisk:
    def test_overnight_gap(self, model):
        result = model.estimate_gap_risk(100_000, 0.02, gap_type="overnight")
        assert result["gap_bps"] > 0
        assert result["gap_dollars"] > 0
        assert result["gap_dollars_p90"] > result["gap_dollars"]

    def test_zero_position_zero_gap(self, model):
        result = model.estimate_gap_risk(0, 0.02, gap_type="overnight")
        assert result["gap_bps"] == 0.0
        assert result["gap_dollars"] == 0.0

    def test_earnings_gap_largest(self, model):
        overnight = model.estimate_gap_risk(100_000, 0.02, gap_type="overnight")
        earnings = model.estimate_gap_risk(100_000, 0.02, gap_type="earnings")
        assert earnings["gap_bps"] > overnight["gap_bps"]

    def test_crisis_regime_amplifies_gap(self, model):
        calm = model.estimate_gap_risk(100_000, 0.02, gap_type="overnight", regime="calm")
        crisis = model.estimate_gap_risk(100_000, 0.02, gap_type="overnight", regime="crisis")
        assert crisis["gap_bps"] > calm["gap_bps"]

    def test_higher_vol_larger_gap(self, model):
        low_vol = model.estimate_gap_risk(100_000, 0.01, gap_type="overnight")
        high_vol = model.estimate_gap_risk(100_000, 0.05, gap_type="overnight")
        assert high_vol["gap_bps"] > low_vol["gap_bps"]

    def test_returns_gap_type(self, model):
        result = model.estimate_gap_risk(100_000, 0.02, gap_type="weekend")
        assert result["gap_type"] == "weekend"

    def test_all_gap_types_produce_positive_risk(self, model):
        for gap_type in ("overnight", "weekend", "holiday", "halt_resume", "earnings"):
            result = model.estimate_gap_risk(100_000, 0.02, gap_type=gap_type)
            assert result["gap_bps"] > 0, f"gap_type={gap_type} produced zero gap"
