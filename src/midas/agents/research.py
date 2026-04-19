"""Research agent — RAG-based research assistant.

Retrieves relevant documents from the embeddings store and synthesizes
a research summary using the frontier LLM provider.
"""

import json
import math

import structlog

logger = structlog.get_logger("midas.agents.research")


class ResearchAgent:
    """RAG-based research assistant.

    Queries the embeddings store for relevant documents, then uses the LLM
    to synthesize a structured research summary with sources and relevance
    scores.
    """

    RESEARCH_SYSTEM_PROMPT = (
        "You are a financial research assistant. "
        "You MUST respond with valid JSON only, no markdown fences. "
        "The JSON must have keys: "
        '"summary" (string), '
        '"sources" (array of strings), '
        'and "relevance_scores" (array of floats between 0.0 and 1.0).'
    )

    def __init__(self, provider, db):
        self._provider = provider
        self._db = db

    async def research(
        self,
        query: str,
        tickers: list[str] | None = None,
        max_results: int = 10,
    ) -> dict:
        """Research a query against the knowledge base.

        Parameters
        ----------
        query:
            The research question.
        tickers:
            Optional list of ticker symbols to filter by.
        max_results:
            Maximum number of results to return.

        Returns
        -------
        dict
            Keys: 'summary', 'sources', 'relevance_scores'.
        """
        # Retrieve documents from the embeddings store
        documents = await self._retrieve_from_db(query, tickers)

        # Build context from retrieved documents
        context_parts = []
        sources = []
        for doc in documents[:max_results]:
            source_type = doc.get("source_type", "unknown")
            source_id = doc.get("source_id", doc.get("id", ""))
            similarity = doc.get("similarity", 0.0)
            sources.append(f"{source_type}:{source_id}")
            context_parts.append(
                f"[{source_type}:{source_id}] (relevance: {similarity:.2f}) "
                f"{doc.get('content_hash', 'No content available')}"
            )

        context_str = "\n".join(context_parts) if context_parts else "No relevant documents found."

        messages = [
            {"role": "system", "content": self.RESEARCH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Query: {query}\n"
                    f"Tickers: {json.dumps(tickers or [])}\n"
                    f"Retrieved context:\n{context_str}\n"
                    f"Synthesize a research summary in JSON format."
                ),
            },
        ]

        result = await self._provider.complete(
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )

        try:
            parsed = json.loads(result["content"])
        except json.JSONDecodeError:
            logger.warning("research.result.parse_failed", content=result["content"][:200])
            parsed = {
                "summary": result["content"],
                "sources": sources,
                "relevance_scores": [doc.get("similarity", 0.0) for doc in documents],
            }

        logger.info(
            "research.complete",
            query=query[:80],
            sources_count=len(parsed.get("sources", [])),
        )

        return parsed

    async def retrieve_documents(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Retrieve relevant documents from embeddings store.

        Uses cosine similarity between the query embedding and stored
        embeddings to rank and return the most relevant documents.

        Parameters
        ----------
        query_embedding:
            The embedding vector for the query.
        top_k:
            Number of top results to return.

        Returns
        -------
        list[dict]
            Documents with similarity scores.
        """
        try:
            all_rows = await self._db.express.list("embeddings")
        except Exception as exc:
            logger.error("research.retrieve_documents_failed", error=str(exc))
            return []

        scored: list[tuple[float, dict]] = []
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

    async def _retrieve_from_db(self, query: str, tickers: list[str] | None = None) -> list[dict]:
        """Retrieve documents from the fabric tables.

        Searches news, filings, and embeddings tables for relevant content.
        """
        documents = []

        # Search news table
        try:
            news_filter = {}
            if tickers:
                news_filter["ticker"] = tickers[0]
            news_rows = await self._db.express.list("news", filter=news_filter or None)
            for row in news_rows:
                row["source_type"] = "news"
                row["similarity"] = self._keyword_similarity(query, row)
                documents.append(row)
        except Exception as exc:
            logger.warning("research.news_query_failed", error=str(exc))

        # Search filings table
        try:
            filings_filter = {}
            if tickers:
                filings_filter["ticker"] = tickers[0]
            filings_rows = await self._db.express.list("filings", filter=filings_filter or None)
            for row in filings_rows:
                row["source_type"] = "filing"
                row["similarity"] = self._keyword_similarity(query, row)
                documents.append(row)
        except Exception as exc:
            logger.warning("research.filings_query_failed", error=str(exc))

        return documents

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _keyword_similarity(self, query: str, row: dict) -> float:
        """Keyword overlap similarity for text-based rows without embeddings."""
        query_terms = set(query.lower().split())
        text_fields = []
        for key in ("title", "headline", "summary", "body", "content"):
            val = row.get(key, "")
            if val:
                text_fields.append(str(val).lower())
        combined = " ".join(text_fields)
        doc_terms = set(combined.split())
        if not query_terms or not doc_terms:
            return 0.0
        return len(query_terms & doc_terms) / len(query_terms | doc_terms)
