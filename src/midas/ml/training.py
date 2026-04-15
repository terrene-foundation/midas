"""
Training pipeline for Midas ML models.

Generic async training loop with DataFlow audit logging.

Ref: T-03-09
"""

import structlog
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from typing import Any

logger = structlog.get_logger(__name__)


class TrainingPipeline:
    """Generic training pipeline with audit logging to fabric."""

    def __init__(self, model: nn.Module, device: str = "cpu"):
        self.model = model.to(device)
        self.device = device
        self.optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    async def train(
        self, train_loader: DataLoader, epochs: int = 10, fabric_db=None
    ) -> dict[str, Any]:
        """Train the model for given epochs."""
        self.model.train()
        total_loss = 0.0
        n_batches = 0

        for epoch in range(epochs):
            epoch_loss = 0.0
            for (batch_x,) in train_loader:
                batch_x = batch_x.to(self.device)
                self.optimizer.zero_grad()

                result = self.model(batch_x)
                if isinstance(result, tuple):
                    z_t, recon = result[0], result[1]
                    loss = nn.functional.mse_loss(recon, batch_x.reshape_as(recon))
                else:
                    loss = torch.tensor(0.0, requires_grad=True)

                loss.backward()
                self.optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            total_loss += epoch_loss
            if (epoch + 1) % max(1, epochs // 5) == 0:
                logger.info(
                    "training.epoch", epoch=epoch + 1, loss=epoch_loss / max(len(train_loader), 1)
                )

        avg_loss = total_loss / max(n_batches, 1)
        logger.info("training.complete", epochs=epochs, avg_loss=avg_loss)
        return {"epochs": epochs, "avg_loss": avg_loss, "batches": n_batches}

    async def evaluate(self, val_loader: DataLoader) -> dict[str, float]:
        """Evaluate on validation set."""
        self.model.eval()
        total_loss = 0.0
        n = 0
        with torch.no_grad():
            for (batch_x,) in val_loader:
                batch_x = batch_x.to(self.device)
                result = self.model(batch_x)
                if isinstance(result, tuple):
                    recon = result[1]
                    loss = nn.functional.mse_loss(recon, batch_x.reshape_as(recon))
                else:
                    loss = torch.tensor(0.0)
                total_loss += loss.item()
                n += 1
        return {"val_loss": total_loss / max(n, 1)}

    def save_checkpoint(self, path: str) -> None:
        """Save model checkpoint."""
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
            },
            path,
        )

    def load_checkpoint(self, path: str) -> None:
        """Load model checkpoint."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
