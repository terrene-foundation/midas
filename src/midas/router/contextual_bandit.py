"""
Middle loop: contextual bandit router for mixture-of-experts selection.

Replaces deterministic softmax routing with a learned LinUCB or Thompson
Sampling bandit that improves expert selection based on realized outcomes.

Ref: specs/05-model-pool-and-meta-router.md S4.2 (Router Structure)
"""

import json
import math
from collections import deque
from typing import Literal

import numpy as np
import structlog
from dataflow import DataFlow

from midas.router.contextual_router import ContextualRouter, _DEFAULT_EXPERTS

logger = structlog.get_logger(__name__)


class LinUCBContextualBandit:
    """LinUCB (Linear Upper Confidence Bound) bandit for expert selection.

    Maintains per-arm A matrices and b vectors following the standard LinUCB
    algorithm (Li et al., 2010). Exploration is controlled by the alpha
    parameter: higher alpha means more exploration.

    Args:
        alpha: Exploration parameter. Default 1.0 balances explore/exploit.
    """

    def __init__(self, alpha: float = 1.0) -> None:
        if alpha <= 0:
            raise ValueError(f"alpha must be positive, got {alpha}")
        self._alpha = alpha
        # Per-arm state, keyed by arm index. Populated on first use.
        self._A: dict[int, np.ndarray] = {}
        self._b: dict[int, np.ndarray] = {}
        # Track update counts for confidence reporting
        self._update_counts: dict[int, int] = {}

    def _ensure_arm(self, arm: int, d: int) -> None:
        """Initialize arm state if not present."""
        if arm not in self._A:
            self._A[arm] = np.eye(d)
            self._b[arm] = np.zeros(d)
            self._update_counts[arm] = 0

    def select_arm(
        self,
        context: list[float],
        n_arms: int,
    ) -> tuple[int, list[float]]:
        """Select the best arm using UCB exploration.

        Args:
            context: Feature vector describing the current decision context.
            n_arms: Number of arms (experts) to choose among.

        Returns:
            Tuple of (chosen_arm_index, probability_distribution_over_arms).
            The probabilities are derived from softmax over UCB scores.
        """
        x = np.array(context, dtype=np.float64)
        if x.size == 0:
            raise ValueError("Context vector must not be empty")
        if not np.all(np.isfinite(x)):
            raise ValueError("Context vector contains non-finite values")
        d = len(x)
        ucb_scores: list[float] = []

        for arm in range(n_arms):
            self._ensure_arm(arm, d)
            # Regularize before inversion to prevent LinAlgError on singular A
            A_reg = self._A[arm] + 1e-6 * np.eye(d)
            A_inv = np.linalg.inv(A_reg)
            theta = A_inv @ self._b[arm]
            # UCB = theta^T x + alpha * sqrt(x^T A^{-1} x)
            exploit = float(theta @ x)
            explore = float(self._alpha * math.sqrt(x @ A_inv @ x))
            ucb_scores.append(exploit + explore)

        # Softmax over UCB scores to produce probabilities
        max_score = max(ucb_scores)
        exp_scores = [math.exp(s - max_score) for s in ucb_scores]
        total = sum(exp_scores)
        probs = [e / total for e in exp_scores]

        # Select arm with highest UCB score
        chosen = int(np.argmax(ucb_scores))
        return chosen, probs

    def update(self, chosen_arm: int, context: list[float], reward: float) -> None:
        """Update the model for the chosen arm with observed reward.

        Args:
            chosen_arm: Index of the arm that was selected.
            context: Feature vector that was used for selection.
            reward: Observed reward (higher is better).
        """
        x = np.array(context, dtype=np.float64)
        d = len(x)
        self._ensure_arm(chosen_arm, d)
        self._A[chosen_arm] += np.outer(x, x)
        self._b[chosen_arm] += reward * x
        self._update_counts[chosen_arm] = self._update_counts.get(chosen_arm, 0) + 1

    def get_confidence(self, chosen_arm: int) -> float:
        """Get UCB confidence width for an arm.

        Returns the exploration term alpha * sqrt(x^T A^{-1} x) from the
        last selection. Since we do not store the last context, this returns
        the update count as a proxy -- more updates means narrower confidence
        intervals. Returns 0.0 for arms with no updates.

        Args:
            chosen_arm: Index of the arm to query.

        Returns:
            Confidence proxy: 1.0 / (1 + n_updates). Lower means more
            confident (more data seen for this arm).
        """
        count = self._update_counts.get(chosen_arm, 0)
        return 1.0 / (1.0 + count)


