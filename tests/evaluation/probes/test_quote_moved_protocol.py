"""
Tests for T-00-18: Quote-Moved-Since-Brief Protocol.

Tier 2: synthesises a 0.4% mid move between brief and approval in Elevated band;
asserts modal surfaces and auto-execute is blocked.

Ref: specs/10-moments-of-truth.md §6.4
Ref: specs/14-ibkr-integration.md §8.2
Ref: T-00-18
"""

from __future__ import annotations

import pytest

from midas.evaluation.probes.quote_moved_protocol import (
    QuoteMovedProtocol,
    QuoteMovedCheckResult,
    QuoteMovedError,
    RegimeBand,
)


class TestQuoteMovedProtocol:
    """Tier 2 tests for quote-moved protocol."""

    def test_calm_0_5pct_move_within_threshold(self):
        """Move of 0.3% in CALM regime → within 0.5% threshold → auto-execute permitted."""
        protocol = QuoteMovedProtocol()
        result = protocol.check(
            instrument="AAPL",
            regime_band=RegimeBand.CALM,
            brief_mid_price=185.00,
            current_mid_price=185.55,  # 0.3% move
        )

        assert result.threshold_exceeded is False
        assert result.auto_execute_permitted is True
        assert "within" in result.message

    def test_calm_0_6pct_move_exceeds_threshold(self):
        """Move of 0.6% in CALM regime → exceeds 0.5% threshold → auto-execute blocked."""
        protocol = QuoteMovedProtocol()
        result = protocol.check(
            instrument="AAPL",
            regime_band=RegimeBand.CALM,
            brief_mid_price=185.00,
            current_mid_price=186.11,  # 0.6% move
        )

        assert result.threshold_exceeded is True
        assert result.auto_execute_permitted is False
        assert "requires explicit user re-confirm" in result.message

    def test_elevated_0_3pct_move_within_threshold(self):
        """Move of 0.2% in ELEVATED regime → within 0.3% threshold → permitted."""
        protocol = QuoteMovedProtocol()
        result = protocol.check(
            instrument="SPY",
            regime_band=RegimeBand.ELEVATED,
            brief_mid_price=510.00,
            current_mid_price=510.99,  # ~0.19% move
        )

        assert result.threshold_exceeded is False
        assert result.auto_execute_permitted is True

    def test_elevated_0_4pct_move_exceeds_threshold(self):
        """Move of 0.4% in ELEVATED regime → exceeds 0.3% threshold → blocked.

        This is the T-00-18 acceptance criterion: 0.4% mid move in Elevated band
        must surface the modal.
        """
        protocol = QuoteMovedProtocol()
        result = protocol.check(
            instrument="AAPL",
            regime_band=RegimeBand.ELEVATED,
            brief_mid_price=185.00,
            current_mid_price=185.74,  # 0.4% move
        )

        assert result.threshold_exceeded is True
        assert result.auto_execute_permitted is False
        assert result.regime_band == RegimeBand.ELEVATED
        assert result.threshold == 0.003

    def test_urgent_0_2pct_move_exactly_at_threshold(self):
        """Move exactly at 0.2% in URGENT regime → not exceeded (must be strictly below)."""
        protocol = QuoteMovedProtocol()
        result = protocol.check(
            instrument="TSLA",
            regime_band=RegimeBand.URGENT,
            brief_mid_price=250.00,
            current_mid_price=250.50,  # exactly 0.2% move
        )

        # "Exceeds" means strictly greater than — exactly at is NOT exceeded
        assert result.threshold_exceeded is False
        assert result.auto_execute_permitted is True

    def test_urgent_0_15pct_move_within_threshold(self):
        """Move of 0.15% in URGENT regime → within 0.2% threshold → permitted."""
        protocol = QuoteMovedProtocol()
        result = protocol.check(
            instrument="TSLA",
            regime_band=RegimeBand.URGENT,
            brief_mid_price=250.00,
            current_mid_price=250.375,  # 0.15% move
        )

        assert result.threshold_exceeded is False
        assert result.auto_execute_permitted is True

    def test_price_decreases_also_detected(self):
        """Price moving down by more than threshold → also blocked."""
        protocol = QuoteMovedProtocol()
        result = protocol.check(
            instrument="AAPL",
            regime_band=RegimeBand.CALM,
            brief_mid_price=185.00,
            current_mid_price=183.89,  # -0.6% move
        )

        assert result.threshold_exceeded is True
        assert result.auto_execute_permitted is False
        assert result.current_mid_price < result.brief_mid_price

    def test_negative_prices_raise(self):
        """Zero or negative prices → raise ValueError."""
        protocol = QuoteMovedProtocol()
        with pytest.raises(ValueError, match="must be positive"):
            protocol.check("AAPL", RegimeBand.CALM, -1.0, 185.00)

        with pytest.raises(ValueError, match="must be positive"):
            protocol.check("AAPL", RegimeBand.CALM, 185.00, -1.0)

        with pytest.raises(ValueError, match="must be positive"):
            protocol.check("AAPL", RegimeBand.CALM, 0.0, 185.00)

    def test_check_and_raise_raises_on_threshold_exceeded(self):
        """check_and_raise raises QuoteMovedError when threshold exceeded."""
        protocol = QuoteMovedProtocol()
        with pytest.raises(QuoteMovedError) as exc_info:
            protocol.check_and_raise(
                instrument="AAPL",
                regime_band=RegimeBand.ELEVATED,
                brief_mid_price=185.00,
                current_mid_price=185.74,  # 0.4% — exceeds 0.3% threshold
            )

        assert exc_info.value.result.threshold_exceeded is True
        assert exc_info.value.result.instrument == "AAPL"

    def test_check_and_raise_does_not_raise_when_permitted(self):
        """check_and_raise returns result without raising when auto-execute permitted."""
        protocol = QuoteMovedProtocol()
        result = protocol.check_and_raise(
            instrument="AAPL",
            regime_band=RegimeBand.CALM,
            brief_mid_price=185.00,
            current_mid_price=185.30,  # 0.16% — within 0.5% threshold
        )

        assert result.auto_execute_permitted is True

    def test_regime_band_values(self):
        """All three regime bands have distinct thresholds."""
        protocol = QuoteMovedProtocol()
        calm = protocol.threshold_for(RegimeBand.CALM)
        elevated = protocol.threshold_for(RegimeBand.ELEVATED)
        urgent = protocol.threshold_for(RegimeBand.URGENT)

        assert calm == 0.005
        assert elevated == 0.003
        assert urgent == 0.002
        # Stricter regimes have tighter thresholds
        assert calm > elevated > urgent

    def test_custom_thresholds(self):
        """Protocol accepts custom threshold map."""
        custom = {
            RegimeBand.CALM: 0.010,
            RegimeBand.ELEVATED: 0.008,
            RegimeBand.URGENT: 0.005,
        }
        protocol = QuoteMovedProtocol(thresholds=custom)
        assert protocol.threshold_for(RegimeBand.CALM) == 0.010
        assert protocol.threshold_for(RegimeBand.URGENT) == 0.005

    def test_quote_moved_error_carries_result(self):
        """QuoteMovedError.result exposes the full check result."""
        protocol = QuoteMovedProtocol()
        try:
            protocol.check_and_raise(
                instrument="AAPL",
                regime_band=RegimeBand.ELEVATED,
                brief_mid_price=185.00,
                current_mid_price=186.00,  # ~0.54% — exceeds 0.3%
            )
        except QuoteMovedError as e:
            assert e.result.instrument == "AAPL"
            assert e.result.regime_band == RegimeBand.ELEVATED
            assert e.result.price_move_fraction > 0.003
