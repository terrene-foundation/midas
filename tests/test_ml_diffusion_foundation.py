"""Tier 1 tests for DiffusionModel and FoundationTSWrapper representation learners."""

import asyncio
import os
import tempfile

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from midas.ml.models.representation import DiffusionModel, FoundationTSWrapper
from midas.ml.training import TrainingPipeline


# ---------------------------------------------------------------------------
# DiffusionModel tests
# ---------------------------------------------------------------------------


class TestDiffusionModelConstruction:
    """Tests for DiffusionModel initialization and parameter setup."""

    def test_default_construction(self):
        """Default parameters produce a valid model."""
        model = DiffusionModel()
        assert model.input_dim == 20
        assert model.latent_dim == 16
        assert model.timesteps == 100

    def test_custom_construction(self):
        """Custom parameters are stored correctly."""
        model = DiffusionModel(
            input_dim=10, latent_dim=8, timesteps=50, hidden_dim=32, n_res_blocks=2
        )
        assert model.input_dim == 10
        assert model.latent_dim == 8
        assert model.timesteps == 50

    def test_beta_schedule_registered_as_buffer(self):
        """Beta schedule is a non-parameter buffer."""
        model = DiffusionModel(timesteps=50)
        assert "_betas" in dict(model.named_buffers())
        betas = model._betas
        assert betas.shape == (50,)
        assert betas[0].item() < betas[-1].item()  # increasing

    def test_alpha_cumprod_registered_as_buffer(self):
        """Alpha cumulative product is a non-parameter buffer."""
        model = DiffusionModel(timesteps=50)
        assert "_alphas_cumprod" in dict(model.named_buffers())
        alphas_cumprod = model._alphas_cumprod
        assert alphas_cumprod.shape == (50,)
        # Cumulative product of alphas should be monotonically decreasing
        for i in range(1, 50):
            assert alphas_cumprod[i] <= alphas_cumprod[i - 1]

    def test_n_res_blocks_controls_denoiser_depth(self):
        """More res blocks means more denoiser parameters."""
        model_small = DiffusionModel(hidden_dim=32, n_res_blocks=1)
        model_large = DiffusionModel(hidden_dim=32, n_res_blocks=5)
        params_small = sum(p.numel() for p in model_small.parameters())
        params_large = sum(p.numel() for p in model_large.parameters())
        assert params_large > params_small

    def test_has_trainable_parameters(self):
        """Model has trainable parameters after construction."""
        model = DiffusionModel()
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        assert trainable > 0


