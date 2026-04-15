"""Tail-risk prediction heads.

Champion: Normalizing-flow-based tail posterior.
Challenger: Quantile DL variant.
"""

import torch
import torch.nn as nn


class NormalizingFlowTailChampion(nn.Module):
    """Normalizing-flow-based tail posterior for extreme event estimation."""

    def __init__(self, z_dim: int = 16, hidden_dim: int = 64, n_flows: int = 4):
        super().__init__()
        self.n_flows = n_flows
        self.base_mean = nn.Linear(z_dim, 1)
        self.base_logvar = nn.Linear(z_dim, 1)
        layers = []
        for _ in range(n_flows):
            layers.append(nn.Linear(1, hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Linear(hidden_dim, 1))
        self.flow_layers = nn.ModuleList(
            [nn.Sequential(*layers[i * 3 : (i + 1) * 3]) for i in range(n_flows)]
        )

    def forward(self, z_t: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns (tail_mean, tail_log_variance)."""
        mean = self.base_mean(z_t)
        logvar = self.base_logvar(z_t)

        # Simple planar flow transform
        h = mean
        for flow in self.flow_layers:
            h = h + flow(h) * 0.1

        return h.squeeze(-1), logvar.squeeze(-1)


class QuantileDLChallenger(nn.Module):
    """Quantile regression DL challenger for tail risk."""

    def __init__(self, z_dim: int = 16, hidden_dim: int = 64, quantiles=None):
        super().__init__()
        if quantiles is None:
            quantiles = [0.01, 0.05, 0.10]
        self.quantiles = list(quantiles)
        self.trunk = nn.Sequential(
            nn.Linear(z_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
        )
        self.quantile_heads = nn.ModuleList([nn.Linear(hidden_dim, 1) for _ in self.quantiles])

    def forward(self, z_t: torch.Tensor) -> dict[float, torch.Tensor]:
        """Returns dict mapping quantile -> value tensor."""
        h = self.trunk(z_t)
        results = {}
        for q, head in zip(self.quantiles, self.quantile_heads):
            results[q] = head(h).squeeze(-1)
        return results