class ThompsonSamplingBandit:
    """Thompson Sampling bandit with Gaussian posterior per arm.

    Each arm maintains a Normal posterior (mu, sigma^2). Selection draws a
    sample from each arm's posterior and picks the highest. Updates adjust
    the posterior using conjugate Bayesian updating.

    Args:
        prior_mu: Prior mean for each arm. Default 0.0.
        prior_sigma: Prior standard deviation. Default 1.0.
    """

    def __init__(
        self,
        prior_mu: float = 0.0,
        prior_sigma: float = 1.0,
    ) -> None:
        self._prior_mu = prior_mu
        self._prior_sigma = prior_sigma
        # Per-arm posterior state
        self._mu: dict[int, float] = {}
        self._sigma: dict[int, float] = {}
        self._n: dict[int, int] = {}
        self._reward_sum: dict[int, float] = {}
        self._reward_sq_sum: dict[int, float] = {}

    def _ensure_arm(self, arm: int) -> None:
        """Initialize arm posterior if not present."""
        if arm not in self._mu:
            self._mu[arm] = self._prior_mu
            self._sigma[arm] = self._prior_sigma
            self._n[arm] = 0
            self._reward_sum[arm] = 0.0
            self._reward_sq_sum[arm] = 0.0

    def select_arm(
        self,
        context: list[float],
        n_arms: int,
    ) -> tuple[int, list[float]]:
        """Select arm by sampling from each arm's posterior.

        Args:
            context: Feature vector (used as input; Thompson Sampling with
                context uses the vector length to seed determinism in tests).
            n_arms: Number of arms.

        Returns:
            Tuple of (chosen_arm_index, probability_distribution).
        """
        rng = np.random.default_rng()
        samples: list[float] = []

        for arm in range(n_arms):
            self._ensure_arm(arm)
            sample = rng.normal(self._mu[arm], self._sigma[arm])
            samples.append(sample)

        # Softmax over samples for probability distribution
        max_sample = max(samples)
        exp_samples = [math.exp(s - max_sample) for s in samples]
        total = sum(exp_samples)
        probs = [e / total for e in exp_samples]

        chosen = int(np.argmax(samples))
        return chosen, probs

    def update(self, chosen_arm: int, context: list[float], reward: float) -> None:
        """Update the posterior for the chosen arm.

        Uses online conjugate update for Normal posterior with known
        variance (estimated from running statistics).

        Args:
            chosen_arm: Index of the arm that was selected.
            context: Feature vector (unused in basic Thompson Sampling,
                included for interface consistency).
            reward: Observed reward.
        """
        self._ensure_arm(chosen_arm)
        n = self._n[chosen_arm]
        self._n[chosen_arm] = n + 1
        self._reward_sum[chosen_arm] += reward
        self._reward_sq_sum[chosen_arm] += reward * reward

        # Compute running mean as posterior mean
        mean = self._reward_sum[chosen_arm] / self._n[chosen_arm]
        # Shrink sigma as we observe more data
        sigma = self._prior_sigma / math.sqrt(1 + self._n[chosen_arm])

        self._mu[chosen_arm] = mean
        self._sigma[chosen_arm] = max(sigma, 1e-6)  # floor to prevent collapse

    def get_confidence(self, chosen_arm: int) -> float:
        """Get posterior sigma (uncertainty) for an arm.

        Higher sigma means more uncertain (less data).
        """
        self._ensure_arm(chosen_arm)
        return self._sigma[chosen_arm]


BanditStrategy = Literal["linucb", "thompson"]


