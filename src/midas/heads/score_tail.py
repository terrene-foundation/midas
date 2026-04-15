"""Score-based challenger for tail risk estimation."""

import torch
import torch.nn as nn


class ScoreBasedChallenger(nn.Module):
    """Score-based model for implicit tail risk estimation."""

    def __init__(self, z_dim: int = 16, hidden_dim: int = 64):
        super().__init__()
        self.score_net = nn.Sequential(
            nn.Linear(z_dim + 1, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, z_t: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns (tail_mean, tail_log_variance)."""
        noise = torch.randn(z_t.size(0), 1, device=z_t.device) * 0.1
        x = torch.cat([z_t, noise], dim=-1)
        score = self.score_net(x)
        return score.squeeze(-1), torch.zeros_like(score).squeeze(-1)
