"""
Perplexity API adapter for research queries and debate-agent context.

On-demand adapter that writes results to the ``news`` and ``embeddings``
fabric tables. Follows the same contract as EODHD: never returns raw API
responses, auth failures return empty results with audit entry.

Ref: specs/07-evidence-first-decision.md §3.3
Ref: T-01-07
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from dataflow import DataFlow

from midas.config import PERPLEXITY_API_KEY
from midas.fabric.adapters.base import (
    AdapterError,
    AuthenticationError,
    BaseAdapter,
    RateLimitExceeded,
)

logger = structlog.get_logger("midas.fabric.adapters.perplexity")

PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
HTTP_TIMEOUT_S = 30.0


class PerplexityAdapter(BaseAdapter):
    """Adapter for Perplexity AI research queries."""

    SOURCE_NAME = "perplexity"

    def __init__(
        self,
        db: DataFlow | None = None,
        *,
        api_key: str | None = None,
        base_url: str = PERPLEXITY_BASE_URL,
        http_timeout_s: float = HTTP_TIMEOUT_S,
        **kwargs,
    ) -> None:
        super().__init__(db, **kwargs)
        self._api_key = api_key or PERPLEXITY_API_KEY
        self._base_url = base_url.rstrip("/")
        self._http_timeout_s = http_timeout_s
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._http_timeout_s),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> dict[str, Any]:
        if not self._api_key:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": "PERPLEXITY_API_KEY not configured",
            }
        try:
            result = await self.research("test connectivity")
            return {
                "source": self.SOURCE_NAME,
                "healthy": True,
                "detail": f"returned {len(result)} results",
            }
        except Exception as exc:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": str(exc),
            }

    async def _request(self, payload: dict[str, Any], operation: str) -> Any:
        if not self._api_key:
            raise AuthenticationError(self.SOURCE_NAME, operation)

        headers = {"Authorization": f"Bearer {self._api_key}"}

        async def _do_request() -> Any:
            client = self._get_client()
            response = await client.post("/chat/completions", json=payload, headers=headers)

            if response.status_code in (401, 403):
                raise AuthenticationError(
                    self.SOURCE_NAME, operation, status_code=response.status_code
                )
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_after_s = float(retry_after) if retry_after else 60.0
                self._handle_rate_limit_headers(dict(response.headers))
                raise RateLimitExceeded(self.SOURCE_NAME, operation, retry_after_s)
            if response.status_code >= 500:
                raise AdapterError(
                    self.SOURCE_NAME, operation, f"server error: HTTP {response.status_code}"
                )
            if response.status_code >= 400:
                raise AdapterError(
                    self.SOURCE_NAME,
                    operation,
                    f"client error: HTTP {response.status_code}: {response.text[:200]}",
                )
            return response.json()

        return await self._retry(operation, _do_request)

    async def research(
        self,
        query: str,
        tickers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a research query and write results to fabric."""
        operation = "research"
        self._log.info("research.start", query=query[:100], tickers=tickers)

        context = ""
        if tickers:
            context = f"Focus on these tickers: {', '.join(tickers)}. "

        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a financial research assistant. Provide concise, factual answers with specific data points.",
                },
                {
                    "role": "user",
                    "content": f"{context}{query}",
                },
            ],
            "max_tokens": 1024,
        }

        try:
            data = await self._request(payload, operation)
        except AuthenticationError as exc:
            self._log.error("research.auth_failed", error=str(exc))
            await self._write_audit(
                operation=operation, success=False, detail=f"auth failed: {exc}"
            )
            return []
        except AdapterError as exc:
            self._log.error("research.failed", error=str(exc))
            await self._write_audit(operation=operation, success=False, detail=str(exc))
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        content = ""
        citations: list[str] = []
        if isinstance(data, dict):
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
            citations = data.get("citations", [])

        if not content:
            self._log.info("research.empty", query=query[:50])
            return []

        headline_id = f"perplexity:{uuid.uuid4().hex[:12]}"
        row: dict[str, Any] = {
            "ticker": ",".join(tickers) if tickers else "",
            "headline": query[:200],
            "summary": content[:2000],
            "source": "perplexity",
            "published_at": now.isoformat(),
            "url": citations[0] if citations else "",
            "embedding_id": "",
            "portfolio_impact": "",
            "sentiment_score": None,
        }

        try:
            await db.express.create("news", row)
            created_rows.append(row)
        except Exception as exc:
            self._log.warning("research.row_write_failed", headline_id=headline_id, error=str(exc))

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"research completed, wrote {len(created_rows)} rows",
            rows_written=len(created_rows),
        )

        self._log.info("research.complete", rows_written=len(created_rows))
        return created_rows
