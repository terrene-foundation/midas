"""
M19 — Paper Trading Flow.

Paper-mode feature flag, two-week timer, report generator, and Go Live action.

Ref: specs/08 §6, specs/10 §3
"""

from midas.paper_trading.paper_manager import PaperTradingManager
from midas.paper_trading.report import PaperTradingReport

__all__ = [
    "PaperTradingManager",
    "PaperTradingReport",
]
