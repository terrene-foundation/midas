"""
Bayesian filtering architectures for latent state inference.

Provides five architectures for producing posterior distributions over
latent states from observation sequences:

* **DeepBayesianFilter** -- GRU encoder with linear projections for
  mean and log-variance (champion architecture).
* **NormalizingFlowChallenger** -- Coupling layers for non-Gaussian
  posteriors (challenger).
* **NeuralKalmanChallenger** -- Linear Gaussian transition with
  nonlinear emission via MLP (challenger).
* **EnergyBasedChallenger** -- Energy-based model using implicit
  posterior via Langevin dynamics on a learned energy function.
* **GPSSMHybridChallenger** -- Gaussian-process state-space hybrid
  with data-dependent variance inflation for low-data regimes.

All share the same interface:
    forward(observation_sequence) -> (posterior_mean, posterior_variance, log_likelihood)
    sample_posterior(n_samples) -> samples

Ref: M04 State Inference Pool specification
Ref: specs/04-latent-first-architecture.md SS5 (challenger families)
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


class EnergyBasedChallenger(nn.Module):
    """Energy-based model challenger using implicit posterior via Langevin dynamics.

    Learns an energy function E(z, x) that assigns low energy to likely
    (latent, observation) pairs. The posterior is recovered by running a
    few steps of Langevin dynamics (gradient descent on z to minimize
    energy), and variance is estimated from the energy landscape curvature.

    Parameters
    ----------
    input_dim:
        Dimensionality of input observations.
    latent_dim:
        Dimensionality of the latent state posterior.
    num_langevin_steps:
        Number of Langevin dynamics steps for posterior inference.
    langevin_step_size:
        Step size for Langevin dynamics updates.
    """

    def __init__(
        self,
        input_dim: int,
        latent_dim: int,
        num_langevin_steps: int = 5,
        langevin_step_size: float = 0.1,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.num_langevin_steps = num_langevin_steps
        self.langevin_step_size = langevin_step_size

        hidden_dim = max(latent_dim * 2, 32)

        # GRU encoder: compress observation sequence to a context vector
        self.encoder = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True,
        )

        # Energy head: scores (z, h) pairs
        # Takes concatenated [z, h] and outputs a scalar energy
        self.energy_net = nn.Sequential(
            nn.Linear(latent_dim + hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

        # Initial z prediction from context
        self.z_init_proj = nn.Linear(hidden_dim, latent_dim)

        self._last_mean: torch.Tensor | None = None
        self._last_log_var: torch.Tensor | None = None

    def _compute_energy(self, z: torch.Tensor, h: torch.Tensor) -> torch.Tensor:
        """Compute energy E(z, h) for each (z, h) pair.

        Parameters
        ----------
        z:
            Shape (batch, latent_dim).
        h:
            Shape (batch, hidden_dim).

        Returns
        -------
        torch.Tensor
            Shape (batch, 1) scalar energy per sample.
        """
        joint = torch.cat([z, h], dim=-1)
        return self.energy_net(joint)

    def forward(
        self, observation_sequence: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Run forward pass with Langevin dynamics posterior inference.

        Parameters
        ----------
        observation_sequence:
            Shape (batch, seq_len, input_dim).

        Returns
        -------
        posterior_mean:
            Shape (batch, latent_dim).
        posterior_variance:
            Shape (batch, latent_dim). Always positive.
        log_likelihood:
            Shape (batch,). Negative energy as proxy log-likelihood.
        """
        # Encode observation sequence
        gru_out, _ = self.encoder(observation_sequence)
        h = gru_out[:, -1, :]  # (batch, hidden_dim)

        # Initialize z from context projection
        z = self.z_init_proj(h)  # (batch, latent_dim)

        # Langevin dynamics: minimize energy w.r.t. z
        z = z.detach().requires_grad_(True)
        for _ in range(self.num_langevin_steps):
            energy = self._compute_energy(z, h)
            grad_z = torch.autograd.grad(energy.sum(), z, create_graph=False)[0]
            # Clip gradients to prevent NaN cascade from exploding energy landscape
            grad_z = torch.clamp(grad_z, -1.0, 1.0)
            # Langevin step: move against energy gradient + noise
            z = z - self.langevin_step_size * grad_z
            z = z + self.langevin_step_size * torch.randn_like(z)
            z = z.detach().requires_grad_(True)

        # Final mean is the converged z
        mean = z.detach()  # (batch, latent_dim)

        # Estimate variance from energy curvature (second-order approximation)
        # Use finite-difference Hessian diagonal approximation
        z_for_hess = mean.clone().detach().requires_grad_(True)
        eps = 1e-3
        e_center = self._compute_energy(z_for_hess, h)
        grad_center = torch.autograd.grad(e_center.sum(), z_for_hess, create_graph=True)[0]

        # Diagonal Hessian via second gradient
        hessian_diag = torch.autograd.grad(grad_center.sum(), z_for_hess)[0]

        # Variance ~ 1 / (curvature + epsilon) for each dimension
        curvature = torch.abs(hessian_diag) + 1e-4
        var = 1.0 / curvature
        # Clamp to prevent numerical issues
        var = torch.clamp(var, min=1e-6, max=100.0)

        log_var = torch.log(var)

        self._last_mean = mean.detach()
        self._last_log_var = log_var.detach()

        # Log-likelihood proxy: negative energy (lower energy = higher likelihood)
        final_energy = self._compute_energy(mean, h)
        log_likelihood = -final_energy.squeeze(-1)

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
        mean = self._last_mean[0]
        std = torch.exp(0.5 * self._last_log_var[0])
        eps = torch.randn(n_samples, self.latent_dim, device=mean.device)
        return mean + eps * std


