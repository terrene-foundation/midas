"""
Representation learner architectures — SSL Transformer, Contrastive, MAE, VAE, Deep SSM,
Diffusion, Foundation TS Wrapper.

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
        self.decoder = nn.Linear(latent_dim, input_dim)
        self.latent_dim = latent_dim

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """x: (batch, seq_len, input_dim) -> (z_t, reconstruction)"""
        z = self.encode(x)
        if x.dim() == 3:
            seq_len = x.size(1)
            z_expanded = z.unsqueeze(1).expand(-1, seq_len, -1)
            recon = self.decoder(z_expanded)
        else:
            recon = self.decoder(z)
        return z, recon

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
        logvar = torch.clamp(logvar, min=-10.0, max=10.0)
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def encode_detailed(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Return (z, mu, logvar) for VAE loss computation."""
        if x.dim() == 3:
            x = x.mean(dim=1)
        h = self.encoder(x)
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        logvar = torch.clamp(logvar, min=-10.0, max=10.0)
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        z = mu + eps * std
        return z, mu, logvar

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        return self.decoder(z)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """x: (batch, seq_len, input_dim) -> (z_t, reconstruction)."""
        z, mu, logvar = self.encode_detailed(x)
        self._last_mu = mu.detach()
        self._last_logvar = logvar.detach()
        seq_len = x.size(1)
        z_expanded = z.unsqueeze(1).expand(-1, seq_len, -1)
        recon = self.decode(z_expanded)
        return z, recon

    @property
    def last_kl_params(self) -> tuple[torch.Tensor, torch.Tensor] | None:
        """Return (mu, logvar) from the last forward pass, for KL loss."""
        if not hasattr(self, "_last_mu"):
            return None
        return self._last_mu, self._last_logvar


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


