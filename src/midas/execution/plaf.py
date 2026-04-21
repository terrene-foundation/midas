"""Paper-to-Live Adjustment Factor (PLAF).

IBKR paper-trading fills are well-known to be optimistic: instant mid fills,
no impact, stale NBBO, no halts. PLAF scales paper-trading costs to estimate
what the same trades would have cost in live execution.

Default PLAF multipliers are seeded from documented IBKR paper-vs-live
comparisons and are updated via Bayesian posterior as live data accumulates.

Ref: specs/13-execution-cost-and-microstructure.md S6
Ref: specs/14-ibkr-integration.md S9
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger("midas.execution.plaf")


@dataclass
class PLAFConfig:
    """Configuration for PLAF adjustment factors.

    Attributes
    ----------
    spread_multiplier:
        Paper spreads are tighter than live. Applied to spread cost.
    impact_multiplier:
        Paper impact underestimates real market impact. Applied to impact cost.
    slippage_add_bps:
        Basis points added to paper slippage to account for optimistic fills.
    update_threshold:
        Minimum number of matched paper/live trade pairs before the Bayesian
        posterior starts influencing the multipliers. Below this threshold
        the seed values are used unchanged.
    prior_strength:
        Number of pseudo-observations in the Bayesian prior. Higher values
        make the posterior more resistant to early noise.
    """

    spread_multiplier: float = 1.5
    impact_multiplier: float = 2.0
    slippage_add_bps: float = 5.0
    update_threshold: int = 20
    prior_strength: float = 10.0


@dataclass
class _BayesianState:
    """Internal Bayesian conjugate-prior state for one multiplier.

    We model the ratio R = live_cost / paper_cost as having a
    log-normal posterior. The conjugate prior on log(R) is Normal
    with mean ``mu`` and precision ``tau`` (inverse variance).

    When enough paired observations arrive (>= update_threshold),
    we update the posterior and derive the multiplier from the
    posterior mean of R.
    """

    mu: float = 0.0  # prior mean of log(R) — 0 means ratio=1 (no adjustment)
    tau: float = 0.1  # prior precision (low = uncertain)
    n_observations: int = 0
    _sum_log_ratios: float = 0.0
    _sum_sq_log_ratios: float = 0.0

    def update(self, log_ratios: list[float], prior_strength: float) -> None:
        """Bayesian posterior update with new log-ratio observations."""
        if not log_ratios:
            return

        n = len(log_ratios)
        s = sum(log_ratios)
        ss = sum(x * x for x in log_ratios)

        self.n_observations += n
        self._sum_log_ratios += s
        self._sum_sq_log_ratios += ss

        # Posterior precision = prior precision + n * sample precision
        sample_mean = s / n
        sample_var = max((ss / n) - (sample_mean**2), 1e-8)
        sample_tau = 1.0 / sample_var

        prior_tau = prior_strength  # use prior_strength as prior precision
        posterior_tau = prior_tau + n * sample_tau
        posterior_mu = (prior_tau * self.mu + n * sample_tau * sample_mean) / posterior_tau

        self.mu = posterior_mu
        self.tau = posterior_tau

    def multiplier(self) -> float:
        """Return the posterior mean of R = exp(log_ratio).

        Uses the log-normal mean: E[R] = exp(mu + 1/(2*tau)).
        """
        return float(math.exp(self.mu + 0.5 / max(self.tau, 1e-8)))


class PLAFCalculator:
    """Paper-to-Live Adjustment Factor calculator.

    Adjusts paper-trading cost estimates to approximate live execution
    costs. Multipliers start from configured seed values and shift toward
    empirical ratios as matched paper/live data accumulates.

    Usage::

        plaf = PLAFCalculator(PLAFConfig())
        adjusted = plaf.adjust_cost(paper_cost_dict)
        plaf.update_with_live(paper_costs, live_costs)

    Ref: specs/13-execution-cost-and-microstructure.md S6
    Ref: specs/14-ibkr-integration.md S9
    """

    def __init__(self, config: PLAFConfig | None = None) -> None:
        self._config = config or PLAFConfig()
        self._log = structlog.get_logger("midas.execution.plaf")

        # Bayesian state per cost component
        self._spread_state = _BayesianState(
            mu=math.log(self._config.spread_multiplier)
        )
        self._impact_state = _BayesianState(
            mu=math.log(self._config.impact_multiplier)
        )
        self._slippage_state = _BayesianState(mu=0.0)  # additive, not multiplicative

        # Track cumulative slippage observations for additive adjustment
        self._slippage_additions: list[float] = []
        self._live_slippage_sum: float = 0.0
        self._paper_slippage_sum: float = 0.0

    @property
    def config(self) -> PLAFConfig:
        """Return the active PLAF configuration."""
        return self._config

    def _spread_multiplier(self) -> float:
        """Return the effective spread multiplier (Bayesian or seed)."""
        if self._spread_state.n_observations >= self._config.update_threshold:
            return self._spread_state.multiplier()
        return self._config.spread_multiplier

    def _impact_multiplier(self) -> float:
        """Return the effective impact multiplier (Bayesian or seed)."""
        if self._impact_state.n_observations >= self._config.update_threshold:
            return self._impact_state.multiplier()
        return self._config.impact_multiplier

    def _slippage_adjustment(self) -> float:
        """Return the effective slippage additive adjustment (bps).

        Once enough observations exist, the adjustment is the empirical
        mean of (live_slippage_bps - paper_slippage_bps). Before the
        threshold, the seed value is used.
        """
        if (
            self._slippage_state.n_observations >= self._config.update_threshold
            and self._slippage_additions
        ):
            return float(np.mean(self._slippage_additions))
        return self._config.slippage_add_bps

    def adjust_cost(self, paper_cost: dict[str, Any]) -> dict[str, Any]:
        """Apply PLAF multipliers to a paper-trading cost breakdown.

        Parameters
        ----------
        paper_cost:
            Dict with keys like ``spread_cost``, ``impact_cost``,
            ``slippage_bps``, and any other cost components.

        Returns
        -------
        Dict with the same keys plus ``plaf_adjusted`` flag and
        ``plaf_multipliers`` dict showing which factors were applied.
        """
        spread_m = self._spread_multiplier()
        impact_m = self._impact_multiplier()
        slippage_add = self._slippage_adjustment()

        adjusted = dict(paper_cost)

        # Apply multipliers
        adjusted["spread_cost"] = float(paper_cost.get("spread_cost", 0.0)) * spread_m
        adjusted["impact_cost"] = float(paper_cost.get("impact_cost", 0.0)) * impact_m

        paper_slippage = float(paper_cost.get("slippage_bps", 0.0))
        adjusted["slippage_bps"] = paper_slippage + slippage_add

        # Recompute total if it exists
        if "total_cost" in paper_cost:
            original_total = float(paper_cost["total_cost"])
            # Delta from multipliers
            spread_delta = adjusted["spread_cost"] - float(paper_cost.get("spread_cost", 0.0))
            impact_delta = adjusted["impact_cost"] - float(paper_cost.get("impact_cost", 0.0))
            slippage_delta = slippage_add  # bps, converted to cost by caller
            adjusted["total_cost"] = original_total + spread_delta + impact_delta + slippage_delta

        adjusted["plaf_adjusted"] = True
        adjusted["plaf_multipliers"] = {
            "spread": round(spread_m, 4),
            "impact": round(impact_m, 4),
            "slippage_add_bps": round(slippage_add, 4),
            "using_bayesian": self._spread_state.n_observations >= self._config.update_threshold,
        }

        return adjusted

    def update_with_live(
        self,
        paper_costs: list[dict[str, Any]],
        live_costs: list[dict[str, Any]],
    ) -> None:
        """Update PLAF multipliers from matched paper/live cost pairs.

        Parameters
        ----------
        paper_costs:
            List of paper-trading cost dicts. Each must have ``spread_cost``
            and/or ``impact_cost`` and/or ``slippage_bps`` keys.
        live_costs:
            Matching list of live cost dicts with the same keys.

        Raises
        ------
        ValueError
            If the two lists have different lengths.
        """
        if len(paper_costs) != len(live_costs):
            raise ValueError(
                f"paper_costs ({len(paper_costs)}) and live_costs "
                f"({len(live_costs)}) must have the same length"
            )

        if not paper_costs:
            return

        spread_log_ratios: list[float] = []
        impact_log_ratios: list[float] = []
        slippage_deltas: list[float] = []

        for paper, live in zip(paper_costs, live_costs):
            p_spread = float(paper.get("spread_cost", 0.0))
            l_spread = float(live.get("spread_cost", 0.0))
            p_impact = float(paper.get("impact_cost", 0.0))
            l_impact = float(live.get("impact_cost", 0.0))
            p_slip = float(paper.get("slippage_bps", 0.0))
            l_slip = float(live.get("slippage_bps", 0.0))

            # Only include ratios where the paper cost is nonzero to avoid
            # log(0) or division-by-zero.
            if p_spread > 1e-12 and l_spread > 1e-12:
                spread_log_ratios.append(math.log(l_spread / p_spread))
            if p_impact > 1e-12 and l_impact > 1e-12:
                impact_log_ratios.append(math.log(l_impact / p_impact))
            slippage_deltas.append(l_slip - p_slip)

        self._spread_state.update(spread_log_ratios, self._config.prior_strength)
        self._impact_state.update(impact_log_ratios, self._config.prior_strength)
        self._slippage_state.update(
            [math.log(max(d, 1e-8)) for d in slippage_deltas if d > 0],
            self._config.prior_strength,
        )
        self._slippage_additions.extend(slippage_deltas)

        self._log.info(
            "plaf.bayesian_update",
            spread_obs=len(spread_log_ratios),
            impact_obs=len(impact_log_ratios),
            slippage_obs=len(slippage_deltas),
            total_obs=self._spread_state.n_observations,
            threshold=self._config.update_threshold,
        )

    def get_adjusted_cost_breakdown(self, paper_cost_breakdown: dict[str, Any]) -> dict[str, Any]:
        """Return a full PLAF-adjusted cost breakdown with raw and adjusted.

        The returned dict contains:
        - ``raw``: the original paper costs unchanged
        - ``adjusted``: the PLAF-adjusted costs
        - ``adjustment_deltas``: difference between adjusted and raw per component
        - ``multipliers``: the multipliers used

        Parameters
        ----------
        paper_cost_breakdown:
            Full cost dict from ``ExecutionCostModel.estimate_total_cost()``
            or similar, including at least ``spread_cost``, ``impact_cost``,
            and optionally ``slippage_bps``.
        """
        raw = dict(paper_cost_breakdown)
        adjusted = self.adjust_cost(paper_cost_breakdown)

        deltas: dict[str, float] = {}
        for key in ("spread_cost", "impact_cost", "slippage_bps", "total_cost"):
            raw_val = float(raw.get(key, 0.0))
            adj_val = float(adjusted.get(key, 0.0))
            deltas[key] = round(adj_val - raw_val, 6)

        return {
            "raw": raw,
            "adjusted": adjusted,
            "adjustment_deltas": deltas,
            "multipliers": adjusted.get("plaf_multipliers", {}),
        }
