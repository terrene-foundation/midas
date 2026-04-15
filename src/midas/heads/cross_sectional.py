"""Cross-sectional heads — ranking securities across the universe.

Champion: CNN over cross-sectional features.
Challengers: GNN and transformer variants.
"""

import torch
import torch.nn as nn


class CNNChampion(nn.Module):
    """CNN over cross-sectional universe for security ranking."""

    def __init__(self, n_assets: int = 50, feature_dim: int = 32, hidden_dim: int = 64):
        super().__init__()
        self.conv = nn.Conv1d(feature_dim, hidden_dim, kernel_size=3, padding=1)
        self.fc = nn.Linear(hidden_dim, 1)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        """features: (batch, n_assets, feature_dim) -> scores: (batch, n_assets)."""
        x = features.permute(0, 2, 1)  # (batch, feature_dim, n_assets)
        h = torch.relu(self.conv(x))  # (batch, hidden, n_assets)
        scores = self.fc(h.permute(0, 2, 1)).squeeze(-1)  # (batch, n_assets)
        return scores


class GNNChallenger(nn.Module):
    """Graph neural network challenger over asset-relationship graphs."""

    def __init__(self, n_assets: int = 50, feature_dim: int = 32, hidden_dim: int = 64):
        super().__init__()
        self.linear1 = nn.Linear(feature_dim, hidden_dim)
        self.linear2 = nn.Linear(hidden_dim, hidden_dim)
        self.score_head = nn.Linear(hidden_dim, 1)

    def forward(self, features: torch.Tensor, adj_matrix: torch.Tensor = None) -> torch.Tensor:
        """features: (batch, n_assets, feature_dim) -> scores: (batch, n_assets)."""
        h = torch.relu(self.linear1(features))
        if adj_matrix is not None:
            h = torch.bmm(adj_matrix, h)
        h = torch.relu(self.linear2(h))
        scores = self.score_head(h).squeeze(-1)
        return scores


class XSTransformerChallenger(nn.Module):
    """Cross-sectional transformer with ticker-level attention."""

    def __init__(
        self, n_assets: int = 50, feature_dim: int = 32, hidden_dim: int = 64, n_heads: int = 4
    ):
        super().__init__()
        self.input_proj = nn.Linear(feature_dim, hidden_dim)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=n_heads,
            dim_feedforward=hidden_dim * 2,
            batch_first=True,
            dropout=0.1,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
        self.score_head = nn.Linear(hidden_dim, 1)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        """features: (batch, n_assets, feature_dim) -> scores: (batch, n_assets)."""
        h = self.input_proj(features)
        h = self.transformer(h)
        scores = self.score_head(h).squeeze(-1)
        return scores
