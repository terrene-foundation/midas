"""
Data source adapters for the Midas fabric.

Every adapter writes to the fabric via DataFlow express. No caller ever
sees a raw API response. Failures write a health-check entry to the
audit_log table, not an exception to the caller.

Usage::

    from midas.fabric.adapters import EODHDAdapter, YahooFinanceAdapter, FREDAdapter

    eodhd = EODHDAdapter()
    rows = await eodhd.fetch_prices("AAPL.US", "2024-01-01", "2024-01-31")

    yahoo = YahooFinanceAdapter()
    cross = await yahoo.cross_check_prices("AAPL", "2024-01-02")

    fred = FREDAdapter()
    macro = await fred.fetch_series("CPIAUCSL", "2020-01-01", "2024-01-01")

Ref: specs/03-universe-and-data.md §3.2 — adapter layer is the only place
that makes outbound calls.
Ref: T-01-02, T-01-03, T-01-06
"""

from midas.fabric.adapters.base import (
    AdapterError,
    AuthenticationError,
    BaseAdapter,
    RateLimitExceeded,
)
from midas.fabric.adapters.eodhd import EODHDAdapter
from midas.fabric.adapters.fred import FREDAdapter
from midas.fabric.adapters.yahoo import YahooFinanceAdapter

__all__ = [
    # Base classes and errors
    "AdapterError",
    "AuthenticationError",
    "BaseAdapter",
    "RateLimitExceeded",
    # Concrete adapters
    "EODHDAdapter",
    "FREDAdapter",
    "YahooFinanceAdapter",
]
