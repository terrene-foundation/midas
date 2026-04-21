"""Execution cost model — Almgren-Chriss impact, participation caps, liquidity tiers.

Implements the transaction cost decomposition from specs/13:
  C_total = C_spread + C_impact + C_commission + C_tax + C_slippage + C_gap

The impact model uses Almgren-Chriss square-root temporary + linear permanent:
  C_impact = gamma * sigma * (q / ADV)^0.5 + eta * sigma * (q / V_schedule)

Ref: specs/13-execution-cost-and-microstructure.md
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger("midas.execution.cost_model")


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


# ---------------------------------------------------------------------------
# Tax / dividend withholding defaults (spec S2.4)
# ---------------------------------------------------------------------------

# Singapore domicile: no capital gains tax. US-source dividends: 30% WHT
# absent treaty; ~15% for Ireland-domiciled UCITS. The default drag is
# expressed in basis points of position value per year.
DEFAULT_TAX_DRAG_BPS: float = 0.5  # conservative for non-tax-advantaged accounts

# ---------------------------------------------------------------------------
# Slippage parameters (spec S2.5)
# ---------------------------------------------------------------------------

# Time-of-day multipliers: opening/closing 15 min have wider slippage.
TIME_OF_DAY_MULTIPLIERS: dict[str, float] = {
    "pre_open": 1.5,    # 09:30-09:45 ET
    "normal": 1.0,      # 09:45-15:45 ET
    "close": 1.5,       # 15:45-16:00 ET
    "overnight": 2.0,   # used for gap risk, not slippage per se
}

# Regime multipliers on slippage (higher regime = more slippage).
SLIPPAGE_REGIME_MULTIPLIERS: dict[str, float] = {
    "calm": 1.0,
    "elevated": 1.5,
    "urgent": 2.0,
    "crisis": 3.0,
}

# Tier multipliers on slippage (thinner liquidity = more slippage).
SLIPPAGE_TIER_MULTIPLIERS: dict[LiquidityTier, float] = {
    LiquidityTier.L1_DEEP: 1.0,
    LiquidityTier.L2_LIQUID: 1.2,
    LiquidityTier.L3_MODERATE: 1.5,
    LiquidityTier.L4_THIN: 2.0,
}

# ---------------------------------------------------------------------------
# Gap risk parameters (spec S2.6)
# ---------------------------------------------------------------------------

# Historical gap volatility multipliers per discontinuity type.
# These are annualized-vol-scaled multipliers; actual gap bps is computed
# as: gap_sigma * sqrt(time_fraction) * regime_multiplier.
GAP_TYPE_MULTIPLIERS: dict[str, float] = {
    "overnight": 0.8,   # typical overnight gap ~ 0.8x daily vol
    "weekend": 1.2,     # 2.5 days of info compressed
    "holiday": 1.5,     # extended close
    "halt_resume": 2.0, # halt-resume gaps can be severe
    "earnings": 3.0,    # earnings gap is the largest source
}

# Regime multipliers on gap risk.
GAP_REGIME_MULTIPLIERS: dict[str, float] = {
    "calm": 1.0,
    "elevated": 1.5,
    "urgent": 2.0,
    "crisis": 3.0,
}


class ExecutionCostModel:
    """Almgren-Chriss execution cost model with liquidity-tiered parameters.

    Full cost decomposition:
      C_total = C_spread + C_impact + C_commission + C_tax + C_slippage + C_gap

    Ref: specs/13 S2.2, S2.4, S2.5, S2.6, S4.3, S5
    """

    def __init__(
        self,
        commission_per_share: float = 0.005,
        default_participation_cap: float = 0.05,
        tax_drag_bps: float = DEFAULT_TAX_DRAG_BPS,
    ) -> None:
        self._commission_per_share = commission_per_share
        self._default_cap = default_participation_cap
        self._tax_drag_bps = tax_drag_bps

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

    # ------------------------------------------------------------------
    # Tax / dividend withholding drag (spec S2.4)
    # ------------------------------------------------------------------

    def estimate_tax_drag(
        self,
        position_value: float,
        holding_period_days: float = 30.0,
        tax_advantaged: bool = False,
    ) -> dict[str, Any]:
        """Estimate dividend withholding tax drag for a position.

        Singapore domicile has no capital gains tax. US-source dividends
        carry withholding that becomes a drag on total return. This is a
        carry cost factored into "If approved" projections, not a per-trade
        cost.

        Parameters
        ----------
        position_value:
            Dollar value of the position.
        holding_period_days:
            Expected holding period in calendar days.
        tax_advantaged:
            If True, the account is tax-advantaged and drag is zero.

        Returns
        -------
        Dict with ``tax_drag_bps``, ``tax_drag_dollars``, ``holding_period_days``.
        """
        if tax_advantaged or position_value <= 0:
            return {
                "tax_drag_bps": 0.0,
                "tax_drag_dollars": 0.0,
                "holding_period_days": holding_period_days,
                "tax_advantaged": tax_advantaged,
            }

        # Annualize: bps * (holding_days / 365)
        annualized_bps = self._tax_drag_bps * (holding_period_days / 365.0)
        drag_dollars = position_value * annualized_bps / 10_000.0

        return {
            "tax_drag_bps": float(annualized_bps),
            "tax_drag_dollars": float(drag_dollars),
            "holding_period_days": holding_period_days,
            "tax_advantaged": tax_advantaged,
        }

    # ------------------------------------------------------------------
    # Execution slippage (spec S2.5)
    # ------------------------------------------------------------------

    def estimate_slippage(
        self,
        volatility: float,
        order_size: float,
        avg_daily_volume: float,
        tier: LiquidityTier = LiquidityTier.L2_LIQUID,
        regime: str = "calm",
        time_of_day: str = "normal",
    ) -> dict[str, Any]:
        """Estimate execution slippage via quantile regression inputs.

        The model uses (vol, time-of-day, liquidity tier, regime) as
        features. Returns the mean estimate and an upper quantile for
        compliance rule reading.

        Parameters
        ----------
        volatility:
            Annualized volatility at execution horizon.
        order_size:
            Number of shares in the order.
        avg_daily_volume:
            Average daily volume for the instrument.
        tier:
            Liquidity tier of the instrument.
        regime:
            Current regime band.
        time_of_day:
            Execution window (``pre_open``, ``normal``, ``close``).

        Returns
        -------
        Dict with ``slippage_bps``, ``slippage_bps_p90``, ``participation_rate``.
        """
        if avg_daily_volume <= 0 or volatility <= 0:
            return {
                "slippage_bps": 0.0,
                "slippage_bps_p90": 0.0,
                "participation_rate": float("inf"),
                "tier": tier.value,
                "regime": regime,
                "time_of_day": time_of_day,
            }

        participation_rate = abs(order_size) / avg_daily_volume

        # Base slippage: proportional to vol * participation
        # Calibrated from typical US equity microstructure
        base_slippage_bps = volatility * 10_000 * participation_rate

        # Apply time-of-day multiplier
        tod_mult = TIME_OF_DAY_MULTIPLIERS.get(time_of_day, 1.0)

        # Apply tier multiplier
        tier_mult = SLIPPAGE_TIER_MULTIPLIERS.get(tier, 1.2)

        # Apply regime multiplier
        regime_mult = SLIPPAGE_REGIME_MULTIPLIERS.get(regime, 1.0)

        mean_slippage = base_slippage_bps * tod_mult * tier_mult * regime_mult

        # P90: add 1.28 standard deviations (log-normal approximation)
        # The spread of the slippage distribution scales with the mean.
        p90_slippage = mean_slippage * (1.0 + 1.28 * 0.5)  # sigma ~ 0.5 * mean

        return {
            "slippage_bps": float(mean_slippage),
            "slippage_bps_p90": float(p90_slippage),
            "participation_rate": float(participation_rate),
            "tier": tier.value,
            "regime": regime,
            "time_of_day": time_of_day,
        }

    # ------------------------------------------------------------------
    # Gap risk (spec S2.6)
    # ------------------------------------------------------------------

    def estimate_gap_risk(
        self,
        position_value: float,
        volatility: float,
        gap_type: str = "overnight",
        regime: str = "calm",
    ) -> dict[str, Any]:
        """Estimate gap risk across discontinuities.

        Gap risk is the PnL impact when an order or position is exposed
        across a discontinuity (overnight, weekend, holiday, halt-resume,
        earnings). Any order that cannot execute in a single continuous
        trading window carries a C_gap term.

        Parameters
        ----------
        position_value:
            Dollar value of the position exposed to the gap.
        volatility:
            Annualized volatility of the instrument.
        gap_type:
            Type of discontinuity (``overnight``, ``weekend``,
            ``holiday``, ``halt_resume``, ``earnings``).
        regime:
            Current regime band.

        Returns
        -------
        Dict with ``gap_bps``, ``gap_dollars``, ``gap_dollars_p90``.
        """
        if position_value <= 0 or volatility <= 0:
            return {
                "gap_bps": 0.0,
                "gap_dollars": 0.0,
                "gap_dollars_p90": 0.0,
                "gap_type": gap_type,
                "regime": regime,
            }

        # Time fraction of each gap type (relative to 1 trading day = 1/252 year)
        time_fractions: dict[str, float] = {
            "overnight": 1.0 / 252.0,
            "weekend": 3.0 / 252.0,
            "holiday": 4.0 / 252.0,
            "halt_resume": 0.5 / 252.0,
            "earnings": 1.0 / 252.0,
        }
        dt = time_fractions.get(gap_type, 1.0 / 252.0)

        gap_mult = GAP_TYPE_MULTIPLIERS.get(gap_type, 1.0)
        regime_mult = GAP_REGIME_MULTIPLIERS.get(regime, 1.0)

        # Expected gap in bps = vol * sqrt(dt) * gap_mult * regime_mult * 10000
        gap_sigma = volatility * np.sqrt(dt) * gap_mult * regime_mult
        gap_bps = float(gap_sigma * 10_000)

        # Mean gap (absolute value of normal with this sigma)
        mean_gap_bps = gap_bps * np.sqrt(2.0 / np.pi)

        # P90 gap
        p90_gap_bps = gap_bps * 1.28

        return {
            "gap_bps": float(mean_gap_bps),
            "gap_dollars": float(position_value * mean_gap_bps / 10_000),
            "gap_dollars_p90": float(position_value * p90_gap_bps / 10_000),
            "gap_type": gap_type,
            "regime": regime,
        }

    def estimate_total_cost(
        self,
        order_size: float,
        avg_daily_volume: float,
        volatility: float,
        spread: float = 0.0,
        tier: LiquidityTier | None = None,
        regime: str = "calm",
        position_value: float | None = None,
        holding_period_days: float = 30.0,
        tax_advantaged: bool = False,
        gap_type: str | None = None,
        time_of_day: str = "normal",
    ) -> dict[str, Any]:
        """Full cost decomposition for an order.

        Returns all cost components (spread, impact, commission, tax,
        slippage, gap risk) plus participation cap check.

        Parameters
        ----------
        order_size:
            Number of shares in the order.
        avg_daily_volume:
            Average daily volume for the instrument.
        volatility:
            Annualized volatility.
        spread:
            Current bid-ask spread (price units).
        tier:
            Liquidity tier; auto-classified if not provided.
        regime:
            Current regime band.
        position_value:
            Dollar value of resulting position. Used for tax drag and
            gap risk. Derived from order_size * price if not provided.
        holding_period_days:
            Expected holding period for tax drag estimation.
        tax_advantaged:
            Whether the account is tax-advantaged (reduces tax drag to zero).
        gap_type:
            If the order crosses a discontinuity, the type of gap. If None,
            gap risk is estimated as zero (single-session execution).
        time_of_day:
            Execution window for slippage estimation.
        """
        if tier is None:
            tier = self.classify_tier(avg_daily_volume)

        impact = self.estimate_impact(order_size, avg_daily_volume, volatility, tier)
        cap = self.check_participation_cap(order_size, avg_daily_volume, tier, regime)
        slippage = self.estimate_slippage(
            volatility, order_size, avg_daily_volume, tier, regime, time_of_day
        )

        spread_cost = 0.5 * spread * abs(order_size)
        commission = self._commission_per_share * abs(order_size)

        # Tax drag (carry cost, not per-trade)
        if position_value is None:
            position_value = abs(order_size) * (spread or 1.0)
        tax = self.estimate_tax_drag(position_value, holding_period_days, tax_advantaged)

        # Gap risk (only if crossing a discontinuity)
        if gap_type is not None:
            gap = self.estimate_gap_risk(position_value, volatility, gap_type, regime)
        else:
            gap = {
                "gap_bps": 0.0,
                "gap_dollars": 0.0,
                "gap_dollars_p90": 0.0,
                "gap_type": "none",
                "regime": regime,
            }

        # Total cost in dollars (spread + commission + impact_dollar + slippage + gap)
        impact_dollars = float(impact.get("total_impact", 0.0)) * abs(order_size)
        slippage_dollars = position_value * float(slippage.get("slippage_bps", 0.0)) / 10_000
        total_cost = (
            spread_cost
            + commission
            + impact_dollars
            + slippage_dollars
            + float(gap.get("gap_dollars", 0.0))
        )

        # Upper quantile total (for compliance: C_total at p90)
        slippage_p90_dollars = (
            position_value * float(slippage.get("slippage_bps_p90", 0.0)) / 10_000
        )
        gap_p90_dollars = float(gap.get("gap_dollars_p90", 0.0))
        total_cost_p90 = (
            spread_cost
            + commission
            + impact_dollars
            + slippage_p90_dollars
            + gap_p90_dollars
        )

        return {
            "spread_cost": spread_cost,
            "commission": commission,
            "impact": impact,
            "tax": tax,
            "slippage": slippage,
            "gap": gap,
            "total_cost": total_cost,
            "total_cost_p90": total_cost_p90,
            "participation_cap": cap,
            "tier": tier.value,
            "regime": regime,
        }
