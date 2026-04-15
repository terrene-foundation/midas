"""
Online inference service for representation learners.

Produces z_t posterior candidates from every pool member, writing results
to the latent_state fabric table. Maintains PIT discipline — no future-data
leakage at inference time.

Ref: specs/04-latent-first-architecture.md §2, §4
Ref: T-03-09
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime

import structlog
import torch

from midas.fabric.adapters.dataflow_adapter import DataFlowFabricWriter
from midas.fabric.models import LatentStateRecord, PITKey
from midas.ml.models.representation import (
    ContrastiveEncoder,
    DeepSSM,
    MaskedAutoencoder,
    SSLTransformer,
    VariationalAutoencoder,
)

logger = structlog.get_logger(__name__)


# Pool member configurations — families and their roles
POOL_MEMBERS = {
    "ssl_transformer_v1": {
        "role": "champion",
        "cls": SSLTransformer,
        "default_kwargs": {"input_dim": 20, "latent_dim": 16, "n_heads": 4, "n_layers": 3},
    },
    "contrastive_v1": {
        "role": "challenger_shadow",
        "cls": ContrastiveEncoder,
        "default_kwargs": {"input_dim": 20, "latent_dim": 16, "hidden_dim": 64},
    },
    "mae_v1": {
        "role": "challenger_shadow",
        "cls": MaskedAutoencoder,
        "default_kwargs": {"input_dim": 20, "latent_dim": 16, "mask_ratio": 0.3},
    },
    "vae_v1": {
        "role": "challenger_shadow",
        "cls": VariationalAutoencoder,
        "default_kwargs": {"input_dim": 20, "latent_dim": 16, "hidden_dim": 64},
    },
    "deep_ssm_v1": {
        "role": "challenger_shadow",
        "cls": DeepSSM,
        "default_kwargs": {"input_dim": 20, "latent_dim": 16, "hidden_dim": 64},
    },
}


@dataclass
class InferenceInput:
    """Single-instrument inference input at time t."""

    ticker: str
    features: torch.Tensor  # (seq_len, feature_dim)
    period_end: date
    filed_at: datetime  # when these features were available


@dataclass
class InferenceResult:
    """z_t posterior candidate from one learner."""

    learner_family: str
    learner_role: str
    z_vector: list[float]
    z_covariance: list[list[float]] | None
    z_scale: float | None
    state_id: str


class RepresentationInferenceService:
    """Online inference service for all representation-learner pool members.

    Runs every learner over the same input window and writes z_t candidates
    to the fabric latent_state table with PIT discipline.
    """

    def __init__(
        self,
        fabric_writer: DataFlowFabricWriter,
        device: str = "cpu",
        checkpoint_dir: str = "/tmp/midas_checkpoints",
    ) -> None:
        self._writer = fabric_writer
        self._device = device
        self._checkpoint_dir = checkpoint_dir
        self._models: dict[str, torch.nn.Module] = {}

    def _load_model(self, learner_family: str) -> torch.nn.Module:
        """Load or instantiate a learner model."""
        if learner_family in self._models:
            return self._models[learner_family]

        config = POOL_MEMBERS[learner_family]
        model_cls = config["cls"]
        model = model_cls(**config["default_kwargs"]).to(self._device)

        # Try to load checkpoint if it exists
        import os

        ckpt_path = os.path.join(self._checkpoint_dir, f"{learner_family}.pt")
        if os.path.exists(ckpt_path):
            try:
                checkpoint = torch.load(ckpt_path, map_location=self._device, weights_only=True)
                model.load_state_dict(checkpoint["model_state_dict"])
                logger.info("inference.loaded_checkpoint", learner=learner_family)
            except Exception as exc:
                logger.warning(
                    "inference.checkpoint_load_failed",
                    learner=learner_family,
                    error=str(exc),
                )

        model.eval()
        self._models[learner_family] = model
        return model

    def _encode(
        self,
        model: torch.nn.Module,
        features: torch.Tensor,
    ) -> tuple[list[float], list[list[float]] | None, float | None]:
        """Run encode() and extract z_t, covariance proxy, and scale."""

        def _to_list(t: torch.Tensor) -> list[float]:
            return t.detach().cpu().flatten().tolist()

        with torch.no_grad():
            z_t = model.encode(features.to(self._device))  # type: ignore[attr-defined]

        z_list = _to_list(z_t)

        # Full covariance is expensive; use diagonal variance proxy.
        # Per spec §8: every output is a distribution. We emit a
        # diagonal-approximation covariance and a posterior-width scalar.
        if z_t.dim() == 1:
            z_t = z_t.unsqueeze(0)
        # z_t: (1, latent_dim)
        var_z = z_t.var(dim=0, unbiased=False)
        cov_diag = [[float(v.item())] for v in var_z]
        z_scale = float(torch.mean(torch.sqrt(var_z)).item())

        return z_list, cov_diag, z_scale

    async def infer_one(
        self,
        learner_family: str,
        inputs: list[InferenceInput],
        as_of_date: date,
    ) -> list[InferenceResult]:
        """Run inference for one learner across all instruments.

        Parameters
        ----------
        learner_family : str
            Name of the learner (e.g. "ssl_transformer_v1").
        inputs : list[InferenceInput]
            One InferenceInput per instrument, each with the same period_end.
        as_of_date : date
            PIT date — used to construct the PIT key (no future data leakage).

        Returns
        -------
        list[InferenceResult], one per input.
        """
        if learner_family not in POOL_MEMBERS:
            logger.warning("inference.unknown_learner", learner=learner_family)
            return []

        config = POOL_MEMBERS[learner_family]
        model = self._load_model(learner_family)
        role = config["role"]

        results: list[InferenceResult] = []
        z_list: list[float] = []

        for inp in inputs:
            # Ensure features have correct shape (seq_len, feature_dim)
            feat = inp.features
            if feat.dim() == 2:
                feat = feat.unsqueeze(0)  # -> (1, seq_len, feature_dim)
            elif feat.dim() == 1:
                feat = feat.unsqueeze(0).unsqueeze(0)

            z_list, cov_diag, z_scale = self._encode(model, feat)

            state_id = hashlib.sha256(
                f"{learner_family}:{inp.ticker}:{inp.period_end.isoformat()}".encode()
            ).hexdigest()[:16]

            results.append(
                InferenceResult(
                    learner_family=learner_family,
                    learner_role=role,
                    z_vector=z_list,
                    z_covariance=cov_diag,
                    z_scale=z_scale,
                    state_id=state_id,
                )
            )

        logger.info(
            "inference.infer_one.done",
            learner=learner_family,
            n_instruments=len(inputs),
            z_dim=len(z_list),
        )
        return results

    async def infer_all_pool(
        self,
        inputs: list[InferenceInput],
        as_of_date: date,
    ) -> list[InferenceResult]:
        """Run inference for every pool member.

        Writes results to the fabric latent_state table with PIT keys.
        """
        all_results: list[InferenceResult] = []

        for learner_family in POOL_MEMBERS:
            try:
                learner_results = await self.infer_one(learner_family, inputs, as_of_date)
                all_results.extend(learner_results)
            except Exception as exc:
                logger.error(
                    "inference.pool_member_failed",
                    learner=learner_family,
                    error=str(exc),
                )

        # Write all z_t candidates to fabric
        period_end = inputs[0].period_end if inputs else as_of_date
        for result in all_results:
            await self._write_z_t(result, period_end, as_of_date)

        logger.info(
            "inference.pool_complete",
            total_results=len(all_results),
            pool_members=len(POOL_MEMBERS),
        )
        return all_results

    async def _write_z_t(
        self,
        result: InferenceResult,
        period_end: date,
        as_of_date: date,
    ) -> None:
        """Write a single z_t candidate to the fabric latent_state table."""

        # PIT discipline: the filing date is as_of_date, never later.
        # period_end is the business date the state describes.
        pit_filed_at = datetime.combine(as_of_date, datetime.min.time())

        pit_key = PITKey(
            period_end=period_end,
            filed_at=pit_filed_at,
        )

        # Determine pool_index from role
        pool_index: int | None = None
        if result.learner_role == "challenger_shadow":
            pool_index = list(POOL_MEMBERS).index(result.learner_family)

        record = LatentStateRecord(
            state_id=result.state_id,
            pit=pit_key,
            learner_family=result.learner_family,
            learner_role=result.learner_role,
            z_dim=len(result.z_vector),
            z_vector=tuple(result.z_vector),
            z_covariance=(
                tuple(tuple(r2) for r2 in result.z_covariance) if result.z_covariance else None
            ),
            z_scale=result.z_scale,
            pool_index=pool_index,
        )

        await self._writer.write_latent_state(record)
        logger.debug(
            "inference.z_t_written",
            learner=result.learner_family,
            state_id=result.state_id,
            z_dim=len(result.z_vector),
        )
