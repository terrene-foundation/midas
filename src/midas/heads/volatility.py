"""Volatility prediction heads.

Champion: DL-hybrid vol posterior conditioned on z_t.
Challenger: Deep-GARCH variant.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class VolHeadChampion(nn.Module):
    """DL-hybrid vol posterior conditioned on z_t.

    Produces continuous volatility posterior (mean + log_variance).
    """

    def __init__(self, z_dim: int = 16, hidden_dim: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(z_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
        )
        self.mean_head = nn.Linear(hidden_dim, 1)
        self.logvar_head = nn.Linear(hidden_dim, 1)

    def forward(self, z_t: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns (vol_mean, vol_log_variance)."""
        h = self.net(z_t)
        mean = F.softplus(self.mean_head(h)).squeeze(-1)  # ensure positive, (batch,)
        logvar = self.logvar_head(h).squeeze(-1)
        return mean, logvar


class DeepGARCHChallenger(nn.Module):
    """GARCH-family hybrid challenger for volatility."""

    def __init__(self, z_dim: int = 16, hidden_dim: int = 64):
        super().__init__()
        self.alpha_net = nn.Sequential(
            nn.Linear(z_dim + 1, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Softplus(),
        )
        self.beta_net = nn.Sequential(
            nn.Linear(z_dim + 1, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Softplus(),
        )
        self.omega_net = nn.Sequential(
            nn.Linear(z_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Softplus(),
        )

    def forward(
        self, z_t: torch.Tensor, realized_vol: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns (vol_mean, vol_log_variance)."""
        omega = self.omega_net(z_t)
        if realized_vol.dim() == 1:
            realized_vol = realized_vol.unsqueeze(-1)
        x = torch.cat([z_t, realized_vol], dim=-1)
        alpha = self.alpha_net(x)
        beta = self.beta_net(x)
        vol = omega + alpha * realized_vol + beta * realized_vol
        logvar = torch.zeros_like(vol)
        return vol.squeeze(-1), logvar.squeeze(-1)
