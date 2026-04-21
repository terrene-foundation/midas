"""Execution algorithm catalog for parent-to-child order decomposition.

Each algorithm decomposes a parent order into a schedule of child orders
based on its strategy (VWAP, TWAP, POV, etc.). The execution head
(``05-`` T-05-14 pool) selects per (order_size / ADV, regime, tier, deadline).

Ref: specs/13-execution-cost-and-microstructure.md S4
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger("midas.execution.algorithms")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Order:
    """A parent order to be decomposed into child orders.

    Attributes
    ----------
    ticker:
        Instrument symbol.
    side:
        ``"BUY"`` or ``"SELL"``.
    quantity:
        Total number of shares.
    order_type:
        Order type (``"LMT"``, ``"MKT"``, etc.).
    limit_price:
        Limit price for LMT orders. Zero for market orders.
    urgency:
        Execution urgency (``"low"``, ``"medium"``, ``"high"``).
    deadline_utc:
        Hard deadline for full execution. If None, the algorithm
        chooses a default window.
    """

    ticker: str
    side: str
    quantity: float
    order_type: str = "LMT"
    limit_price: float = 0.0
    urgency: str = "medium"
    deadline_utc: str | None = None


@dataclass
class ChildOrder:
    """A single child order in an execution schedule.

    Attributes
    ----------
    ticker:
        Instrument symbol (inherited from parent).
    side:
        ``"BUY"`` or ``"SELL"`` (inherited from parent).
    quantity:
        Number of shares for this child.
    order_type:
        Order type for this child.
    limit_price:
        Limit price. Zero means use market.
    tif:
        Time-in-force (``"DAY"``, ``"IOC"``, ``"GTC"``).
    scheduled_time:
        ISO timestamp for when this child should be submitted.
    venue:
        Venue preference (``"SMART"``, primary exchange, etc.).
    participation_rate:
        Target participation rate for this child (0.0-1.0).
    sequence:
        Ordinal position in the schedule (0-indexed).
    """

    ticker: str
    side: str
    quantity: float
    order_type: str = "LMT"
    limit_price: float = 0.0
    tif: str = "DAY"
    scheduled_time: str = ""
    venue: str = "SMART"
    participation_rate: float = 0.0
    sequence: int = 0


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ExecutionAlgorithm(ABC):
    """Protocol for execution algorithms.

    Each algorithm decomposes a parent ``Order`` into a list of
    ``ChildOrder`` instances based on the algorithm's strategy.
    """

    name: str

    @abstractmethod
    def decompose(self, order: Order, params: dict[str, Any]) -> list[ChildOrder]:
        """Decompose a parent order into child orders.

        Parameters
        ----------
        order:
            The parent order to decompose.
        params:
            Algorithm-specific parameters (e.g. ``num_slices``,
            ``duration_minutes``, ``target_participation``).

        Returns
        -------
            Ordered list of child orders forming the execution schedule.
        """
        ...

    def participation_rate(self, volume: float, params: dict[str, Any]) -> float:
        """Return the target participation rate for a given volume.

        Parameters
        ----------
        volume:
            Expected market volume at the time of execution.
        params:
            Algorithm-specific parameters.

        Returns
        -------
            Participation rate as a fraction (0.0 to 1.0).
        """
        target = float(params.get("target_participation", 0.05))
        cap = float(params.get("participation_cap", 0.05))
        return min(target, cap)


# ---------------------------------------------------------------------------
# Algorithm implementations
# ---------------------------------------------------------------------------


class VWAPAlgorithm(ExecutionAlgorithm):
    """Volume-Weighted Average Price algorithm.

    Decomposes the parent order into child orders that follow a
    historical volume curve throughout the trading session. Slices
    are weighted by expected volume per time bucket.

    Preferred for: medium-size orders, Calm/Elevated band, no
    directional urgency.
    """

    name = "VWAP"

    def decompose(self, order: Order, params: dict[str, Any]) -> list[ChildOrder]:
        num_slices = int(params.get("num_slices", 10))
        duration_minutes = int(params.get("duration_minutes", 390))  # full session
        volume_profile = params.get("volume_profile")

        if volume_profile is None:
            # Default U-shaped volume profile (higher at open and close)
            t = np.linspace(0, 1, num_slices)
            profile = 1.0 - 2.0 * (t - 0.5) ** 2  # parabolic U-shape
            profile = profile / profile.sum()
        else:
            profile = np.array(volume_profile[:num_slices])
            if len(profile) < num_slices:
                # Pad with uniform distribution
                pad = np.full(num_slices - len(profile), 1.0 / num_slices)
                profile = np.concatenate([profile, pad])
            profile = profile / profile.sum()

        now = datetime.now(timezone.utc)
        children: list[ChildOrder] = []

        for i in range(num_slices):
            slice_qty = round(order.quantity * float(profile[i]), 2)
            if slice_qty <= 0:
                continue

            minutes_offset = int(duration_minutes * (i / num_slices))
            scheduled = _minutes_from_now(now, minutes_offset)

            children.append(
                ChildOrder(
                    ticker=order.ticker,
                    side=order.side,
                    quantity=slice_qty,
                    order_type=order.order_type,
                    limit_price=order.limit_price,
                    tif="DAY",
                    scheduled_time=scheduled,
                    venue="SMART",
                    participation_rate=float(profile[i])
                    * num_slices
                    * 0.05,  # normalized
                    sequence=i,
                )
            )

        return children


class TWAPAlgorithm(ExecutionAlgorithm):
    """Time-Weighted Average Price algorithm.

    Splits the parent order into equal-sized slices executed at
    uniform time intervals. Simpler than VWAP but does not adapt
    to intraday volume patterns.

    Preferred for: medium-size orders, Calm band, any duration.
    """

    name = "TWAP"

    def decompose(self, order: Order, params: dict[str, Any]) -> list[ChildOrder]:
        num_slices = int(params.get("num_slices", 10))
        duration_minutes = int(params.get("duration_minutes", 390))

        slice_qty = round(order.quantity / num_slices, 2)
        now = datetime.now(timezone.utc)
        interval = duration_minutes / num_slices
        children: list[ChildOrder] = []

        for i in range(num_slices):
            minutes_offset = int(interval * i)
            scheduled = _minutes_from_now(now, minutes_offset)

            # Last slice gets the remainder to avoid rounding drift
            qty = slice_qty if i < num_slices - 1 else order.quantity - slice_qty * (num_slices - 1)
            qty = max(round(qty, 2), 0.0)

            if qty <= 0:
                continue

            children.append(
                ChildOrder(
                    ticker=order.ticker,
                    side=order.side,
                    quantity=qty,
                    order_type=order.order_type,
                    limit_price=order.limit_price,
                    tif="DAY",
                    scheduled_time=scheduled,
                    venue="SMART",
                    participation_rate=float(params.get("target_participation", 0.05)),
                    sequence=i,
                )
            )

        return children


class POVAlgorithm(ExecutionAlgorithm):
    """Percentage of Volume algorithm.

    Maintains a target participation rate relative to real-time
    market volume. Child order sizes are dynamic and depend on
    observed volume. The decomposition produces placeholder children
    that are re-sized at execution time.

    Preferred for: medium-to-large orders, liquidity-sensitive.
    """

    name = "POV"

    def decompose(self, order: Order, params: dict[str, Any]) -> list[ChildOrder]:
        target_participation = float(params.get("target_participation", 0.05))
        num_slices = int(params.get("num_slices", 10))
        duration_minutes = int(params.get("duration_minutes", 390))

        now = datetime.now(timezone.utc)
        interval = duration_minutes / num_slices
        children: list[ChildOrder] = []

        for i in range(num_slices):
            minutes_offset = int(interval * i)
            scheduled = _minutes_from_now(now, minutes_offset)

            # Placeholder quantity; re-sized at execution based on actual volume
            placeholder_qty = round(order.quantity / num_slices, 2)

            children.append(
                ChildOrder(
                    ticker=order.ticker,
                    side=order.side,
                    quantity=placeholder_qty,
                    order_type=order.order_type,
                    limit_price=order.limit_price,
                    tif="DAY",
                    scheduled_time=scheduled,
                    venue="SMART",
                    participation_rate=target_participation,
                    sequence=i,
                )
            )

        return children

    def participation_rate(self, volume: float, params: dict[str, Any]) -> float:
        target = float(params.get("target_participation", 0.05))
        cap = float(params.get("participation_cap", 0.05))
        # POV always targets the configured rate, capped
        return min(target, cap)


class ImplementationShortfallAlgorithm(ExecutionAlgorithm):
    """Implementation Shortfall (Almgren-Chriss optimal) algorithm.

    Minimizes total market impact by choosing a front-loaded or
    back-loaded schedule based on trader aversion parameter. Higher
    aversion -> more front-loaded (execute quickly to reduce timing
    risk). Lower aversion -> more back-loaded (spread out to reduce
    impact).

    Preferred for: large orders where impact dominates.
    """

    name = "ImplementationShortfall"

    def decompose(self, order: Order, params: dict[str, Any]) -> list[ChildOrder]:
        num_slices = int(params.get("num_slices", 10))
        duration_minutes = int(params.get("duration_minutes", 390))
        # Trader aversion: 0 = purely back-loaded, 1 = purely front-loaded
        aversion = float(params.get("aversion", 0.5))

        # Exponential decay schedule parameterized by aversion
        # Higher aversion -> steeper decay (more front-loaded)
        t = np.linspace(0, 1, num_slices)
        decay_rate = 1.0 + aversion * 5.0  # range: [1.0, 6.0]
        weights = np.exp(-decay_rate * t)
        weights = weights / weights.sum()

        now = datetime.now(timezone.utc)
        children: list[ChildOrder] = []

        for i in range(num_slices):
            qty = round(order.quantity * float(weights[i]), 2)
            if qty <= 0:
                continue

            minutes_offset = int(duration_minutes * (i / num_slices))
            scheduled = _minutes_from_now(now, minutes_offset)

            children.append(
                ChildOrder(
                    ticker=order.ticker,
                    side=order.side,
                    quantity=qty,
                    order_type=order.order_type,
                    limit_price=order.limit_price,
                    tif="DAY",
                    scheduled_time=scheduled,
                    venue="SMART",
                    participation_rate=float(weights[i]) * num_slices * 0.05,
                    sequence=i,
                )
            )

        return children


class LiquiditySeekingAlgorithm(ExecutionAlgorithm):
    """Liquidity-seeking / passive midpoint algorithm.

    Passively rests at the midpoint with periodic repricing. Targets
    dark pools and hidden liquidity venues. Low participation rate to
    minimize footprint.

    Preferred for: any size when cost is the binding constraint.
    """

    name = "LiquiditySeeking"

    def decompose(self, order: Order, params: dict[str, Any]) -> list[ChildOrder]:
        num_slices = int(params.get("num_slices", 6))
        duration_minutes = int(params.get("duration_minutes", 390))
        reprice_interval_minutes = int(params.get("reprice_interval_minutes", 30))

        slice_qty = round(order.quantity / num_slices, 2)
        now = datetime.now(timezone.utc)
        interval = max(reprice_interval_minutes, duration_minutes / num_slices)
        children: list[ChildOrder] = []

        for i in range(num_slices):
            minutes_offset = int(interval * i)
            scheduled = _minutes_from_now(now, minutes_offset)

            qty = slice_qty if i < num_slices - 1 else order.quantity - slice_qty * (num_slices - 1)
            qty = max(round(qty, 2), 0.0)

            if qty <= 0:
                continue

            children.append(
                ChildOrder(
                    ticker=order.ticker,
                    side=order.side,
                    quantity=qty,
                    order_type="LMT",
                    # No limit price — set at execution time to midpoint
                    limit_price=0.0,
                    tif="DAY",
                    scheduled_time=scheduled,
                    venue="SMART",
                    participation_rate=0.01,  # minimal footprint
                    sequence=i,
                )
            )

        return children

    def participation_rate(self, volume: float, params: dict[str, Any]) -> float:
        # Liquidity-seeking uses minimal participation
        return min(float(params.get("target_participation", 0.01)), 0.02)


class AuctionParticipantAlgorithm(ExecutionAlgorithm):
    """Auction participation algorithm for opening/closing auctions.

    Submits MOO (Market-On-Open) or MOC (Market-On-Close) orders
    for index-rebalancing days. No child-order decomposition needed;
    the single order goes directly to the auction.

    Preferred for: opening/closing auctions on rebalancing days.
    """

    name = "AuctionParticipant"

    def decompose(self, order: Order, params: dict[str, Any]) -> list[ChildOrder]:
        auction_type = params.get("auction_type", "close")  # "open" or "close"
        now = datetime.now(timezone.utc)

        # Auction orders are single-shot: one child = full quantity
        order_type = "MOO" if auction_type == "open" else "MOC"

        scheduled = params.get("scheduled_time", "")
        if not scheduled:
            # Default: next market open (9:30 ET) or close (16:00 ET)
            scheduled = _minutes_from_now(now, 1)  # submit shortly before auction

        return [
            ChildOrder(
                ticker=order.ticker,
                side=order.side,
                quantity=order.quantity,
                order_type=order_type,
                limit_price=order.limit_price,
                tif="DAY",
                scheduled_time=scheduled,
                venue="PRIMARY",
                participation_rate=0.0,  # auction, no continuous participation
                sequence=0,
            )
        ]

    def participation_rate(self, volume: float, params: dict[str, Any]) -> float:
        # Auction participation is not measured against continuous volume
        return 0.0


# ---------------------------------------------------------------------------
# Algorithm registry
# ---------------------------------------------------------------------------

ALGORITHM_CATALOG: dict[str, type[ExecutionAlgorithm]] = {
    "VWAP": VWAPAlgorithm,
    "TWAP": TWAPAlgorithm,
    "POV": POVAlgorithm,
    "ImplementationShortfall": ImplementationShortfallAlgorithm,
    "LiquiditySeeking": LiquiditySeekingAlgorithm,
    "AuctionParticipant": AuctionParticipantAlgorithm,
}


def get_algorithm(name: str) -> ExecutionAlgorithm:
    """Return an instance of the named algorithm.

    Parameters
    ----------
    name:
        Algorithm name (case-sensitive). Must be in ``ALGORITHM_CATALOG``.

    Raises
    ------
    ValueError
        If the algorithm name is not recognized.
    """
    cls = ALGORITHM_CATALOG.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown algorithm '{name}'. "
            f"Available: {sorted(ALGORITHM_CATALOG.keys())}"
        )
    return cls()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minutes_from_now(now: datetime, minutes: int) -> str:
    """Return an ISO timestamp ``minutes`` from ``now``."""
    from datetime import timedelta

    return (now + timedelta(minutes=minutes)).isoformat()
