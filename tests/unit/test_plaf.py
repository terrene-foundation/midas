"""Tier 1 tests for the PLAF (Paper-to-Live Adjustment Factor) calculator.

Ref: specs/13-execution-cost-and-microstructure.md S6
Ref: specs/14-ibkr-integration.md S9
Ref: src/midas/execution/plaf.py
"""

import math

import pytest

from midas.execution.plaf import PLAFConfig, PLAFCalculator


@pytest.fixture
def calculator():
    return PLAFCalculator(PLAFConfig())


@pytest.fixture
def custom_calculator():
    return PLAFCalculator(
        PLAFConfig(
            spread_multiplier=2.0,
            impact_multiplier=3.0,
            slippage_add_bps=10.0,
            update_threshold=5,
            prior_strength=5.0,
        )
    )


# ---------------------------------------------------------------------------
# PLAFConfig
# ---------------------------------------------------------------------------


class TestPLAFConfig:
    def test_defaults(self):
        config = PLAFConfig()
        assert config.spread_multiplier == 1.5
        assert config.impact_multiplier == 2.0
        assert config.slippage_add_bps == 5.0
        assert config.update_threshold == 20

    def test_custom_values(self):
        config = PLAFConfig(
            spread_multiplier=2.5,
            impact_multiplier=3.0,
            slippage_add_bps=8.0,
            update_threshold=50,
        )
        assert config.spread_multiplier == 2.5
        assert config.impact_multiplier == 3.0
        assert config.slippage_add_bps == 8.0
        assert config.update_threshold == 50


# ---------------------------------------------------------------------------
# adjust_cost
# ---------------------------------------------------------------------------


class TestAdjustCost:
    def test_applies_spread_multiplier(self, calculator):
        paper = {"spread_cost": 100.0}
        result = calculator.adjust_cost(paper)
        assert result["spread_cost"] == 150.0  # 100 * 1.5

    def test_applies_impact_multiplier(self, calculator):
        paper = {"impact_cost": 50.0}
        result = calculator.adjust_cost(paper)
        assert result["impact_cost"] == 100.0  # 50 * 2.0

    def test_adds_slippage_bps(self, calculator):
        paper = {"slippage_bps": 3.0}
        result = calculator.adjust_cost(paper)
        assert result["slippage_bps"] == 8.0  # 3 + 5

    def test_preserves_original_keys(self, calculator):
        paper = {"spread_cost": 100.0, "impact_cost": 50.0, "other_key": "value"}
        result = calculator.adjust_cost(paper)
        assert result["other_key"] == "value"

    def test_flags_plaf_adjusted(self, calculator):
        result = calculator.adjust_cost({"spread_cost": 100.0})
        assert result["plaf_adjusted"] is True

    def test_includes_multiplier_details(self, calculator):
        result = calculator.adjust_cost({"spread_cost": 100.0})
        assert "plaf_multipliers" in result
        mults = result["plaf_multipliers"]
        assert "spread" in mults
        assert "impact" in mults
        assert "slippage_add_bps" in mults
        assert "using_bayesian" in mults
        assert mults["using_bayesian"] is False  # no data yet

    def test_zero_paper_cost_stays_zero_after_multiplier(self, calculator):
        paper = {"spread_cost": 0.0, "impact_cost": 0.0}
        result = calculator.adjust_cost(paper)
        assert result["spread_cost"] == 0.0
        assert result["impact_cost"] == 0.0

    def test_custom_multipliers(self, custom_calculator):
        paper = {"spread_cost": 100.0, "impact_cost": 50.0}
        result = custom_calculator.adjust_cost(paper)
        assert result["spread_cost"] == 200.0  # 100 * 2.0
        assert result["impact_cost"] == 150.0  # 50 * 3.0

    def test_total_cost_adjusted_when_present(self, calculator):
        paper = {
            "spread_cost": 100.0,
            "impact_cost": 50.0,
            "slippage_bps": 3.0,
            "total_cost": 153.0,
        }
        result = calculator.adjust_cost(paper)
        # spread_delta: 150 - 100 = 50
        # impact_delta: 100 - 50 = 50
        # slippage_delta: 5 bps (additive)
        assert result["total_cost"] == 153.0 + 50.0 + 50.0 + 5.0


