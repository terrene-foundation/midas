"""Tier 1 tests for ContrastiveEncoder challenger training."""

import torch
import asyncio
from torch.utils.data import DataLoader, TensorDataset
from midas.ml.models.representation import ContrastiveEncoder
from midas.ml.training import TrainingPipeline


class TestContrastiveEncoderTraining:
    """Tests for contrastive encoder challenger."""

    def test_contrastive_train_produces_loss(self):
        """Training produces a loss value."""
        model = ContrastiveEncoder(input_dim=20, latent_dim=16, hidden_dim=32)
        pipeline = TrainingPipeline(model, device="cpu")

        X = torch.randn(50, 60, 20)  # (samples, seq, features)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=8)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(pipeline.train(loader, epochs=2))
        finally:
            loop.close()

        assert "avg_loss" in result
        assert result["avg_loss"] >= 0

    def test_contrastive_encode_returns_latent(self):
        """encode() returns latent representation."""
        model = ContrastiveEncoder(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        z = model.encode(x)
        assert z.shape == (4, 16)

    def test_contrastive_forward_returns_z_and_recon(self):
        """forward() returns (z_t, reconstruction) tuple."""
        model = ContrastiveEncoder(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        z, recon = model(x)
        assert z.shape == (4, 16)
        assert recon.shape == (4, 60, 20)

    def test_contrastive_gradient_flow(self):
        """Loss backward updates all parameters."""
        model = ContrastiveEncoder(input_dim=20, latent_dim=16, hidden_dim=32)
        X = torch.randn(8, 60, 20)

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        optimizer.zero_grad()

        z, recon = model(X)
        loss = torch.nn.functional.mse_loss(recon, X)
        loss.backward()

        for p in model.parameters():
            assert p.grad is not None

    def test_contrastive_different_seq_lengths(self):
        """Handles varying sequence lengths gracefully."""
        model = ContrastiveEncoder(input_dim=20, latent_dim=16)

        # Different batch shapes
        z1 = model.encode(torch.randn(4, 30, 20))
        z2 = model.encode(torch.randn(4, 120, 20))
        assert z1.shape == (4, 16)
        assert z2.shape == (4, 16)

    def test_contrastive_checkpoint_save_load(self):
        """Checkpoint save/load restores weights."""
        import tempfile, os

        model = ContrastiveEncoder(input_dim=20, latent_dim=16)
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

            model2 = ContrastiveEncoder(input_dim=20, latent_dim=16)
            pipeline2 = TrainingPipeline(model2, device="cpu")
            pipeline2.load_checkpoint(ckpt_path)

            state1 = pipeline.model.state_dict()
            state2 = pipeline2.model.state_dict()
            for k in state1:
                assert torch.allclose(state1[k], state2[k], atol=1e-6)
        finally:
            os.unlink(ckpt_path)
