"""
Posterior combination strategies for multi-model latent state pooling.

Provides mixture averaging, precision-weighted averaging, and
router-based selection to combine posteriors from champion and
challenger models into a single posterior for downstream use.

Ref: M04 State Inference Pool specification
Ref: specs/04-latent-first-architecture.md SS2.3 (pool combination)
"""

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class PosteriorCombination:
    """Combine multiple posterior distributions into a single posterior.

    Each posterior is represented as a dict with 'mean' and 'variance'
    keys, each holding numpy arrays of shape (latent_dim,).

    Three combination strategies:

    * **mixture_average** -- weighted average of means, variance includes
      between-component spread (accounts for model disagreement).
    * **weighted_average** -- precision-weighted fusion that reduces
      variance when models agree.
    * **router_selected** -- picks the single posterior with the highest
      router score (no mixing).
    """

    def mixture_average(
        self,
        posteriors: list[dict[str, np.ndarray]],
        weights: list[float],
    ) -> dict[str, np.ndarray]:
        """Weighted mixture of posteriors.

        The mixture mean is the weighted average of component means.
        The mixture variance includes both within-component variance and
        between-component spread (law of total variance).

        Parameters
        ----------
        posteriors:
            List of dicts with 'mean' and 'variance' numpy arrays.
        weights:
            Mixing weights (must sum to 1.0, one per posterior).

        Returns
        -------
        dict with 'mean' and 'variance' arrays.
        """
        self._validate_inputs(posteriors, weights)

        if len(posteriors) == 1:
            return {
                "mean": posteriors[0]["mean"].copy(),
                "variance": posteriors[0]["variance"].copy(),
            }

        weights_arr = np.array(weights, dtype=np.float64)
        means = np.array([p["mean"] for p in posteriors])
        variances = np.array([p["variance"] for p in posteriors])

        # Mixture mean: E[mu] = sum(w_i * mu_i)
        mixture_mean = np.sum(weights_arr[:, None] * means, axis=0)

        # Law of total variance:
        # Var = E[Var] + Var[E]
        #     = sum(w_i * var_i) + sum(w_i * (mu_i - E[mu])^2)
        within = np.sum(weights_arr[:, None] * variances, axis=0)
        between = np.sum(weights_arr[:, None] * (means - mixture_mean[None, :]) ** 2, axis=0)
        mixture_variance = within + between

        logger.debug(
            "posterior.mixture_average",
            n_components=len(posteriors),
            mean_norm=float(np.linalg.norm(mixture_mean)),
            variance_mean=float(np.mean(mixture_variance)),
        )

        return {"mean": mixture_mean, "variance": mixture_variance}

    def weighted_average(
        self,
        posteriors: list[dict[str, np.ndarray]],
        weights: list[float],
    ) -> dict[str, np.ndarray]:
        """Precision-weighted posterior fusion.

        Each component is weighted by its precision (1/variance) scaled by
        the provided weight. This produces a fused posterior with variance
        strictly less than any input variance when models agree.

        Parameters
        ----------
        posteriors:
            List of dicts with 'mean' and 'variance' numpy arrays.
        weights:
            Per-posterior confidence weights.

        Returns
        -------
        dict with 'mean' and 'variance' arrays.
        """
        self._validate_inputs(posteriors, weights)

        if len(posteriors) == 1:
            return {
                "mean": posteriors[0]["mean"].copy(),
                "variance": posteriors[0]["variance"].copy(),
            }

        weights_arr = np.array(weights, dtype=np.float64)
        means = np.array([p["mean"] for p in posteriors])
        variances = np.array([p["variance"] for p in posteriors])

        # Weighted precision: w_i / var_i
        precisions = weights_arr[:, None] / variances

        # Fused precision: sum of weighted precisions
        fused_precision = np.sum(precisions, axis=0)

        # Fused variance: 1 / fused_precision
        fused_variance = 1.0 / fused_precision

        # Fused mean: sum(precision_i * mu_i) / fused_precision
        fused_mean = np.sum(precisions * means, axis=0) / fused_precision

        logger.debug(
            "posterior.weighted_average",
            n_components=len(posteriors),
            mean_norm=float(np.linalg.norm(fused_mean)),
            variance_mean=float(np.mean(fused_variance)),
        )

        return {"mean": fused_mean, "variance": fused_variance}

    def router_selected(
        self,
        posteriors: list[dict[str, np.ndarray]],
        router_scores: list[float],
        z_t: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Select a single posterior based on router scores.

        The posterior with the highest router score is returned unchanged.
        No mixing or averaging is performed.

        Parameters
        ----------
        posteriors:
            List of dicts with 'mean' and 'variance' numpy arrays.
        router_scores:
            Per-posterior scores from the routing network.
        z_t:
            Current latent state (used for logging/tracing only).

        Returns
        -------
        dict with 'mean' and 'variance' arrays from the selected posterior.
        """
        if not posteriors:
            raise ValueError("Cannot select from empty posteriors list")
        if len(posteriors) != len(router_scores):
            raise ValueError(
                f"Length mismatch: {len(posteriors)} posteriors vs "
                f"{len(router_scores)} router scores"
            )

        winner_idx = int(np.argmax(router_scores))

        logger.info(
            "posterior.router_selected",
            winner_idx=winner_idx,
            winner_score=router_scores[winner_idx],
            n_candidates=len(posteriors),
        )

        return {
            "mean": posteriors[winner_idx]["mean"].copy(),
            "variance": posteriors[winner_idx]["variance"].copy(),
        }

    @staticmethod
    def _validate_inputs(
        posteriors: list[dict[str, np.ndarray]],
        weights: list[float],
    ) -> None:
        """Validate that inputs are well-formed."""
        if not posteriors:
            raise ValueError("posteriors list must not be empty")
        if len(posteriors) != len(weights):
            raise ValueError(
                f"Length mismatch: {len(posteriors)} posteriors vs " f"{len(weights)} weights"
            )

        for i, p in enumerate(posteriors):
            if "mean" not in p or "variance" not in p:
                raise ValueError(f"Posterior at index {i} missing 'mean' or 'variance' key")
            if not isinstance(p["mean"], np.ndarray):
                raise ValueError(
                    f"Posterior mean at index {i} must be numpy array, " f"got {type(p['mean'])}"
                )
            if not isinstance(p["variance"], np.ndarray):
                raise ValueError(
                    f"Posterior variance at index {i} must be numpy array, "
                    f"got {type(p['variance'])}"
                )
            if p["mean"].shape != p["variance"].shape:
                raise ValueError(
                    f"Shape mismatch at index {i}: mean {p['mean'].shape} "
                    f"vs variance {p['variance'].shape}"
                )

        total_weight = sum(weights)
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")
