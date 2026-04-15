"""
Outer loop: population-based training harness.

Runs generations of configs against a fitness function, selects winners,
and mutates to refill the population. The PBT harness drives continuous
improvement of the model pool.

Ref: specs/06-meta-router.md
"""

import copy
import random

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)


class PBTHarness:
    """Population-based training harness backed by DataFlow."""

    def __init__(self, db: DataFlow, population_size: int = 8) -> None:
        self._db = db
        self._population_size = population_size

    async def run_generation(
        self,
        configs: list[dict],
        fitness_fn,
    ) -> list[dict]:
        """Run one PBT generation.

        Evaluates each config against the fitness function and returns
        (config, fitness) pairs sorted by fitness descending.
        """
        results: list[dict] = []

        for config in configs:
            fitness = fitness_fn(config)
            results.append(
                {
                    "config": config,
                    "fitness": fitness,
                }
            )

        # Sort by fitness descending
        results.sort(key=lambda r: r["fitness"], reverse=True)

        logger.info(
            "pbt.generation_complete",
            population_size=len(results),
            best_fitness=results[0]["fitness"] if results else None,
        )
        return results

    async def select_and_mutate(
        self,
        population: list[dict],
        n_winners: int = 3,
    ) -> list[dict]:
        """Select top performers and mutate to fill population.

        Returns a new population of size population_size. The first
        n_winners entries are the elite (unchanged). Remaining slots
        are filled by mutating random winners with small perturbations.
        """
        sorted_pop = sorted(population, key=lambda r: r["fitness"], reverse=True)
        winners = sorted_pop[:n_winners]

        next_gen: list[dict] = [copy.deepcopy(w) for w in winners]

        # Fill remaining slots with mutated copies of winners
        while len(next_gen) < self._population_size:
            parent = copy.deepcopy(random.choice(winners))
            mutated_config = self._mutate_config(parent["config"])
            next_gen.append(
                {
                    "config": mutated_config,
                    "fitness": parent["fitness"],  # will be re-evaluated next generation
                }
            )

        logger.info(
            "pbt.select_and_mutate",
            n_winners=n_winners,
            next_gen_size=len(next_gen),
        )
        return next_gen

    @staticmethod
    def _mutate_config(config: dict) -> dict:
        """Apply a small random perturbation to numeric config values."""
        mutated = copy.deepcopy(config)
        for key, value in mutated.items():
            if isinstance(value, (int, float)):
                # Perturb by +/- 20%
                factor = 1.0 + random.uniform(-0.2, 0.2)
                mutated[key] = type(value)(value * factor)
        return mutated
