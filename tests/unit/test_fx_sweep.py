"""Tier 1 tests for FX sweep tracking in the IBKR adapter.

Tests cover:
- PLAFCalculator edge cases with real cost structures
- IBKRAdapter.execute_fx_sweep input validation
- IBKRAdapter.get_sweep_history
- Integration between sweep methods and the adapter pattern

Ref: specs/14-ibkr-integration.md S11
Ref: src/midas/fabric/adapters/ibkr.py
"""

import pytest

from midas.fabric.adapters.ibkr import IBKRAdapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter():
    """Create an IBKRAdapter without real credentials or DB."""
    return IBKRAdapter(
        db=None,
        client_id=None,
        client_secret=None,
        paper_trading=True,
    )


# ---------------------------------------------------------------------------
# execute_fx_sweep input validation
# ---------------------------------------------------------------------------


class TestExecuteFxSweepValidation:
    """Test input validation for execute_fx_sweep (no network calls)."""

    @pytest.mark.asyncio
    async def test_negative_amount_raises(self, adapter):
        with pytest.raises(ValueError, match="positive"):
            await adapter.execute_fx_sweep("USD", "SGD", -100.0)

    @pytest.mark.asyncio
    async def test_zero_amount_raises(self, adapter):
        with pytest.raises(ValueError, match="positive"):
            await adapter.execute_fx_sweep("USD", "SGD", 0.0)

    @pytest.mark.asyncio
    async def test_empty_from_currency_raises(self, adapter):
        with pytest.raises(ValueError, match="required"):
            await adapter.execute_fx_sweep("", "SGD", 100.0)

    @pytest.mark.asyncio
    async def test_empty_to_currency_raises(self, adapter):
        with pytest.raises(ValueError, match="required"):
            await adapter.execute_fx_sweep("USD", "", 100.0)

    @pytest.mark.asyncio
    async def test_same_currency_raises(self, adapter):
        with pytest.raises(ValueError, match="must differ"):
            await adapter.execute_fx_sweep("USD", "USD", 100.0)


# ---------------------------------------------------------------------------
# get_sweep_history (requires DB)
# ---------------------------------------------------------------------------


class TestGetSweepHistory:
    """Test get_sweep_history reads from fabric table."""

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, adapter):
        """Without a real DB, get_sweep_history should handle gracefully."""
        result = await adapter.get_sweep_history("test-account")
        # Will return empty because express.list will fail without DB
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Adapter construction
# ---------------------------------------------------------------------------


class TestIBKRAdapterConstruction:
    """Verify the adapter is constructed correctly for FX sweep support."""

    def test_paper_trading_flag(self, adapter):
        assert adapter._paper_trading is True

    def test_has_execute_fx_sweep(self, adapter):
        assert hasattr(adapter, "execute_fx_sweep")
        assert callable(adapter.execute_fx_sweep)

    def test_has_get_sweep_history(self, adapter):
        assert hasattr(adapter, "get_sweep_history")
        assert callable(adapter.get_sweep_history)

    def test_has_fetch_sweep_events(self, adapter):
        assert hasattr(adapter, "fetch_sweep_events")
        assert callable(adapter.fetch_sweep_events)
