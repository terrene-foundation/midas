"""Tier 1 tests for execution algorithm catalog.

Ref: specs/13-execution-cost-and-microstructure.md S4
Ref: src/midas/execution/algorithms.py
"""

import pytest

from midas.execution.algorithms import (
    ALGORITHM_CATALOG,
    AuctionParticipantAlgorithm,
    ChildOrder,
    ExecutionAlgorithm,
    ImplementationShortfallAlgorithm,
    LiquiditySeekingAlgorithm,
    Order,
    POVAlgorithm,
    TWAPAlgorithm,
    VWAPAlgorithm,
    get_algorithm,
)


@pytest.fixture
def buy_order():
    return Order(
        ticker="SPY",
        side="BUY",
        quantity=1000,
        order_type="LMT",
        limit_price=450.0,
    )


@pytest.fixture
def sell_order():
    return Order(
        ticker="QQQ",
        side="SELL",
        quantity=500,
        order_type="LMT",
        limit_price=380.0,
    )


# ---------------------------------------------------------------------------
# Order / ChildOrder dataclass
# ---------------------------------------------------------------------------


class TestOrderDataclass:
    def test_order_defaults(self):
        order = Order(ticker="SPY", side="BUY", quantity=100)
        assert order.order_type == "LMT"
        assert order.limit_price == 0.0
        assert order.urgency == "medium"
        assert order.deadline_utc is None

    def test_child_order_defaults(self):
        child = ChildOrder(ticker="SPY", side="BUY", quantity=100, sequence=0)
        assert child.tif == "DAY"
        assert child.venue == "SMART"
        assert child.participation_rate == 0.0


# ---------------------------------------------------------------------------
# VWAPAlgorithm
# ---------------------------------------------------------------------------


class TestVWAPAlgorithm:
    def test_decompose_returns_children(self, buy_order):
        algo = VWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 5, "duration_minutes": 60})
        assert len(children) == 5
        assert algo.name == "VWAP"

    def test_total_quantity_preserved(self, buy_order):
        algo = VWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 5})
        total = sum(c.quantity for c in children)
        assert abs(total - buy_order.quantity) < 1.0  # rounding tolerance

    def test_children_inherit_ticker_and_side(self, buy_order):
        algo = VWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 3})
        for child in children:
            assert child.ticker == "SPY"
            assert child.side == "BUY"

    def test_custom_volume_profile(self, buy_order):
        algo = VWAPAlgorithm()
        profile = [0.3, 0.25, 0.2, 0.15, 0.1]
        children = algo.decompose(
            buy_order,
            {"num_slices": 5, "volume_profile": profile},
        )
        assert len(children) == 5
        # First slice should be the largest
        assert children[0].quantity > children[-1].quantity

    def test_default_profile_weights_vary(self, buy_order):
        algo = VWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 10})
        # The default profile should produce varying slice sizes (not uniform)
        quantities = [c.quantity for c in children]
        assert len(set(round(q, 1) for q in quantities)) > 1  # not all equal

    def test_sequence_numbers(self, buy_order):
        algo = VWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 5})
        for i, child in enumerate(children):
            assert child.sequence == i

    def test_scheduled_times_increasing(self, buy_order):
        algo = VWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 5, "duration_minutes": 390})
        for i in range(len(children) - 1):
            assert children[i].scheduled_time <= children[i + 1].scheduled_time


# ---------------------------------------------------------------------------
# TWAPAlgorithm
# ---------------------------------------------------------------------------


class TestTWAPAlgorithm:
    def test_decompose_returns_children(self, buy_order):
        algo = TWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 5})
        assert len(children) == 5
        assert algo.name == "TWAP"

    def test_equal_slice_sizes(self, buy_order):
        algo = TWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 10})
        # All slices except last should be equal
        for i in range(len(children) - 1):
            assert abs(children[i].quantity - children[0].quantity) < 0.01

    def test_total_quantity_preserved(self, buy_order):
        algo = TWAPAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 7})
        total = sum(c.quantity for c in children)
        assert abs(total - buy_order.quantity) < 1.0

    def test_works_for_sell(self, sell_order):
        algo = TWAPAlgorithm()
        children = algo.decompose(sell_order, {"num_slices": 4})
        assert all(c.side == "SELL" for c in children)
        assert all(c.ticker == "QQQ" for c in children)


# ---------------------------------------------------------------------------
# POVAlgorithm
# ---------------------------------------------------------------------------


class TestPOVAlgorithm:
    def test_decompose_returns_children(self, buy_order):
        algo = POVAlgorithm()
        children = algo.decompose(
            buy_order,
            {"num_slices": 5, "target_participation": 0.03},
        )
        assert len(children) == 5
        assert algo.name == "POV"

    def test_target_participation_set(self, buy_order):
        algo = POVAlgorithm()
        children = algo.decompose(
            buy_order,
            {"num_slices": 5, "target_participation": 0.04},
        )
        for child in children:
            assert child.participation_rate == 0.04

    def test_custom_participation_rate_method(self):
        algo = POVAlgorithm()
        rate = algo.participation_rate(
            1_000_000,
            {"target_participation": 0.04, "participation_cap": 0.05},
        )
        assert rate == 0.04

    def test_participation_rate_capped(self):
        algo = POVAlgorithm()
        rate = algo.participation_rate(
            1_000_000,
            {"target_participation": 0.10, "participation_cap": 0.05},
        )
        assert rate == 0.05


# ---------------------------------------------------------------------------
# ImplementationShortfallAlgorithm
# ---------------------------------------------------------------------------


