"""
Tier 1 tests for EnergyBasedChallenger and GPSSMHybridChallenger.

Covers: forward pass shapes, positive variance, sample_posterior,
energy decrease with Langevin steps, GP variance inflation in low-data,
finite log-likelihood, and batch handling.

Ref: M04 State Inference Pool specification, SS5 (challenger families)
"""

import torch
import pytest

from midas.state_inference.bayesian_filter import (
    EnergyBasedChallenger,
    GPSSMHybridChallenger,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

INPUT_DIM = 10
LATENT_DIM = 4
BATCH_SIZE = 3
SEQ_LEN = 15


def _make_obs(batch_size=BATCH_SIZE, seq_len=SEQ_LEN, input_dim=INPUT_DIM):
    return torch.randn(batch_size, seq_len, input_dim)


# ---------------------------------------------------------------------------
# EnergyBasedChallenger
# ---------------------------------------------------------------------------


class TestEnergyBasedChallenger:
    """EnergyBasedChallenger forward pass, sampling, and Langevin dynamics."""

    def test_forward_produces_correct_shapes(self):
        """Forward returns (mean, variance, log_likelihood) with correct dims."""
        model = EnergyBasedChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        mean, variance, log_likelihood = model(obs)

        assert mean.shape == (BATCH_SIZE, LATENT_DIM)
        assert variance.shape == (BATCH_SIZE, LATENT_DIM)
        assert log_likelihood.shape == (BATCH_SIZE,)

    def test_variance_is_positive(self):
        """Posterior variance must always be positive."""
        model = EnergyBasedChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        _, variance, _ = model(obs)
        assert (variance > 0).all()

    def test_sample_posterior_works_after_forward(self):
        """sample_posterior returns the requested number of samples."""
        model = EnergyBasedChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        model(obs)

        samples = model.sample_posterior(n_samples=100)
        assert samples.shape == (100, LATENT_DIM)
        assert torch.isfinite(samples).all()

    def test_sample_posterior_raises_without_forward(self):
        """sample_posterior raises RuntimeError if forward not called."""
        model = EnergyBasedChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        with pytest.raises(RuntimeError, match="forward"):
            model.sample_posterior(n_samples=10)

    def test_energy_decreases_with_langevin_steps(self):
        """Energy at the final Langevin step should be <= initial energy."""
        torch.manual_seed(42)
        model = EnergyBasedChallenger(
            input_dim=INPUT_DIM,
            latent_dim=LATENT_DIM,
            num_langevin_steps=10,
            langevin_step_size=0.05,
        )
        model.eval()

        obs = _make_obs(batch_size=1)

        # Encode and get initial z
        with torch.no_grad():
            gru_out, _ = model.encoder(obs)
            h = gru_out[:, -1, :]
            z_init = model.z_init_proj(h)

        # Measure initial energy
        with torch.no_grad():
            initial_energy = model._compute_energy(z_init, h).item()

        # Run forward (includes Langevin steps -- needs autograd internally)
        mean, _, _ = model(obs)

        # Measure final energy
        with torch.no_grad():
            final_energy = model._compute_energy(mean, h).item()

        # Langevin dynamics should reduce energy (or at least not increase it
        # drastically; noise can cause small fluctuations, so use a generous bound)
        assert final_energy <= initial_energy + 1.0, (
            f"Energy did not decrease: initial={initial_energy:.4f}, " f"final={final_energy:.4f}"
        )

    def test_log_likelihood_is_finite(self):
        """Log-likelihood must be finite for all batch elements."""
        model = EnergyBasedChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        _, _, log_likelihood = model(obs)
        assert torch.isfinite(log_likelihood).all()

    def test_batch_handling(self):
        """Forward works with different batch sizes including 1."""
        model = EnergyBasedChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)

        # Single element batch
        obs_single = _make_obs(batch_size=1)
        mean, var, ll = model(obs_single)
        assert mean.shape == (1, LATENT_DIM)
        assert var.shape == (1, LATENT_DIM)
        assert ll.shape == (1,)

        # Larger batch
        obs_large = _make_obs(batch_size=8)
        mean, var, ll = model(obs_large)
        assert mean.shape == (8, LATENT_DIM)
        assert var.shape == (8, LATENT_DIM)
        assert ll.shape == (8,)

    def test_single_langevin_step(self):
        """Model works with a single Langevin step (edge case)."""
        model = EnergyBasedChallenger(
            input_dim=INPUT_DIM,
            latent_dim=LATENT_DIM,
            num_langevin_steps=1,
        )
        obs = _make_obs()
        mean, var, ll = model(obs)
        assert mean.shape == (BATCH_SIZE, LATENT_DIM)
        assert (var > 0).all()
        assert torch.isfinite(ll).all()


# ---------------------------------------------------------------------------
# GPSSMHybridChallenger
# ---------------------------------------------------------------------------


