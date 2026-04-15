"""Composite track record scoring.

Computes a 0-100 composite score from risk-adjusted performance metrics
using a weighted formula that balances return, risk, and consistency.

Ref: M16 — Track record scorer
"""

import structlog

logger = structlog.get_logger("midas.attribution.track_record")

# Weights for composite score components.
_WEIGHTS = {
    "sharpe_ratio": 0.25,
    "sortino_ratio": 0.15,
    "max_drawdown": 0.20,
    "win_rate": 0.20,
    "avg_return": 0.20,
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
            Must contain: sharpe_ratio, sortino_ratio, max_drawdown,
            win_rate, avg_return.

        Returns
        -------
        float
            Score between 0 and 100.
        """
        # Normalize each component to a 0-1 scale
        sharpe = metrics.get("sharpe_ratio", 0.0)
        sortino = metrics.get("sortino_ratio", 0.0)
        max_dd = metrics.get("max_drawdown", 0.0)
        win_rate = metrics.get("win_rate", 0.5)
        avg_return = metrics.get("avg_return", 0.0)

        # Sharpe: map [-2, 3] -> [0, 1]
        sharpe_score = max(0.0, min(1.0, (sharpe + 2.0) / 5.0))

        # Sortino: map [-2, 4] -> [0, 1]
        sortino_score = max(0.0, min(1.0, (sortino + 2.0) / 6.0))

        # Max drawdown: map [0.5, 0] -> [0, 1] (lower drawdown is better)
        dd_score = max(0.0, min(1.0, 1.0 - max_dd / 0.5))

        # Win rate: already 0-1
        win_score = max(0.0, min(1.0, win_rate))

        # Avg return: map [-0.2, 0.3] -> [0, 1]
        return_score = max(0.0, min(1.0, (avg_return + 0.2) / 0.5))

        # Weighted composite
        raw_score = (
            _WEIGHTS["sharpe_ratio"] * sharpe_score
            + _WEIGHTS["sortino_ratio"] * sortino_score
            + _WEIGHTS["max_drawdown"] * dd_score
            + _WEIGHTS["win_rate"] * win_score
            + _WEIGHTS["avg_return"] * return_score
        )

        # Scale to 0-100 and clamp
        composite = max(0.0, min(100.0, raw_score * 100.0))

        return composite
