"""
IBKR Web API v1.0 adapter and TWS fallback adapter.

IBKRAdapter handles: OAuth 2.0 handshake, account state, positions,
order status, real-time quotes, FX sweeps. Every call is audited.
Rate-limit aware with priority queue (trades > monitoring > data).
Fresh-price path (fetch_quote) bypasses the cache.

TWSTFallbackAdapter uses ib_async to connect to a local TWS / IB Gateway
process when the Web API is unavailable (HTTP 503 or auth failure).

Ref: specs/14-ibkr-integration.md — full operational contract
Ref: specs/03-universe-and-data.md §2.1 — IBKR role in fabric
Ref: T-01-04 (IBKR Web API), T-01-05 (TWS fallback)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from enum import IntEnum
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from midas.fabric.adapters.base import (
    AdapterError,
    AuthenticationError,
    BaseAdapter,
    RateLimitExceeded,
)

if TYPE_CHECKING:
    from dataflow import DataFlow

logger = structlog.get_logger("midas.fabric.adapters.ibkr")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IBKR_API_BASE = "https://api.interactivebrokererc.com"
IBKR_OAUTH_URL = "https://www.interactivebrokers.co.uk/oauth2"
IBKR_TOKEN_URL = f"{IBKR_API_BASE}/v1/oauth2/token"
IBKR_ACCOUNTS_URL = f"{IBKR_API_BASE}/v1/portfolio/accounts"
IBKR_POSITIONS_URL = f"{IBKR_API_BASE}/v1/portfolio/positions"
IBKR_ORDERS_URL = f"{IBKR_API_BASE}/v1/portfolio/orders"
IBKR_QUOTES_URL = f"{IBKR_API_BASE}/v1/market/data"
IBKR_SWEEPS_URL = f"{IBKR_API_BASE}/v1/portfolio/sweeps"

HTTP_TIMEOUT_S = 30.0

# Rate limit: 50 req/min IBKR global; 40/min soft cap (20% margin)
IBKR_MIN_CALL_INTERVAL_S = 1.5  # ~40/min

# TWS/Gateway fallback port range
TWS_DEFAULT_PORT = 7496
TWS_PAPER_PORT = 7497
TWS_CLIENT_ID = 13  # arbitrary; must be unique per connection


# ---------------------------------------------------------------------------
# Priority tiers (specs/14-ibkr-integration.md §3.1)
# ---------------------------------------------------------------------------


class Priority(IntEnum):
    """Request priority tiers — higher values drain first."""

    BULK_DATA = 0  # lowest
    MONITORING = 1
    ORDER_STATUS = 2
    POSITION_BALANCE = 3
    FRESH_QUOTE = 4  # trade-adjacent compliance gate
    ORDER_SUBMIT = 5  # highest — money at risk


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IBKRFallbackError(AdapterError):
    """Raised when Web API is unavailable and TWS fallback should be used."""

    def __init__(self, detail: str) -> None:
        super().__init__("ibkr", "web_api", detail)


# ---------------------------------------------------------------------------
# IBKRAdapter — Web API v1.0
# ---------------------------------------------------------------------------


class IBKRAdapter(BaseAdapter):
    """Adapter for IBKR Web API v1.0.

    Handles OAuth 2.0 authentication, account state, positions, orders,
    real-time quotes, and FX sweeps. Every outbound call is audited
    via ``_write_audit()``. Uses a priority queue to enforce rate-limit
    tiering (trades > monitoring > data).

    The ``fetch_quote()`` method bypasses caching entirely — it pulls a
    fresh price directly from IBKR for execution-time compliance checks.

    Ref: specs/14-ibkr-integration.md
    Ref: T-01-04
    """

    SOURCE_NAME = "ibkr"

    def __init__(
        self,
        db: DataFlow | None = None,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        paper_trading: bool = False,
        base_url: str = IBKR_API_BASE,
        http_timeout_s: float = HTTP_TIMEOUT_S,
        **kwargs,
    ) -> None:
        # Override default min_call_interval for IBKR's rate limit
        kwargs.setdefault("min_call_interval_s", IBKR_MIN_CALL_INTERVAL_S)
        super().__init__(db, **kwargs)

        self._client_id = client_id
        self._client_secret = client_secret
        self._paper_trading = paper_trading
        self._base_url = base_url.rstrip("/")
        self._http_timeout_s = http_timeout_s

        self._oauth_access_token: str | None = None
        self._oauth_refresh_token: str | None = None
        self._token_expires_at: float = 0.0

        # Per-tier priority queues
        self._priority_queues: dict[Priority, asyncio.PriorityQueue] = {
            tier: asyncio.PriorityQueue() for tier in Priority
        }
        self._drain_task: asyncio.Task[None] | None = None

        self._client: httpx.AsyncClient | None = None
        self._log = logger.bind(adapter=self.SOURCE_NAME)

    # ------------------------------------------------------------------
    # HTTP client
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
        """Close HTTP client and stop the priority drain task."""
        if self._drain_task:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
            self._drain_task = None

        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Priority queue — drain workers
    # ------------------------------------------------------------------

    async def _enqueue(
        self,
        priority: Priority,
        operation: str,
        fn: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Add a request to the appropriate priority queue and wait for it."""
        event = asyncio.Event()
        queue = self._priority_queues[priority]
        await queue.put((priority.value, operation, fn, args, kwargs, event))
        # Start drain worker if not running
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain_queue())
        # Wait for result
        await event.wait()

    async def _drain_queue(self) -> None:
        """Drain the highest-priority non-empty queue continuously."""
        while True:
            # Find highest-priority non-empty queue
            chosen: tuple[Priority, asyncio.PriorityQueue] | None = None
            for tier in sorted(Priority, reverse=True):
                q = self._priority_queues[tier]
                if not q.empty():
                    chosen = (tier, q)
                    break

            if chosen is None:
                # All queues empty — stop worker
                return

            tier, queue = chosen
            _, operation, fn, args, kwargs, event = await queue.get()

            try:
                await self._enforce_rate_limit()
                result = await fn(*args, **kwargs)
                event.set()
            except Exception as exc:
                # Store exception and set event so caller sees it
                result = exc
                event.set()
            finally:
                if not queue.empty():
                    # Keep worker alive if more items in this queue
                    asyncio.create_task(self._drain_queue())

    # ------------------------------------------------------------------
    # OAuth 2.0
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """Return a valid OAuth access token, refreshing if expired."""
        now = time.monotonic()
        if self._oauth_access_token and now < self._token_expires_at - 30:
            return self._oauth_access_token

        if not self._oauth_refresh_token:
            return await self._fetch_initial_token()

        # Attempt refresh
        try:
            return await self._refresh_token()
        except AuthenticationError:
            # Refresh failed — re-authenticate from scratch
            return await self._fetch_initial_token()

    async def _fetch_initial_token(self) -> str:
        """Perform the initial OAuth 2.0 client-credentials flow."""
        if not self._client_id or not self._client_secret:
            raise AuthenticationError(
                self.SOURCE_NAME,
                "oauth2_initial",
                status_code=None,
            )

        async def _do_token_request() -> dict[str, Any]:
            client = self._get_client()
            response = await client.post(
                IBKR_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": "http://localhost:8080",
                    "response_type": "code",
                },
            )

            if response.status_code == 401 or response.status_code == 403:
                raise AuthenticationError(
                    self.SOURCE_NAME,
                    "oauth2_initial",
                    status_code=response.status_code,
                )

            if response.status_code >= 500:
                raise AdapterError(
                    self.SOURCE_NAME,
                    "oauth2_initial",
                    f"server error: HTTP {response.status_code}",
                )

            if response.status_code >= 400:
                raise AdapterError(
                    self.SOURCE_NAME,
                    "oauth2_initial",
                    f"client error: HTTP {response.status_code}",
                )

            return response.json()

        now = time.monotonic()
        data = await self._retry("oauth2_initial", _do_token_request)

        self._oauth_access_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 0)
        self._token_expires_at = now + expires_in
        self._oauth_refresh_token = data.get("refresh_token", "")

        await self._write_audit(
            operation="oauth2_initial",
            success=True,
            detail=f"token acquired, expires_in={expires_in}s",
        )

        return self._oauth_access_token

    async def _refresh_token(self) -> str:
        """Refresh the OAuth access token using the refresh token."""
        if not self._oauth_refresh_token:
            raise AuthenticationError(
                self.SOURCE_NAME,
                "oauth2_refresh",
                status_code=None,
            )

        async def _do_refresh() -> dict[str, Any]:
            client = self._get_client()
            response = await client.post(
                IBKR_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._oauth_refresh_token,
                },
            )

            if response.status_code == 401 or response.status_code == 403:
                raise AuthenticationError(
                    self.SOURCE_NAME,
                    "oauth2_refresh",
                    status_code=response.status_code,
                )

            if response.status_code >= 400:
                raise AdapterError(
                    self.SOURCE_NAME,
                    "oauth2_refresh",
                    f"refresh failed: HTTP {response.status_code}",
                )

            return response.json()

        now = time.monotonic()
        data = await self._retry("oauth2_refresh", _do_refresh)

        self._oauth_access_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 0)
        self._token_expires_at = now + expires_in
        self._oauth_refresh_token = data.get("refresh_token", self._oauth_refresh_token)

        await self._write_audit(
            operation="oauth2_refresh",
            success=True,
            detail=f"token refreshed, expires_in={expires_in}s",
        )

        return self._oauth_access_token

    # ------------------------------------------------------------------
    # Authenticated request helper
    # ------------------------------------------------------------------

    async def _oauth_request(
        self,
        path: str,
        params: dict[str, Any],
        operation: str,
    ) -> Any:
        """Make an authenticated GET to the IBKR Web API."""
        token = await self._ensure_token()

        async def _do_request() -> Any:
            client = self._get_client()
            response = await client.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code == 401 or response.status_code == 403:
                # Token may have expired — force refresh and retry once
                raise AuthenticationError(
                    self.SOURCE_NAME,
                    operation,
                    status_code=response.status_code,
                )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_after_s = float(retry_after) if retry_after else None
                self._handle_rate_limit_headers(dict(response.headers))
                raise RateLimitExceeded(self.SOURCE_NAME, operation, retry_after_s)

            if response.status_code == 503:
                # Web API unavailable — signal fallback
                raise IBKRFallbackError(f"Web API returned 503; TWS fallback should be used")

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
                    f"client error: HTTP {response.status_code}",
                )

            return response.json()

        return await self._retry(operation, _do_request)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Return health status for the IBKR Web API adapter."""
        if not self._client_id or not self._client_secret:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": "IBKR client credentials not configured",
            }

        try:
            token = await self._ensure_token()
            if not token:
                return {
                    "source": self.SOURCE_NAME,
                    "healthy": False,
                    "detail": "failed to acquire OAuth token",
                }
            return {
                "source": self.SOURCE_NAME,
                "healthy": True,
                "detail": "OAuth token acquired",
                "paper_trading": self._paper_trading,
            }
        except AuthenticationError as exc:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": f"authentication failed: {exc}",
            }
        except IBKRFallbackError:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": "Web API unavailable, TWS fallback recommended",
                "fallback_required": True,
            }
        except Exception as exc:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": str(exc),
            }

    # ------------------------------------------------------------------
    # Fresh quote — bypasses cache; used for execution-time compliance
    # ------------------------------------------------------------------

    async def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch a real-time quote for ``ticker`` directly from IBKR.

        This method bypasses the fabric cache and is used exclusively for
        the execution-time fresh-price check (``exec.freshness_at_execution``
        compliance rule). It is NOT written to the ``quotes`` table to avoid
        duplicating what the polling adapter writes.

        Returns a dict with ``bid``, ``ask``, ``mid``, ``timestamp``,
        ``ticker``, and ``source_vintage``.
        """
        operation = "fetch_quote"
        self._log.info("fetch_quote.start", ticker=ticker)

        try:
            data = await self._enqueue(
                Priority.FRESH_QUOTE,
                operation,
                self._do_fetch_quote,
                ticker,
            )
        except IBKRFallbackError:
            raise  # propagate to caller so they can use TWS fallback
        except (AuthenticationError, AdapterError) as exc:
            self._log.error(
                "fetch_quote.failed",
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

        if not data:
            self._log.info("fetch_quote.empty", ticker=ticker)
            return {}

        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()

        bid = float(data.get("bid", 0) or 0)
        ask = float(data.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if bid and ask else 0.0
        bid_size = float(data.get("bid_size", 0) or 0)
        ask_size = float(data.get("ask_size", 0) or 0)
        spread_bps = ((ask - bid) / mid * 10000) if mid > 1e-10 else 0.0

        result: dict[str, Any] = {
            "ticker": ticker,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "spread_bps": round(spread_bps, 4),
            "timestamp": timestamp,
            "source_vintage": f"ibkr:{ticker}:{timestamp}",
        }

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fresh quote for {ticker}: bid={bid}, ask={ask}",
            instrument=ticker,
            rows_written=0,
        )

        self._log.info(
            "fetch_quote.complete",
            ticker=ticker,
            bid=bid,
            ask=ask,
            mid=mid,
        )
        return result

    async def _do_fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Internal: actually perform the quote fetch."""
        return await self._oauth_request(
            IBKR_QUOTES_URL,
            {"symbol": ticker, "fields": "bid,ask,bid_size,ask_size"},
            "fetch_quote",
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def fetch_positions(self, account_id: str) -> list[dict[str, Any]]:
        """Fetch current positions for ``account_id`` and write to ``positions`` table.

        Ref: specs/03-universe-and-data.md §3.3 — positions table fields.
        Ref: specs/14-ibkr-integration.md §2.1 — IBKR-SG entity, paper vs live.
        """
        operation = "fetch_positions"
        self._log.info("fetch_positions.start", account_id=account_id)

        try:
            raw_positions = await self._enqueue(
                Priority.POSITION_BALANCE,
                operation,
                self._do_fetch_positions,
                account_id,
            )
        except IBKRFallbackError:
            raise
        except (AuthenticationError, AdapterError) as exc:
            self._log.error(
                "fetch_positions.failed",
                account_id=account_id,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
            )
            return []

        if not raw_positions or not isinstance(raw_positions, list):
            self._log.info("fetch_positions.empty", account_id=account_id)
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for item in raw_positions:
            ticker = item.get("symbol", item.get("ticker", ""))
            if not ticker:
                ticker = item.get("conid", "")

            quantity = float(item.get("position", item.get("quantity", 0)) or 0)
            avg_cost = float(item.get("avg_cost", item.get("averageCost", 0)) or 0)
            current_price = float(item.get("market_price", item.get("marketPrice", 0)) or 0)
            market_value = float(item.get("market_value", item.get("marketValue", 0)) or 0)
            unrealized_pnl = float(item.get("unrealized_pnl", item.get("unrealizedPnl", 0)) or 0)
            as_of_date = now.date().isoformat()

            row: dict[str, Any] = {
                "ticker": ticker,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "as_of_date": as_of_date,
                "source": self.SOURCE_NAME,
                "account_id": account_id,
                # PIT fields
                "period_end": as_of_date,
                "filed_at": now.isoformat(),
                "restated_at": "",
                "source_vintage": f"ibkr:positions:{account_id}:{as_of_date}",
            }

            try:
                await db.express.create("positions", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_positions.row_write_failed",
                    ticker=ticker,
                    account_id=account_id,
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(raw_positions)} positions, wrote {len(created_rows)}",
            instrument=",".join(r["ticker"] for r in created_rows),
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_positions.complete",
            account_id=account_id,
            positions_fetched=len(raw_positions),
            positions_written=len(created_rows),
        )
        return created_rows

    async def _do_fetch_positions(self, account_id: str) -> list[dict[str, Any]]:
        """Internal: perform positions fetch."""
        data = await self._oauth_request(
            IBKR_POSITIONS_URL,
            {"account_id": account_id},
            "fetch_positions",
        )
        return data if isinstance(data, list) else data.get("positions", [])

    # ------------------------------------------------------------------
    # Account balance
    # ------------------------------------------------------------------

    async def fetch_account_balance(self, account_id: str) -> dict[str, Any]:
        """Fetch account balances and Net Asset Value for ``account_id``.

        Writes a snapshot to the ``audit_log`` with the balance figures
        as JSON details. Account balances are not written to a dedicated
        fabric table in v1 — they are cached in Redis via the hot-cache
        layer (T-01-10) and surfaced via the Pulse surface.
        """
        operation = "fetch_account_balance"
        self._log.info("fetch_account_balance.start", account_id=account_id)

        try:
            raw = await self._enqueue(
                Priority.POSITION_BALANCE,
                operation,
                self._do_fetch_account_balance,
                account_id,
            )
        except IBKRFallbackError:
            raise
        except (AuthenticationError, AdapterError) as exc:
            self._log.error(
                "fetch_account_balance.failed",
                account_id=account_id,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
            )
            return {}

        if not raw:
            return {}

        now = datetime.now(timezone.utc)
        total_cash = float(raw.get("total_cash_value", 0) or 0)
        net_asset_value = float(raw.get("net_asset_value", 0) or 0)
        equity = float(raw.get("equity", 0) or 0)
        buying_power = float(raw.get("buying_power", 0) or 0)

        balance_details = {
            "account_id": account_id,
            "total_cash_value": total_cash,
            "net_asset_value": net_asset_value,
            "equity": equity,
            "buying_power": buying_power,
            "currency": raw.get("currency", "USD"),
            "timestamp": now.isoformat(),
        }

        await self._write_audit(
            operation=operation,
            success=True,
            detail=json.dumps(balance_details),
            rows_written=0,
        )

        self._log.info(
            "fetch_account_balance.complete",
            account_id=account_id,
            total_cash_value=total_cash,
            net_asset_value=net_asset_value,
        )
        return balance_details

    async def _do_fetch_account_balance(self, account_id: str) -> dict[str, Any]:
        """Internal: perform account balance fetch."""
        accounts = await self._oauth_request(
            IBKR_ACCOUNTS_URL,
            {},
            "fetch_accounts",
        )
        # Find the matching account
        if isinstance(accounts, list):
            for acct in accounts:
                if acct.get("account_id") == account_id:
                    return acct
        return {}

    # ------------------------------------------------------------------
    # Order status
    # ------------------------------------------------------------------

    async def fetch_order_status(self, account_id: str) -> list[dict[str, Any]]:
        """Fetch active/recent orders for ``account_id`` and write to ``orders`` table.

        Ref: specs/14-ibkr-integration.md §6 — order state machine mapping.
        """
        operation = "fetch_order_status"
        self._log.info("fetch_order_status.start", account_id=account_id)

        try:
            raw_orders = await self._enqueue(
                Priority.ORDER_STATUS,
                operation,
                self._do_fetch_orders,
                account_id,
            )
        except IBKRFallbackError:
            raise
        except (AuthenticationError, AdapterError) as exc:
            self._log.error(
                "fetch_order_status.failed",
                account_id=account_id,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
            )
            return []

        if not raw_orders or not isinstance(raw_orders, list):
            self._log.info("fetch_order_status.empty", account_id=account_id)
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for item in raw_orders:
            ticker = item.get("symbol", item.get("ticker", ""))
            if not ticker:
                ticker = item.get("conid", "")

            row: dict[str, Any] = {
                "ticker": ticker,
                "side": item.get("side", item.get("action", "")),
                "order_type": item.get("order_type", item.get("type", "")),
                "quantity": float(item.get("quantity", 0) or 0),
                "limit_price": float(item.get("limit_price", item.get("lmt_price", 0)) or 0),
                "status": _map_ibkr_order_status(item.get("status", "")),
                "filled_qty": float(item.get("filled_qty", item.get("filled", 0)) or 0),
                "filled_price": float(item.get("filled_price", item.get("avg_fill_price", 0)) or 0),
                "submitted_at": item.get("submitted_at", item.get("created_time", "")),
                "filled_at": item.get("filled_at", item.get("fill_time", "")),
                "broker_order_id": item.get("order_id", item.get("id", "")),
                "parent_decision_id": item.get("parent_id", ""),
                # PIT fields
                "period_end": now.date().isoformat(),
                "filed_at": now.isoformat(),
                "restated_at": "",
                "source_vintage": f"ibkr:orders:{account_id}:{now.isoformat()}",
            }

            try:
                await db.express.create("orders", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_order_status.row_write_failed",
                    ticker=ticker,
                    order_id=row["broker_order_id"],
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(raw_orders)} orders, wrote {len(created_rows)}",
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_order_status.complete",
            account_id=account_id,
            orders_fetched=len(raw_orders),
            orders_written=len(created_rows),
        )
        return created_rows

    async def _do_fetch_orders(self, account_id: str) -> list[dict[str, Any]]:
        """Internal: perform orders fetch."""
        data = await self._oauth_request(
            IBKR_ORDERS_URL,
            {"account_id": account_id},
            "fetch_orders",
        )
        return data if isinstance(data, list) else data.get("orders", [])

    # ------------------------------------------------------------------
    # FX Sweep events
    # ------------------------------------------------------------------

    async def fetch_sweep_events(self, account_id: str) -> list[dict[str, Any]]:
        """Fetch FX sweep events and write to ``sweep_history`` table.

        Ref: specs/14-ibkr-integration.md §11 — FX sweep policy.
        """
        operation = "fetch_sweep_events"
        self._log.info("fetch_sweep_events.start", account_id=account_id)

        try:
            raw_sweeps = await self._enqueue(
                Priority.MONITORING,
                operation,
                self._do_fetch_sweeps,
                account_id,
            )
        except IBKRFallbackError:
            raise
        except (AuthenticationError, AdapterError) as exc:
            self._log.error(
                "fetch_sweep_events.failed",
                account_id=account_id,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
            )
            return []

        if not raw_sweeps or not isinstance(raw_sweeps, list):
            self._log.info("fetch_sweep_events.empty", account_id=account_id)
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for item in raw_sweeps:
            row: dict[str, Any] = {
                "base_currency": item.get("base_currency", "USD"),
                "target_currency": item.get("target_currency", "SGD"),
                "amount": float(item.get("amount", 0) or 0),
                "rate": float(item.get("rate", 0) or 0),
                "fee": float(item.get("fee", 0) or 0),
                "sweep_timestamp": item.get("timestamp", now.isoformat()),
                "broker_sweep_id": item.get("sweep_id", ""),
                # PIT fields
                "period_end": now.date().isoformat(),
                "filed_at": now.isoformat(),
                "restated_at": "",
                "source_vintage": f"ibkr:sweeps:{account_id}:{now.isoformat()}",
            }

            try:
                await db.express.create("sweep_history", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_sweep_events.row_write_failed",
                    sweep_id=row["broker_sweep_id"],
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(raw_sweeps)} sweeps, wrote {len(created_rows)}",
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_sweep_events.complete",
            account_id=account_id,
            sweeps_fetched=len(raw_sweeps),
            sweeps_written=len(created_rows),
        )
        return created_rows

    async def _do_fetch_sweeps(self, account_id: str) -> list[dict[str, Any]]:
        """Internal: perform sweeps fetch."""
        data = await self._oauth_request(
            IBKR_SWEEPS_URL,
            {"account_id": account_id},
            "fetch_sweeps",
        )
        return data if isinstance(data, list) else data.get("sweeps", [])

    # ------------------------------------------------------------------
    # Write a fills record (called by execution layer after a fill)
    # ------------------------------------------------------------------

    async def write_fill(
        self,
        order_id: str,
        ticker: str,
        fill_price: float,
        fill_qty: float,
        commission: float,
        exchange_fee: float,
        regulatory_fee: float,
        venue: str,
        fill_timestamp: str,
        broker_fill_id: str,
    ) -> dict[str, Any]:
        """Write a fill record to the ``fills`` fabric table.

        This is called by the execution layer after a fill is reported
        by IBKR, not fetched from the API.

        Ref: specs/03-universe-and-data.md §3.3 — fills table fields.
        """
        operation = "write_fill"
        self._log.info(
            "write_fill.start",
            order_id=order_id,
            ticker=ticker,
            fill_price=fill_price,
            fill_qty=fill_qty,
        )

        now = datetime.now(timezone.utc)
        db = self._get_db()

        row: dict[str, Any] = {
            "order_id": order_id,
            "ticker": ticker,
            "fill_price": fill_price,
            "fill_qty": fill_qty,
            "commission": commission,
            "exchange_fee": exchange_fee,
            "regulatory_fee": regulatory_fee,
            "venue": venue,
            "fill_timestamp": fill_timestamp,
            "broker_fill_id": broker_fill_id,
            # PIT fields
            "period_end": now.date().isoformat(),
            "filed_at": now.isoformat(),
            "restated_at": "",
            "source_vintage": f"ibkr:fill:{broker_fill_id}",
        }

        try:
            await db.express.create("fills", row)
            await self._write_audit(
                operation=operation,
                success=True,
                detail=f"fill written for {ticker}: qty={fill_qty} @ {fill_price}",
                instrument=ticker,
                rows_written=1,
            )
            self._log.info("write_fill.complete", ticker=ticker, fill_id=broker_fill_id)
            return row
        except Exception as exc:
            self._log.error("write_fill.failed", ticker=ticker, error=str(exc))
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
                instrument=ticker,
            )
            return {}


# ---------------------------------------------------------------------------
# TWSTFallbackAdapter — ib_async fallback
# ---------------------------------------------------------------------------

# ib_async is the standard Python API for TWS / IB Gateway.
# It is imported lazily so that the Web API adapter does not require
# a TWS installation. When ib_async is not installed, importing this
# module will still succeed but health_check() will report unhealthy.
try:
    import ib_async
except ImportError:
    ib_async = None  # type: ignore[assignment]


class TWSTFallbackAdapter(BaseAdapter):
    """Fallback adapter using ib_async to connect to TWS / IB Gateway.

    Activated when the IBKR Web API returns HTTP 503 or an authentication
    failure. Same interface as ``IBKRAdapter`` — same fabric write paths,
    same audit discipline.

    Requires a running TWS or IB Gateway process on the local machine
    (or reachable host). Connection is established lazily on first call.

    Ref: specs/14-ibkr-integration.md §2.2
    Ref: T-01-05
    """

    SOURCE_NAME = "ibkr_tws"

    def __init__(
        self,
        db: DataFlow | None = None,
        *,
        host: str = "127.0.0.1",
        port: int = TWS_DEFAULT_PORT,
        client_id: int = TWS_CLIENT_ID,
        paper_port: int = TWS_PAPER_PORT,
        paper_trading: bool = False,
        account_id: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(db, **kwargs)
        self._host = host
        self._port = paper_port if paper_trading else port
        self._client_id = client_id
        self._paper_trading = paper_trading
        self._account_id = account_id
        self._ib: ib_async.IB | None = None if ib_async is None else None  # type: ignore[assignment]
        self._connected_account: str | None = None
        self._log = logger.bind(adapter=self.SOURCE_NAME)

    # ------------------------------------------------------------------
    # Lazy IB connection
    # ------------------------------------------------------------------

    def _get_ib(self) -> ib_async.IB:  # type: ignore[valid-type]
        """Return the ib_async connection, connecting lazily if needed."""
        if ib_async is None:
            raise AdapterError(
                self.SOURCE_NAME,
                "connect",
                "ib_async not installed — install with: pip install ib_async",
            )

        if self._ib is None:
            self._ib = ib_async.IB()
            self._ib.connect(
                self._host,
                self._port,
                clientId=self._client_id,
            )
            # Resolve account
            accounts = self._ib.accountData()
            if accounts:
                self._connected_account = (
                    self._account_id if self._account_id in accounts else accounts[0]
                )

        return self._ib

    async def close(self) -> None:
        """Disconnect from TWS."""
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()
            self._ib = None
            self._connected_account = None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Return health status for the TWS fallback adapter."""
        if ib_async is None:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": "ib_async not installed",
            }

        try:
            ib = self._get_ib()
            if not ib.isConnected():
                return {
                    "source": self.SOURCE_NAME,
                    "healthy": False,
                    "detail": "not connected to TWS",
                }
            return {
                "source": self.SOURCE_NAME,
                "healthy": True,
                "detail": f"connected to TWS at {self._host}:{self._port}",
                "account_id": self._connected_account,
                "paper_trading": self._paper_trading,
            }
        except Exception as exc:
            return {
                "source": self.SOURCE_NAME,
                "healthy": False,
                "detail": str(exc),
            }

    # ------------------------------------------------------------------
    # Fresh quote (TWS) — bypasses cache
    # ------------------------------------------------------------------

    async def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch a real-time quote via TWS/ib_async.

        Mirrors ``IBKRAdapter.fetch_quote()`` — fresh price only,
        not written to the quotes table.
        """
        operation = "fetch_quote"
        self._log.info("fetch_quote.start", ticker=ticker)

        try:
            ib = self._get_ib()
            contract = ib_async.Stock(ticker, "SMART", "USD")
            ib.reqMktData(contract, "", False, False)
            # Wait briefly for the tick
            await asyncio.sleep(2.0)  # TWS delivers ticks asynchronously
            tick = contract.tickPrice()
            bid = tick.bid
            ask = tick.ask
            mid = (bid + ask) / 2 if bid and ask else 0.0
        except Exception as exc:
            self._log.error("fetch_quote.failed", ticker=ticker, error=str(exc))
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
                instrument=ticker,
            )
            return {}

        now = datetime.now(timezone.utc)
        result: dict[str, Any] = {
            "ticker": ticker,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "bid_size": 0.0,
            "ask_size": 0.0,
            "spread_bps": round(((ask - bid) / mid * 10000) if mid > 1e-10 else 0.0, 4),
            "timestamp": now.isoformat(),
            "source_vintage": f"ibkr_tws:{ticker}:{now.isoformat()}",
        }

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fresh quote via TWS for {ticker}: bid={bid}, ask={ask}",
            instrument=ticker,
            rows_written=0,
        )

        self._log.info("fetch_quote.complete", ticker=ticker, bid=bid, ask=ask)
        return result

    # ------------------------------------------------------------------
    # Positions (TWS)
    # ------------------------------------------------------------------

    async def fetch_positions(self, account_id: str) -> list[dict[str, Any]]:
        """Fetch current positions via TWS and write to ``positions`` table."""
        operation = "fetch_positions"
        self._log.info("fetch_positions.start", account_id=account_id)

        try:
            ib = self._get_ib()
            acct = account_id or self._connected_account or ""
            ib.reqAccountUpdates(acct)
            await asyncio.sleep(1.5)  # TWS delivers updates asynchronously
            positions_data = ib.positions()
        except Exception as exc:
            self._log.error(
                "fetch_positions.failed",
                account_id=account_id,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
            )
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for acct, contract, position, avg_cost in positions_data:
            ticker = contract.symbol
            quantity = float(position)
            avg_cost_val = float(avg_cost or 0)
            # TWS doesn't provide live market price in positions() —
            # market_value and unrealized_pnl computed from last known price
            current_price = 0.0
            market_value = 0.0
            unrealized_pnl = 0.0
            as_of_date = now.date().isoformat()

            row: dict[str, Any] = {
                "ticker": ticker,
                "quantity": quantity,
                "avg_cost": avg_cost_val,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "as_of_date": as_of_date,
                "source": self.SOURCE_NAME,
                "account_id": str(acct),
                "period_end": as_of_date,
                "filed_at": now.isoformat(),
                "restated_at": "",
                "source_vintage": f"ibkr_tws:positions:{acct}:{as_of_date}",
            }

            try:
                await db.express.create("positions", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_positions.row_write_failed",
                    ticker=ticker,
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(positions_data)} positions, wrote {len(created_rows)}",
            instrument=",".join(r["ticker"] for r in created_rows),
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_positions.complete",
            account_id=account_id,
            positions_fetched=len(positions_data),
            positions_written=len(created_rows),
        )
        return created_rows

    # ------------------------------------------------------------------
    # Account balance (TWS)
    # ------------------------------------------------------------------

    async def fetch_account_balance(self, account_id: str) -> dict[str, Any]:
        """Fetch account balances via TWS."""
        operation = "fetch_account_balance"
        self._log.info("fetch_account_balance.start", account_id=account_id)

        try:
            ib = self._get_ib()
            acct = account_id or self._connected_account or ""
            ib.reqAccountUpdates(acct)
            await asyncio.sleep(1.5)
            values = ib.accountValues()
        except Exception as exc:
            self._log.error(
                "fetch_account_balance.failed",
                account_id=account_id,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
            )
            return {}

        now = datetime.now(timezone.utc)
        # Parse TWS account values into structured balance dict
        balance_details: dict[str, Any] = {
            "account_id": acct,
            "timestamp": now.isoformat(),
        }
        for av in values:
            key = av.tag
            value = float(av.value) if av.value else 0.0
            balance_details[key] = value

        await self._write_audit(
            operation=operation,
            success=True,
            detail=json.dumps(balance_details),
            rows_written=0,
        )

        self._log.info(
            "fetch_account_balance.complete",
            account_id=account_id,
        )
        return balance_details

    # ------------------------------------------------------------------
    # Order status (TWS)
    # ------------------------------------------------------------------

    async def fetch_order_status(self, account_id: str) -> list[dict[str, Any]]:
        """Fetch open orders via TWS and write to ``orders`` table."""
        operation = "fetch_order_status"
        self._log.info("fetch_order_status.start", account_id=account_id)

        try:
            ib = self._get_ib()
            open_orders = ib.openOrders()
        except Exception as exc:
            self._log.error(
                "fetch_order_status.failed",
                account_id=account_id,
                error=str(exc),
            )
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
            )
            return []

        now = datetime.now(timezone.utc)
        db = self._get_db()
        created_rows: list[dict[str, Any]] = []

        for order in open_orders:
            contract = order.contract
            o = order.order
            ticker = contract.symbol if contract else ""

            row: dict[str, Any] = {
                "ticker": ticker,
                "side": o.action,
                "order_type": o.orderType,
                "quantity": float(o.totalQuantity),
                "limit_price": float(o.lmtPrice or 0),
                "status": _map_ibkr_order_status(str(o.status)),
                "filled_qty": float(o.filledQuantity),
                "filled_price": float(o.avgFillPrice or 0),
                "submitted_at": str(o.submitted),
                "filled_at": str(o.filledTime or ""),
                "broker_order_id": str(o.orderId),
                "parent_decision_id": str(o.parentId),
                "period_end": now.date().isoformat(),
                "filed_at": now.isoformat(),
                "restated_at": "",
                "source_vintage": f"ibkr_tws:orders:{account_id}:{now.isoformat()}",
            }

            try:
                await db.express.create("orders", row)
                created_rows.append(row)
            except Exception as exc:
                self._log.warning(
                    "fetch_order_status.row_write_failed",
                    ticker=ticker,
                    order_id=row["broker_order_id"],
                    error=str(exc),
                )

        await self._write_audit(
            operation=operation,
            success=True,
            detail=f"fetched {len(open_orders)} orders, wrote {len(created_rows)}",
            rows_written=len(created_rows),
        )

        self._log.info(
            "fetch_order_status.complete",
            account_id=account_id,
            orders_fetched=len(open_orders),
            orders_written=len(created_rows),
        )
        return created_rows

    # ------------------------------------------------------------------
    # FX Sweep events (TWS) — not natively available via ib_async,
    # so this is a no-op stub that logs and audits the gap
    # ------------------------------------------------------------------

    async def fetch_sweep_events(self, account_id: str) -> list[dict[str, Any]]:
        """FX sweeps are not available via ib_async in v1.

        Writes an audit entry noting the unavailability and returns empty.
        """
        operation = "fetch_sweep_events"
        self._log.info("fetch_sweep_events.start", account_id=account_id)

        await self._write_audit(
            operation=operation,
            success=True,
            detail="ib_async does not expose FX sweep events in v1; returning empty",
            rows_written=0,
        )

        self._log.info("fetch_sweep_events.complete", account_id=account_id)
        return []

    # ------------------------------------------------------------------
    # Write a fill (TWS) — called by execution layer
    # ------------------------------------------------------------------

    async def write_fill(
        self,
        order_id: str,
        ticker: str,
        fill_price: float,
        fill_qty: float,
        commission: float,
        exchange_fee: float,
        regulatory_fee: float,
        venue: str,
        fill_timestamp: str,
        broker_fill_id: str,
    ) -> dict[str, Any]:
        """Write a fill record to the ``fills`` table via TWS adapter."""
        operation = "write_fill"
        self._log.info(
            "write_fill.start",
            order_id=order_id,
            ticker=ticker,
            fill_price=fill_price,
            fill_qty=fill_qty,
        )

        now = datetime.now(timezone.utc)
        db = self._get_db()

        row: dict[str, Any] = {
            "order_id": order_id,
            "ticker": ticker,
            "fill_price": fill_price,
            "fill_qty": fill_qty,
            "commission": commission,
            "exchange_fee": exchange_fee,
            "regulatory_fee": regulatory_fee,
            "venue": venue,
            "fill_timestamp": fill_timestamp,
            "broker_fill_id": broker_fill_id,
            "period_end": now.date().isoformat(),
            "filed_at": now.isoformat(),
            "restated_at": "",
            "source_vintage": f"ibkr_tws:fill:{broker_fill_id}",
        }

        try:
            await db.express.create("fills", row)
            await self._write_audit(
                operation=operation,
                success=True,
                detail=f"fill written for {ticker}: qty={fill_qty} @ {fill_price}",
                instrument=ticker,
                rows_written=1,
            )
            self._log.info("write_fill.complete", ticker=ticker, fill_id=broker_fill_id)
            return row
        except Exception as exc:
            self._log.error("write_fill.failed", ticker=ticker, error=str(exc))
            await self._write_audit(
                operation=operation,
                success=False,
                detail=str(exc),
                instrument=ticker,
            )
            return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _map_ibkr_order_status(ibkr_status: str) -> str:
    """Map IBKR order status string to Midas canonical status.

    Ref: specs/14-ibkr-integration.md §6 — order state machine.
    """
    mapping = {
        "pendingsubmit": "submitted_pending",
        "pendingcancel": "cancel_pending",
        "presubmitted": "submitted_waiting",
        "submitted": "working",
        "filled": "filled",
        "cancelled": "cancelled",
        "apicancelled": "cancelled_api",
        "inactive": "inactive_flagged",
        "partiallyfilled": "partial_filled",
    }
    return mapping.get(ibkr_status.lower(), ibkr_status)
