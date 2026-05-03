"""
Nexus application factory for the Midas API.

Creates and configures the FastAPI-based API with all routers mounted.
Follows Kailash Nexus patterns for multi-channel deployment.

Ref: specs/09, specs/10, specs/11 S6.2 (JWT auth)
"""

import hmac
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from midas.api.auth import AuthRouter, verify_jwt_or_pass, AUTH_EXEMPT_PATHS
from midas.api.routes import (
    AuditRouter,
    BacktestRouter,
    ComplianceRouter,
    DebateRouter,
    DecisionsRouter,
    HealthRouter,
    PortfolioRouter,
    PulseRouter,
    SettingsRouter,
    SignalRouter,
)
from midas.api.routes_extended import (
    BacktestDetailRouter,
    DebateResolutionRouter,
    DecisionModifyRouter,
    MultiTurnDebateRouter,
    NotificationRouter,
    OnboardingRouter,
    PaperLiveRouter,
    PositionHistoryRouter,
)
from midas.api.websocket import WebSocketRouter

logger = logging.getLogger(__name__)

# SC-H2: Per-IP sliding-window rate limiter
_RATE_LIMIT_WINDOW_SECS = 60
_RATE_LIMIT_MAX_REQUESTS = 60
_MAX_TRACKED_IPS = 10000
_ip_timestamps: dict[str, deque[float]] = defaultdict(
    lambda: deque(maxlen=_RATE_LIMIT_MAX_REQUESTS)
)
_ip_last_seen: dict[str, float] = {}


def _get_client_ip(request: Request) -> str:
    """Extract client IP, accounting for X-Forwarded-For proxy header."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> tuple[bool, int]:
    """Check and record request. Returns (allowed, remaining)."""
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECS

    # Evict stale IPs to bound memory growth
    if len(_ip_last_seen) > _MAX_TRACKED_IPS:
        stale = [k for k, v in _ip_last_seen.items() if v < cutoff]
        for k in stale:
            _ip_timestamps.pop(k, None)
            del _ip_last_seen[k]

    _ip_last_seen[ip] = now
    timestamps = _ip_timestamps[ip]
    while timestamps and timestamps[0] < cutoff:
        timestamps.popleft()
    if len(timestamps) >= _RATE_LIMIT_MAX_REQUESTS:
        return False, 0
    timestamps.append(now)
    return True, _RATE_LIMIT_MAX_REQUESTS - len(timestamps)


def create_app(
    cors_origins: list[str] | None = None,
    title: str = "Midas API",
    version: str = "0.1.0",
    api_key: str | None = None,
) -> FastAPI:
    """Create and configure the Midas FastAPI application.

    Parameters
    ----------
    cors_origins:
        Allowed CORS origins. Defaults to localhost for development.
    title:
        API title for OpenAPI docs.
    version:
        API version.
    api_key:
        Legacy API key. Ignored when JWT_SECRET is set.

    Returns
    -------
    FastAPI
        Configured application with all routers mounted.
    """
    origins = cors_origins or [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    app = FastAPI(
        title=title,
        version=version,
        description="Midas autonomous investment assistant API",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Per-IP sliding-window rate limit (60 req/min)."""
        ip = _get_client_ip(request)
        allowed, remaining = _check_rate_limit(ip)
        if not allowed:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        """JWT auth on all non-exempt endpoints. Falls back to API key."""
        path = request.url.path

        # Exempt paths
        if path in AUTH_EXEMPT_PATHS or path.startswith("/api/v1/health/"):
            return await call_next(request)

        # JWT verification (passes in dev mode if JWT_SECRET not set)
        payload = await verify_jwt_or_pass(request)
        if payload is not None:
            request.state.user = payload
            return await call_next(request)

        # Legacy API key fallback (when JWT_SECRET is not configured)
        legacy_key = api_key or os.environ.get("MIDAS_API_KEY", "")
        if legacy_key:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
            elif auth.startswith("ApiKey "):
                token = auth[7:]
            else:
                token = auth
            if not hmac.compare_digest(token, legacy_key):
                logger.warning("auth.unauthorized", extra={"path": path})
                raise HTTPException(status_code=401, detail="Invalid or missing API key")
            return await call_next(request)

        # No auth configured (dev mode — requires explicit DEV_MODE=true)
        dev_mode = os.environ.get("DEV_MODE", "").lower() == "true"
        if dev_mode:
            logger.warning(
                "auth.dev_mode_enabled",
                extra={
                    "path": path,
                    "note": "DEV_MODE=true: all endpoints accessible without authentication",
                },
            )
            return await call_next(request)
        logger.warning(
            "auth.unauthorized.no_credentials",
            extra={"path": path, "note": "No JWT_SECRET, no DEV_MODE=true — rejecting request"},
        )
        raise HTTPException(
            status_code=401, detail="Authentication required: set JWT_SECRET or DEV_MODE=true"
        )

    # Mount all routers
    health = HealthRouter()
    app.include_router(health.router, prefix="/api/v1/health", tags=["health"])

    auth = AuthRouter()
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])

    pulse = PulseRouter()
    app.include_router(pulse.router, prefix="/api/v1/pulse", tags=["pulse"])

    decisions = DecisionsRouter()
    app.include_router(decisions.router, prefix="/api/v1/decisions", tags=["decisions"])

    debate = DebateRouter()
    app.include_router(debate.router, prefix="/api/v1/debate", tags=["debate"])

    portfolio = PortfolioRouter()
    app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["portfolio"])

    backtest = BacktestRouter()
    app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["backtest"])

    signal = SignalRouter()
    app.include_router(signal.router, prefix="/api/v1/signal", tags=["signal"])

    settings = SettingsRouter()
    app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])

    compliance = ComplianceRouter()
    app.include_router(compliance.router, prefix="/api/v1/compliance", tags=["compliance"])

    audit = AuditRouter()
    app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])

    onboarding = OnboardingRouter()
    app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])

    decision_modify = DecisionModifyRouter()
    app.include_router(decision_modify.router, prefix="/api/v1/decisions", tags=["decisions"])

    debate_resolution = DebateResolutionRouter()
    app.include_router(debate_resolution.router, prefix="/api/v1/debate", tags=["debate"])

    multi_turn_debate = MultiTurnDebateRouter()
    app.include_router(multi_turn_debate.router, prefix="/api/v1/debate", tags=["debate"])

    notifications = NotificationRouter()
    app.include_router(
        notifications.router, prefix="/api/v1/settings/notifications", tags=["notifications"]
    )

    backtest_detail = BacktestDetailRouter()
    app.include_router(backtest_detail.router, prefix="/api/v1/backtest", tags=["backtest"])

    paper_live = PaperLiveRouter()
    app.include_router(paper_live.router, prefix="/api/v1/settings/paper-live", tags=["paper-live"])

    position_history = PositionHistoryRouter()
    app.include_router(position_history.router, prefix="/api/v1/portfolio", tags=["portfolio"])

    ws = WebSocketRouter()
    app.include_router(ws.router, prefix="/api/v1", tags=["websocket"])

    @app.on_event("startup")
    async def startup() -> None:
        logger.info("midas.api.startup", extra={"version": version})

    @app.on_event("shutdown")
    async def shutdown() -> None:
        logger.info("midas.api.shutdown")

    return app
