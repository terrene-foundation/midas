"""Tier 1 tests for the representation-learner online inference service."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import torch

from midas.ml.online_inference import (
    InferenceInput,
    POOL_MEMBERS,
    RepresentationInferenceService,
)


class TestPoolMembers:
    """Tests for the pool member configuration."""

    def test_pool_has_ssl_transformer_as_champion(self):
        """SSL transformer is the champion per spec §4."""
        assert "ssl_transformer_v1" in POOL_MEMBERS
        assert POOL_MEMBERS["ssl_transformer_v1"]["role"] == "champion"

    def test_pool_has_all_five_learner_families(self):
        """All five learner families are registered."""
        expected = {
            "ssl_transformer_v1",
            "contrastive_v1",
            "mae_v1",
            "vae_v1",
            "deep_ssm_v1",
        }
        assert set(POOL_MEMBERS.keys()) == expected

    def test_ssl_transformer_creates_correct_architecture(self):
        """SSLTransformer is used for the champion."""
        from midas.ml.models.representation import SSLTransformer

        config = POOL_MEMBERS["ssl_transformer_v1"]
        assert config["cls"] == SSLTransformer
        assert config["default_kwargs"]["latent_dim"] == 16

    def test_all_members_have_valid_roles(self):
        """Every pool member has a valid role."""
        valid_roles = {"champion", "challenger_shadow"}
        for name, config in POOL_MEMBERS.items():
            assert config["role"] in valid_roles, f"{name} has invalid role"


class TestInferenceInput:
    """Tests for InferenceInput dataclass."""

    def test_inference_input_stores_features(self):
        """InferenceInput stores the feature tensor."""
        features = torch.randn(60, 20)
        inp = InferenceInput(
            ticker="AAPL",
            features=features,
            period_end=date(2024, 12, 31),
            filed_at=datetime(2024, 12, 31, 16, 0, 0),
        )
        assert inp.ticker == "AAPL"
        assert inp.features.shape == (60, 20)
        assert inp.period_end == date(2024, 12, 31)


class TestInferenceServiceInstantiation:
    """Tests for RepresentationInferenceService instantiation and model loading."""

    def test_service_instantiates_with_mock_writer(self):
        """Service creates without errors given a mock writer."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(
            fabric_writer=mock_writer,
            device="cpu",
        )
        assert service._device == "cpu"

    def test_load_model_returns_ssl_transformer(self):
        """_load_model returns the correct architecture for ssl_transformer_v1."""
        from midas.ml.models.representation import SSLTransformer

        mock_writer = MagicMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")
        model = service._load_model("ssl_transformer_v1")
        assert isinstance(model, SSLTransformer)
        assert model.latent_dim == 16

    def test_load_model_returns_contrastive_encoder(self):
        """_load_model returns ContrastiveEncoder for contrastive_v1."""
        from midas.ml.models.representation import ContrastiveEncoder

        mock_writer = MagicMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")
        model = service._load_model("contrastive_v1")
        assert isinstance(model, ContrastiveEncoder)

    def test_load_model_caches_model(self):
        """_load_model returns the same instance on repeated calls."""
        mock_writer = MagicMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")
        model1 = service._load_model("ssl_transformer_v1")
        model2 = service._load_model("ssl_transformer_v1")
        assert model1 is model2


class TestEncode:
    """Tests for the _encode method."""

    def test_encode_ssl_transformer_produces_z_vector(self):
        """SSL transformer encode produces a latent vector of correct dim."""
        from midas.ml.models.representation import SSLTransformer

        mock_writer = MagicMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")
        model = SSLTransformer(input_dim=20, latent_dim=16)
        # 3D input: (batch=2, seq=60, features=20) -> encode pools over seq -> (batch, latent_dim)
        features = torch.randn(2, 60, 20)
        z_list, _, _ = service._encode(model, features)
        # encode() pools over sequence, returns (batch, latent_dim). flatten() -> batch * latent_dim.
        # For batch=2, latent_dim=16: 2 * 16 = 32 elements
        assert len(z_list) == 32

    def test_encode_contrastive_encoder_produces_z_vector(self):
        """Contrastive encoder produces a latent vector."""
        from midas.ml.models.representation import ContrastiveEncoder

        mock_writer = MagicMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")
        model = ContrastiveEncoder(input_dim=20, latent_dim=16)
        # ContrastiveEncoder.encode pools over seq dim (dim=1), returning (batch, latent_dim)
        features = torch.randn(2, 60, 20)
        z_list, _, _ = service._encode(model, features)
        # batch=2, latent_dim=16 -> 32 elements
        assert len(z_list) == 32

    def test_encode_vae_produces_z_vector(self):
        """VAE encode produces a latent vector."""
        from midas.ml.models.representation import VariationalAutoencoder

        mock_writer = MagicMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")
        model = VariationalAutoencoder(input_dim=20, latent_dim=16)
        # VAE.encode pools over seq, returns (batch, latent_dim)
        features = torch.randn(2, 60, 20)
        z_list, _, _ = service._encode(model, features)
        assert len(z_list) == 32