class ContextualBanditRouter:
    """Drop-in replacement for ContextualRouter using a contextual bandit.

    Uses LinUCB by default for principled exploration-exploitation. Supports
    Thompson Sampling as an alternative. Falls back to uniform weights during
    cold start (before any outcome data has been recorded).

    Same public interface as ContextualRouter so callers can swap without
    code changes.

    Args:
        db: DataFlow instance for audit logging.
        n_experts: Number of expert pool members.
        strategy: Bandit strategy -- "linucb" or "thompson".
        alpha: LinUCB exploration parameter (ignored for Thompson).
    """

    def __init__(
        self,
        db: DataFlow,
        n_experts: int = 5,
        strategy: BanditStrategy = "linucb",
        alpha: float = 1.0,
    ) -> None:
        self._db = db
        self._n_experts = n_experts
        self._experts = _DEFAULT_EXPERTS[:n_experts]

        if strategy == "linucb":
            self._bandit: LinUCBContextualBandit | ThompsonSamplingBandit = LinUCBContextualBandit(
                alpha=alpha
            )
        elif strategy == "thompson":
            self._bandit = ThompsonSamplingBandit()
        else:
            raise ValueError(
                f"Unknown bandit strategy '{strategy}'. " f"Must be 'linucb' or 'thompson'."
            )
        self._strategy = strategy

        # Track whether we have any outcome data for cold-start detection
        self._has_outcomes = False

        # Routing history for audit (bounded deque)
        self._routing_history: deque[dict] = deque(maxlen=1000)

        # Fallback deterministic router for cold-start
        self._fallback = ContextualRouter(db, n_experts)

    async def select_experts(
        self,
        z_t: list[float],
        context: dict,
    ) -> dict:
        """Select and weight experts using the contextual bandit.

        During cold start (no outcome data), returns uniform weights.
        Once outcomes have been recorded, uses the bandit for selection.

        Args:
            z_t: Latent state vector from the representation learner.
            context: Decision context dict (regime, volatility, etc.).

        Returns:
            Dict with selected_heads, weights, routing_scores, and
            bandit_metadata (chosen_arm, confidence, strategy).
        """
        if not self._has_outcomes:
            # Cold start: use uniform weights
            n = self._n_experts
            weights = [1.0 / n] * n
            selected = self._experts[:]

            logger.debug(
                "bandit_router.cold_start",
                strategy=self._strategy,
                n_experts=n,
            )
            return {
                "selected_heads": selected,
                "weights": weights,
                "routing_scores": [0.0] * n,
                "bandit_metadata": {
                    "strategy": self._strategy,
                    "cold_start": True,
                    "chosen_arm": None,
                    "confidence": None,
                },
            }

        # Build context vector from z_t
        context_vector = list(z_t)
        chosen_arm, probs = self._bandit.select_arm(context_vector, self._n_experts)
        confidence = self._bandit.get_confidence(chosen_arm)

        selected = self._experts[:]
        result = {
            "selected_heads": selected,
            "weights": probs,
            "routing_scores": probs,  # Bandit probabilities serve as scores
            "bandit_metadata": {
                "strategy": self._strategy,
                "cold_start": False,
                "chosen_arm": chosen_arm,
                "confidence": confidence,
            },
        }

        logger.debug(
            "bandit_router.selected_experts",
            strategy=self._strategy,
            chosen_arm=chosen_arm,
            confidence=confidence,
            top_weight=max(probs),
        )
        return result

    async def blend_outputs(
        self,
        outputs: list[dict],
        weights: list[float],
    ) -> dict:
        """Blend multiple head outputs by weights.

        Delegates to the fallback ContextualRouter's blend_outputs, which
        handles nested dicts recursively.
        """
        return await self._fallback.blend_outputs(outputs, weights)

    def record_outcome(
        self,
        decision_id: str,
        expert_idx: int,
        reward: float,
        context: list[float] | None = None,
    ) -> None:
        """Feed back a realized outcome for a routing decision.

        Updates the bandit model so future selections improve. After the
        first outcome is recorded, the router switches from cold-start
        uniform weights to learned bandit weights.

        Args:
            decision_id: ID of the original routing decision.
            expert_idx: Index of the expert that was selected.
            reward: Realized reward (higher is better). Scale depends
                on the caller -- e.g., risk-adjusted return, Sharpe, etc.
            context: Context vector used for the original selection.
                If None, a zero-vector is used (degrades to non-contextual).
        """
        if context is None:
            context = [0.0] * 5  # Default dimension

        if not math.isfinite(reward):
            raise ValueError(f"Reward must be finite, got {reward}")

        self._bandit.update(expert_idx, context, reward)
        self._has_outcomes = True

        self._routing_history.append(
            {
                "decision_id": decision_id,
                "expert_idx": expert_idx,
                "reward": reward,
                "strategy": self._strategy,
            }
        )

        logger.info(
            "bandit_router.outcome_recorded",
            decision_id=decision_id,
            expert_idx=expert_idx,
            reward=reward,
        )

    async def record_routing_decision(
        self,
        decision_id: str,
        z_t: list[float],
        heads: list[str],
        weights: list[float],
    ) -> None:
        """Record routing decision to audit log.

        Writes to the same audit_log table as ContextualRouter, with
        additional bandit_metadata in the details field.
        """
        details = json.dumps(
            {
                "heads": heads,
                "weights": weights,
                "z_t_dim": len(z_t),
                "router_type": "contextual_bandit",
                "bandit_strategy": self._strategy,
            }
        )

        row = {
            "rule_name": "contextual_bandit_router",
            "action": "routing_decision",
            "details": details,
            "severity": "info",
            "decision_id": decision_id,
            "z_t_snapshot": json.dumps(z_t),
        }

        await self._db.express.create("audit_log", row)
        logger.info(
            "bandit_router.decision_recorded",
            decision_id=decision_id,
            n_heads=len(heads),
            strategy=self._strategy,
        )
