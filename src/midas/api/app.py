"""
Nexus application factory for the Midas API.

Creates and configures the FastAPI-based API with all routers mounted.
Follows Kailash Nexus patterns for multi-channel deployment.

Ref: specs/09, specs/10
"""

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

logger = logging.getLogger(__name__)


def create_app(
    cors_origins: list[str] | None = None,
    title: str = "Midas API",
    version: str = "0.1.0",
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
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount all routers
    health = HealthRouter()
    app.include_router(health.router, prefix="/api/v1/health", tags=["health"])

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

    @app.on_event("startup")
    async def startup() -> None:
        logger.info("midas.api.startup", extra={"version": version})

    @app.on_event("shutdown")
    async def shutdown() -> None:
        logger.info("midas.api.shutdown")

    return app
