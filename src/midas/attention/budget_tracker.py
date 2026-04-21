"""Attention budget tracker -- monitors user cognitive load for regime-adaptive disclosure.

Tracks decision time, notification volume, and fatigue signals so the
system can compress routine briefs, batch approvals, and warn the user
when they are approving without reading.

Per specs/09-surfaces-and-attention.md S3:
- Decision-seconds per day
- Decision volume per day / week
- Notification volume by tier
- Time-to-decide distributions
- Fatigue signals (trending up time-to-decide, tap-immediately rate)

The budget does NOT silently hide decisions.  It changes how they are
presented.
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger("midas.attention.budget_tracker")


@dataclass
class AttentionBudget:
    """Snapshot of the user's current attention budget state."""

    decision_seconds_today: float = 0.0
    decisions_today: int = 0
    notifications_by_tier: dict[str, int] = field(default_factory=dict)
    avg_time_to_decide_ms: float = 0.0
    fatigue_score: float = 0.0  # 0-1 where 1 = maximum fatigue

    # Internal tracking -- not part of the public snapshot contract
    _decision_times: list[float] = field(default_factory=list, repr=False)
    _tap_immediately_count: int = 0  # decisions made in < 2 seconds


# Thresholds for fatigue computation.
_TAP_IMMEDIATELY_THRESHOLD_S = 2.0  # decisions faster than this count as "tap-immediately"
_DAILY_DECISION_SECONDS_CEILING = 300.0  # 5 minutes of active decision time
_DAILY_DECISION_COUNT_CEILING = 50  # beyond this, fatigue starts rising faster
_NOTIFICATION_FATIGUE_WEIGHTS: dict[str, float] = {
    "emergency": 3.0,
    "prominent_push": 2.0,
    "standard_push": 1.0,
    "silent_in_app": 0.1,
}


class AttentionBudgetTracker:
    """Tracks user attention load for regime-adaptive disclosure.

    Thread-safety: this class is NOT thread-safe.  In async contexts,
    call from a single event loop or protect with a lock externally.
    """

    def __init__(self, *, daily_decision_seconds_ceiling: float | None = None) -> None:
        self._budget = AttentionBudget()
        self._daily_decision_seconds_ceiling = (
            daily_decision_seconds_ceiling or _DAILY_DECISION_SECONDS_CEILING
        )
        self._day_start: float = time.monotonic()
        self._log = logger.bind(component="AttentionBudgetTracker")

    def record_decision(self, duration_seconds: float, decision_type: str) -> None:
        """Record a user decision event.

        Parameters
        ----------
        duration_seconds:
            How long the user spent on this decision surface.
        decision_type:
            Type of decision (e.g. ``rebalance``, ``tactical_tilt``).
        """
        if not math.isfinite(duration_seconds) or duration_seconds < 0:
            self._log.warning(
                "attention.record_decision.invalid_duration",
                duration=duration_seconds,
                decision_type=decision_type,
            )
            return

        self._budget.decision_seconds_today += duration_seconds
        self._budget.decisions_today += 1
        self._budget._decision_times.append(duration_seconds)

        if duration_seconds < _TAP_IMMEDIATELY_THRESHOLD_S:
            self._budget._tap_immediately_count += 1

        self._log.debug(
            "attention.decision_recorded",
            duration_s=round(duration_seconds, 2),
            decision_type=decision_type,
            total_decisions=self._budget.decisions_today,
            total_seconds=round(self._budget.decision_seconds_today, 1),
        )

    def record_notification(self, tier: str) -> None:
        """Record a notification sent to the user.

        Parameters
        ----------
        tier:
            Notification tier: ``emergency``, ``prominent_push``,
            ``standard_push``, or ``silent_in_app``.
        """
        counts = dict(self._budget.notifications_by_tier)
        counts[tier] = counts.get(tier, 0) + 1
        self._budget.notifications_by_tier = counts

        self._log.debug(
            "attention.notification_recorded",
            tier=tier,
            total_by_tier=counts,
        )

    def compute_budget(self) -> AttentionBudget:
        """Compute and return the current attention budget snapshot.

        Updates the fatigue score and average time-to-decide before
        returning.

        Returns
        -------
        AttentionBudget
            Current state of the user's attention budget.
        """
        self._budget.fatigue_score = self.compute_fatigue()
        self._budget.avg_time_to_decide_ms = self._compute_avg_time_ms()
        return self._budget

    def compute_fatigue(self) -> float:
        """Compute a 0-1 fatigue score from the current session data.

        Fatigue rises from four signals:
        1. Decision time consumed vs ceiling
        2. Decision count vs ceiling
        3. Tap-immediately rate (approving without reading)
        4. Notification overload (weighted by tier)

        Returns
        -------
        float
            Fatigue score in [0, 1].
        """
        components: list[float] = []

        # Signal 1: decision time exhaustion
        if self._daily_decision_seconds_ceiling > 0:
            time_ratio = (
                self._budget.decision_seconds_today / self._daily_decision_seconds_ceiling
            )
            components.append(min(time_ratio, 1.0))

        # Signal 2: decision count exhaustion
        if _DAILY_DECISION_COUNT_CEILING > 0:
            count_ratio = self._budget.decisions_today / _DAILY_DECISION_COUNT_CEILING
            components.append(min(count_ratio, 1.0))

        # Signal 3: tap-immediately rate
        if self._budget.decisions_today > 3:
            tap_rate = self._budget._tap_immediately_count / self._budget.decisions_today
            components.append(min(tap_rate, 1.0))

        # Signal 4: notification overload
        total_notification_weight = 0.0
        for tier, count in self._budget.notifications_by_tier.items():
            weight = _NOTIFICATION_FATIGUE_WEIGHTS.get(tier, 1.0)
            total_notification_weight += weight * count
        # Normalize: 10 weighted notifications = full fatigue contribution
        if total_notification_weight > 0:
            notif_ratio = total_notification_weight / 10.0
            components.append(min(notif_ratio, 1.0))

        if not components:
            return 0.0

        # Weighted average: each component contributes equally.
        # Clamp to [0, 1].
        fatigue = sum(components) / len(components)
        return max(0.0, min(1.0, fatigue))

    def should_suppress_notification(self, tier: str) -> bool:
        """Determine whether a notification should be suppressed.

        Suppression only applies to non-critical tiers.  Emergency
        notifications are never suppressed (they always surface per
        specs/09 S7).

        Parameters
        ----------
        tier:
            Notification tier to evaluate.

        Returns
        -------
        bool
            True if the notification should be suppressed or deferred.
        """
        # Emergency notifications are NEVER suppressed
        if tier == "emergency":
            return False

        budget = self.compute_budget()

        # Suppress routine notifications when fatigue is high
        if tier in ("silent_in_app", "standard_push"):
            return budget.fatigue_score > 0.7

        # Prominent push: suppress only at extreme fatigue
        if tier == "prominent_push":
            return budget.fatigue_score > 0.9

        return False

    def _compute_avg_time_ms(self) -> float:
        """Compute average time-to-decide in milliseconds."""
        times = self._budget._decision_times
        if not times:
            return 0.0
        return (sum(times) / len(times)) * 1000.0

    def reset_daily(self) -> None:
        """Reset daily counters. Called at the start of a new day."""
        self._budget = AttentionBudget()
        self._day_start = time.monotonic()
        self._log.info("attention.budget_reset")