class TestImplementationShortfallAlgorithm:
    def test_decompose_returns_children(self, buy_order):
        algo = ImplementationShortfallAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 8})
        assert len(children) == 8
        assert algo.name == "ImplementationShortfall"

    def test_total_quantity_preserved(self, buy_order):
        algo = ImplementationShortfallAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 6})
        total = sum(c.quantity for c in children)
        assert abs(total - buy_order.quantity) < 1.0

    def test_high_aversion_front_loaded(self, buy_order):
        algo = ImplementationShortfallAlgorithm()
        children = algo.decompose(
            buy_order,
            {"num_slices": 10, "aversion": 0.9},
        )
        # First child should be significantly larger than last
        assert children[0].quantity > children[-1].quantity

    def test_low_aversion_less_front_loaded_than_high(self, buy_order):
        algo = ImplementationShortfallAlgorithm()
        high = algo.decompose(buy_order, {"num_slices": 10, "aversion": 0.9})
        low = algo.decompose(buy_order, {"num_slices": 10, "aversion": 0.1})
        # High aversion should have a larger first-to-last ratio than low aversion
        high_ratio = high[0].quantity / max(high[-1].quantity, 0.01)
        low_ratio = low[0].quantity / max(low[-1].quantity, 0.01)
        assert high_ratio > low_ratio


# ---------------------------------------------------------------------------
# LiquiditySeekingAlgorithm
# ---------------------------------------------------------------------------


class TestLiquiditySeekingAlgorithm:
    def test_decompose_returns_children(self, buy_order):
        algo = LiquiditySeekingAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 4})
        assert len(children) == 4
        assert algo.name == "LiquiditySeeking"

    def test_total_quantity_preserved(self, buy_order):
        algo = LiquiditySeekingAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 4})
        total = sum(c.quantity for c in children)
        assert abs(total - buy_order.quantity) < 1.0

    def test_low_participation_rate(self, buy_order):
        algo = LiquiditySeekingAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 4})
        for child in children:
            assert child.participation_rate <= 0.02

    def test_no_limit_price_set(self, buy_order):
        algo = LiquiditySeekingAlgorithm()
        children = algo.decompose(buy_order, {"num_slices": 4})
        for child in children:
            assert child.limit_price == 0.0  # set at execution time

    def test_participation_rate_method(self):
        algo = LiquiditySeekingAlgorithm()
        rate = algo.participation_rate(1_000_000, {})
        assert rate <= 0.02


# ---------------------------------------------------------------------------
# AuctionParticipantAlgorithm
# ---------------------------------------------------------------------------


class TestAuctionParticipantAlgorithm:
    def test_close_auction_single_child(self, buy_order):
        algo = AuctionParticipantAlgorithm()
        children = algo.decompose(buy_order, {"auction_type": "close"})
        assert len(children) == 1
        assert children[0].order_type == "MOC"
        assert children[0].quantity == buy_order.quantity
        assert algo.name == "AuctionParticipant"

    def test_open_auction_single_child(self, buy_order):
        algo = AuctionParticipantAlgorithm()
        children = algo.decompose(buy_order, {"auction_type": "open"})
        assert len(children) == 1
        assert children[0].order_type == "MOO"

    def test_auction_primary_venue(self, buy_order):
        algo = AuctionParticipantAlgorithm()
        children = algo.decompose(buy_order, {"auction_type": "close"})
        assert children[0].venue == "PRIMARY"

    def test_zero_participation_rate(self):
        algo = AuctionParticipantAlgorithm()
        rate = algo.participation_rate(1_000_000, {})
        assert rate == 0.0


# ---------------------------------------------------------------------------
# Algorithm registry
# ---------------------------------------------------------------------------


class TestAlgorithmRegistry:
    def test_all_algorithms_registered(self):
        expected = {"VWAP", "TWAP", "POV", "ImplementationShortfall", "LiquiditySeeking", "AuctionParticipant"}
        assert set(ALGORITHM_CATALOG.keys()) == expected

    def test_get_algorithm_returns_instance(self):
        algo = get_algorithm("VWAP")
        assert isinstance(algo, VWAPAlgorithm)
        assert isinstance(algo, ExecutionAlgorithm)

    def test_get_algorithm_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown algorithm"):
            get_algorithm("NonExistent")

    def test_all_algorithms_instantiate(self):
        for name, cls in ALGORITHM_CATALOG.items():
            instance = cls()
            assert instance.name == name


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """Verify every algorithm implements the ExecutionAlgorithm protocol."""

    @pytest.mark.parametrize("algo_name", list(ALGORITHM_CATALOG.keys()))
    def test_has_name(self, algo_name):
        algo = get_algorithm(algo_name)
        assert hasattr(algo, "name")
        assert isinstance(algo.name, str)

    @pytest.mark.parametrize("algo_name", list(ALGORITHM_CATALOG.keys()))
    def test_decompose_returns_children(self, algo_name):
        algo = get_algorithm(algo_name)
        order = Order(ticker="TEST", side="BUY", quantity=1000)
        children = algo.decompose(order, {})
        assert isinstance(children, list)
        for child in children:
            assert isinstance(child, ChildOrder)
            assert child.ticker == "TEST"
            assert child.side == "BUY"

    @pytest.mark.parametrize("algo_name", list(ALGORITHM_CATALOG.keys()))
    def test_has_participation_rate_method(self, algo_name):
        algo = get_algorithm(algo_name)
        rate = algo.participation_rate(1_000_000, {})
        assert isinstance(rate, float)
        assert 0.0 <= rate <= 1.0
