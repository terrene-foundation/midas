"""Composite track record scoring.

Computes a 0-100 composite score from risk-adjusted performance metrics
using a weighted formula that balances attribution, risk, calibration,
and execution quality.

Ref: specs/12-attribution.md S6.1 (Track Record Scorer Weights)
"""

import structlog

logger = structlog.get_logger("midas.attribution.track_record")

# Weights for composite score components (specs/12 S6.1).
_WEIGHTS = {
    "brinson_allocation": 0.15,
    "brinson_selection": 0.15,
    "calmar": 0.15,
    "calibration_quality": 0.15,
    "override_convergence": 0.10,
    "degradation_events": 0.10,
    "turnover_cost_drag": 0.10,
    "worst_case_window": 0.10,
}


class TrackRecordScorer:
    """Composite track record score."""

    def __init__(self):
        pass

    def compute_composite(self, metrics: dict) -> float:
        """Compute composite score from metrics dict.

        Score is normalized to 0-100 range based on each metric's
        contribution.

        Parameters
        ----------
        metrics : dict
            Must contain: brinson_allocation, brinson_selection, calmar,
            calibration_quality, override_convergence, degradation_events,
            turnover_cost_drag, worst_case_window.

        Returns
        -------
        float
            Score between 0 and 100.
        """
        # Normalize each component to a 0-1 scale
        brinson_alloc = metrics.get("brinson_allocation", 0.0)
        brinson_sel = metrics.get("brinson_selection", 0.0)
        calmar = metrics.get("calmar", 0.0)
        cal_quality = metrics.get("calibration_quality", 0.0)
        override_conv = metrics.get("override_convergence", 0.0)
        degradation = metrics.get("degradation_events", 0.0)
        turnover_drag = metrics.get("turnover_cost_drag", 0.0)
        worst_case = metrics.get("worst_case_window", 0.0)

        # Brinson allocation: map [-0.05, 0.05] -> [0, 1]
        alloc_score = max(0.0, min(1.0, (brinson_alloc + 0.05) / 0.10))

        # Brinson selection: map [-0.05, 0.05] -> [0, 1]
        sel_score = max(0.0, min(1.0, (brinson_sel + 0.05) / 0.10))

        # Calmar: map [-5, 5] -> [0, 1]
        calmar_score = max(0.0, min(1.0, (calmar + 5.0) / 10.0))

        # Calibration quality: already 0-1 (higher is better)
        cal_score = max(0.0, min(1.0, cal_quality))

        # Override convergence: already 0-1 (higher is better)
        override_score = max(0.0, min(1.0, override_conv))

        # Degradation events: map [10, 0] -> [0, 1] (fewer is better)
        degradation_score = max(0.0, min(1.0, 1.0 - degradation / 10.0))

        # Turnover/cost drag: map [0.05, 0] -> [0, 1] (lower is better)
        turnover_score = max(0.0, min(1.0, 1.0 - turnover_drag / 0.05))

        # Worst-case window: map [0.30, 0] -> [0, 1] (lower is better)
        worst_score = max(0.0, min(1.0, 1.0 - worst_case / 0.30))

        # Weighted composite
        raw_score = (
            _WEIGHTS["brinson_allocation"] * alloc_score
            + _WEIGHTS["brinson_selection"] * sel_score
            + _WEIGHTS["calmar"] * calmar_score
            + _WEIGHTS["calibration_quality"] * cal_score
            + _WEIGHTS["override_convergence"] * override_score
            + _WEIGHTS["degradation_events"] * degradation_score
            + _WEIGHTS["turnover_cost_drag"] * turnover_score
            + _WEIGHTS["worst_case_window"] * worst_score
        )

        # Scale to 0-100 and clamp
        composite = max(0.0, min(100.0, raw_score * 100.0))

        return composite
