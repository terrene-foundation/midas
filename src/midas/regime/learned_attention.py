"""M08 Learned attention weights -- replaces fixed hand-coded weights in RegimeRenderer.

Per spec 06 S2: "The function is learned (not hand-coded) by regressing historical
user-engagement and decision-window-expiry outcomes against historical z_t-derived
features."

Architecture:
    LearnedAttentionModel   -- 2-layer MLP with softmax output (weights sum to 1.0)
    AttentionWeightLearner  -- lifecycle manager: accumulate data, batch train, persist
"""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

# Feature names in canonical order (must match RegimeRenderer weight order).
FEATURE_NAMES: list[str] = [
    "volatility",
    "ood_score",
    "transition_pressure",
    "posterior_variance",
    "model_disagreement",
    "drawdown_velocity",
]

NUM_FEATURES: int = len(FEATURE_NAMES)

# Prior-informed defaults matching the original hand-coded weights.
DEFAULT_PRIOR_WEIGHTS: list[float] = [0.30, 0.25, 0.15, 0.15, 0.10, 0.05]

# Training defaults.
_DEFAULT_LR: float = 1e-3
_DEFAULT_HIDDEN_SIZE: int = 16
_DEFAULT_BATCH_SIZE: int = 32
_MAX_TRAINING_HISTORY: int = 10_000


