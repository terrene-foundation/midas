"""
Middle loop: contextual bandit router for mixture-of-experts selection.

Selects and blends pool outputs per z_t context, recording every routing
decision to the audit log for provenance.

Ref: specs/06-meta-router.md
"""

import json
import math

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)

# Default expert pool names (matching the ML pool members)
_DEFAULT_EXPERTS = [
    "ssl_transformer_v1",
    "contrastive_v1",
    "mae_v1",
    "vae_v1",
    "deep_ssm_v1",
]


class ContextualRouter:
    """Mixture-of-experts router that selects/blends pool outputs per z_t context."""

    def __init__(self, db: DataFlow, n_experts: int = 5) -> None:
        self._db = db
        self._n_experts = n_experts
        self._experts = _DEFAULT_EXPERTS[:n_experts]

    async def select_experts(
        self,
        z_t: list[float],
        context: dict,
    ) -> dict:
        """Select and weight experts for given z_t context.

        Uses a softmax over routing scores derived from z_t dot-product
        with per-expert embeddings. Returns dict with selected_heads,
        weights, and routing_scores.

        The routing is deterministic for the same z_t input, ensuring
        reproducible decisions for audit and backtesting.
        """
        z_dim = len(z_t)
        routing_scores: list[float] = []

        for i, expert in enumerate(self._experts):
            # Deterministic routing score: dot product of z_t with a
            # position-dependent pseudo-embedding. Each expert gets a
            # shifted version of z_t to create differentiation.
            score = 0.0
            for j, z_val in enumerate(z_t):
                # Phase-shifted weight per expert creates distinct preferences
                weight = math.sin((i + 1) * (j + 1) * 0.1)
                score += z_val * weight
            routing_scores.append(score)

        # Softmax with temperature
        temperature = 1.0
        max_score = max(routing_scores)
        exp_scores = [math.exp((s - max_score) / temperature) for s in routing_scores]
        sum_exp = sum(exp_scores)
        weights = [e / sum_exp for e in exp_scores]

        # Select top-k experts (all experts participate, weighted)
        selected = self._experts[:]

        result = {
            "selected_heads": selected,
            "weights": weights,
            "routing_scores": routing_scores,
        }

        logger.debug(
            "router.selected_experts",
            n_selected=len(selected),
            top_weight=max(weights),
        )
        return result

    async def blend_outputs(
        self,
        outputs: list[dict],
        weights: list[float],
    ) -> dict:
        """Blend multiple head outputs by weights.

        For each key in the output dicts, computes the weighted average.
        Handles nested dicts (e.g. allocation sub-dicts) recursively.
        """
        if not outputs:
            return {}

        if len(outputs) != len(weights):
            raise ValueError(
                f"outputs length ({len(outputs)}) must match weights length ({len(weights)})"
            )

        blended: dict = {}
        all_keys = set()
        for output in outputs:
            all_keys.update(output.keys())

        for key in all_keys:
            values = [o.get(key) for o in outputs]
            if all(isinstance(v, dict) for v in values):
                # Recursive blend for nested dicts
                nested_outputs = values
                blended[key] = await self.blend_outputs(nested_outputs, weights)
            elif all(isinstance(v, (int, float)) for v in values):
                weighted_sum = sum(v * w for v, w in zip(values, weights))
                blended[key] = weighted_sum
            else:
                # For non-numeric, take the value from the highest-weighted output
                best_idx = weights.index(max(weights))
                blended[key] = values[best_idx]

        return blended

    async def record_routing_decision(
        self,
        decision_id: str,
        z_t: list[float],
        heads: list[str],
        weights: list[float],
    ) -> None:
        """Record routing decision to audit log."""
        details = json.dumps(
            {
                "heads": heads,
                "weights": weights,
                "z_t_dim": len(z_t),
            }
        )

        row = {
            "rule_name": "contextual_router",
            "action": "routing_decision",
            "details": details,
            "severity": "info",
            "decision_id": decision_id,
            "z_t_snapshot": json.dumps(z_t),
        }

        await self._db.express.create("audit_log", row)
        logger.info(
            "router.decision_recorded",
            decision_id=decision_id,
            n_heads=len(heads),
        )