# ---------------------------------------------------------------------------
# update_with_live
# ---------------------------------------------------------------------------


class TestUpdateWithLive:
    def test_rejects_mismatched_lengths(self, calculator):
        with pytest.raises(ValueError, match="same length"):
            calculator.update_with_live(
                [{"spread_cost": 100.0}],
                [{"spread_cost": 100.0}, {"spread_cost": 200.0}],
            )

    def test_empty_lists_no_error(self, calculator):
        calculator.update_with_live([], [])

    def test_observsations_recorded(self, custom_calculator):
        paper = [{"spread_cost": 100.0, "impact_cost": 50.0, "slippage_bps": 3.0}]
        live = [{"spread_cost": 200.0, "impact_cost": 100.0, "slippage_bps": 10.0}]
        custom_calculator.update_with_live(paper, live)
        # Internal state should reflect 1 observation
        assert custom_calculator._spread_state.n_observations == 1
        assert custom_calculator._impact_state.n_observations == 1

    def test_below_threshold_uses_seeds(self, custom_calculator):
        """Below update_threshold, the seed multipliers are used."""
        # custom_calculator has update_threshold=5
        for _ in range(4):
            custom_calculator.update_with_live(
                [{"spread_cost": 100.0, "impact_cost": 50.0, "slippage_bps": 3.0}],
                [{"spread_cost": 200.0, "impact_cost": 100.0, "slippage_bps": 10.0}],
            )
        # Still below threshold: 4 < 5
        mults = custom_calculator.adjust_cost({"spread_cost": 100.0})["plaf_multipliers"]
        assert mults["using_bayesian"] is False

    def test_above_threshold_switches_to_bayesian(self, custom_calculator):
        """Above update_threshold, Bayesian posterior drives multipliers."""
        # custom_calculator has update_threshold=5
        for _ in range(6):
            custom_calculator.update_with_live(
                [{"spread_cost": 100.0, "impact_cost": 50.0, "slippage_bps": 3.0}],
                [{"spread_cost": 200.0, "impact_cost": 100.0, "slippage_bps": 10.0}],
            )
        # Now 6 >= 5 threshold
        mults = custom_calculator.adjust_cost({"spread_cost": 100.0})["plaf_multipliers"]
        assert mults["using_bayesian"] is True

    def test_zero_paper_cost_skipped(self, calculator):
        """Zero paper costs are skipped (avoid log(0))."""
        paper = [{"spread_cost": 0.0, "impact_cost": 0.0, "slippage_bps": 0.0}]
        live = [{"spread_cost": 200.0, "impact_cost": 100.0, "slippage_bps": 10.0}]
        # Should not raise
        calculator.update_with_live(paper, live)


# ---------------------------------------------------------------------------
# get_adjusted_cost_breakdown
# ---------------------------------------------------------------------------


class TestGetAdjustedCostBreakdown:
    def test_returns_raw_and_adjusted(self, calculator):
        paper = {"spread_cost": 100.0, "impact_cost": 50.0, "slippage_bps": 3.0}
        result = calculator.get_adjusted_cost_breakdown(paper)
        assert "raw" in result
        assert "adjusted" in result
        assert "adjustment_deltas" in result
        assert "multipliers" in result

    def test_raw_unchanged(self, calculator):
        paper = {"spread_cost": 100.0}
        result = calculator.get_adjusted_cost_breakdown(paper)
        assert result["raw"]["spread_cost"] == 100.0

    def test_deltas_computed(self, calculator):
        paper = {"spread_cost": 100.0, "impact_cost": 50.0}
        result = calculator.get_adjusted_cost_breakdown(paper)
        deltas = result["adjustment_deltas"]
        assert deltas["spread_cost"] == 50.0  # 150 - 100
        assert deltas["impact_cost"] == 50.0  # 100 - 50
