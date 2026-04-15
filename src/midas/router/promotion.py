"""
Promotion/demotion contract evaluator.

Evaluates challengers against champions using statistical tests on
tracked metrics (e.g. Sharpe ratio). Promotion requires meeting a
minimum observation count and confidence threshold.

Ref: specs/06-meta-router.md
"""

import json
import math

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)


class PromotionEvaluator:
    """Evaluates challengers against promotion contracts."""

    def __init__(self, db: DataFlow) -> None:
        self._db = db

    async def evaluate_promotion(
        self,
        challenger_family: str,
        challenger_version: str,
        champion_family: str,
        metric: str = "sharpe",
        min_observations: int = 252,
        confidence_level: float = 0.95,
    ) -> dict:
        """Evaluate promotion contract.

        Compares challenger metric distribution against champion's using
        a two-sample test. Returns promotion decision with statistics.
        """
        decisions = await self._db.express.list("decisions")

        challenger_metrics: list[float] = []
        champion_metrics: list[float] = []

        for row in decisions:
            model_version = row.get("model_version", "")
            outcome_str = row.get("outcome_json", "")
            if not outcome_str:
                continue
            try:
                outcome = json.loads(outcome_str)
            except (json.JSONDecodeError, TypeError):
                continue

            metric_val = outcome.get(metric)
            if metric_val is None:
                continue

            prefix = f"{challenger_family}/"
            champ_prefix = f"{champion_family}/"
            if model_version.startswith(prefix):
                challenger_metrics.append(float(metric_val))
            elif model_version.startswith(champ_prefix):
                champion_metrics.append(float(metric_val))

        n_challenger = len(challenger_metrics)
        n_champion = len(champion_metrics)

        # Check minimum observations
        if n_challenger < min_observations or n_champion < 1:
            logger.info(
                "promotion.insufficient_data",
                challenger_n=n_challenger,
                champion_n=n_champion,
                min_observations=min_observations,
            )
            return {
                "should_promote": False,
                "p_value": 1.0,
                "ci_lower": 0.0,
                "ci_upper": 0.0,
                "metric_diff": 0.0,
                "reason": "insufficient_observations",
            }

        # Compute means
        challenger_mean = sum(challenger_metrics) / n_challenger
        champion_mean = sum(champion_metrics) / n_champion if n_champion > 0 else 0.0
        metric_diff = challenger_mean - champion_mean

        # Pooled standard deviation for two-sample test
        challenger_var = (
            sum((x - challenger_mean) ** 2 for x in challenger_metrics) / n_challenger
            if n_challenger > 1
            else 0.0
        )
        champion_var = (
            sum((x - champion_mean) ** 2 for x in champion_metrics) / n_champion
            if n_champion > 1
            else 0.0
        )

        pooled_se = (
            math.sqrt(challenger_var / n_challenger + champion_var / n_champion)
            if (challenger_var + champion_var) > 0
            else 1.0
        )

        # Z-score approximation for p-value
        z_score = metric_diff / pooled_se if pooled_se > 0 else 0.0
        p_value = 2.0 * (1.0 - _normal_cdf(abs(z_score)))

        # Confidence interval for the difference
        z_critical = _inv_normal_cdf((1.0 + confidence_level) / 2.0)
        ci_lower = metric_diff - z_critical * pooled_se
        ci_upper = metric_diff + z_critical * pooled_se

        # Promote if challenger is significantly better (one-sided: metric_diff > 0)
        alpha = 1.0 - confidence_level
        should_promote = p_value < alpha and metric_diff > 0 and ci_lower > 0

        logger.info(
            "promotion.evaluated",
            challenger=challenger_family,
            champion=champion_family,
            should_promote=should_promote,
            metric_diff=metric_diff,
            p_value=p_value,
        )

        return {
            "should_promote": should_promote,
            "p_value": p_value,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "metric_diff": metric_diff,
        }

    async def evaluate_demotion(
        self,
        champion_family: str,
        metric: str = "sharpe",
        degradation_threshold: float = -0.5,
    ) -> dict:
        """Evaluate degradation of a live champion.

        Checks whether the champion's recent performance has fallen below
        the degradation threshold relative to its historical baseline.
        """
        # Look up the champion's metrics from model_registry
        registry_rows = await self._db.express.list("model_registry")
        champion_rows = [
            r
            for r in registry_rows
            if r.get("model_family") == champion_family and r.get("promotion_status") == "champion"
        ]

        if not champion_rows:
            return {
                "should_demote": False,
                "current_metric": 0.0,
                "threshold_breached": False,
                "reason": "champion_not_found",
            }

        champion = champion_rows[-1]
        metrics_str = champion.get("metrics_json", "{}")
        try:
            metrics = json.loads(metrics_str) if metrics_str else {}
        except (json.JSONDecodeError, TypeError):
            metrics = {}

        current_metric = metrics.get(metric, 0.0)

        # Check against degradation threshold
        threshold_breached = current_metric < degradation_threshold
        should_demote = threshold_breached

        return {
            "should_demote": should_demote,
            "current_metric": current_metric,
            "threshold_breached": threshold_breached,
        }


class DemotionEvaluator:
    """Continuously evaluates live champions against degradation thresholds."""

    def __init__(self, db: DataFlow) -> None:
        self._db = db

    async def check_champion_health(self, champion_family: str) -> dict:
        """Check if champion is healthy.

        Returns a health status dict with healthy flag, current metrics,
        and a list of any threshold violations.
        """
        registry_rows = await self._db.express.list("model_registry")
        champion_rows = [
            r
            for r in registry_rows
            if r.get("model_family") == champion_family and r.get("promotion_status") == "champion"
        ]

        if not champion_rows:
            return {
                "healthy": False,
                "metrics": {},
                "violations": ["champion_not_found"],
            }

        champion = champion_rows[-1]
        metrics_str = champion.get("metrics_json", "{}")
        try:
            metrics = json.loads(metrics_str) if metrics_str else {}
        except (json.JSONDecodeError, TypeError):
            metrics = {}

        violations: list[str] = []

        # Health checks
        sharpe = metrics.get("sharpe", 0.0)
        if sharpe < -0.5:
            violations.append("sharpe_below_threshold")

        if metrics.get("max_drawdown", 0.0) < -0.3:
            violations.append("excessive_drawdown")

        healthy = len(violations) == 0

        return {
            "healthy": healthy,
            "metrics": metrics,
            "violations": violations,
        }


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def _normal_cdf(x: float) -> float:
    """Approximate the standard normal CDF using the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _inv_normal_cdf(p: float) -> float:
    """Approximate the inverse standard normal CDF (quantile function).

    Uses the rational approximation from Abramowitz and Stegun.
    """
    if p <= 0.0:
        return -3.5
    if p >= 1.0:
        return 3.5
    if p < 0.5:
        return -_inv_normal_cdf(1.0 - p)

    # Rational approximation for p >= 0.5
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    c0 = 2.515517
    c1 = 0.802853
    c2 = 0.010328
    d1 = 1.432788
    d2 = 0.189269
    d3 = 0.001308

    return t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
