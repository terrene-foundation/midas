"""Return time-series prediction heads — multi-horizon return forecasting.

Champion (ReturnTSHead) uses an MLP with per-horizon output heads producing
mean and log-variance estimates. Challengers provide alternative architectures
(TCN, Transformer, Mamba/S4) following the same output interface.

Ref: specs/04-latent-first-architecture.md
"""

import torch
import torch.nn as nn


class ReturnTSHead(nn.Module):
    """Champion: Multi-horizon return predictor conditioned on z_t.

    Architecture: z_dim -> shared trunk (MLP) -> per-horizon heads,
    each producing (mean, log_variance).
    """

    def __init__(self, z_dim=16, hidden_dim=64, horizons=None):
        if horizons is None:
            horizons = [21, 63, 126]
        super().__init__()
        self.horizons = list(horizons)
        self.trunk = nn.Sequential(
            nn.Linear(z_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
        )
        # Per-horizon heads: each produces mean + log_variance
        self.mean_heads = nn.ModuleDict({str(h): nn.Linear(hidden_dim, 1) for h in self.horizons})
        self.logvar_heads = nn.ModuleDict({str(h): nn.Linear(hidden_dim, 1) for h in self.horizons})

    def forward(self, z_t):
        """z_t: (batch, z_dim) -> dict mapping horizon -> (mean, log_variance)."""
        h = self.trunk(z_t)
        result = {}
        for horizon in self.horizons:
            key = str(horizon)
            mean = self.mean_heads[key](h).squeeze(-1)
            log_var = self.logvar_heads[key](h).squeeze(-1)
            result[horizon] = (mean, log_var)
        return result


class TCNChallenger(nn.Module):
    """TCN-family challenger for multi-horizon return prediction.

    Uses 1D causal convolutions over a constructed sequence from z_t,
    then per-horizon output heads.
    """

    def __init__(self, z_dim=16, hidden_dim=64, horizons=None, num_channels=None):
        if horizons is None:
            horizons = [21, 63, 126]
        if num_channels is None:
            num_channels = [64, 64, 64]
        super().__init__()
        self.horizons = list(horizons)
        # Project z_t into a sequence for TCN processing
        self.input_proj = nn.Linear(z_dim, num_channels[0])
        layers = []
        for i in range(len(num_channels) - 1):
            layers.append(nn.Conv1d(num_channels[i], num_channels[i + 1], kernel_size=3, padding=1))
            layers.append(nn.ReLU())
        self.tcn = nn.Sequential(*layers)
        self.pool_proj = nn.Linear(num_channels[-1], hidden_dim)
        self.mean_heads = nn.ModuleDict({str(h): nn.Linear(hidden_dim, 1) for h in self.horizons})
        self.logvar_heads = nn.ModuleDict({str(h): nn.Linear(hidden_dim, 1) for h in self.horizons})

    def forward(self, z_t):
        """z_t: (batch, z_dim) -> dict mapping horizon -> (mean, log_variance)."""
        # Expand z_t into a short sequence for TCN
        seq = self.input_proj(z_t).unsqueeze(-1)  # (batch, channels, 1)
        # Repeat to create a sequence length
        seq = seq.expand(-1, -1, 4)  # (batch, channels, 4)
        out = self.tcn(seq)  # (batch, channels, 4)
        pooled = out.mean(dim=-1)  # (batch, channels)
        h = torch.relu(self.pool_proj(pooled))
        result = {}
        for horizon in self.horizons:
            key = str(horizon)
            mean = self.mean_heads[key](h).squeeze(-1)
            log_var = self.logvar_heads[key](h).squeeze(-1)
            result[horizon] = (mean, log_var)
        return result


class TransformerChallenger(nn.Module):
    """iTransformer/PatchTST challenger for multi-horizon return prediction.

    Treats horizon predictions as tokens in a sequence and applies
    transformer self-attention.
    """

    def __init__(self, z_dim=16, hidden_dim=64, horizons=None, n_heads=4, n_layers=2):
        if horizons is None:
            horizons = [21, 63, 126]
        super().__init__()
        self.horizons = list(horizons)
        n_horizons = len(self.horizons)
        self.input_proj = nn.Linear(z_dim, hidden_dim)
        # Learnable horizon tokens
        self.horizon_queries = nn.Parameter(torch.randn(1, n_horizons, hidden_dim) * 0.02)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=n_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=0.1,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.mean_heads = nn.ModuleDict({str(h): nn.Linear(hidden_dim, 1) for h in self.horizons})
        self.logvar_heads = nn.ModuleDict({str(h): nn.Linear(hidden_dim, 1) for h in self.horizons})

    def forward(self, z_t):
        """z_t: (batch, z_dim) -> dict mapping horizon -> (mean, log_variance)."""
        batch_size = z_t.size(0)
        # Broadcast z_t context to each horizon query
        z_ctx = self.input_proj(z_t).unsqueeze(1)  # (batch, 1, hidden)
        queries = self.horizon_queries.expand(batch_size, -1, -1) + z_ctx
        h_seq = self.transformer(queries)  # (batch, n_horizons, hidden)
        result = {}
        for idx, horizon in enumerate(self.horizons):
            key = str(horizon)
            h_i = h_seq[:, idx, :]
            mean = self.mean_heads[key](h_i).squeeze(-1)
            log_var = self.logvar_heads[key](h_i).squeeze(-1)
            result[horizon] = (mean, log_var)
        return result


class MambaChallenger(nn.Module):
    """S4/Mamba-style challenger (simplified state-space model).

    Uses a learned linear recurrence for sequence processing from z_t.
    """

    def __init__(self, z_dim=16, hidden_dim=64, horizons=None):
        if horizons is None:
            horizons = [21, 63, 126]
        super().__init__()
        self.horizons = list(horizons)
        self.input_proj = nn.Linear(z_dim, hidden_dim)
        # SSM-style parameters
        self.A = nn.Parameter(torch.randn(hidden_dim, hidden_dim) * 0.01)
        self.B = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.C = nn.Linear(hidden_dim, 1, bias=False)
        self.D = nn.Parameter(torch.ones(1) * 0.01)
        self.mean_heads = nn.ModuleDict({str(h): nn.Linear(hidden_dim, 1) for h in self.horizons})
        self.logvar_heads = nn.ModuleDict({str(h): nn.Linear(hidden_dim, 1) for h in self.horizons})

    def forward(self, z_t):
        """z_t: (batch, z_dim) -> dict mapping horizon -> (mean, log_variance)."""
        batch_size = z_t.size(0)
        h = self.input_proj(z_t)
        # Run simplified SSM recurrence for a few steps
        state = h
        for _ in range(3):
            state = torch.relu(state @ self.A.t() + self.B(state))
        state = state + self.D * h
        result = {}
        for horizon in self.horizons:
            key = str(horizon)
            mean = self.mean_heads[key](state).squeeze(-1)
            log_var = self.logvar_heads[key](state).squeeze(-1)
            result[horizon] = (mean, log_var)
        return result
