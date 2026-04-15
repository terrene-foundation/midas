"""Execution heads — cost-aware order sizing and timing.

Champion: Cost-aware RL.
Challenger: Linear impact model (Almgren-Chriss).
"""

from typing import Optional

import numpy as np
import torch
import torch.nn as nn


class CostAwareRLChampion(nn.Module):
    """Order-sizing + timing bandit for execution."""

    def __init__(self, z_dim: int = 16, hidden_dim: int = 64):
        super().__init__()
        self.size_net = nn.Sequential(
            nn.LazyLinear(hidden_dim),
            nn.ReLU(),
            nn.LazyLinear(1),
            nn.Sigmoid(),  # size fraction [0, 1]
        )
        self.timing_net = nn.Sequential(
            nn.LazyLinear(hidden_dim),
            nn.ReLU(),
            nn.LazyLinear(1),
            nn.Sigmoid(),  # timing score [0, 1]
        )

    def forward(
        self,
        z_t: torch.Tensor,
        order_params: torch.Tensor,
        venue_features: Optional[torch.Tensor] = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns (size_fraction, timing_score)."""
        parts = [z_t, order_params]
        if venue_features is not None:
            parts.append(venue_features)
        x = torch.cat(parts, dim=-1)
        size_frac = self.size_net(x).squeeze(-1)
        timing = self.timing_net(x).squeeze(-1)
        return size_frac, timing


class LinearImpactBaseline:
    """Classical Almgren-Chriss impact model."""

    def estimate_impact(
        self,
        order_size: float,
        avg_volume: float,
        volatility: float,
    ) -> float:
        """Estimate market impact cost.

        Uses simplified Almgren-Chriss:
        impact = sigma * sqrt(|X| / V) * eta
        where X = order size, V = avg volume, sigma = volatility
        """
        if avg_volume <= 0:
            return float("inf")
        eta = 0.1  # temporary impact coefficient
        permanent = 0.05  # permanent impact coefficient
        temp_impact = eta * volatility * np.sqrt(abs(order_size) / avg_volume)
        perm_impact = permanent * volatility * abs(order_size) / avg_volume
        return temp_impact + perm_impact
