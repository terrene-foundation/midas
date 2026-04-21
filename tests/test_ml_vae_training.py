"""Tier 1 tests for VariationalAutoencoder challenger training."""

import torch
import asyncio
from torch.utils.data import DataLoader, TensorDataset
from midas.ml.models.representation import VariationalAutoencoder
from midas.ml.training import TrainingPipeline


class TestVAETraining:
    """Tests for VAE challenger."""

    def test_vae_train_produces_loss(self):
        """Training produces loss with reconstruction + KL terms."""
        model = VariationalAutoencoder(input_dim=20, latent_dim=16, hidden_dim=32)
        pipeline = TrainingPipeline(model, device="cpu")

        X = torch.randn(50, 60, 20)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=8)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(pipeline.train(loader, epochs=2))
        finally:
            loop.close()

        assert "avg_loss" in result
        assert result["avg_loss"] >= 0

    def test_vae_encode_returns_latent(self):
        """encode() returns latent representation (stochastic)."""
        model = VariationalAutoencoder(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)

        # Set seed for reproducibility
        torch.manual_seed(42)
        z1 = model.encode(x)

        torch.manual_seed(42)
        z2 = model.encode(x)

        assert z1.shape == (4, 16)
        assert z2.shape == (4, 16)

    def test_vae_forward_returns_z_and_recon(self):
        """forward() returns (z, recon) 2-tuple."""
        model = VariationalAutoencoder(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        result = model(x)
        assert isinstance(result, tuple)
        assert len(result) == 2  # z, recon
        z, recon = result
        assert z.shape == (4, 16)
        assert recon.shape == (4, 60, 20)

    def test_vae_kl_divergence_is_positive(self):
        """KL divergence term is always non-negative."""
        model = VariationalAutoencoder(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)

        model(x)  # triggers forward, stores mu/logvar
        kl_params = model.last_kl_params
        assert kl_params is not None
        mu, logvar = kl_params

        # KL = -0.5 * sum(1 + logvar - mu^2 - exp(logvar))
        kl = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
        assert kl >= 0

    def test_vae_gradient_flow(self):
        """All parameters have gradients after backward."""
        model = VariationalAutoencoder(input_dim=20, latent_dim=16, hidden_dim=32)
        X = torch.randn(8, 60, 20)

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        optimizer.zero_grad()

        z, recon = model(X)
        # VAE loss: MSE recon + KL (via encode_detailed)
        recon_loss = torch.nn.functional.mse_loss(recon, X)
        _, mu, logvar = model.encode_detailed(X)
        kl = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
        loss = recon_loss + 0.01 * kl
        loss.backward()

        for p in model.parameters():
            assert p.grad is not None

    def test_vae_decode(self):
        """decode() produces reconstruction from latent."""
        model = VariationalAutoencoder(input_dim=20, latent_dim=16)
        z = torch.randn(4, 16)
        recon = model.decode(z)
        assert recon.shape == (4, 20)

    def test_vae_checkpoint_save_load(self):
        """VAE checkpoint preserves weights."""
        import tempfile, os

        model = VariationalAutoencoder(input_dim=20, latent_dim=16)
        pipeline = TrainingPipeline(model, device="cpu")

        X = torch.randn(20, 60, 20)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=8)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(pipeline.train(loader, epochs=1))
        finally:
            loop.close()

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            ckpt_path = f.name
        try:
            pipeline.save_checkpoint(ckpt_path)

            model2 = VariationalAutoencoder(input_dim=20, latent_dim=16)
            pipeline2 = TrainingPipeline(model2, device="cpu")
            pipeline2.load_checkpoint(ckpt_path)

            state1 = pipeline.model.state_dict()
            state2 = pipeline2.model.state_dict()
            for k in state1:
                assert torch.allclose(state1[k], state2[k], atol=1e-6)
        finally:
            os.unlink(ckpt_path)