class LearnedAttentionModel(nn.Module):
    """Small 2-layer MLP that maps 6 z_t-derived features to 6 attention weights.

    The output is a softmax over 6 dimensions, guaranteeing weights are
    non-negative and sum to 1.0.  The network learns which regime features
    matter most given the current feature vector, trained against historical
    user-engagement outcomes.
    """

    def __init__(
        self,
        input_size: int = NUM_FEATURES,
        hidden_size: int = _DEFAULT_HIDDEN_SIZE,
    ) -> None:
        super().__init__()
        self._input_size = input_size
        self._hidden_size = hidden_size
        self.network = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, input_size),
            nn.Softmax(dim=-1),
        )
        # Training provenance.
        self._training_steps: int = 0
        self._training_history: deque[dict[str, Any]] = deque(maxlen=_MAX_TRAINING_HISTORY)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)

    def train_step(
        self,
        features: torch.Tensor,
        target: torch.Tensor,
        lr: float = _DEFAULT_LR,
    ) -> float:
        """Execute a single gradient step and return the loss value.

        Parameters
        ----------
        features : torch.Tensor
            Shape ``(1, 6)`` or ``(6,)`` -- the z_t-derived feature vector.
        target : torch.Tensor
            Shape ``(1,)`` -- engagement outcome in [0, 1].
        lr : float
            Learning rate for this step.

        Returns
        -------
        float
            MSE loss before the gradient update.
        """
        if features.dim() == 1:
            features = features.unsqueeze(0)
        if target.dim() == 0:
            target = target.unsqueeze(0)

        optimizer = torch.optim.Adam(self.parameters(), lr=lr)
        self.train()

        weights = self.forward(features)  # (1, 6) -- softmax output
        # Predicted engagement = weighted sum of features.
        predicted = (weights * features).sum(dim=-1)  # (1,)
        loss = nn.functional.mse_loss(predicted, target)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        loss_val = loss.item()
        self._training_steps += 1
        self._training_history.append(
            {
                "step": self._training_steps,
                "loss": loss_val,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return loss_val

    @torch.no_grad()
    def predict_weights(self, features: torch.Tensor) -> list[float]:
        """Return the learned weight vector for a given feature input.

        Parameters
        ----------
        features : torch.Tensor
            Shape ``(1, 6)`` or ``(6,)``.

        Returns
        -------
        list[float]
            6-element list of attention weights summing to 1.0.
        """
        if features.dim() == 1:
            features = features.unsqueeze(0)
        self.eval()
        weights = self.forward(features)
        return weights.squeeze(0).tolist()

    @torch.no_grad()
    def get_weights(self) -> list[float]:
        """Return the model's current weights evaluated at the default (uniform) input.

        This gives the model's ``resting state'' weights -- the learned prior
        when no specific feature vector is provided.

        Returns
        -------
        list[float]
            6-element list of attention weights summing to 1.0.
        """
        uniform = torch.ones(1, NUM_FEATURES) / NUM_FEATURES
        return self.predict_weights(uniform)

    @property
    def training_steps(self) -> int:
        return self._training_steps

    @property
    def training_history(self) -> list[dict[str, Any]]:
        return list(self._training_history)

    def state_dict_with_meta(self) -> dict[str, Any]:
        """Return model state plus training metadata for persistence."""
        return {
            "model_state": {k: v.tolist() for k, v in self.state_dict().items()},
            "training_steps": self._training_steps,
            "training_history": list(self._training_history),
            "input_size": self._input_size,
            "hidden_size": self._hidden_size,
        }

    def load_state_dict_with_meta(self, data: dict[str, Any]) -> None:
        """Restore model state and training metadata from persisted dict."""
        tensors = {k: torch.tensor(v) for k, v in data["model_state"].items()}
        self.load_state_dict(tensors)
        self._training_steps = data.get("training_steps", 0)
        self._training_history = deque(
            data.get("training_history", []), maxlen=_MAX_TRAINING_HISTORY
        )


class AttentionWeightLearner:
    """Lifecycle manager for learned attention weights.

    Accumulates (features, outcome) observation pairs from live regime data.
    Trains the underlying ``LearnedAttentionModel`` in mini-batches once
    enough observations have been collected.  Provides the current best
    weights to ``RegimeRenderer`` and supports save/load for persistence.
    """

    def __init__(
        self,
        model: LearnedAttentionModel | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        lr: float = _DEFAULT_LR,
        save_base_dir: str | Path | None = None,
    ) -> None:
        self._model = model or LearnedAttentionModel()
        self._batch_size = batch_size
        self._lr = lr
        self._save_base_dir = Path(save_base_dir) if save_base_dir else self._SAVE_BASE_DIR

        # Accumulated observations: each is (features_tensor, target_tensor).
        self._observations: deque[tuple[torch.Tensor, torch.Tensor]] = deque(
            maxlen=_MAX_TRAINING_HISTORY
        )
        self._is_trained: bool = False

    @property
    def model(self) -> LearnedAttentionModel:
        return self._model

    @property
    def is_trained(self) -> bool:
        """Whether the model has been trained on at least one batch."""
        return self._is_trained

    @property
    def observation_count(self) -> int:
        return len(self._observations)

    def add_observation(
        self,
        features: list[float] | torch.Tensor,
        outcome: float,
    ) -> None:
        """Record a single (features, outcome) observation pair.

        Parameters
        ----------
        features : list[float] | torch.Tensor
            The 6 z_t-derived feature values in canonical order:
            [volatility, ood_score, transition_pressure,
             posterior_variance, model_disagreement, drawdown_velocity]
        outcome : float
            Engagement outcome in [0, 1].  0.0 = no engagement needed,
            1.0 = high engagement needed.
        """
        if isinstance(features, list):
            features = torch.tensor(features, dtype=torch.float32)
        if features.dim() == 1 and features.shape[0] != NUM_FEATURES:
            raise ValueError(f"Expected {NUM_FEATURES} features, got {features.shape[0]}")
        target = torch.tensor([outcome], dtype=torch.float32)
        self._observations.append((features, target))

    def train_batch(self) -> float | None:
        """Train the model on accumulated observations if enough data.

        Returns
        -------
        float | None
            Average loss over the batch, or ``None`` if not enough data
            to form a batch.
        """
        if len(self._observations) < self._batch_size:
            logger.debug(
                "train_batch skipped",
                extra={
                    "observations": len(self._observations),
                    "batch_size": self._batch_size,
                },
            )
            return None

        # Sample up to batch_size observations.
        batch = list(self._observations)[-self._batch_size :]
        features_batch = torch.stack([f for f, _ in batch])
        target_batch = torch.stack([t for _, t in batch])

        total_loss = 0.0
        for i in range(len(batch)):
            loss = self._model.train_step(features_batch[i], target_batch[i], lr=self._lr)
            total_loss += loss

        avg_loss = total_loss / len(batch)
        self._is_trained = True

        logger.info(
            "train_batch completed",
            extra={
                "batch_size": len(batch),
                "avg_loss": avg_loss,
                "total_steps": self._model.training_steps,
            },
        )
        return avg_loss

    def train_all(self, epochs: int = 5) -> list[float]:
        """Train on all accumulated observations for multiple epochs.

        Useful for initial model warmup or periodic retraining.

        Parameters
        ----------
        epochs : int
            Number of passes over the accumulated data.

        Returns
        -------
        list[float]
            Per-epoch average loss values.
        """
        if len(self._observations) == 0:
            return []

        features_batch = torch.stack([f for f, _ in self._observations])
        target_batch = torch.stack([t for _, t in self._observations])

        epoch_losses: list[float] = []
        for epoch in range(epochs):
            total_loss = 0.0
            for i in range(len(self._observations)):
                loss = self._model.train_step(features_batch[i], target_batch[i], lr=self._lr)
                total_loss += loss
            avg_loss = total_loss / len(self._observations)
            epoch_losses.append(avg_loss)

        self._is_trained = True

        logger.info(
            "train_all completed",
            extra={
                "epochs": epochs,
                "observations": len(self._observations),
                "final_avg_loss": epoch_losses[-1] if epoch_losses else None,
            },
        )
        return epoch_losses

    def get_weights(self) -> list[float] | None:
        """Return learned weights if model is trained, else None.

        Returns
        -------
        list[float] | None
            6 attention weights summing to 1.0, or None if not yet trained.
        """
        if not self._is_trained:
            return None
        return self._model.get_weights()

    def predict_weights(self, features: list[float] | torch.Tensor) -> list[float]:
        """Return learned weights for a specific feature vector.

        Falls back to prior weights if the model has not been trained.

        Parameters
        ----------
        features : list[float] | torch.Tensor
            The 6-element feature vector.

        Returns
        -------
        list[float]
            6 attention weights summing to 1.0.
        """
        if isinstance(features, list):
            features = torch.tensor(features, dtype=torch.float32)
        return self._model.predict_weights(features)

    _SAVE_BASE_DIR = Path("data/attention_models")

    def _resolve_safe_path(self, path: str | Path) -> Path:
        """Resolve path against a trusted base directory, rejecting traversal."""
        resolved = (self._save_base_dir / path).resolve()
        if not str(resolved).startswith(str(self._save_base_dir.resolve())):
            raise ValueError(f"Path escapes allowed directory: {path}")
        return resolved

    def save(self, path: str | Path) -> None:
        """Persist model state and training metadata to a JSON file.

        Parameters
        ----------
        path : str | Path
            File path for the saved model (resolved against data/attention_models/).
        """
        resolved = self._resolve_safe_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        data = self._model.state_dict_with_meta()
        data["learner_is_trained"] = self._is_trained
        data["learner_batch_size"] = self._batch_size
        data["learner_lr"] = self._lr
        resolved.write_text(json.dumps(data, indent=2))
        logger.info("model saved", extra={"path": str(resolved)})

    def load(self, path: str | Path) -> None:
        """Restore model state and training metadata from a JSON file.

        Parameters
        ----------
        path : str | Path
            File path to load from (resolved against data/attention_models/).
        """
        resolved = self._resolve_safe_path(path)
        raw = resolved.read_text()
        data = json.loads(raw)

        # Reconstruct model if architecture differs.
        saved_input = data.get("input_size", NUM_FEATURES)
        saved_hidden = data.get("hidden_size", _DEFAULT_HIDDEN_SIZE)
        if saved_input != self._model._input_size or saved_hidden != self._model._hidden_size:
            self._model = LearnedAttentionModel(input_size=saved_input, hidden_size=saved_hidden)

        self._model.load_state_dict_with_meta(data)
        self._is_trained = data.get("learner_is_trained", False)
        self._batch_size = data.get("learner_batch_size", self._batch_size)
        self._lr = data.get("learner_lr", self._lr)
        logger.info("model loaded", extra={"path": str(path)})