class TestDiffusionModelForward:
    """Tests for DiffusionModel forward pass."""

    def test_forward_returns_two_tensors(self):
        """forward(x) returns (z_t, reconstruction)."""
        model = DiffusionModel(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        result = model(x)
        assert isinstance(result, tuple)
        assert len(result) == 2
        z_t, recon = result
        assert z_t.shape == (4, 16)
        assert recon.shape == (4, 60, 20)

    def test_forward_shape_matches_input(self):
        """Reconstruction shape matches input shape exactly."""
        model = DiffusionModel(input_dim=10, latent_dim=8)
        x = torch.randn(8, 30, 10)
        z_t, recon = model(x)
        assert recon.shape == x.shape

    def test_forward_latent_dim_correct(self):
        """z_t has the specified latent dimension."""
        model = DiffusionModel(input_dim=20, latent_dim=32)
        x = torch.randn(4, 60, 20)
        z_t, _ = model(x)
        assert z_t.shape == (4, 32)

    def test_forward_different_batch_sizes(self):
        """Forward pass works with batch size 1 and larger batches."""
        model = DiffusionModel(input_dim=20, latent_dim=16)
        for batch_size in [1, 4, 16]:
            x = torch.randn(batch_size, 30, 20)
            z_t, recon = model(x)
            assert z_t.shape[0] == batch_size
            assert recon.shape[0] == batch_size

    def test_forward_different_seq_lengths(self):
        """Forward pass works with various sequence lengths."""
        model = DiffusionModel(input_dim=20, latent_dim=16)
        for seq_len in [10, 60, 200]:
            x = torch.randn(4, seq_len, 20)
            z_t, recon = model(x)
            assert recon.shape == (4, seq_len, 20)


class TestDiffusionModelEncode:
    """Tests for DiffusionModel encode method."""

    def test_encode_returns_latent(self):
        """encode(x) returns a tensor of shape (batch, latent_dim)."""
        model = DiffusionModel(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        z_t = model.encode(x)
        assert z_t.shape == (4, 16)

    def test_encode_latent_dim_correct(self):
        """encode respects the latent_dim parameter."""
        model = DiffusionModel(input_dim=20, latent_dim=32)
        x = torch.randn(4, 60, 20)
        z_t = model.encode(x)
        assert z_t.shape == (4, 32)

    def test_encode_is_stochastic(self):
        """encode adds noise so two calls with same input produce different outputs."""
        model = DiffusionModel(input_dim=20, latent_dim=16, timesteps=50)
        x = torch.randn(4, 60, 20)
        z1 = model.encode(x)
        z2 = model.encode(x)
        # With noise injection, outputs should differ
        assert not torch.allclose(z1, z2)

    def test_encode_no_gradient_leak(self):
        """encode works under torch.no_grad()."""
        model = DiffusionModel(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        with torch.no_grad():
            z_t = model.encode(x)
        assert z_t.shape == (4, 16)


class TestDiffusionModelTraining:
    """Tests for DiffusionModel training via TrainingPipeline."""

    def test_train_produces_loss(self):
        """Training produces a non-negative average loss."""
        model = DiffusionModel(input_dim=20, latent_dim=16, hidden_dim=32, timesteps=20)
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

    def test_gradient_flow(self):
        """All parameters receive gradients after backward."""
        model = DiffusionModel(input_dim=20, latent_dim=16, hidden_dim=32)
        X = torch.randn(8, 60, 20)

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        optimizer.zero_grad()

        z_t, recon = model(X)
        loss = nn.functional.mse_loss(recon, X)
        loss.backward()

        for name, p in model.named_parameters():
            assert p.grad is not None, f"No gradient for {name}"

    def test_loss_decreases_over_epochs(self):
        """Training loss decreases over multiple epochs."""
        model = DiffusionModel(input_dim=10, latent_dim=8, hidden_dim=32, timesteps=20)
        X = torch.randn(32, 30, 10)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=8)

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        losses = []
        for _ in range(5):
            epoch_loss = 0.0
            for (batch_x,) in loader:
                optimizer.zero_grad()
                z_t, recon = model(batch_x)
                loss = nn.functional.mse_loss(recon, batch_x)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
            losses.append(epoch_loss)

        # Last epoch loss should be less than first (allowing for noise)
        assert losses[-1] < losses[0]

    def test_checkpoint_save_load(self):
        """Checkpoint save/load preserves model weights."""
        model = DiffusionModel(input_dim=20, latent_dim=16, hidden_dim=32, timesteps=20)
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

            model2 = DiffusionModel(input_dim=20, latent_dim=16, hidden_dim=32, timesteps=20)
            pipeline2 = TrainingPipeline(model2, device="cpu")
            pipeline2.load_checkpoint(ckpt_path)

            state1 = pipeline.model.state_dict()
            state2 = pipeline2.model.state_dict()
            for k in state1:
                assert torch.allclose(state1[k], state2[k], atol=1e-6)
        finally:
            os.unlink(ckpt_path)


class TestDiffusionModelForwardDiffusion:
    """Tests for the internal forward diffusion mechanics."""

    def test_zero_timestep_preserves_input(self):
        """At t=0, forward diffusion should approximately preserve the input."""
        model = DiffusionModel(input_dim=10, latent_dim=8, timesteps=100)
        h = torch.randn(2, 5, 64)  # hidden dim
        t = torch.zeros(2, dtype=torch.long)
        noise = torch.randn_like(h)

        h_noisy = model._forward_diffusion(h, t, noise)
        # At t=0, alpha_cumprod ~= 1 - 1e-4 ~ 0.9999, so h_noisy ~= h
        # Deviation is sqrt(beta_0) * noise ~= 0.01 * noise, up to ~0.04 for
        # standard normal outliers.
        assert torch.allclose(h_noisy, h, atol=0.05)

    def test_high_timestep_corrupts_input(self):
        """At high timesteps, forward diffusion significantly corrupts the input."""
        model = DiffusionModel(input_dim=10, latent_dim=8, timesteps=100)
        h = torch.randn(2, 5, 64)
        t = torch.full((2,), 99, dtype=torch.long)
        noise = torch.randn_like(h)

        h_noisy = model._forward_diffusion(h, t, noise)
        # At t=99, alpha_cumprod is small, so output should differ significantly
        assert not torch.allclose(h_noisy, h, atol=0.1)

    def test_custom_timesteps_short_schedule(self):
        """Model with few timesteps still works end-to-end."""
        model = DiffusionModel(input_dim=10, latent_dim=8, timesteps=5)
        x = torch.randn(4, 30, 10)
        z_t, recon = model(x)
        assert z_t.shape == (4, 8)
        assert recon.shape == (4, 30, 10)


# ---------------------------------------------------------------------------
# FoundationTSWrapper tests
# ---------------------------------------------------------------------------


class TestFoundationTSWrapperConstruction:
    """Tests for FoundationTSWrapper initialization."""

    def test_default_backbone_construction(self):
        """Default MLP backbone is created when none provided."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        assert model._using_default_backbone is True
        assert isinstance(model.backbone, nn.Sequential)

    def test_custom_backbone_construction(self):
        """Custom backbone is accepted."""
        backbone = nn.Sequential(
            nn.Linear(20, 32),
            nn.ReLU(),
            nn.Linear(32, 48),
        )
        model = FoundationTSWrapper(
            input_dim=20, latent_dim=16, backbone=backbone, backbone_output_dim=48
        )
        assert model._using_default_backbone is False
        assert model.backbone is backbone

    def test_freeze_backbone_flag(self):
        """freeze_backbone=True sets requires_grad=False on all backbone params."""
        backbone = nn.Sequential(
            nn.Linear(20, 32),
            nn.ReLU(),
            nn.Linear(32, 48),
        )
        model = FoundationTSWrapper(
            input_dim=20,
            latent_dim=16,
            backbone=backbone,
            backbone_output_dim=48,
            freeze_backbone=True,
        )
        for p in model.backbone.parameters():
            assert p.requires_grad is False

    def test_default_backbone_not_frozen(self):
        """Default backbone is not frozen by default."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        for p in model.backbone.parameters():
            assert p.requires_grad is True

    def test_projection_head_trainable_with_frozen_backbone(self):
        """Projection head remains trainable even when backbone is frozen."""
        backbone = nn.Sequential(nn.Linear(20, 32))
        model = FoundationTSWrapper(
            input_dim=20,
            latent_dim=16,
            backbone=backbone,
            backbone_output_dim=32,
            freeze_backbone=True,
        )
        for p in model.projection.parameters():
            assert p.requires_grad is True
        for p in model.decoder.parameters():
            assert p.requires_grad is True

    def test_has_trainable_parameters(self):
        """Model has trainable parameters after construction."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        assert trainable > 0


class TestFoundationTSWrapperForward:
    """Tests for FoundationTSWrapper forward pass."""

    def test_forward_returns_two_tensors(self):
        """forward(x) returns (z_t, reconstruction)."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        result = model(x)
        assert isinstance(result, tuple)
        assert len(result) == 2
        z_t, recon = result
        assert z_t.shape == (4, 16)
        assert recon.shape == (4, 60, 20)

    def test_forward_shape_matches_input(self):
        """Reconstruction shape matches input shape."""
        model = FoundationTSWrapper(input_dim=10, latent_dim=8)
        x = torch.randn(8, 30, 10)
        z_t, recon = model(x)
        assert recon.shape == x.shape

    def test_forward_with_custom_backbone(self):
        """Forward works with a custom backbone."""
        backbone = nn.Sequential(
            nn.Linear(10, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
        )
        model = FoundationTSWrapper(
            input_dim=10, latent_dim=8, backbone=backbone, backbone_output_dim=16
        )
        x = torch.randn(4, 30, 10)
        z_t, recon = model(x)
        assert z_t.shape == (4, 8)
        assert recon.shape == (4, 30, 10)

    def test_forward_different_batch_sizes(self):
        """Forward works with batch size 1 and larger."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        for batch_size in [1, 4, 16]:
            x = torch.randn(batch_size, 30, 20)
            z_t, recon = model(x)
            assert z_t.shape[0] == batch_size
            assert recon.shape[0] == batch_size

    def test_forward_different_seq_lengths(self):
        """Forward works with various sequence lengths."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        for seq_len in [10, 60, 200]:
            x = torch.randn(4, seq_len, 20)
            z_t, recon = model(x)
            assert recon.shape == (4, seq_len, 20)


class TestFoundationTSWrapperEncode:
    """Tests for FoundationTSWrapper encode method."""

    def test_encode_returns_latent(self):
        """encode(x) returns tensor of shape (batch, latent_dim)."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        z_t = model.encode(x)
        assert z_t.shape == (4, 16)

    def test_encode_is_deterministic(self):
        """encode is deterministic (no stochastic elements)."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        x = torch.randn(4, 60, 20)
        z1 = model.encode(x)
        z2 = model.encode(x)
        assert torch.allclose(z1, z2)

    def test_encode_2d_input(self):
        """encode handles 2D input (batch, input_dim) without sequence dim."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        x = torch.randn(8, 20)
        z_t = model.encode(x)
        assert z_t.shape == (8, 16)

    def test_encode_with_custom_backbone(self):
        """encode routes through the provided backbone."""
        backbone = nn.Sequential(
            nn.Linear(20, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
        )
        model = FoundationTSWrapper(
            input_dim=20, latent_dim=16, backbone=backbone, backbone_output_dim=32
        )
        x = torch.randn(4, 60, 20)
        z_t = model.encode(x)
        assert z_t.shape == (4, 16)


class TestFoundationTSWrapperTraining:
    """Tests for FoundationTSWrapper training via TrainingPipeline."""

    def test_train_produces_loss(self):
        """Training produces a non-negative average loss."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
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

    def test_gradient_flow_default_backbone(self):
        """All parameters receive gradients with default backbone."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
        X = torch.randn(8, 60, 20)

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        optimizer.zero_grad()

        z_t, recon = model(X)
        loss = nn.functional.mse_loss(recon, X)
        loss.backward()

        for name, p in model.named_parameters():
            assert p.grad is not None, f"No gradient for {name}"

    def test_gradient_flow_frozen_backbone(self):
        """Only projection and decoder get gradients with frozen backbone."""
        backbone = nn.Sequential(
            nn.Linear(20, 32),
            nn.ReLU(),
            nn.Linear(32, 48),
        )
        model = FoundationTSWrapper(
            input_dim=20,
            latent_dim=16,
            backbone=backbone,
            backbone_output_dim=48,
            freeze_backbone=True,
        )
        X = torch.randn(8, 60, 20)

        model.train()
        optimizer = torch.optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=1e-3)
        optimizer.zero_grad()

        z_t, recon = model(X)
        loss = nn.functional.mse_loss(recon, X)
        loss.backward()

        # Backbone should NOT have gradients
        for name, p in model.backbone.named_parameters():
            assert p.grad is None, f"Backbone param {name} should not have gradient"

        # Projection and decoder SHOULD have gradients
        for name, p in model.projection.named_parameters():
            assert p.grad is not None, f"No gradient for projection.{name}"
        for name, p in model.decoder.named_parameters():
            assert p.grad is not None, f"No gradient for decoder.{name}"

    def test_loss_decreases_over_epochs(self):
        """Training loss decreases over multiple epochs."""
        model = FoundationTSWrapper(input_dim=10, latent_dim=8)
        X = torch.randn(32, 30, 10)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=8)

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        losses = []
        for _ in range(5):
            epoch_loss = 0.0
            for (batch_x,) in loader:
                optimizer.zero_grad()
                z_t, recon = model(batch_x)
                loss = nn.functional.mse_loss(recon, batch_x)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
            losses.append(epoch_loss)

        assert losses[-1] < losses[0]

    def test_checkpoint_save_load(self):
        """Checkpoint save/load preserves model weights."""
        model = FoundationTSWrapper(input_dim=20, latent_dim=16)
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

            model2 = FoundationTSWrapper(input_dim=20, latent_dim=16)
            pipeline2 = TrainingPipeline(model2, device="cpu")
            pipeline2.load_checkpoint(ckpt_path)

            state1 = pipeline.model.state_dict()
            state2 = pipeline2.model.state_dict()
            for k in state1:
                assert torch.allclose(state1[k], state2[k], atol=1e-6)
        finally:
            os.unlink(ckpt_path)

    def test_frozen_backbone_weights_preserved_after_training(self):
        """Frozen backbone weights do not change after training."""
        backbone = nn.Sequential(nn.Linear(20, 32), nn.ReLU(), nn.Linear(32, 48))
        model = FoundationTSWrapper(
            input_dim=20,
            latent_dim=16,
            backbone=backbone,
            backbone_output_dim=48,
            freeze_backbone=True,
        )

        # Record initial backbone weights
        initial_weights = {name: p.clone() for name, p in model.backbone.named_parameters()}

        X = torch.randn(16, 30, 20)
        dataset = TensorDataset(X)
        loader = DataLoader(dataset, batch_size=8)

        model.train()
        optimizer = torch.optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=1e-3)

        for _ in range(3):
            for (batch_x,) in loader:
                optimizer.zero_grad()
                z_t, recon = model(batch_x)
                loss = nn.functional.mse_loss(recon, batch_x)
                loss.backward()
                optimizer.step()

        # Verify backbone weights are unchanged
        for name, p in model.backbone.named_parameters():
            assert torch.allclose(
                initial_weights[name], p
            ), f"Backbone weight {name} changed during training"


class TestFoundationTSWrapperWithTransformerBackbone:
    """Tests using a transformer as the backbone (realistic use case)."""

    def test_transformer_backbone_forward(self):
        """FoundationTSWrapper works with a transformer backbone."""

        class TransformerBackbone(nn.Module):
            def __init__(self, input_dim, d_model):
                super().__init__()
                self.proj = nn.Linear(input_dim, d_model)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=d_model, nhead=2, dim_feedforward=d_model * 2, batch_first=True
                )
                self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=1)
                self.out_proj = nn.Linear(d_model, d_model)

            def forward(self, x):
                return self.out_proj(self.proj(x))

        backbone = TransformerBackbone(20, 32)
        model = FoundationTSWrapper(
            input_dim=20, latent_dim=16, backbone=backbone, backbone_output_dim=32
        )
        x = torch.randn(4, 60, 20)
        z_t, recon = model(x)
        assert z_t.shape == (4, 16)
        assert recon.shape == (4, 60, 20)
