"""
M17 — Nexus API backbone.

Multi-channel API surface exposing all Midas decision, debate, portfolio,
backtest, signal, and settings endpoints via Kailash Nexus.

Ref: specs/09, specs/10
"""

from midas.api.app import create_app
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

__all__ = [
    "create_app",
    "HealthRouter",
    "PulseRouter",
    "DecisionsRouter",
    "DebateRouter",
    "PortfolioRouter",
    "BacktestRouter",
    "SignalRouter",
    "SettingsRouter",
    "ComplianceRouter",
    "AuditRouter",
]
