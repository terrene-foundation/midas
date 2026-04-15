"""
Yahoo Finance fallback data adapter.

Secondary adapter providing the same interface as EODHD. Used when EODHD
is unavailable and for cross-check validation. Uses yfinance for data
retrieval.

Cross-check mode compares Yahoo prices against EODHD prices and logs
discrepancies to the audit_log fabric table.

Ref: specs/03-universe-and-data.md §2.1 — Yahoo Finance is fallback + cross-check.
Ref: T-01-03
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import Any

import structlog
import yfinance as yf
from dataflow import DataFlow

from midas.fabric.adapters.base import AdapterError, BaseAdapter

logger = structlog.get_logger("midas.fabric.adapters.yahoo")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Price discrepancy threshold — log to audit if close prices differ by more
# than this percentage.
DEFAULT_DISCREPANCY_THRESHOLD_PCT = 1.0


class YahooFinanceAdapter(BaseAdapter):
    """Fallback adapter using yfinance for OHLCV and cross-check.

    Every method:
    - Returns the same shape as the EODHD adapter
    - Writes rows to the fabric with ``source_vintage`` starting with ``"yahoo"``
    - Never raises to callers on data-source failure (returns empty results)
    """

    SOURCE_NAME = "yahoo"

    def __init__(
        self,
        db: DataFlow | None = None,
        *,
        discrepancy_threshold_pct: float = DEFAULT_DISCREPANCY_THRESHOLD_PCT,
        **kwargs,
    ) -> None:
        super().__init__(db, **kwargs)
        self._discrepancy_threshold_pct = discrepancy_threshold_pct

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Check Yahoo Finance connectivity by downloading a known ticker."""
        try:
            rows = await self.fetch_prices("AAPL", "2024-01-02", "2024-01-03")
            return {
                "source": self.SOURCE_NAME,
                "healthy": True,
                "detail": f"returned {len(rows)} rows for AAPL",
            }
        except Exception as exc:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": str(exc),
            }

    # ------------------------------------------------------------------
    # Internal download helper
    # ------------------------------------------------------------------

    def _download_sync(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> Any:
        """Synchronous yfinance download — called via run_in_executor."""
        return yf.download(
            ticker,
            start=start,
            end=end,
            progress=False,
            auto_adjust=True,
        )

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------

    async def fetch_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch EOD OHLCV for ``ticker`` via Yahoo Finance.

        Writes to the ``prices`` fabric table with source_vintage
        starting with ``"yahoo"``. Returns created rows.

        Parameters
        ----------
        ticker:
            Yahoo-style ticker (e.g. ``"AAPL"``, ``"SPY"``).
        start_date, end_date:
            ISO date strings (``"YYYY-MM-DD"``).
        """
        operation = "fetch_prices"
        self._log.info(
            "fetch_prices.start",
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            df = await self._retry(
                operation,
                lambda: asyncio.get_event_loop().run_in_executor(
                    None,
                    self._download_sync,
                    ticker,
                    start_date,
                    end_date,
                ),
            )
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

        if df is None or df.empty:
            self._log.info("fetch_prices.empty", ticker=ticker)
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        # yfinance returns a DataFrame with DatetimeIndex and columns
        # like Open, High, Low, Close, Volume. When single ticker,
        # columns are flat; multi-ticker returns MultiIndex.
        for row_idx, row_data in df.iterrows():
            # row_idx is a Timestamp
            row_date_str = (
                row_idx.strftime("%Y-%m-%d") if hasattr(row_idx, "strftime") else str(row_idx)
            )

            # Handle both flat and MultiIndex column structures
            def _col_val(data_row, *col_names):
                for name in col_names:
                    if name in data_row:
                        val = data_row[name]
                        return (
                            None
                            if (hasattr(val, "item") and val != val)
                            else (
                                float(val)
                                if hasattr(val, "item")
                                else (None if val != val else float(val))
                            )
                        )
                return None

            open_val = _col_val(row_data, "Open", ("Open", ticker))
            high_val = _col_val(row_data, "High", ("High", ticker))
            low_val = _col_val(row_data, "Low", ("Low", ticker))
            close_val = _col_val(row_data, "Close", ("Close", ticker))
            volume_val = _col_val(row_data, "Volume", ("Volume", ticker))
            volume_int = int(volume_val) if volume_val is not None else None

            row: dict[str, Any] = {
                "instrument": ticker,
                "period_end": row_date_str,
                "filed_at": now.isoformat(),
                "restated_at": None,
                "source_vintage": f"yahoo:{row_date_str}",
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": volume_int,
                "dividend": None,
                "split_ratio": None,
            }

            try:
                await db.express.create("prices", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_prices.row_write_failed",
                    ticker=ticker,
                    date=row_date_str,
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"downloaded {len(df)} rows, wrote {len(created_rows)}",
            instrument=ticker,
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_prices.complete",
            ticker=ticker,
            rows_downloaded=len(df),
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
        """Fetch financial statements and ratios for ``ticker`` via Yahoo.

        Writes to the ``fundamentals`` table. Returns the most recent
        written row (or empty dict on failure).
        """
        operation = "fetch_fundamentals"
        self._log.info("fetch_fundamentals.start", ticker=ticker)

        try:
            info = await self._retry(
                operation,
                lambda: asyncio.get_event_loop().run_in_executor(
                    None,
                    self._fetch_ticker_info_sync,
                    ticker,
                ),
            )
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

        if not info:
            self._log.info("fetch_fundamentals.empty", ticker=ticker)
            return {}

        now = datetime.now(timezone.utc)
        db = self._get_db()

        # yfinance .info returns a flat dict of current-moment metrics
        row: dict[str, Any] = {
            "instrument": ticker,
            "period_end": now.date().isoformat(),
            "filed_at": now.isoformat(),
            "restated_at": None,
            "source_vintage": "yahoo:info",
            "fiscal_period": None,
            "revenue": info.get("totalRevenue"),
            "ebitda": info.get("ebitda"),
            "net_income": info.get("netIncomeToCommon"),
            "book_value": info.get("bookValue"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "de_ratio": None,
            "roe": None,
        }

        # Compute de_ratio from totalDebt / bookValue if available
        total_debt = info.get("totalDebt")
        bv = row["book_value"]
        if total_debt is not None and bv is not None and bv != 0:
            row["de_ratio"] = round(total_debt / bv, 4)

        # Compute ROE from net_income / bookValue
        ni = row["net_income"]
        if ni is not None and bv is not None and bv != 0:
            row["roe"] = round(ni / bv, 4)

        try:
            await db.express.create("fundamentals", row)
        except Exception as exc:
            self._log.warning(
                "fetch_fundamentals.row_write_failed",
                ticker=ticker,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=f"write failed: {exc}",
                instrument=ticker,
            )
            return {}

        await self._write_audit(
            operation=operation,
            success=True,
            detail="wrote 1 fundamental record",
            instrument=ticker,
            rows_written=1,
        )

        self._log.info("fetch_fundamentals.complete", ticker=ticker)
        return row

    @staticmethod
    def _fetch_ticker_info_sync(ticker: str) -> dict[str, Any]:
        """Synchronous yfinance ticker info fetch."""
        t = yf.Ticker(ticker)
        return t.info or {}

    # ------------------------------------------------------------------
    # News (best-effort via yfinance)
    # ------------------------------------------------------------------

    async def fetch_news(
        self,
        ticker: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch news via Yahoo Finance.

        yfinance provides limited news. This is a best-effort
        implementation that returns whatever yfinance provides.
        """
        operation = "fetch_news"
        self._log.info("fetch_news.start", ticker=ticker or "general", limit=limit)

        if not ticker:
            self._log.info("fetch_news.no_ticker_skip", detail="Yahoo requires a ticker")
            return []

        try:
            raw_news = await self._retry(
                operation,
                lambda: asyncio.get_event_loop().run_in_executor(
                    None,
                    self._fetch_ticker_news_sync,
                    ticker,
                ),
            )
        except AdapterError as exc:
            self._log.error(
                "fetch_news.failed",
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

        if not raw_news:
            self._log.info("fetch_news.empty", ticker=ticker)
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for item in raw_news[:limit]:
            headline_id = f"yahoo:{item.get('uuid', uuid.uuid4().hex[:12])}"

            # yfinance news items have 'title', 'publisher', 'link', 'providerPublishTime'
            publish_ts = item.get("providerPublishTime")
            if isinstance(publish_ts, (int, float)):
                published_at = datetime.fromtimestamp(publish_ts, tz=timezone.utc)
            else:
                published_at = now

            related_tickers = item.get("relatedTickers", [])
            if isinstance(related_tickers, str):
                related_tickers = [t.strip() for t in related_tickers.split(",") if t.strip()]

            row: dict[str, Any] = {
                "headline_id": headline_id,
                "period_end": now.date().isoformat(),
                "filed_at": now.isoformat(),
                "headline": item.get("title", ""),
                "published_at": published_at.isoformat(),
                "tickers": tuple(related_tickers),
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
            detail=f"wrote {len(created_rows)} news items",
            instrument=ticker,
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_news.complete",
            ticker=ticker,
            rows_written=len(created_rows),
        )
        return created_rows

    @staticmethod
    def _fetch_ticker_news_sync(ticker: str) -> list[dict[str, Any]]:
        """Synchronous yfinance news fetch."""
        t = yf.Ticker(ticker)
        return t.news or []

    # ------------------------------------------------------------------
    # Corporate Actions
    # ------------------------------------------------------------------

    async def fetch_corporate_actions(
        self,
        ticker: str,
    ) -> list[dict[str, Any]]:
        """Fetch splits and dividends for ``ticker`` via Yahoo Finance.

        Writes to ``corporate_actions`` table. Returns created rows.
        """
        operation = "fetch_corporate_actions"
        self._log.info("fetch_corporate_actions.start", ticker=ticker)

        try:
            actions_df = await self._retry(
                operation,
                lambda: asyncio.get_event_loop().run_in_executor(
                    None,
                    self._fetch_actions_sync,
                    ticker,
                ),
            )
        except AdapterError as exc:
            self._log.error(
                "fetch_corporate_actions.failed",
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

        if actions_df is None or actions_df.empty:
            self._log.info("fetch_corporate_actions.empty", ticker=ticker)
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for row_idx, row_data in actions_df.iterrows():
            row_date_str = (
                row_idx.strftime("%Y-%m-%d") if hasattr(row_idx, "strftime") else str(row_idx)
            )
            try:
                effective = date.fromisoformat(row_date_str)
            except ValueError:
                effective = now.date()

            # yfinance actions DataFrame has 'Dividends' and 'Stock Splits' columns
            div_val = row_data.get("Dividends", 0)
            split_val = row_data.get("Stock Splits", 0)

            # Handle NaN values
            has_div = div_val != 0 and div_val == div_val  # NaN check
            has_split = split_val != 0 and split_val == split_val

            if has_div:
                action_row: dict[str, Any] = {
                    "instrument": ticker,
                    "period_end": row_date_str,
                    "filed_at": now.isoformat(),
                    "restated_at": None,
                    "source_vintage": f"yahoo:dividend:{row_date_str}",
                    "action_type": "DIVIDEND",
                    "effective_date": effective.isoformat(),
                    "ratio_or_amount": float(div_val),
                    "ticker_after": None,
                }
                try:
                    await db.express.create("corporate_actions", action_row)
                    created_rows.append(action_row)
                except Exception as exc:
                    self._log.warning(
                        "fetch_corporate_actions.dividend_write_failed",
                        ticker=ticker,
                        date=row_date_str,
                        error=str(exc),
                    )

            if has_split:
                action_row = {
                    "instrument": ticker,
                    "period_end": row_date_str,
                    "filed_at": now.isoformat(),
                    "restated_at": None,
                    "source_vintage": f"yahoo:split:{row_date_str}",
                    "action_type": "SPLIT",
                    "effective_date": effective.isoformat(),
                    "ratio_or_amount": float(split_val),
                    "ticker_after": None,
                }
                try:
                    await db.express.create("corporate_actions", action_row)
                    created_rows.append(action_row)
                except Exception as exc:
                    self._log.warning(
                        "fetch_corporate_actions.split_write_failed",
                        ticker=ticker,
                        date=row_date_str,
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

    @staticmethod
    def _fetch_actions_sync(ticker: str) -> Any:
        """Synchronous yfinance actions fetch."""
        t = yf.Ticker(ticker)
        return t.actions

    # ------------------------------------------------------------------
    # Cross-check
    # ------------------------------------------------------------------

    async def cross_check_prices(
        self,
        ticker: str,
        date_str: str,
    ) -> dict[str, Any]:
        """Compare Yahoo and EODHD prices for a single date.

        Fetches the close price from both sources and logs any
        discrepancy exceeding the configured threshold to ``audit_log``.

        Returns a dict with both prices and the discrepancy percentage.
        """
        operation = "cross_check_prices"
        self._log.info(
            "cross_check_prices.start",
            ticker=ticker,
            date=date_str,
        )

        yahoo_rows = await self.fetch_prices(ticker, date_str, date_str)
        yahoo_close: float | None = None
        if yahoo_rows:
            yahoo_close = yahoo_rows[0].get("close")

        # For EODHD we need the .US suffix conventionally, but the caller
        # provides whatever ticker format their adapter uses.
        from midas.fabric.adapters.eodhd import EODHDAdapter

        eodhd = EODHDAdapter(db=self._get_db())
        eodhd_ticker = f"{ticker}.US" if "." not in ticker else ticker
        eodhd_rows = await eodhd.fetch_prices(eodhd_ticker, date_str, date_str)
        await eodhd.close()

        eodhd_close: float | None = None
        if eodhd_rows:
            eodhd_close = eodhd_rows[0].get("close")

        result: dict[str, Any] = {
            "ticker": ticker,
            "date": date_str,
            "yahoo_close": yahoo_close,
            "eodhd_close": eodhd_close,
            "discrepancy_pct": None,
            "flagged": False,
        }

        if yahoo_close is not None and eodhd_close is not None and eodhd_close != 0:
            disc_pct = abs(yahoo_close - eodhd_close) / abs(eodhd_close) * 100.0
            result["discrepancy_pct"] = round(disc_pct, 4)
            result["flagged"] = disc_pct > self._discrepancy_threshold_pct

            if result["flagged"]:
                self._log.warning(
                    "cross_check.discrepancy",
                    ticker=ticker,
                    date=date_str,
                    yahoo_close=yahoo_close,
                    eodhd_close=eodhd_close,
                    discrepancy_pct=round(disc_pct, 4),
                    threshold_pct=self._discrepancy_threshold_pct,
                )
                await self._write_audit(
                    operation=operation,
                    success=True,
                    detail=(
                        f"price discrepancy: yahoo={yahoo_close} vs eodhd={eodhd_close} "
                        f"({disc_pct:.2f}% diff, threshold={self._discrepancy_threshold_pct}%)"
                    ),
                    instrument=ticker,
                    extra={
                        "date": date_str,
                        "yahoo_close": yahoo_close,
                        "eodhd_close": eodhd_close,
                        "discrepancy_pct": round(disc_pct, 4),
                    },
                )
            else:
                self._log.info(
                    "cross_check.consistent",
                    ticker=ticker,
                    date=date_str,
                    discrepancy_pct=round(disc_pct, 4),
                )
        else:
            detail_parts = []
            if yahoo_close is None:
                detail_parts.append("yahoo_close=missing")
            if eodhd_close is None:
                detail_parts.append("eodhd_close=missing")
            self._log.info(
                "cross_check.incomplete",
                ticker=ticker,
                date=date_str,
                detail=", ".join(detail_parts),
            )

        return result
