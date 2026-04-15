"""M08 Regime Rendering — continuous a_t attention score from z_t posterior."""

import enum
from dataclasses import dataclass
from typing import Any


class AttentionBand(enum.Enum):
    CALM = "calm"
    ELEVATED = "elevated"
    URGENT = "urgent"
    CRISIS = "crisis"


@dataclass(frozen=True)
class RegimeState:
    a_t: float
    band: AttentionBand
    z_t_posterior: list[float]
    volatility_percentile: float
    ood_score: float
    transition_pressure: float
    timestamp: str


class RegimeRenderer:
    """Compute continuous a_t from latent state components."""

    # Weights for a_t computation
    _W_VOL = 0.35
    _W_OOD = 0.30
    _W_TRANSITION = 0.20
    _W_VARIANCE = 0.15

    def render(
        self,
        z_t_posterior: list[float],
        volatility: float,
        ood_score: float,
        change_point_prob: float,
        timestamp: str = "",
    ) -> RegimeState:
        """Compute a_t from z_t components."""
        from datetime import datetime, timezone

        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        vol_pct = min(max(volatility, 0.0), 1.0)
        ood = min(max(ood_score, 0.0), 1.0)
        trans = min(max(change_point_prob, 0.0), 1.0)

        # Posterior variance as uncertainty signal
        if z_t_posterior:
            mean = sum(z_t_posterior) / len(z_t_posterior)
            variance = sum((x - mean) ** 2 for x in z_t_posterior) / len(z_t_posterior)
            var_signal = min(variance / 2.0, 1.0)
        else:
            var_signal = 0.5

        a_t = (
            self._W_VOL * vol_pct
            + self._W_OOD * ood
            + self._W_TRANSITION * trans
            + self._W_VARIANCE * var_signal
        )
        a_t = min(max(a_t, 0.0), 1.0)

        return RegimeState(
            a_t=a_t,
            band=self.get_band(a_t),
            z_t_posterior=z_t_posterior,
            volatility_percentile=vol_pct,
            ood_score=ood,
            transition_pressure=trans,
            timestamp=timestamp,
        )

    @staticmethod
    def get_band(a_t: float) -> AttentionBand:
        if a_t >= 0.85:
            return AttentionBand.CRISIS
        if a_t >= 0.6:
            return AttentionBand.URGENT
        if a_t >= 0.3:
            return AttentionBand.ELEVATED
        return AttentionBand.CALM

    @staticmethod
    def get_disclosure_level(band: AttentionBand) -> str:
        levels = {
            AttentionBand.CALM: "minimal",
            AttentionBand.ELEVATED: "standard",
            AttentionBand.URGENT: "detailed",
            AttentionBand.CRISIS: "full",
        }
        return levels[band]

    @staticmethod
    def get_recommended_actions(state: RegimeState) -> list[str]:
        actions = {
            AttentionBand.CALM: ["auto_rebalance", "daily_brief"],
            AttentionBand.ELEVATED: ["monitor_closely", "shorter_brief_interval"],
            AttentionBand.URGENT: ["manual_approval_large_trades", "debate_suggested"],
            AttentionBand.CRISIS: [
                "all_decisions_surfaced",
                "biometric_required",
                "kill_switch_prominent",
            ],
        }
        return actions.get(state.band, [])
