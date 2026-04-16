"""
Representation learner architectures — SSL Transformer, Contrastive, MAE, VAE, Deep SSM.

All models produce z_t latent representations from financial time series input.
Each follows a standard interface: forward(x) -> z_t, encode(x) -> z_t.

Ref: specs/04-latent-first-architecture.md §4
Ref: T-03-03 through T-03-08
"""

import math

import torch
import torch.nn as nn


class SSLTransformer(nn.Module):
    """Self-supervised transformer for financial time series (champion candidate)."""

    def __init__(
        self,
        input_dim: int = 20,
        latent_dim: int = 16,
        n_heads: int = 4,
        n_layers: int = 3,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, latent_dim)
        self.pos_encoding = nn.Parameter(torch.randn(1, 500, latent_dim) * 0.02)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=latent_dim,
            nhead=n_heads,
            dim_feedforward=latent_dim * 4,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        # Decoder: expand pooled z back to sequence-level reconstruction
        self.decoder = nn.Linear(latent_dim, input_dim)
        self.latent_dim = latent_dim

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """x: (batch, seq_len, input_dim) -> (z_t, reconstruction)"""
        z = self.encode(x)
        # Broadcast pooled z to sequence length and decode
        seq_len = x.size(1)
        z_expanded = z.unsqueeze(1).expand(-1, seq_len, -1)  # (batch, seq, latent_dim)
        recon = self.decoder(z_expanded)  # (batch, seq, input_dim)
        return z, recon

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Produce latent representation z_t."""
        h = self.input_proj(x)
        seq_len = h.size(1)
        h = h + self.pos_encoding[:, :seq_len, :]
        h = self.transformer(h)
        return h.mean(dim=1)  # pool over sequence


class ContrastiveEncoder(nn.Module):
    """Contrastive/InfoNCE encoder (challenger)."""

    def __init__(self, input_dim: int = 20, latent_dim: int = 16, hidden_dim: int = 64):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
        )
        self.latent_dim = latent_dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.encode(x)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 3:
            return self.encoder(x.mean(dim=1))
        return self.encoder(x)


class MaskedAutoencoder(nn.Module):
    """Masked autoencoder over temporal windows (challenger)."""

    def __init__(self, input_dim: int = 20, latent_dim: int = 16, mask_ratio: float = 0.3):
        super().__init__()
        self.mask_ratio = mask_ratio
        self.encoder = nn.Sequential(nn.Linear(input_dim, 64), nn.ReLU(), nn.Linear(64, latent_dim))
        self.decoder = nn.Sequential(nn.Linear(latent_dim, 64), nn.ReLU(), nn.Linear(64, input_dim))
        self.latent_dim = latent_dim

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        z = self.encode(x)
        # Broadcast pooled z to sequence length and decode
        if x.dim() == 3:
            seq_len = x.size(1)
            z_expanded = z.unsqueeze(1).expand(-1, seq_len, -1)  # (batch, seq, latent_dim)
            recon = self.decoder(z_expanded)  # (batch, seq, input_dim)
        else:
            recon = self.decoder(z)
        return z, recon

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 3:
            return (
                self.encoder(x.reshape(-1, x.size(-1)))
                .reshape(x.size(0), x.size(1), -1)
                .mean(dim=1)
            )
        return self.encoder(x)


class VariationalAutoencoder(nn.Module):
    """VAE for explicit posterior structure (challenger)."""

    def __init__(self, input_dim: int = 20, latent_dim: int = 16, hidden_dim: int = 64):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(input_dim, hidden_dim), nn.ReLU())
        self.fc_mu = nn.Linear(hidden_dim, latent_dim)
        self.fc_logvar = nn.Linear(hidden_dim, latent_dim)
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, input_dim)
        )
        self.latent_dim = latent_dim

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 3:
            x = x.mean(dim=1)
        h = self.encoder(x)
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        return self.decoder(z)

    def forward(
        self, x: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        if x.dim() == 3:
            x_flat = x.mean(dim=1)
        else:
            x_flat = x
        h = self.encoder(x_flat)
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        z = mu + eps * std
        # Broadcast z to sequence length for full-sequence reconstruction (like SSLTransformer)
        seq_len = x.size(1)
        z_expanded = z.unsqueeze(1).expand(-1, seq_len, -1)
        recon = self.decode(z_expanded)
        return z, recon, mu, logvar


class DeepSSM(nn.Module):
    """Deep state-space model using linear recurrence (S4-style challenger)."""

    def __init__(self, input_dim: int = 20, latent_dim: int = 16, hidden_dim: int = 64):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        self.state_proj = nn.Linear(hidden_dim, latent_dim)
        self.transition = nn.Linear(latent_dim, latent_dim, bias=False)
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, latent_dim * 2),
            nn.ReLU(),
            nn.Linear(latent_dim * 2, input_dim),
        )
        self.latent_dim = latent_dim

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        z = self.encode(x)
        # Broadcast pooled z to sequence length and decode
        seq_len = x.size(1)
        z_expanded = z.unsqueeze(1).expand(-1, seq_len, -1)  # (batch, seq, latent_dim)
        recon = self.decoder(z_expanded)  # (batch, seq, input_dim)
        return z, recon

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        h = self.input_proj(x)
        # Simple recurrent encoding
        batch_size = h.size(0)
        state = torch.zeros(batch_size, self.latent_dim, device=h.device)
        for t in range(h.size(1)):
            obs = self.state_proj(h[:, t, :])
            state = self.transition(state) + obs
        return state
