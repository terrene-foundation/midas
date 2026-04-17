"""Execution cost model — Almgren-Chriss impact, participation caps, liquidity tiers.

Implements the transaction cost decomposition from specs/13:
  C_total = C_spread + C_impact + C_commission + C_slippage + C_gap

The impact model uses Almgren-Chriss square-root temporary + linear permanent:
  C_impact = gamma * sigma * (q / ADV)^0.5 + eta * sigma * (q / V_schedule)

Ref: specs/13-execution-cost-and-microstructure.md
"""

from enum import Enum
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Liquidity tiering (spec S5)
# ---------------------------------------------------------------------------


class LiquidityTier(str, Enum):
    """Universe instrument liquidity tiers."""

    L1_DEEP = "L1"  # SPY, QQQ, IEF, TLT, GLD
    L2_LIQUID = "L2"  # Sector ETFs, S&P 500 large caps
    L3_MODERATE = "L3"  # Smaller sector ETFs, S&P 400 mid caps
    L4_THIN = "L4"  # S&P 600 small caps, niche ETFs


# Impact parameters per tier (gamma, eta)
# Calibrated from typical US equity market microstructure
TIER_PARAMS: dict[LiquidityTier, dict[str, float]] = {
    LiquidityTier.L1_DEEP: {"gamma": 0.05, "eta": 0.02, "default_cap": 0.05},
    LiquidityTier.L2_LIQUID: {"gamma": 0.10, "eta": 0.04, "default_cap": 0.05},
    LiquidityTier.L3_MODERATE: {"gamma": 0.20, "eta": 0.08, "default_cap": 0.03},
    LiquidityTier.L4_THIN: {"gamma": 0.35, "eta": 0.15, "default_cap": 0.02},
}

# Regime multipliers on participation cap (spec S4.3)
REGIME_CAP_MULTIPLIERS: dict[str, float] = {
    "calm": 1.0,
    "elevated": 0.6,  # 3% default -> tighter
    "urgent": 0.4,  # 2% default
    "crisis": 0.0,  # pause unless user overrides
}


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------


class ExecutionCostModel:
    """Almgren-Chriss execution cost model with liquidity-tiered parameters.

    Ref: specs/13 S2.2, S4.3, S5
    """

    def __init__(
        self,
        commission_per_share: float = 0.005,
        default_participation_cap: float = 0.05,
    ) -> None:
        self._commission_per_share = commission_per_share
        self._default_cap = default_participation_cap

    def estimate_impact(
        self,
        order_size: float,
        avg_daily_volume: float,
        volatility: float,
        tier: LiquidityTier = LiquidityTier.L2_LIQUID,
        schedule_volume: float | None = None,
    ) -> dict[str, Any]:
        if avg_daily_volume <= 0:
            return {
                "temp_impact": float("inf"),
                "perm_impact": float("inf"),
                "total_impact": float("inf"),
                "impact_bps": float("inf"),
                "tier": tier.value,
            }

        params = TIER_PARAMS.get(tier, TIER_PARAMS[LiquidityTier.L2_LIQUID])
        gamma = params["gamma"]
        eta = params["eta"]

        v_schedule = schedule_volume or avg_daily_volume
        if v_schedule <= 0:
            v_schedule = avg_daily_volume

        temp_impact = gamma * volatility * np.sqrt(abs(order_size) / avg_daily_volume)
        perm_impact = eta * volatility * abs(order_size) / v_schedule

        total = temp_impact + perm_impact
        impact_bps = total * 10_000  # convert to basis points

        return {
            "temp_impact": float(temp_impact),
            "perm_impact": float(perm_impact),
            "total_impact": float(total),
            "impact_bps": float(impact_bps),
            "tier": tier.value,
        }

    def check_participation_cap(
        self,
        order_size: float,
        avg_daily_volume: float,
        tier: LiquidityTier = LiquidityTier.L2_LIQUID,
        regime: str = "calm",
    ) -> dict[str, Any]:
        """Check if order respects the participation cap.

        Spec S4.3: order <= N% of expected session ADV, regime-adaptive.
        Small-cap (L4) gets stricter cap.

        Parameters
        ----------
        order_size:
            Number of shares in the order.
        avg_daily_volume:
            Expected session ADV.
        tier:
            Liquidity tier of the instrument.
        regime:
            Current regime band (calm, elevated, urgent, crisis).

        Returns
        -------
        dict with ``cap_pct``, ``actual_pct``, ``passes``, ``tier``, ``regime``.
        """
        if avg_daily_volume <= 0:
            return {
                "cap_pct": 0.0,
                "actual_pct": float("inf"),
                "passes": False,
                "tier": tier.value,
                "regime": regime,
            }

        tier_params = TIER_PARAMS.get(tier, TIER_PARAMS[LiquidityTier.L2_LIQUID])
        base_cap = tier_params.get("default_cap", self._default_cap)

        # L4 gets stricter defaults
        if tier == LiquidityTier.L4_THIN:
            base_cap = min(base_cap, 0.02)

        regime_multiplier = REGIME_CAP_MULTIPLIERS.get(regime, 1.0)
        effective_cap = base_cap * regime_multiplier

        actual_pct = abs(order_size) / avg_daily_volume
        passes = actual_pct <= effective_cap

        return {
            "cap_pct": effective_cap,
            "actual_pct": float(actual_pct),
            "passes": passes,
            "tier": tier.value,
            "regime": regime,
        }

    def classify_tier(
        self,
        avg_daily_volume: float,
        market_cap: float | None = None,
    ) -> LiquidityTier:
        """Classify an instrument into a liquidity tier.

        Uses ADV as primary signal, market cap as secondary.
        """
        if avg_daily_volume >= 10_000_000:
            return LiquidityTier.L1_DEEP
        elif avg_daily_volume >= 2_000_000:
            return LiquidityTier.L2_LIQUID
        elif avg_daily_volume >= 500_000:
            return LiquidityTier.L3_MODERATE
        else:
            return LiquidityTier.L4_THIN

    def estimate_total_cost(
        self,
        order_size: float,
        avg_daily_volume: float,
        volatility: float,
        spread: float = 0.0,
        tier: LiquidityTier | None = None,
        regime: str = "calm",
    ) -> dict[str, Any]:
        """Full cost decomposition for an order.

        Returns all cost components plus participation cap check.
        """
        if tier is None:
            tier = self.classify_tier(avg_daily_volume)

        impact = self.estimate_impact(order_size, avg_daily_volume, volatility, tier)
        cap = self.check_participation_cap(order_size, avg_daily_volume, tier, regime)

        spread_cost = 0.5 * spread * abs(order_size)
        commission = self._commission_per_share * abs(order_size)

        return {
            "spread_cost": spread_cost,
            "commission": commission,
            "impact": impact,
            "participation_cap": cap,
            "tier": tier.value,
            "regime": regime,
        }