class GPSSMHybridChallenger(nn.Module):
    """Gaussian-process state-space hybrid challenger for calibrated uncertainty.

    Combines a parametric transition model with a GP-like uncertainty
    estimation using learned inducing points. In low-data regions (few
    observations), variance is inflated via a data-dependent prior. In
    high-data regions, the parametric model dominates.

    Parameters
    ----------
    input_dim:
        Dimensionality of input observations.
    latent_dim:
        Dimensionality of the latent state.
    num_inducing:
        Number of inducing points for the sparse GP approximation.
    """

    def __init__(
        self,
        input_dim: int,
        latent_dim: int,
        num_inducing: int = 10,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.num_inducing = num_inducing

        hidden_dim = max(latent_dim * 2, 32)

        # GRU encoder for observation sequences
        self.encoder = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True,
        )
        self.mean_proj = nn.Linear(hidden_dim, latent_dim)
        self.log_var_proj = nn.Linear(hidden_dim, latent_dim)

        # Parametric transition model
        self.transition = nn.Linear(latent_dim, latent_dim, bias=False)
        nn.init.eye_(self.transition.weight)

        # Inducing points: learnable locations in latent space
        self.inducing_points = nn.Parameter(torch.randn(num_inducing, latent_dim) * 0.1)
        # Inducing point log-variances (learnable)
        self.inducing_log_var = nn.Parameter(torch.zeros(num_inducing, latent_dim))

        # Data-confidence estimator: maps hidden state to a confidence scalar
        self.confidence_net = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid(),
        )

        # Length-scale for GP kernel (learnable, positive)
        self.log_lengthscale = nn.Parameter(torch.tensor(0.0))

        # Process noise
        self.log_process_noise = nn.Parameter(torch.zeros(latent_dim))

        self._last_mean: torch.Tensor | None = None
        self._last_log_var: torch.Tensor | None = None

    def _rbf_kernel(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """Compute RBF kernel between x and y.

        Parameters
        ----------
        x:
            Shape (n, latent_dim).
        y:
            Shape (m, latent_dim).

        Returns
        -------
        torch.Tensor
            Shape (n, m).
        """
        lengthscale = torch.exp(self.log_lengthscale)
        # Squared Euclidean distance
        xx = torch.sum(x**2, dim=-1, keepdim=True)  # (n, 1)
        yy = torch.sum(y**2, dim=-1, keepdim=True)  # (m, 1)
        dist = xx + yy.t() - 2.0 * (x @ y.t())  # (n, m)
        return torch.exp(-0.5 * dist / (lengthscale**2))

    def _gp_variance(self, z: torch.Tensor, confidence: torch.Tensor) -> torch.Tensor:
        """Compute GP-informed variance for each latent state.

        Uses inducing points for a sparse GP approximation. In low-data
        regions (low confidence), inflates variance by upweighting the GP
        prior. In high-data regions (high confidence), relies more on the
        parametric estimate.

        Parameters
        ----------
        z:
            Shape (batch, latent_dim) -- parametric posterior means.
        confidence:
            Shape (batch, 1) -- data confidence in [0, 1].

        Returns
        -------
        torch.Tensor
            Shape (batch, latent_dim) -- adjusted variance.
        """
        # Compute kernel between z and inducing points
        k_zu = self._rbf_kernel(z, self.inducing_points)  # (batch, num_inducing)
        # Compute kernel between inducing points
        k_uu = self._rbf_kernel(
            self.inducing_points, self.inducing_points
        )  # (num_inducing, num_inducing)
        # Add jitter for numerical stability
        k_uu_reg = k_uu + 1e-3 * torch.eye(self.num_inducing, device=k_uu.device)

        # Inducing point variances
        inducing_var = torch.exp(self.inducing_log_var)  # (num_inducing, latent_dim)

        # Weighted interpolation: kernel weights determine GP influence
        # Solve K_uu @ alpha = K_zu^T for alpha, then weight inducing variances
        alpha = torch.linalg.solve(k_uu_reg.T, k_zu.T)  # (num_inducing, batch)
        # GP variance estimate: weighted combination of inducing variances
        gp_var = torch.clamp(
            alpha.T @ inducing_var,  # (batch, latent_dim)
            min=1e-6,
        )

        # Data-dependent prior variance (base uncertainty)
        prior_var = torch.exp(torch.tensor(2.0, device=z.device))  # wide prior

        # Blend: low confidence -> more GP/prior inflation, high confidence -> less
        # confidence in [0, 1], inflation_factor in [1, prior_var]
        inflation_factor = 1.0 + (1.0 - confidence) * (prior_var - 1.0)
        adjusted_var = gp_var * inflation_factor

        return adjusted_var

    def forward(
        self, observation_sequence: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass with GP-enhanced uncertainty estimation.

        Parameters
        ----------
        observation_sequence:
            Shape (batch, seq_len, input_dim).

        Returns
        -------
        posterior_mean, posterior_variance, log_likelihood
        """
        gru_out, _ = self.encoder(observation_sequence)
        h = gru_out[:, -1, :]  # (batch, hidden_dim)

        # Parametric posterior estimate
        mean = self.mean_proj(h)  # (batch, latent_dim)
        param_log_var = self.log_var_proj(h)  # (batch, latent_dim)
        param_var = torch.exp(param_log_var)

        # Data confidence: how much data the encoder has seen
        confidence = self.confidence_net(h)  # (batch, 1)

        # GP-enhanced variance
        gp_var = self._gp_variance(mean, confidence)  # (batch, latent_dim)

        # Combine parametric and GP variance
        process_var = torch.exp(self.log_process_noise)  # (latent_dim,)
        total_var = param_var + gp_var + process_var.unsqueeze(0)
        total_var = torch.clamp(total_var, min=1e-6)

        total_log_var = torch.log(total_var)

        self._last_mean = mean.detach()
        self._last_log_var = total_log_var.detach()

        # Log likelihood: proxy from parametric fit quality
        # Negative squared error between predicted mean and transition prior
        transitioned = self.transition(mean)
        recon_error = mean - transitioned
        log_likelihood = -0.5 * torch.sum(recon_error**2, dim=-1)

        return mean, total_var, log_likelihood

    def sample_posterior(self, n_samples: int) -> torch.Tensor:
        """Draw samples from the posterior.

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
        mean = self._last_mean[0]
        std = torch.exp(0.5 * self._last_log_var[0])
        eps = torch.randn(n_samples, self.latent_dim, device=mean.device)
        return mean + eps * std
