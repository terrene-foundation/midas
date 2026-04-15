"""
Embedding store for the Midas fabric.

Stores and retrieves text embeddings using DataFlow. For v1, cosine
similarity search is computed in-memory from stored vectors (no pgvector
requirement for Tier 1 testing).

Ref: T-01-13
"""

import hashlib
import json
from typing import Any

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.fabric.embeddings")


class EmbeddingStore:
    """DataFlow-backed embedding store with cosine similarity search."""

    def __init__(self, db: DataFlow) -> None:
        self._db = db

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    async def store(
        self,
        source_type: str,
        source_id: str,
        content: str,
        embedding: list[float],
        model_name: str = "",
    ) -> dict[str, Any]:
        """Store a content embedding in the fabric."""
        row = {
            "source_type": source_type,
            "source_id": source_id,
            "content_hash": self._content_hash(content),
            "embedding_blob": json.dumps(embedding),
            "model_name": model_name,
        }
        try:
            result = await self._db.express.create("embeddings", row)
            logger.info("embedding.stored", source_type=source_type, source_id=source_id)
            return result
        except Exception as exc:
            logger.error("embedding.store_failed", source_type=source_type, error=str(exc))
            return {}

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        source_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search embeddings by cosine similarity.

        For v1, loads all embeddings and computes similarity in-memory.
        """
        try:
            filter_dict = {}
            if source_type:
                filter_dict["source_type"] = source_type

            all_rows = await self._db.express.list("embeddings", filter=filter_dict or None)
        except Exception as exc:
            logger.error("embedding.search_failed", error=str(exc))
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in all_rows:
            blob = row.get("embedding_blob", "")
            if not blob:
                continue
            try:
                stored_vec = json.loads(blob)
            except (json.JSONDecodeError, TypeError):
                continue

            similarity = self._cosine_similarity(query_embedding, stored_vec)
            scored.append((similarity, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"similarity": s, **row} for s, row in scored[:top_k]]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
