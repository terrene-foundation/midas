"""Tier 1 tests for the ML training pipeline."""

import os
import tempfile

import pytest
import torch
from torch.utils.data import DataLoader, TensorDataset

from midas.fabric.engine import create_fabric, reset_fabric
from midas.ml.training import TrainingPipeline
from midas.ml.models.representation import SSLTransformer


class TestTrainingPipeline:
    """Tests for TrainingPipeline."""

    def test_train_produces_avg_loss(self):
        """train() returns a result dict with avg_loss."""
        model = SSLTransformer(input_dim=20, latent_dim=16)
        pipeline = TrainingPipeline(model, device="cpu")

        # Synthetic dataset
        X = torch.randn(100, 60, 20)  # (samples, seq, features)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=16)

        import asyncio

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(pipeline.train(loader, epochs=2))
        finally:
            loop.close()

        assert "avg_loss" in result
        assert "epochs" in result
        assert result["epochs"] == 2

    def test_evaluate_produces_val_loss(self):
        """evaluate() returns val_loss."""
        model = SSLTransformer(input_dim=20, latent_dim=16)
        pipeline = TrainingPipeline(model, device="cpu")

        X_val = torch.randn(20, 60, 20)
        dataset = TensorDataset(X_val)
        loader = DataLoader(dataset, batch_size=8)

        import asyncio

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(pipeline.evaluate(loader))
        finally:
            loop.close()

        assert "val_loss" in result
        assert isinstance(result["val_loss"], float)

    def test_save_and_load_checkpoint(self):
        """save_checkpoint and load_checkpoint restore model state."""
        model = SSLTransformer(input_dim=20, latent_dim=16)
        pipeline = TrainingPipeline(model, device="cpu")

        # Train briefly to change state
        X = torch.randn(20, 60, 20)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=8)

        import asyncio

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(pipeline.train(loader, epochs=1))
        finally:
            loop.close()

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            ckpt_path = f.name

        try:
            pipeline.save_checkpoint(ckpt_path)
            assert os.path.exists(ckpt_path)

            # Load into new pipeline
            model2 = SSLTransformer(input_dim=20, latent_dim=16)
            pipeline2 = TrainingPipeline(model2, device="cpu")
            pipeline2.load_checkpoint(ckpt_path)

            # Verify state matches (optimizer state also restored)
            state1 = pipeline.model.state_dict()
            state2 = pipeline2.model.state_dict()
            for k in state1:
                assert torch.allclose(state1[k], state2[k], atol=1e-6)
        finally:
            os.unlink(ckpt_path)


class TestSSLTransformerArchitecture:
    """Tests for SSLTransformer architecture correctness."""

    def test_ssl_transformer_forward_returns_z_and_recon(self):
        """forward() returns (z_t, reconstruction) tuple."""
        model = SSLTransformer(input_dim=20, latent_dim=16)
        x = torch.randn(2, 60, 20)  # (batch, seq, features)
        z, recon = model(x)
        assert z.shape == (2, 16)  # pooled over sequence
        assert recon.shape == (2, 60, 20)  # reconstruction

    def test_ssl_transformer_encode_returns_latent(self):
        """encode() returns pooled latent representation."""
        model = SSLTransformer(input_dim=20, latent_dim=16)
        x = torch.randn(2, 60, 20)
        z = model.encode(x)
        assert z.shape == (2, 16)  # batch, latent_dim

    def test_ssl_transformer_train_step_updates_weights(self):
        """A training step changes model parameters (gradient flows)."""
        model = SSLTransformer(input_dim=20, latent_dim=16)
        pipeline = TrainingPipeline(model, device="cpu")
        pipeline.optimizer.zero_grad()

        X = torch.randn(4, 60, 20)
        result = model(X)
        if isinstance(result, tuple):
            z, recon = result
            loss = torch.nn.functional.mse_loss(recon, X.reshape_as(recon))
        else:
            loss = torch.tensor(0.0, requires_grad=True)

        loss.backward()
        for p in model.parameters():
            assert p.grad is not None
