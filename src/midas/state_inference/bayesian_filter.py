"""
Bayesian filtering architectures for latent state inference.

Provides three architectures for producing posterior distributions over
latent states from observation sequences:

* **DeepBayesianFilter** -- GRU encoder with linear projections for
  mean and log-variance (champion architecture).
* **NormalizingFlowChallenger** -- Coupling layers for non-Gaussian
  posteriors (challenger).
* **NeuralKalmanChallenger** -- Linear Gaussian transition with
  nonlinear emission via MLP (challenger).

All share the same interface:
    forward(observation_sequence) -> (posterior_mean, posterior_variance, log_likelihood)
    sample_posterior(n_samples) -> samples

Ref: M04 State Inference Pool specification
Ref: specs/04-latent-first-architecture.md SS2 (state inference)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class DeepBayesianFilter(nn.Module):
    """GRU-based Bayesian filter producing Gaussian posteriors.

    Architecture:
        GRU encoder -> linear projection for mean
                     -> linear projection for log_variance
        Posterior is parameterized as N(mean, exp(log_variance)).

    Parameters
    ----------
    input_dim:
        Dimensionality of input observations.
    latent_dim:
        Dimensionality of the latent state posterior.
    num_layers:
        Number of GRU layers.
    """

    def __init__(
        self,
        input_dim: int,
        latent_dim: int,
        num_layers: int = 2,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.num_layers = num_layers

        hidden_dim = max(latent_dim * 2, 32)

        self.gru = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
        )
        self.mean_proj = nn.Linear(hidden_dim, latent_dim)
        self.log_var_proj = nn.Linear(hidden_dim, latent_dim)

        # Store last posterior for sampling
        self._last_mean: torch.Tensor | None = None
        self._last_log_var: torch.Tensor | None = None

    def forward(
        self, observation_sequence: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Run forward pass over an observation sequence.

        Parameters
        ----------
        observation_sequence:
            Input tensor of shape (batch, seq_len, input_dim).

        Returns
        -------
        posterior_mean:
            Shape (batch, latent_dim).
        posterior_variance:
            Shape (batch, latent_dim). Always positive (exp of log_var).
        log_likelihood:
            Shape (batch,). Log likelihood under the learned posterior.
        """
        # GRU encoding
        gru_out, _ = self.gru(observation_sequence)
        # Use last time step output
        h = gru_out[:, -1, :]  # (batch, hidden_dim)

        mean = self.mean_proj(h)  # (batch, latent_dim)
        log_var = self.log_var_proj(h)  # (batch, latent_dim)
        var = torch.exp(log_var)  # guaranteed positive

        # Store for sampling
        self._last_mean = mean.detach()
        self._last_log_var = log_var.detach()

        # Log likelihood: sum over latent dimensions of log N(mean, var) evaluated at mean
        # This is the entropy term (always negative, higher = more certain)
        log_likelihood = -0.5 * torch.sum(
            log_var + torch.log(torch.tensor(2.0 * 3.141592653589793)),
            dim=-1,
        )

        return mean, var, log_likelihood

    def sample_posterior(self, n_samples: int) -> torch.Tensor:
        """Draw samples from the last computed posterior.

        Parameters
        ----------
        n_samples:
            Number of samples to draw.

        Returns
        -------
        torch.Tensor
            Shape (n_samples, latent_dim).
        """
        if self._last_mean is None or self._last_log_var is None:
            raise RuntimeError(
                "Must call forward() before sample_posterior() to set posterior state"
            )
        # Use first batch element's posterior
        mean = self._last_mean[0]  # (latent_dim,)
        std = torch.exp(0.5 * self._last_log_var[0])  # (latent_dim,)

        eps = torch.randn(n_samples, self.latent_dim, device=mean.device)
        return mean + eps * std


