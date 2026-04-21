"""M08 Regime Rendering — continuous a_t attention score from z_t posterior."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from midas.regime.learned_attention import (
    AttentionWeightLearner,
    LearnedAttentionModel,
)


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
    model_disagreement: float
    drawdown_velocity: float
    timestamp: str


class RegimeRenderer:
    """Compute continuous a_t from latent state components.

    Supports both fixed prior weights (default) and learned weights via
    an AttentionWeightLearner.  Per spec 06 S2, learned weights should
    be trained on historical user-engagement outcomes.
    """

    # Prior-informed default weights (6 contributors per specs/06 S2).
    _DEFAULT_WEIGHTS = [0.30, 0.25, 0.15, 0.15, 0.10, 0.05]

    def __init__(self, weight_learner: AttentionWeightLearner | None = None) -> None:
        self._weight_learner = weight_learner

    def _get_weights(self) -> list[float]:
        """Return learned weights if available, else prior defaults."""
        if self._weight_learner is not None:
            learned = self._weight_learner.get_weights()
            if learned is not None:
                return learned
        return list(self._DEFAULT_WEIGHTS)

    def render(
        self,
        z_t_posterior: list[float],
        volatility: float,
        ood_score: float,
        change_point_prob: float,
        model_disagreement: float = 0.0,
        drawdown_velocity: float = 0.0,
        timestamp: str = "",
    ) -> RegimeState:
        """Compute a_t from z_t components."""
        from datetime import datetime, timezone

        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        vol_pct = min(max(volatility, 0.0), 1.0)
        ood = min(max(ood_score, 0.0), 1.0)
        trans = min(max(change_point_prob, 0.0), 1.0)
        disagreement = min(max(model_disagreement, 0.0), 1.0)
        dd_vel = min(max(drawdown_velocity, 0.0), 1.0)

        # Posterior variance as uncertainty signal
        if z_t_posterior:
            mean = sum(z_t_posterior) / len(z_t_posterior)
            variance = sum((x - mean) ** 2 for x in z_t_posterior) / len(z_t_posterior)
            var_signal = min(variance / 2.0, 1.0)
        else:
            var_signal = 0.5

        w = self._get_weights()
        a_t = (
            w[0] * vol_pct
            + w[1] * ood
            + w[2] * trans
            + w[3] * var_signal
            + w[4] * disagreement
            + w[5] * dd_vel
        )
        a_t = min(max(a_t, 0.0), 1.0)

        return RegimeState(
            a_t=a_t,
            band=self.get_band(a_t),
            z_t_posterior=z_t_posterior,
            volatility_percentile=vol_pct,
            ood_score=ood,
            transition_pressure=trans,
            model_disagreement=disagreement,
            drawdown_velocity=dd_vel,
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
