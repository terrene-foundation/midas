"""
SEC EDGAR adapter for filing ingestion.

Ingests 10-K, 10-Q, 8-K filings with filed_at and document IDs,
writing to the ``filings`` fabric table. Uses the SEC full-text search API.

Ref: T-01-08
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from dataflow import DataFlow

from midas.fabric.adapters.base import (
    AdapterError,
    BaseAdapter,
    RateLimitExceeded,
)

logger = structlog.get_logger("midas.fabric.adapters.sec_edgar")

EDGAR_BASE_URL = "https://efts.sec.gov"
EDGAR_DATA_URL = "https://data.sec.gov"
HTTP_TIMEOUT_S = 30.0
USER_AGENT = "Midas Investment Assistant contact@midas.app"


class SECEdgarAdapter(BaseAdapter):
    """Adapter for SEC EDGAR filing ingestion."""

    SOURCE_NAME = "sec_edgar"

    def __init__(
        self,
        db: DataFlow | None = None,
        *,
        base_url: str = EDGAR_BASE_URL,
        http_timeout_s: float = HTTP_TIMEOUT_S,
        **kwargs,
    ) -> None:
        super().__init__(db, **kwargs)
        self._base_url = base_url.rstrip("/")
        self._http_timeout_s = http_timeout_s
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._http_timeout_s),
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> dict[str, Any]:
        try:
            results = await self.fetch_filings("AAPL", "10-K", "2024-01-01", "2024-12-31")
            return {
                "source": self.SOURCE_NAME,
                "healthy": True,
                "detail": f"returned {len(results)} filings for AAPL",
            }
        except Exception as exc:
            return {"source": self.SOURCE_NAME, "healthy": False, "detail": str(exc)}

    async def _request(self, path: str, params: dict[str, Any], operation: str) -> Any:
        async def _do_request() -> Any:
            client = self._get_client()
            response = await client.get(path, params=params)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_after_s = float(retry_after) if retry_after else 10.0
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

    async def fetch_filings(
        self,
        ticker: str,
        filing_type: str = "10-K",
        start_date: str = "2020-01-01",
        end_date: str = "2024-12-31",
    ) -> list[dict[str, Any]]:
        """Fetch SEC filings and write to the filings fabric table."""
        operation = "fetch_filings"
        self._log.info("fetch_filings.start", ticker=ticker, filing_type=filing_type)

        try:
            data = await self._request(
                "/LATEST/search-index",
                {
                    "q": f"{ticker} {filing_type}",
                    "dateRange": "custom",
                    "startdt": start_date,
                    "enddt": end_date,
                    "forms": filing_type,
                    "from": 0,
                    "size": 20,
                },
                operation,
            )
        except AdapterError as exc:
            self._log.error("fetch_filings.failed", ticker=ticker, error=str(exc))
            await self._write_audit(
                operation=operation, success=False, detail=str(exc), instrument=ticker
            )
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        hits = data.get("hits", {}).get("hits", []) if isinstance(data, dict) else []
        for hit in hits:
            source = hit.get("_source", {})
            filing_id = source.get("file_num", source.get("id", uuid.uuid4().hex[:12]))
            filed_at = source.get("file_date", source.get("filing_date", ""))
            title = (
                source.get("display_names", [ticker])[0] if source.get("display_names") else ticker
            )
            doc_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type={filing_type}"

            row: dict[str, Any] = {
                "ticker": ticker,
                "filing_type": filing_type,
                "filed_at": filed_at or now.isoformat(),
                "document_url": doc_url,
                "title": str(title)[:500],
                "embedding_id": "",
                "source": "sec_edgar",
            }

            try:
                await db.express.create("filings", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning("fetch_filings.row_write_failed", ticker=ticker, error=str(exc))

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(hits)} filings, wrote {len(created_rows)}",
            instrument=ticker,
            rows_written=len(created_rows),
        )

        self._log.info("fetch_filings.complete", ticker=ticker, rows_written=len(created_rows))
        return created_rows