class NormalizingFlowChallenger(nn.Module):
    """Normalizing flow challenger for non-Gaussian posteriors.

    Uses coupling layers to transform a base Gaussian into a flexible
    posterior distribution. Same interface as DeepBayesianFilter.

    Parameters
    ----------
    input_dim:
        Dimensionality of input observations.
    latent_dim:
        Dimensionality of the latent state posterior.
    num_layers:
        Number of coupling layers.
    """

    def __init__(
        self,
        input_dim: int,
        latent_dim: int,
        num_layers: int = 2,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.num_layers = num_layers

        hidden_dim = max(latent_dim * 2, 32)

        # Encoder: reduce sequence to a fixed-size vector
        self.encoder = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True,
        )

        # Base distribution parameters
        self.mean_proj = nn.Linear(hidden_dim, latent_dim)
        self.log_var_proj = nn.Linear(hidden_dim, latent_dim)

        # Coupling layers
        self.coupling_layers = nn.ModuleList([CouplingLayer(latent_dim) for _ in range(num_layers)])

        self._last_mean: torch.Tensor | None = None
        self._last_log_var: torch.Tensor | None = None

    def forward(
        self, observation_sequence: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass through the normalizing flow.

        Parameters
        ----------
        observation_sequence:
            Shape (batch, seq_len, input_dim).

        Returns
        -------
        posterior_mean, posterior_variance, log_likelihood
        """
        gru_out, _ = self.encoder(observation_sequence)
        h = gru_out[:, -1, :]

        base_mean = self.mean_proj(h)
        base_log_var = self.log_var_proj(h)
        base_var = torch.exp(base_log_var)

        # Transform base distribution through coupling layers
        z = base_mean + torch.exp(0.5 * base_log_var) * torch.randn_like(base_mean)
        log_det_jacobian = torch.zeros(z.shape[0], device=z.device)

        for layer in self.coupling_layers:
            z, ldj = layer(z)
            log_det_jacobian = log_det_jacobian + ldj

        # The mean of the transformed distribution is approximated by z (single sample)
        # Variance is approximated by base_var adjusted by Jacobian
        effective_var = base_var * torch.exp(2 * log_det_jacobian.unsqueeze(-1) / self.latent_dim)

        # Clamp variance to prevent numerical issues
        effective_var = torch.clamp(effective_var, min=1e-6)

        self._last_mean = z.detach()
        self._last_log_var = torch.log(effective_var).detach()

        # Log likelihood: base log prob + log det Jacobian
        base_log_prob = -0.5 * torch.sum(
            base_log_var + torch.log(torch.tensor(2.0 * 3.141592653589793)),
            dim=-1,
        )
        log_likelihood = base_log_prob + log_det_jacobian

        return z, effective_var, log_likelihood

    def sample_posterior(self, n_samples: int) -> torch.Tensor:
        """Draw samples from the flow posterior."""
        if self._last_mean is None or self._last_log_var is None:
            raise RuntimeError("Must call forward() before sample_posterior()")
        mean = self._last_mean[0]
        std = torch.exp(0.5 * self._last_log_var[0])
        eps = torch.randn(n_samples, self.latent_dim, device=mean.device)
        return mean + eps * std


class CouplingLayer(nn.Module):
    """Affine coupling layer for normalizing flows.

    Splits input into two halves; transforms the second half conditioned
    on the first.
    """

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim
        half = dim // 2
        if half < 1:
            half = 1
        self.half = half
        self.scale_net = nn.Sequential(
            nn.Linear(half, max(half, 8)),
            nn.ReLU(),
            nn.Linear(max(half, 8), dim - half),
        )
        self.shift_net = nn.Sequential(
            nn.Linear(half, max(half, 8)),
            nn.ReLU(),
            nn.Linear(max(half, 8), dim - half),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Forward transformation.

        Returns transformed x and log determinant of Jacobian.
        """
        x1 = x[:, : self.half]
        x2 = x[:, self.half :]

        scale = torch.tanh(self.scale_net(x1))
        shift = self.shift_net(x1)

        y2 = x2 * torch.exp(scale) + shift
        y = torch.cat([x1, y2], dim=-1)

        log_det_jacobian = torch.sum(scale, dim=-1)
        return y, log_det_jacobian


class NeuralKalmanChallenger(nn.Module):
    """Neural Kalman filter challenger.

    Combines a linear Gaussian state transition with a nonlinear emission
    model via MLP. Same interface as DeepBayesianFilter.

    Parameters
    ----------
    input_dim:
        Dimensionality of input observations.
    latent_dim:
        Dimensionality of the latent state.
    """

    def __init__(
        self,
        input_dim: int,
        latent_dim: int,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim

        hidden_dim = max(latent_dim * 2, 32)

        # Emission model: MLP from latent to observation space
        self.emission_net = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, input_dim),
        )

        # Inference network: encode observations into posterior
        self.encoder = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True,
        )
        self.mean_proj = nn.Linear(hidden_dim, latent_dim)
        self.log_var_proj = nn.Linear(hidden_dim, latent_dim)

        # Linear state transition (learnable)
        self.transition = nn.Linear(latent_dim, latent_dim, bias=False)
        # Initialize near identity for stability
        nn.init.eye_(self.transition.weight)

        # Process noise (learnable log-variance)
        self.log_process_noise = nn.Parameter(torch.zeros(latent_dim))

        self._last_mean: torch.Tensor | None = None
        self._last_log_var: torch.Tensor | None = None

    def forward(
        self, observation_sequence: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass through the neural Kalman filter.

        Parameters
        ----------
        observation_sequence:
            Shape (batch, seq_len, input_dim).

        Returns
        -------
        posterior_mean, posterior_variance, log_likelihood
        """
        gru_out, _ = self.encoder(observation_sequence)
        h = gru_out[:, -1, :]

        mean = self.mean_proj(h)
        log_var = self.log_var_proj(h)
        var = torch.exp(log_var)

        # Add process noise contribution
        process_var = torch.exp(self.log_process_noise)
        total_var = var + process_var.unsqueeze(0)

        self._last_mean = mean.detach()
        self._last_log_var = torch.log(total_var).detach()

        # Log likelihood: reconstruction quality + prior matching
        predicted_obs = self.emission_net(mean)
        recon_error = observation_sequence[:, -1, :] - predicted_obs
        log_likelihood = -0.5 * torch.sum(recon_error**2, dim=-1)

        return mean, total_var, log_likelihood

    def sample_posterior(self, n_samples: int) -> torch.Tensor:
        """Draw samples from the posterior."""
        if self._last_mean is None or self._last_log_var is None:
            raise RuntimeError("Must call forward() before sample_posterior()")
        mean = self._last_mean[0]
        std = torch.exp(0.5 * self._last_log_var[0])
        eps = torch.randn(n_samples, self.latent_dim, device=mean.device)
        return mean + eps * std