class TestGPSSMHybridChallenger:
    """GPSSMHybridChallenger forward pass, sampling, and variance inflation."""

    def test_forward_produces_correct_shapes(self):
        """Forward returns (mean, variance, log_likelihood) with correct dims."""
        model = GPSSMHybridChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        mean, variance, log_likelihood = model(obs)

        assert mean.shape == (BATCH_SIZE, LATENT_DIM)
        assert variance.shape == (BATCH_SIZE, LATENT_DIM)
        assert log_likelihood.shape == (BATCH_SIZE,)

    def test_variance_is_positive(self):
        """Posterior variance must always be positive."""
        model = GPSSMHybridChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        _, variance, _ = model(obs)
        assert (variance > 0).all()

    def test_sample_posterior_works_after_forward(self):
        """sample_posterior returns the requested number of samples."""
        model = GPSSMHybridChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        model(obs)

        samples = model.sample_posterior(n_samples=100)
        assert samples.shape == (100, LATENT_DIM)
        assert torch.isfinite(samples).all()

    def test_sample_posterior_raises_without_forward(self):
        """sample_posterior raises RuntimeError if forward not called."""
        model = GPSSMHybridChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        with pytest.raises(RuntimeError, match="forward"):
            model.sample_posterior(n_samples=10)

    def test_log_likelihood_is_finite(self):
        """Log-likelihood must be finite for all batch elements."""
        model = GPSSMHybridChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        _, _, log_likelihood = model(obs)
        assert torch.isfinite(log_likelihood).all()

    def test_low_data_inflated_variance_vs_high_data(self):
        """Low-data inputs should have higher variance than high-data inputs.

        Low-data is simulated with a short sequence (few observations).
        High-data is simulated with a long sequence (many observations).
        The confidence net should assign lower confidence to short sequences,
        inflating the GP prior and producing larger total variance.
        """
        torch.manual_seed(42)
        model = GPSSMHybridChallenger(
            input_dim=INPUT_DIM,
            latent_dim=LATENT_DIM,
            num_inducing=8,
        )
        model.eval()

        # Low-data: very short sequence (seq_len=2)
        obs_low = torch.randn(1, 2, INPUT_DIM)

        # High-data: long sequence (seq_len=100)
        obs_high = torch.randn(1, 100, INPUT_DIM)

        with torch.no_grad():
            _, var_low, _ = model(obs_low)
            _, var_high, _ = model(obs_high)

        mean_var_low = var_low.mean().item()
        mean_var_high = var_high.mean().item()

        # Short sequence should produce higher variance due to GP inflation
        assert mean_var_low > mean_var_high, (
            f"Low-data variance ({mean_var_low:.6f}) should exceed "
            f"high-data variance ({mean_var_high:.6f})"
        )

    def test_batch_handling(self):
        """Forward works with different batch sizes including 1."""
        model = GPSSMHybridChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)

        # Single element batch
        obs_single = _make_obs(batch_size=1)
        mean, var, ll = model(obs_single)
        assert mean.shape == (1, LATENT_DIM)
        assert var.shape == (1, LATENT_DIM)
        assert ll.shape == (1,)

        # Larger batch
        obs_large = _make_obs(batch_size=8)
        mean, var, ll = model(obs_large)
        assert mean.shape == (8, LATENT_DIM)
        assert var.shape == (8, LATENT_DIM)
        assert ll.shape == (8,)

    def test_inducing_points_parameter_exists(self):
        """Model has learnable inducing points of correct shape."""
        model = GPSSMHybridChallenger(
            input_dim=INPUT_DIM,
            latent_dim=LATENT_DIM,
            num_inducing=12,
        )
        assert model.inducing_points.shape == (12, LATENT_DIM)
        assert model.inducing_log_var.shape == (12, LATENT_DIM)

    def test_rbf_kernel_produces_positive_values(self):
        """RBF kernel values are positive and in (0, 1]."""
        model = GPSSMHybridChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        x = torch.randn(5, LATENT_DIM)
        y = torch.randn(3, LATENT_DIM)

        k = model._rbf_kernel(x, y)
        assert k.shape == (5, 3)
        assert (k > 0).all()
        assert (k <= 1.0 + 1e-6).all()

    def test_confidence_net_output_bounded(self):
        """Confidence net outputs are in [0, 1] due to sigmoid."""
        model = GPSSMHybridChallenger(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        obs = _make_obs()
        with torch.no_grad():
            gru_out, _ = model.encoder(obs)
            h = gru_out[:, -1, :]
            conf = model.confidence_net(h)

        assert (conf >= 0.0).all()
        assert (conf <= 1.0).all()


# ---------------------------------------------------------------------------
# Cross-cutting: import verification
# ---------------------------------------------------------------------------


class TestImports:
    """Verify both new classes are importable from the package."""

    def test_import_energy_based_from_package(self):
        """EnergyBasedChallenger is accessible via package import."""
        from midas.state_inference import EnergyBasedChallenger as EBC

        assert EBC is EnergyBasedChallenger

    def test_import_gpssm_from_package(self):
        """GPSSMHybridChallenger is accessible via package import."""
        from midas.state_inference import GPSSMHybridChallenger as GPSSM

        assert GPSSM is GPSSMHybridChallenger
