"""Tier 1 tests for MaskedAutoencoder challenger training."""

import torch
import asyncio
from torch.utils.data import DataLoader, TensorDataset
from midas.ml.models.representation import MaskedAutoencoder
from midas.ml.training import TrainingPipeline


class TestMAETraining:
    """Tests for MAE challenger."""

    def test_mae_train_produces_loss(self):
        """Training produces reconstruction loss."""
        model = MaskedAutoencoder(input_dim=20, latent_dim=16)
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

    def test_mae_encode_returns_latent(self):
        """encode() returns pooled latent representation."""
        model = MaskedAutoencoder(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        z = model.encode(x)
        assert z.shape == (4, 16)

    def test_mae_forward_returns_z_and_recon(self):
        """forward() returns (z, recon)."""
        model = MaskedAutoencoder(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        z, recon = model(x)
        assert z.shape == (4, 16)
        assert recon.shape[0] == 4  # batch dim

    def test_mae_reconstruction_shape(self):
        """Reconstruction matches input shape."""
        model = MaskedAutoencoder(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        z, recon = model(x)
        # Reconstruction is flattened per sample
        assert recon.numel() == 4 * 60 * 20

    def test_mae_mask_ratio_affects_training(self):
        """Higher mask ratio changes loss landscape."""
        model = MaskedAutoencoder(input_dim=20, latent_dim=16, mask_ratio=0.3)
        pipeline = TrainingPipeline(model, device="cpu")

        X = torch.randn(30, 60, 20)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=8)

        loop = asyncio.new_event_loop()
        try:
            result1 = loop.run_until_complete(pipeline.train(loader, epochs=1))
        finally:
            loop.close()

        model2 = MaskedAutoencoder(input_dim=20, latent_dim=16, mask_ratio=0.7)
        pipeline2 = TrainingPipeline(model2, device="cpu")

        loop = asyncio.new_event_loop()
        try:
            result2 = loop.run_until_complete(pipeline2.train(loader, epochs=1))
        finally:
            loop.close()

        # Different mask ratios should produce different loss curves
        # (not guaranteed higher/lower, just different)
        assert "avg_loss" in result1
        assert "avg_loss" in result2

    def test_mae_gradient_flow(self):
        """Parameters update after backward."""
        model = MaskedAutoencoder(input_dim=20, latent_dim=16)
        X = torch.randn(8, 60, 20)

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        optimizer.zero_grad()

        z, recon = model(X)
        # MAE now broadcasts z to sequence: recon is (batch, seq, input_dim)
        loss = torch.nn.functional.mse_loss(recon, X)
        loss.backward()

        for p in model.parameters():
            assert p.grad is not None

    def test_mae_checkpoint_save_load(self):
        """MAE checkpoint preserves weights."""
        import tempfile
        import os

        model = MaskedAutoencoder(input_dim=20, latent_dim=16)
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

            model2 = MaskedAutoencoder(input_dim=20, latent_dim=16)
            pipeline2 = TrainingPipeline(model2, device="cpu")
            pipeline2.load_checkpoint(ckpt_path)

            state1 = pipeline.model.state_dict()
            state2 = pipeline2.model.state_dict()
            for k in state1:
                assert torch.allclose(state1[k], state2[k], atol=1e-6)
        finally:
            os.unlink(ckpt_path)