class TestInferOne:
    """Tests for infer_one method."""

    @pytest.mark.asyncio
    async def test_infer_one_returns_results_for_ssl_transformer(self):
        """infer_one returns InferenceResult list for one learner."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")

        features = torch.randn(60, 20)
        inputs = [
            InferenceInput(
                ticker="AAPL",
                features=features,
                period_end=date(2024, 12, 31),
                filed_at=datetime(2024, 12, 31, 16, 0, 0),
            )
        ]

        results = await service.infer_one("ssl_transformer_v1", inputs, date(2024, 12, 31))
        assert len(results) == 1
        assert results[0].learner_family == "ssl_transformer_v1"
        assert results[0].learner_role == "champion"
        assert len(results[0].z_vector) == 16
        assert results[0].z_scale is not None

    @pytest.mark.asyncio
    async def test_infer_one_returns_empty_for_unknown_learner(self):
        """infer_one returns empty list for unknown learner family."""
        mock_writer = MagicMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")
        features = torch.randn(60, 20)
        inputs = [
            InferenceInput(
                ticker="AAPL",
                features=features,
                period_end=date(2024, 12, 31),
                filed_at=datetime(2024, 12, 31, 16, 0, 0),
            )
        ]
        results = await service.infer_one("nonexistent_family", inputs, date(2024, 12, 31))
        assert results == []

    @pytest.mark.asyncio
    async def test_infer_one_returns_one_per_input(self):
        """infer_one returns one result per input ticker."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")

        tickers = ["AAPL", "MSFT", "GOOG"]
        inputs = [
            InferenceInput(
                ticker=t,
                features=torch.randn(60, 20),
                period_end=date(2024, 12, 31),
                filed_at=datetime(2024, 12, 31, 16, 0, 0),
            )
            for t in tickers
        ]

        results = await service.infer_one("contrastive_v1", inputs, date(2024, 12, 31))
        assert len(results) == 3
        result_tickers = {r.learner_family for r in results}
        assert len(result_tickers) == 1  # all from contrastive_v1


class TestInferAllPool:
    """Tests for infer_all_pool method."""

    @pytest.mark.asyncio
    async def test_infer_all_pool_returns_results_from_all_members(self):
        """infer_all_pool collects results from every pool member."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")

        inputs = [
            InferenceInput(
                ticker="AAPL",
                features=torch.randn(60, 20),
                period_end=date(2024, 12, 31),
                filed_at=datetime(2024, 12, 31, 16, 0, 0),
            )
        ]

        results = await service.infer_all_pool(inputs, date(2024, 12, 31))
        # 5 pool members × 1 input = 5 results
        assert len(results) == 5

        families = {r.learner_family for r in results}
        assert families == set(POOL_MEMBERS.keys())

    @pytest.mark.asyncio
    async def test_infer_all_pool_writes_to_fabric(self):
        """infer_all_pool calls write_latent_state on the fabric writer."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")

        inputs = [
            InferenceInput(
                ticker="AAPL",
                features=torch.randn(60, 20),
                period_end=date(2024, 12, 31),
                filed_at=datetime(2024, 12, 31, 16, 0, 0),
            )
        ]

        await service.infer_all_pool(inputs, date(2024, 12, 31))
        assert mock_writer.write_latent_state.call_count == 5  # one per pool member

    @pytest.mark.asyncio
    async def test_infer_all_pool_champion_is_flagged(self):
        """Champion is flagged with learner_role='champion'."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")

        inputs = [
            InferenceInput(
                ticker="AAPL",
                features=torch.randn(60, 20),
                period_end=date(2024, 12, 31),
                filed_at=datetime(2024, 12, 31, 16, 0, 0),
            )
        ]

        results = await service.infer_all_pool(inputs, date(2024, 12, 31))
        champion_results = [r for r in results if r.learner_role == "champion"]
        assert len(champion_results) == 1
        assert champion_results[0].learner_family == "ssl_transformer_v1"

    @pytest.mark.asyncio
    async def test_infer_all_pool_shadow_is_flagged(self):
        """Shadow challengers are flagged with learner_role='challenger_shadow'."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")

        inputs = [
            InferenceInput(
                ticker="AAPL",
                features=torch.randn(60, 20),
                period_end=date(2024, 12, 31),
                filed_at=datetime(2024, 12, 31, 16, 0, 0),
            )
        ]

        results = await service.infer_all_pool(inputs, date(2024, 12, 31))
        shadow_results = [r for r in results if r.learner_role == "challenger_shadow"]
        assert len(shadow_results) == 4


class TestPITDiscipline:
    """Tests for PIT discipline at inference time."""

    @pytest.mark.asyncio
    async def test_z_t_record_uses_as_of_date_for_filed_at(self):
        """The PIT key uses as_of_date as the filing date, not today."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")

        as_of = date(2024, 6, 15)
        inputs = [
            InferenceInput(
                ticker="AAPL",
                features=torch.randn(60, 20),
                period_end=date(2024, 6, 14),  # day before as_of
                filed_at=datetime(2024, 6, 14, 16, 0, 0),
            )
        ]

        await service.infer_all_pool(inputs, as_of)
        call_args = mock_writer.write_latent_state.call_args_list
        assert len(call_args) == 5
        # The record's PIT filed_at should use as_of, not the current date
        for call in call_args:
            record = call[0][0]
            assert record.pit.filed_at.year == 2024
            assert record.pit.filed_at.month == 6
            assert record.pit.filed_at.day == 15

    @pytest.mark.asyncio
    async def test_z_t_record_uses_period_end_for_period_end(self):
        """The PIT key period_end is the business date of the state."""
        mock_writer = MagicMock()
        mock_writer.write_latent_state = AsyncMock()
        service = RepresentationInferenceService(fabric_writer=mock_writer, device="cpu")

        inputs = [
            InferenceInput(
                ticker="AAPL",
                features=torch.randn(60, 20),
                period_end=date(2024, 11, 30),
                filed_at=datetime(2024, 11, 30, 16, 0, 0),
            )
        ]

        await service.infer_all_pool(inputs, date(2024, 11, 30))
        call_args = mock_writer.write_latent_state.call_args_list
        for call in call_args:
            record = call[0][0]
            assert record.pit.period_end == date(2024, 11, 30)
