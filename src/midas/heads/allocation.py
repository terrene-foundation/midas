"""Allocation policy heads.

DRL champions and classical baselines for portfolio allocation.
"""

import numpy as np
import torch
import torch.nn as nn
from typing import Optional


class CVaRPPOChampion(nn.Module):
    """CVaR-aware PPO policy net for portfolio allocation."""

    def __init__(self, z_dim: int = 16, n_assets: int = 50, hidden_dim: int = 64):
        super().__init__()
        input_dim = z_dim + n_assets + 1  # z_t + current_positions + envelope (scalar)
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_assets),
        )

    def forward(
        self,
        z_t: torch.Tensor,
        current_positions: torch.Tensor,
        envelope: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Returns target weights (softmax over n_assets)."""
        if envelope is None:
            envelope = torch.zeros(z_t.size(0), 1, device=z_t.device)
        x = torch.cat([z_t, current_positions, envelope], dim=-1)
        logits = self.net(x)
        return torch.softmax(logits, dim=-1)


class MVOBaseline:
    """Classical Mean-Variance Optimization."""

    def optimize(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        risk_aversion: float = 1.0,
    ) -> np.ndarray:
        """Compute MVO optimal weights.

        Uses analytical solution: w = (1/gamma) * Sigma^{-1} * mu
        """
        try:
            inv_cov = np.linalg.inv(cov_matrix)
        except np.linalg.LinAlgError:
            inv_cov = np.linalg.pinv(cov_matrix)
        raw_weights = inv_cov @ expected_returns / risk_aversion
        # Normalize to sum to 1
        weights = raw_weights / raw_weights.sum()
        return weights


class BlackLittermanBaseline:
    """Black-Litterman model."""

    def optimize(
        self,
        prior_returns: np.ndarray,
        cov_matrix: np.ndarray,
        views: np.ndarray,
        view_confidences: np.ndarray,
        tau: float = 0.05,
    ) -> np.ndarray:
        """Compute BL posterior returns and optimal weights."""
        N = len(prior_returns)
        if views.ndim == 1:
            P = np.eye(N)
            Q = views
        else:
            P = views
            Q = np.ones(P.shape[0])
        view_confidences = np.atleast_1d(view_confidences)
        omega = np.diag(1.0 / view_confidences)

        try:
            bl_returns = np.linalg.inv(
                np.linalg.inv(tau * cov_matrix) + P.T @ np.linalg.inv(omega) @ P
            ) @ (np.linalg.inv(tau * cov_matrix) @ prior_returns + P.T @ np.linalg.inv(omega) @ Q)
        except np.linalg.LinAlgError:
            bl_returns = prior_returns

        try:
            inv_cov = np.linalg.inv(cov_matrix)
        except np.linalg.LinAlgError:
            inv_cov = np.linalg.pinv(cov_matrix)

        raw = inv_cov @ bl_returns
        weights = raw / raw.sum()
        return weights


class HRPBaseline:
    """Hierarchical Risk Parity."""

    def optimize(self, cov_matrix: np.ndarray) -> np.ndarray:
        """Compute HRP weights via inverse-volatility weighting."""
        vols = np.sqrt(np.diag(cov_matrix))
        vols = np.where(vols > 0, vols, 1.0)
        inv_vols = 1.0 / vols
        weights = inv_vols / inv_vols.sum()
        return weights


class RiskParityBaseline:
    """Risk Parity allocation."""

    def optimize(self, cov_matrix: np.ndarray) -> np.ndarray:
        """Equal risk contribution weights."""
        vols = np.sqrt(np.diag(cov_matrix))
        vols = np.where(vols > 0, vols, 1.0)
        inv_vols = 1.0 / vols
        weights = inv_vols / inv_vols.sum()
        return weights


class SACChallenger(nn.Module):
    """Soft Actor-Critic challenger for portfolio allocation."""

    def __init__(self, z_dim: int = 16, n_assets: int = 50, hidden_dim: int = 64):
        super().__init__()
        self.policy_net = nn.Sequential(
            nn.Linear(z_dim + n_assets, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_assets),
        )

    def forward(self, z_t: torch.Tensor, current_positions: torch.Tensor) -> torch.Tensor:
        """Returns target weights (softmax over n_assets)."""
        x = torch.cat([z_t, current_positions], dim=-1)
        logits = self.policy_net(x)
        return torch.softmax(logits, dim=-1)


class TD3Challenger(nn.Module):
    """Twin Delayed DDPG challenger for portfolio allocation."""

    def __init__(self, z_dim: int = 16, n_assets: int = 50, hidden_dim: int = 64):
        super().__init__()
        self.actor = nn.Sequential(
            nn.Linear(z_dim + n_assets, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_assets),
        )

    def forward(self, z_t: torch.Tensor, current_positions: torch.Tensor) -> torch.Tensor:
        """Returns target weights (softmax over n_assets)."""
        x = torch.cat([z_t, current_positions], dim=-1)
        logits = self.actor(x)
        return torch.softmax(logits, dim=-1)


class RiskAwareRLChallenger(nn.Module):
    """Risk-aware RL challenger with downside penalty for allocation."""

    def __init__(self, z_dim: int = 16, n_assets: int = 50, hidden_dim: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(z_dim + n_assets, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_assets),
        )

    def forward(self, z_t: torch.Tensor, current_positions: torch.Tensor) -> torch.Tensor:
        """Returns target weights (softmax over n_assets)."""
        x = torch.cat([z_t, current_positions], dim=-1)
        logits = self.net(x)
        return torch.softmax(logits, dim=-1)


class DecisionTransformerChallenger(nn.Module):
    """Decision Transformer challenger for regime-transfer allocation."""

    def __init__(self, z_dim: int = 16, n_assets: int = 50, hidden_dim: int = 64):
        super().__init__()
        self.input_proj = nn.Linear(z_dim + n_assets, hidden_dim)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=4,
            dim_feedforward=hidden_dim * 2,
            batch_first=True,
            dropout=0.1,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
        self.output_head = nn.Linear(hidden_dim, n_assets)

    def forward(self, z_t: torch.Tensor, current_positions: torch.Tensor) -> torch.Tensor:
        """Returns target weights (softmax over n_assets)."""
        x = torch.cat([z_t, current_positions], dim=-1)
        h = self.input_proj(x).unsqueeze(1)  # (batch, 1, hidden)
        h = self.transformer(h).squeeze(1)  # (batch, hidden)
        logits = self.output_head(h)
        return torch.softmax(logits, dim=-1)
