"""Brinson-Fachler attribution decomposition.

Decomposes active return into allocation, selection, and interaction effects.
The Brinson-Fachler model modifies the allocation effect to use benchmark
returns relative to the total benchmark return, avoiding the "large allocation
effect for underweight in a negative-return sector" problem.

Ref: M16 — Brinson decomposition
"""

import numpy as np

import structlog

logger = structlog.get_logger("midas.attribution.brinson")


class BrinsonDecomposition:
    """Brinson-Fachler attribution decomposition."""

    def __init__(self):
        pass

    def decompose(
        self,
        portfolio_weights: np.ndarray,
        benchmark_weights: np.ndarray,
        portfolio_returns: np.ndarray,
        benchmark_returns: np.ndarray,
        categories: list[str] | None = None,
    ) -> dict:
        """Decompose into allocation, selection, interaction effects.

        Uses the Brinson-Fachler model where:
        - Allocation = (w_p - w_b) * (r_b - r_b_total)
        - Selection = w_b * (r_p - r_b)
        - Interaction = (w_p - w_b) * (r_p - r_b)

        Parameters
        ----------
        portfolio_weights : np.ndarray
            Portfolio weight per category. Must sum to ~1.0.
        benchmark_weights : np.ndarray
            Benchmark weight per category. Must sum to ~1.0.
        portfolio_returns : np.ndarray
            Portfolio return per category.
        benchmark_returns : np.ndarray
            Benchmark return per category.
        categories : list[str] | None
            Optional category labels.

        Returns
        -------
        dict with allocation_effect, selection_effect, interaction_effect,
        total_active_return, and per_category breakdown.
        """
        n = len(portfolio_weights)

        if not (len(benchmark_weights) == len(portfolio_returns) == len(benchmark_returns) == n):
            raise ValueError(
                f"All arrays must have the same length. Got "
                f"portfolio_weights={len(portfolio_weights)}, "
                f"benchmark_weights={len(benchmark_weights)}, "
                f"portfolio_returns={len(portfolio_returns)}, "
                f"benchmark_returns={len(benchmark_returns)}"
            )

        # Total benchmark return (used in Brinson-Fachler allocation effect)
        total_benchmark_return = float(np.dot(benchmark_weights, benchmark_returns))

        # Per-category effects (Brinson-Fachler)
        weight_diff = portfolio_weights - benchmark_weights
        return_diff = portfolio_returns - benchmark_returns

        # Allocation effect: (w_p - w_b) * (r_b - R_b)
        allocation_per_cat = weight_diff * (benchmark_returns - total_benchmark_return)

        # Selection effect: w_b * (r_p - r_b)
        selection_per_cat = benchmark_weights * return_diff

        # Interaction effect: (w_p - w_b) * (r_p - r_b)
        interaction_per_cat = weight_diff * return_diff

        # Aggregate effects
        allocation_effect = float(np.sum(allocation_per_cat))
        selection_effect = float(np.sum(selection_per_cat))
        interaction_effect = float(np.sum(interaction_per_cat))
        total_active_return = allocation_effect + selection_effect + interaction_effect

        # Build per-category breakdown
        per_category = []
        for i in range(n):
            label = categories[i] if categories and i < len(categories) else f"category_{i}"
            per_category.append(
                {
                    "category": label,
                    "allocation": float(allocation_per_cat[i]),
                    "selection": float(selection_per_cat[i]),
                    "interaction": float(interaction_per_cat[i]),
                    "portfolio_weight": float(portfolio_weights[i]),
                    "benchmark_weight": float(benchmark_weights[i]),
                    "portfolio_return": float(portfolio_returns[i]),
                    "benchmark_return": float(benchmark_returns[i]),
                }
            )

        return {
            "allocation_effect": allocation_effect,
            "selection_effect": selection_effect,
            "interaction_effect": interaction_effect,
            "total_active_return": total_active_return,
            "per_category": per_category,
        }
