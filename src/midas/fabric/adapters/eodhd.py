"""
EODHD data source adapter.

Primary adapter for EOD OHLCV prices, fundamentals, news, and corporate
actions. Uses httpx.AsyncClient for HTTP calls, writes every result to the
fabric via DataFlow express, and never returns raw API responses to callers.

Authentication failures return empty results (with an audit entry) rather than
raising exceptions to the caller.

Ref: specs/03-universe-and-data.md §2.1 — EODHD is the primary price source.
Ref: T-01-02
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

import httpx
import structlog
from dataflow import DataFlow

from midas.config import EODHD_API_KEY
from midas.fabric.adapters.base import (
    AdapterError,
    AuthenticationError,
    BaseAdapter,
    RateLimitExceeded,
)

logger = structlog.get_logger("midas.fabric.adapters.eodhd")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EODHD_BASE_URL = "https://eodhd.com/api"
DEFAULT_PAGE_SIZE = 100
HTTP_TIMEOUT_S = 30.0
MAX_NEWS_LIMIT = 1000


class EODHDAdapter(BaseAdapter):
    """Adapter for the EODHD All-in-One API.

    Every method:
    - Handles pagination internally
    - Writes rows to the fabric via DataFlow express
    - Returns the created fabric rows (never raw API responses)
    - Logs failures to ``audit_log`` rather than raising to callers
    """

    SOURCE_NAME = "eodhd"

    def __init__(
        self,
        db: DataFlow | None = None,
        *,
        api_key: str | None = None,
        base_url: str = EODHD_BASE_URL,
        http_timeout_s: float = HTTP_TIMEOUT_S,
        **kwargs,
    ) -> None:
        super().__init__(db, **kwargs)
        self._api_key = api_key or EODHD_API_KEY
        self._base_url = base_url.rstrip("/")
        self._http_timeout_s = http_timeout_s
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Return (or lazily create) the httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._http_timeout_s),
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Check EODHD connectivity by fetching a known ticker."""
        if not self._api_key:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": "EODHD_API_KEY not configured",
            }

        try:
            rows = await self.fetch_prices("AAPL.US", "2024-01-02", "2024-01-03")
            return {
                "source": self.SOURCE_NAME,
                "healthy": True,
                "detail": f"returned {len(rows)} rows for AAPL.US",
            }
        except Exception as exc:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": str(exc),
            }

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(
        self,
        path: str,
        params: dict[str, Any],
        operation: str,
    ) -> Any:
        """Make an authenticated GET to EODHD, handling common error codes.

        Returns parsed JSON on success. Raises typed errors on auth or
        rate-limit failures.
        """
        if not self._api_key:
            raise AuthenticationError(self.SOURCE_NAME, operation)

        params_with_key = {**params, "api_token": self._api_key, "fmt": "json"}

        async def _do_request() -> Any:
            client = self._get_client()
            response = await client.get(path, params=params_with_key)

            if response.status_code == 401 or response.status_code == 403:
                raise AuthenticationError(
                    self.SOURCE_NAME, operation, status_code=response.status_code
                )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_after_s = float(retry_after) if retry_after else None
                self._handle_rate_limit_headers(dict(response.headers))
                raise RateLimitExceeded(self.SOURCE_NAME, operation, retry_after_s)

            if response.status_code >= 500:
                raise AdapterError(
                    self.SOURCE_NAME,
                    operation,
                    f"server error: HTTP {response.status_code}",
                )

            if response.status_code >= 400:
                raise AdapterError(
                    self.SOURCE_NAME,
                    operation,
                    f"client error: HTTP {response.status_code}: {response.text[:200]}",
                )

            return response.json()

        return await self._retry(operation, _do_request)

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------

    async def fetch_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch EOD OHLCV for ``ticker``, write to ``prices`` table.

        Parameters
        ----------
        ticker:
            EODHD-style ticker (e.g. ``"AAPL.US"``, ``"SPY.US"``).
        start_date, end_date:
            ISO date strings (``"YYYY-MM-DD"``).

        Returns
        -------
        List of fabric rows created in the ``prices`` table.
        Empty list on authentication failure (error logged to audit).
        """
        operation = "fetch_prices"
        self._log.info(
            "fetch_prices.start",
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            raw_items = await self._request(
                f"/eod/{ticker}",
                {
                    "from": start_date,
                    "to": end_date,
                    "period": "d",
                },
                operation,
            )
        except AuthenticationError as exc:
            self._log.error(
                "fetch_prices.auth_failed",
                ticker=ticker,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=f"auth failed for {ticker}: {exc}",
                instrument=ticker,
            )
            return []
        except AdapterError as exc:
            self._log.error(
                "fetch_prices.failed",
                ticker=ticker,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
                instrument=ticker,
            )
            return []

        if not raw_items or not isinstance(raw_items, list):
            self._log.info("fetch_prices.empty", ticker=ticker)
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for item in raw_items:
            row_date = item.get("date", "")
            row: dict[str, Any] = {
                "instrument": ticker,
                "period_end": row_date,
                "filed_at": now.isoformat(),
                "restated_at": None,
                "source_vintage": f"eodhd:{row_date}",
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": item.get("close"),
                "volume": item.get("volume"),
                "dividend": item.get("dividend", 0.0),
                "split_ratio": None,
            }
            # EODHD returns split_factor in extended endpoints
            if item.get("split_factor") and item["split_factor"] != 1.0:
                row["split_ratio"] = item["split_factor"]

            try:
                await db.express.create("prices", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_prices.row_write_failed",
                    ticker=ticker,
                    date=row_date,
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(raw_items)} rows, wrote {len(created_rows)}",
            instrument=ticker,
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_prices.complete",
            ticker=ticker,
            rows_requested=len(raw_items),
            rows_written=len(created_rows),
        )
        return created_rows

    # ------------------------------------------------------------------
    # Fundamentals
    # ------------------------------------------------------------------

    async def fetch_fundamentals(
        self,
        ticker: str,
    ) -> dict[str, Any]:
        """Fetch financial statements and ratios for ``ticker``.

        Writes to the ``fundamentals`` table. Returns the written row
        (or an empty dict on failure).
        """
        operation = "fetch_fundamentals"
        self._log.info("fetch_fundamentals.start", ticker=ticker)

        try:
            raw = await self._request(
                f"/fundamentals/{ticker}",
                {},
                operation,
            )
        except AuthenticationError as exc:
            self._log.error(
                "fetch_fundamentals.auth_failed",
                ticker=ticker,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=f"auth failed for {ticker}: {exc}",
                instrument=ticker,
            )
            return {}
        except AdapterError as exc:
            self._log.error(
                "fetch_fundamentals.failed",
                ticker=ticker,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
                instrument=ticker,
            )
            return {}

        if not raw or not isinstance(raw, dict):
            self._log.info("fetch_fundamentals.empty", ticker=ticker)
            return {}

        now = datetime.now(timezone.utc)
        db = self._get_db()
        written: dict[str, Any] = {}

        # EODHD fundamentals returns a nested structure with General,
        # Financials (income_statement, balance_sheet, cash_flow), and
        # Highlights/Valuation. We extract the most recent annual period.
        general = raw.get("General", {})
        highlights = raw.get("Highlights", {})
        raw.get("Valuation", {})  # available for future use
        financials = raw.get("Financials", {})
        income_annual = financials.get("Income_Statement", {}).get("annual", {})
        balance_annual = financials.get("Balance_Sheet", {}).get("annual", {})
        financials.get("Cash_Flow", {}).get("annual", {})  # available for future use

        # Process each annual period found
        rows_written = 0
        for period_key in income_annual:
            inc = income_annual.get(period_key, {})
            bal = balance_annual.get(period_key, {})
            # Determine the period_end date from the key or from the data
            period_date = period_key if len(period_key) == 10 else None
            if period_date is None:
                date_value = inc.get("date")
                period_date = date_value if isinstance(date_value, str) else period_key

            fiscal_period_label = f"FY {period_key[:4]}" if len(period_key) >= 4 else period_key

            row: dict[str, Any] = {
                "instrument": ticker,
                "period_end": period_date,
                "filed_at": now.isoformat(),
                "restated_at": None,
                "source_vintage": f"eodhd:fundamentals:{period_key}",
                "fiscal_period": fiscal_period_label,
                "revenue": inc.get("totalRevenue"),
                "ebitda": inc.get("ebitda"),
                "net_income": inc.get("netIncome"),
                "book_value": bal.get("totalStockholderEquity"),
                "shares_outstanding": general.get("SharesOutstanding"),
                "pe_ratio": highlights.get("PERatio"),
                "pb_ratio": highlights.get("PriceToBookRatio"),
                "de_ratio": highlights.get("DebtToEquity"),
                "roe": None,
            }

            # Compute ROE if both net_income and equity are available
            ni = row["net_income"]
            bv = row["book_value"]
            if ni is not None and bv is not None and bv != 0:
                row["roe"] = round(ni / bv, 4)

            try:
                await db.express.create("fundamentals", row)
                rows_written += 1
                if not written:
                    written = row
            except Exception as exc:
                self._log.warning(
                    "fetch_fundamentals.row_write_failed",
                    ticker=ticker,
                    period=period_key,
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"wrote {rows_written} fundamental records",
            instrument=ticker,
            rows_written=rows_written,
        )

        self._log.info(
            "fetch_fundamentals.complete",
            ticker=ticker,
            rows_written=rows_written,
        )
        return written

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    async def fetch_news(
        self,
        ticker: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch news headlines tagged to ``ticker``.

        Writes to the ``news`` fabric table. Returns created rows.
        When ``ticker`` is empty, fetches general financial news.
        """
        operation = "fetch_news"
        limit = min(limit, MAX_NEWS_LIMIT)
        self._log.info("fetch_news.start", ticker=ticker or "general", limit=limit)

        all_items: list[dict[str, Any]] = []
        offset = 0
        page_size = min(DEFAULT_PAGE_SIZE, limit)

        while len(all_items) < limit:
            params: dict[str, Any] = {
                "offset": offset,
                "limit": page_size,
            }
            if ticker:
                params["s"] = ticker

            try:
                page = await self._request("/news", params, operation)
            except AuthenticationError as exc:
                self._log.error(
                    "fetch_news.auth_failed",
                    ticker=ticker,
                    error=str(exc),
                )
                await self._write_audit(
                    operation=operation,
                    success=False,
                    detail=f"auth failed: {exc}",
                    instrument=ticker or "general",
                )
                return []
            except AdapterError as exc:
                self._log.error(
                    "fetch_news.page_failed",
                    ticker=ticker,
                    offset=offset,
                    error=str(exc),
                )
                break

            if not page or not isinstance(page, list):
                break

            all_items.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

            # Respect remaining count
            remaining = limit - len(all_items)
            if remaining <= 0:
                break
            page_size = min(DEFAULT_PAGE_SIZE, remaining)

        if not all_items:
            self._log.info("fetch_news.empty", ticker=ticker or "general")
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for item in all_items:
            published_str = item.get("date", "")
            try:
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                published_at = now

            headline_id = f"eodhd:{item.get('id', uuid.uuid4().hex[:12])}"

            tickers_from_item = item.get("symbols", item.get("tickers", ""))
            if isinstance(tickers_from_item, str):
                ticker_tuple = tuple(t.strip() for t in tickers_from_item.split(",") if t.strip())
            elif isinstance(tickers_from_item, list):
                ticker_tuple = tuple(tickers_from_item)
            else:
                ticker_tuple = ()

            row: dict[str, Any] = {
                "headline_id": headline_id,
                "period_end": now.date().isoformat(),
                "filed_at": now.isoformat(),
                "headline": item.get("title", ""),
                "published_at": published_at.isoformat(),
                "tickers": ticker_tuple,
                "embedding_ids": (),
                "sentiment_score": None,
                "impact_tag": None,
            }

            try:
                await db.express.create("news", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_news.row_write_failed",
                    headline_id=headline_id,
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(all_items)} items, wrote {len(created_rows)}",
            instrument=ticker or "general",
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_news.complete",
            ticker=ticker or "general",
            rows_written=len(created_rows),
        )
        return created_rows

    # ------------------------------------------------------------------
    # Corporate Actions
    # ------------------------------------------------------------------

    async def fetch_corporate_actions(
        self,
        ticker: str,
    ) -> list[dict[str, Any]]:
        """Fetch splits and dividends for ``ticker``.

        Writes to the ``corporate_actions`` fabric table. Returns created rows.
        """
        operation = "fetch_corporate_actions"
        self._log.info("fetch_corporate_actions.start", ticker=ticker)

        # Fetch dividends
        try:
            dividends = await self._request(
                f"/div/{ticker}",
                {},
                f"{operation}:dividends",
            )
        except AuthenticationError as exc:
            self._log.error(
                "fetch_corporate_actions.auth_failed",
                ticker=ticker,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=f"auth failed: {exc}",
                instrument=ticker,
            )
            return []
        except AdapterError as exc:
            self._log.warning(
                "fetch_corporate_actions.dividends_failed",
                ticker=ticker,
                error=str(exc),
            )
            dividends = []

        # Fetch splits
        try:
            splits = await self._request(
                f"/splits/{ticker}",
                {},
                f"{operation}:splits",
            )
        except AuthenticationError as exc:
            self._log.error(
                "fetch_corporate_actions.auth_failed_splits",
                ticker=ticker,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=f"auth failed on splits: {exc}",
                instrument=ticker,
            )
            return []
        except AdapterError as exc:
            self._log.warning(
                "fetch_corporate_actions.splits_failed",
                ticker=ticker,
                error=str(exc),
            )
            splits = []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        # Process dividends
        if isinstance(dividends, list):
            for div in dividends:
                action_date = div.get("date", div.get("exDate", ""))
                try:
                    effective = date.fromisoformat(action_date)
                except (ValueError, TypeError):
                    effective = now.date()

                row: dict[str, Any] = {
                    "instrument": ticker,
                    "period_end": action_date,
                    "filed_at": now.isoformat(),
                    "restated_at": None,
                    "source_vintage": f"eodhd:dividend:{action_date}",
                    "action_type": "DIVIDEND",
                    "effective_date": effective.isoformat(),
                    "ratio_or_amount": div.get("value", div.get("amount")),
                    "ticker_after": None,
                }

                try:
                    await db.express.create("corporate_actions", row)
                    created_rows.append(row)
                except Exception as exc:
                    self._log.warning(
                        "fetch_corporate_actions.dividend_write_failed",
                        ticker=ticker,
                        date=action_date,
                        error=str(exc),
                    )

        # Process splits
        if isinstance(splits, list):
            for split in splits:
                action_date = split.get("date", split.get("effectiveDate", ""))
                try:
                    effective = date.fromisoformat(action_date)
                except (ValueError, TypeError):
                    effective = now.date()

                split_ratio_str = str(split.get("splitRatio", split.get("ratio", "")))
                ratio_value: float | None = None
                try:
                    # "2:1" or "2/1" format -> 2.0
                    if ":" in split_ratio_str:
                        parts = split_ratio_str.split(":")
                        ratio_value = float(parts[0]) / float(parts[1])
                    elif "/" in split_ratio_str:
                        parts = split_ratio_str.split("/")
                        ratio_value = float(parts[0]) / float(parts[1])
                    else:
                        ratio_value = float(split_ratio_str)
                except (ValueError, IndexError, ZeroDivisionError):
                    ratio_value = None

                row: dict[str, Any] = {
                    "instrument": ticker,
                    "period_end": action_date,
                    "filed_at": now.isoformat(),
                    "restated_at": None,
                    "source_vintage": f"eodhd:split:{action_date}",
                    "action_type": "SPLIT",
                    "effective_date": effective.isoformat(),
                    "ratio_or_amount": ratio_value,
                    "ticker_after": None,
                }

                try:
                    await db.express.create("corporate_actions", row)
                    created_rows.append(row)
                except Exception as exc:
                    self._log.warning(
                        "fetch_corporate_actions.split_write_failed",
                        ticker=ticker,
                        date=action_date,
                        error=str(exc),
                    )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"wrote {len(created_rows)} corporate actions",
            instrument=ticker,
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_corporate_actions.complete",
            ticker=ticker,
            rows_written=len(created_rows),
        )
        return created_rows