class _ResBlock1D(nn.Module):
    """Residual block for 1D UNet-style denoiser."""

    def __init__(self, channels: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Linear(channels, channels),
            nn.GELU(),
            nn.Linear(channels, channels),
        )
        self.norm = nn.LayerNorm(channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.norm(x + self.block(x))


class DiffusionModel(nn.Module):
    """Denoising diffusion model of market state for generative scenario work.

    Forward pass applies noise corruption then denoises, returning
    (z_t, reconstruction). encode() produces z_t via the forward diffusion
    process (adding noise over T timesteps) followed by partial reverse.

    Ref: specs/04-latent-first-architecture.md §4
    """

    def __init__(
        self,
        input_dim: int = 20,
        latent_dim: int = 16,
        timesteps: int = 100,
        hidden_dim: int = 64,
        n_res_blocks: int = 3,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.timesteps = timesteps

        # Linear beta schedule: beta_0 = 1e-4, beta_T = 0.02
        self.register_buffer("_betas", torch.linspace(1e-4, 0.02, timesteps))
        alphas = 1.0 - self._betas
        alphas_cumprod = torch.cumprod(alphas, dim=0)
        self.register_buffer("_alphas_cumprod", alphas_cumprod)
        self.register_buffer("_sqrt_alphas_cumprod", torch.sqrt(alphas_cumprod))
        self.register_buffer(
            "_sqrt_one_minus_alphas_cumprod",
            torch.sqrt(1.0 - alphas_cumprod),
        )

        # Encoder: project input to hidden, pool over sequence
        self.input_proj = nn.Linear(input_dim, hidden_dim)

        # UNet-style 1D denoiser: ResNet blocks with skip connections
        denoiser_layers = [_ResBlock1D(hidden_dim) for _ in range(n_res_blocks)]
        self.denoiser = nn.Sequential(*denoiser_layers)

        # Time embedding: sinusoidal positional encoding
        self.time_embed = nn.Linear(1, hidden_dim)

        # Project hidden to latent
        self.to_latent = nn.Linear(hidden_dim, latent_dim)

        # Reconstruction decoder: latent -> hidden -> input
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, input_dim),
        )

    def _sinusoidal_embedding(self, t: torch.Tensor) -> torch.Tensor:
        """Embed timestep as a single feature for the denoiser."""
        # t: (batch,) -> (batch, 1)
        return t.float().unsqueeze(-1)

    def _forward_diffusion(
        self, x0: torch.Tensor, t: torch.Tensor, noise: torch.Tensor
    ) -> torch.Tensor:
        """Apply forward diffusion: x_t = sqrt(alpha_cumprod_t) * x0 + sqrt(1-alpha_cumprod_t) * noise."""
        sqrt_alpha = self._sqrt_alphas_cumprod[t]  # (batch,)
        sqrt_one_minus_alpha = self._sqrt_one_minus_alphas_cumprod[t]  # (batch,)

        # Expand to broadcast: (batch, 1, 1) for (batch, seq, dim)
        sqrt_alpha = sqrt_alpha.unsqueeze(-1).unsqueeze(-1)
        sqrt_one_minus_alpha = sqrt_one_minus_alpha.unsqueeze(-1).unsqueeze(-1)

        return sqrt_alpha * x0 + sqrt_one_minus_alpha * noise

    def _denoise_step(
        self,
        x_t: torch.Tensor,
        t: torch.Tensor,
        pooled: torch.Tensor,
    ) -> torch.Tensor:
        """Single denoising step through the UNet denoiser."""
        t_emb = self.time_embed(self._sinusoidal_embedding(t))  # (batch, hidden)
        # Expand pooled to match x_t's sequence dimension
        seq_len = x_t.size(1)
        pooled_expanded = pooled.unsqueeze(1).expand(-1, seq_len, -1)  # (batch, seq, hidden)
        # Add time embedding to pooled features (broadcast over seq dim)
        h = pooled_expanded + t_emb.unsqueeze(1)  # (batch, seq, hidden)
        h = self.denoiser(h)
        return x_t + h

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """x: (batch, seq_len, input_dim) -> (z_t, reconstruction).

        Applies forward diffusion to get x_t, encodes to z_t,
        then reconstructs from z_t.
        """
        batch_size, seq_len, _ = x.shape

        # Project input to hidden dim
        h = self.input_proj(x)  # (batch, seq, hidden)

        # Sample a random timestep for training
        t = torch.randint(0, self.timesteps, (batch_size,), device=x.device)

        # Forward diffusion: add noise to hidden representation
        noise = torch.randn_like(h)
        h_noisy = self._forward_diffusion(h, t, noise)

        # Pool noisy hidden for denoiser context
        h_pooled = h_noisy.mean(dim=1)  # (batch, hidden)

        # Partial reverse: denoise from t toward t-1
        t_prev = (t - 1).clamp(min=0)
        h_denoised = self._denoise_step(h_noisy, t_prev, h_pooled)

        # Project to latent via mean pooling over sequence
        z_t = self.to_latent(h_denoised.mean(dim=1))  # (batch, latent)

        # Reconstruct: broadcast z to sequence length
        z_expanded = z_t.unsqueeze(1).expand(-1, seq_len, -1)
        recon = self.decoder(z_expanded)  # (batch, seq, input_dim)

        return z_t, recon

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Produce latent representation z_t via forward diffusion + partial reverse."""
        batch_size = x.size(0)

        # Project input to hidden dim
        h = self.input_proj(x)  # (batch, seq, hidden)

        # Apply full forward diffusion (corrupt to T-1)
        t_fill = torch.full((batch_size,), self.timesteps - 1, dtype=torch.long, device=x.device)
        noise = torch.randn_like(h)
        h_noisy = self._forward_diffusion(h, t_fill, noise)

        # Pool noisy hidden for denoiser context
        h_pooled = h_noisy.mean(dim=1)

        # Reverse a few steps to get z_t
        current_t = self.timesteps - 1
        reverse_steps = max(1, self.timesteps // 10)  # reverse ~10% of steps
        for i in range(reverse_steps):
            step_t = torch.full((batch_size,), current_t, dtype=torch.long, device=x.device)
            h_noisy = self._denoise_step(h_noisy, step_t, h_pooled)
            current_t = max(0, current_t - 1)

        # Project to latent
        z_t = self.to_latent(h_noisy.mean(dim=1))
        return z_t


class FoundationTSWrapper(nn.Module):
    """Wraps a pre-trained foundation time-series model fine-tuned on Midas's universe.

    Takes a backbone model (any nn.Module) and adds a projection head.
    forward(x) returns (z_t, reconstruction). encode(x) produces z_t
    through backbone + projection.

    If no backbone provided, uses a simple MLP backbone as default.
    Supports freeze_backbone flag for fine-tuning vs full training.

    Ref: specs/04-latent-first-architecture.md §4
    """

    def __init__(
        self,
        input_dim: int = 20,
        latent_dim: int = 16,
        backbone: nn.Module | None = None,
        backbone_output_dim: int = 64,
        freeze_backbone: bool = False,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.freeze_backbone = freeze_backbone

        # Default backbone: simple MLP
        if backbone is None:
            self.backbone = nn.Sequential(
                nn.Linear(input_dim, backbone_output_dim),
                nn.GELU(),
                nn.Linear(backbone_output_dim, backbone_output_dim),
                nn.GELU(),
            )
            self._using_default_backbone = True
        else:
            self.backbone = backbone
            self._using_default_backbone = False

        # Freeze backbone parameters if requested
        if freeze_backbone:
            for param in self.backbone.parameters():
                param.requires_grad = False

        # Projection head: backbone_output -> latent
        # Infer backbone output dim from the provided backbone
        if backbone is not None:
            # Try to infer by running a dummy forward pass
            self._backbone_output_dim = backbone_output_dim
        else:
            self._backbone_output_dim = backbone_output_dim

        self.projection = nn.Sequential(
            nn.Linear(self._backbone_output_dim, latent_dim),
        )

        # Reconstruction decoder: latent -> input
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, self._backbone_output_dim),
            nn.GELU(),
            nn.Linear(self._backbone_output_dim, input_dim),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """x: (batch, seq_len, input_dim) -> (z_t, reconstruction)."""
        z_t = self.encode(x)

        # Broadcast z to sequence length and decode
        seq_len = x.size(1)
        z_expanded = z_t.unsqueeze(1).expand(-1, seq_len, -1)
        recon = self.decoder(z_expanded)  # (batch, seq, input_dim)

        return z_t, recon

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Produce latent representation z_t through backbone + projection."""
        if x.dim() == 3:
            # Process each timestep through backbone, then pool
            batch_size, seq_len, feat_dim = x.shape
            # Flatten batch and sequence dims for backbone
            x_flat = x.reshape(-1, feat_dim)  # (batch*seq, feat_dim)
            h_flat = self.backbone(x_flat)  # (batch*seq, backbone_out)
            # Reshape back and pool over sequence
            h = h_flat.reshape(batch_size, seq_len, -1)
            h_pooled = h.mean(dim=1)  # (batch, backbone_out)
        else:
            h_pooled = self.backbone(x)  # (batch, backbone_out)

        z_t = self.projection(h_pooled)  # (batch, latent_dim)
        return z_t
