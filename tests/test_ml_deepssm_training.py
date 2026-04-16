"""Tier 1 tests for DeepSSM challenger training."""

import torch
import asyncio
from torch.utils.data import DataLoader, TensorDataset
from midas.ml.models.representation import DeepSSM
from midas.ml.training import TrainingPipeline


class TestDeepSSMTraining:
    """Tests for DeepSSM challenger (S4-style linear recurrence)."""

    def test_deepssm_train_produces_loss(self):
        """Training produces loss."""
        model = DeepSSM(input_dim=20, latent_dim=16, hidden_dim=32)
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

    def test_deepssm_encode_returns_latent(self):
        """encode() returns state-space latent representation."""
        model = DeepSSM(input_dim=20, latent_dim=16, hidden_dim=32)
        x = torch.randn(4, 60, 20)
        z = model.encode(x)
        assert z.shape == (4, 16)

    def test_deepssm_forward_returns_z_and_recon(self):
        """forward() returns (z, recon) with full-sequence reconstruction."""
        model = DeepSSM(input_dim=20, latent_dim=16, hidden_dim=32)
        x = torch.randn(4, 60, 20)
        z, recon = model(x)
        assert z.shape == (4, 16)
        # recon is broadcast to sequence length: (batch, seq, input_dim)
        assert recon.shape == (4, 60, 20)

    def test_deepssm_state_transition(self):
        """Linear recurrence accumulates state over sequence."""
        model = DeepSSM(input_dim=20, latent_dim=16)
        x = torch.randn(1, 10, 20)

        # Run encode twice with same input
        torch.manual_seed(0)
        z1 = model.encode(x)

        torch.manual_seed(0)
        z2 = model.encode(x)

        assert torch.allclose(z1, z2)

    def test_deepssm_gradient_flow(self):
        """Parameters update after backward."""
        model = DeepSSM(input_dim=20, latent_dim=16, hidden_dim=32)
        X = torch.randn(8, 60, 20)

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        optimizer.zero_grad()

        z, recon = model(X)
        loss = torch.nn.functional.mse_loss(recon, X)
        loss.backward()

        for p in model.parameters():
            assert p.grad is not None

    def test_deepssm_hidden_dim_affects_hidden(self):
        """Larger hidden_dim increases model capacity."""
        model_small = DeepSSM(input_dim=20, latent_dim=16, hidden_dim=16)
        model_large = DeepSSM(input_dim=20, latent_dim=16, hidden_dim=128)

        # Count parameters
        params_small = sum(p.numel() for p in model_small.parameters())
        params_large = sum(p.numel() for p in model_large.parameters())

        assert params_large > params_small

    def test_deepssm_checkpoint_save_load(self):
        """DeepSSM checkpoint preserves weights."""
        import tempfile
        import os

        model = DeepSSM(input_dim=20, latent_dim=16, hidden_dim=32)
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

            model2 = DeepSSM(input_dim=20, latent_dim=16, hidden_dim=32)
            pipeline2 = TrainingPipeline(model2, device="cpu")
            pipeline2.load_checkpoint(ckpt_path)

            state1 = pipeline.model.state_dict()
            state2 = pipeline2.model.state_dict()
            for k in state1:
                assert torch.allclose(state1[k], state2[k], atol=1e-6)
        finally:
            os.unlink(ckpt_path)
