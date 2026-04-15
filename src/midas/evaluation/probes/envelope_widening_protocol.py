"""
Envelope-Widening Cooldown And Drawdown Lockout Protocol.

T-00-07: Envelope widening is blocked under drawdown lockout, after only 24h since last
widening, or within 72h of a drawdown event above threshold. The Debate agent must be
invoked before the widening action is even presentable.

Ref: specs/08-autonomy-and-trust.md §1, §7
Ref: specs/11-compliance-and-risk.md §3.1
Ref: specs/10-moments-of-truth.md §7
Ref: T-00-07
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class EnvelopeWideningCheck(Enum):
    PASS = auto()
    FAIL_DRAWDOWN_LOCKOUT = auto()
    FAIL_COOLDOWN = auto()
    FAIL_DRAWDOWN_EVENT_WINDOW = auto()
    FAIL_NO_DEBATE_INVOKED = auto()


@dataclass
class EnvelopeWideningResult:
    check: EnvelopeWideningCheck
    cooldown_hours_remaining: float
    hours_since_last_widening: float
    hours_since_drawdown_event: float | None
    drawdown_fraction_of_ceiling: float | None  # None = not computed
    drawdown_lockout_fraction: float  # the threshold being enforced
    debate_invoked: bool
    message: str


@dataclass
class DrawdownEvent:
    event_id: str
    event_time: datetime
    drawdown_fraction: float  # fraction of envelope ceiling at time of event


@dataclass
class EnvelopeChangeRecord:
    change_id: str
    change_time: datetime
    change_type: str  # "widening" or "tightening"
    parameter: str  # e.g., "max_drawdown_ceiling"
    old_value: float
    new_value: float


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class EnvelopeWideningProtocol:
    """Evaluates whether an envelope widening action is currently permissible.

    The protocol enforces four gates:
      1. Drawdown lockout — widening blocked while drawdown exceeds a configurable
         fraction of the envelope ceiling (default 70%).
      2. Cooldown — minimum 24 hours between any two envelope widenings.
      3. Drawdown-event window — minimum 72 hours since the last drawdown event
         above a threshold fraction of the ceiling.
      4. Debate invocation — the Debate agent must have been invoked before the
         widening action is presentable.

    This is a structural probe that verifies the rules are enforceable. The actual
    PACT rules (`env.widening.cooldown`, `env.widening.drawdown_lockout`) are wired
    in M12.
    """

    DEFAULT_DRAWDOWN_LOCKOUT_FRACTION = 0.70  # 70% of envelope ceiling
    DEFAULT_COOLDOWN_HOURS = 24.0
    DEFAULT_DRAWDOWN_EVENT_WINDOW_HOURS = 72.0
    DEFAULT_DRAWDOWN_EVENT_THRESHOLD = 0.50  # events above 50% of ceiling trigger window

    def __init__(
        self,
        cooldown_hours: float = DEFAULT_COOLDOWN_HOURS,
        drawdown_lockout_fraction: float = DEFAULT_DRAWDOWN_LOCKOUT_FRACTION,
        drawdown_event_window_hours: float = DEFAULT_DRAWDOWN_EVENT_WINDOW_HOURS,
        drawdown_event_threshold: float = DEFAULT_DRAWDOWN_EVENT_THRESHOLD,
    ) -> None:
        self.cooldown_hours = cooldown_hours
        self.drawdown_lockout_fraction = drawdown_lockout_fraction
        self.drawdown_event_window_hours = drawdown_event_window_hours
        self.drawdown_event_threshold = drawdown_event_threshold
        self._widening_history: list[EnvelopeChangeRecord] = []
        self._drawdown_events: list[DrawdownEvent] = []

    # -------------------------------------------------------------------------
    # Data-loading interface (used by the probe test)
    # -------------------------------------------------------------------------

    def load_widening_history(self, records: list[EnvelopeChangeRecord]) -> None:
        self._widening_history = sorted(records, key=lambda r: r.change_time)

    def load_drawdown_events(self, events: list[DrawdownEvent]) -> None:
        self._drawdown_events = sorted(events, key=lambda e: e.event_time)

    def add_widening(self, record: EnvelopeChangeRecord) -> None:
        self._widening_history.append(record)

    def add_drawdown_event(self, event: DrawdownEvent) -> None:
        self._drawdown_events.append(event)

    # -------------------------------------------------------------------------
    # Core evaluation
    # -------------------------------------------------------------------------

    def evaluate(
        self,
        current_drawdown_fraction: float,
        debate_invoked: bool,
        now: datetime | None = None,
    ) -> EnvelopeWideningResult:
        """Evaluate whether an envelope widening is permissible at this moment.

        Args:
            current_drawdown_fraction: Current portfolio drawdown as a fraction of the
                envelope drawdown ceiling (e.g. 0.75 = portfolio has drawn down 75%
                of its permitted ceiling).
            debate_invoked: Whether the Debate agent has been invoked before presenting
                the widening action.
            now: Evaluation time (defaults to utcnow). Exists for test determinism.

        Returns EnvelopeWideningResult with the check outcome and diagnostic values.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Gate 1: Drawdown lockout
        if current_drawdown_fraction >= self.drawdown_lockout_fraction:
            return EnvelopeWideningResult(
                check=EnvelopeWideningCheck.FAIL_DRAWDOWN_LOCKOUT,
                cooldown_hours_remaining=self._cooldown_remaining(now),
                hours_since_last_widening=self._hours_since_last_widening(now),
                hours_since_drawdown_event=self._hours_since_last_drawdown_event(now),
                drawdown_fraction_of_ceiling=current_drawdown_fraction,
                drawdown_lockout_fraction=self.drawdown_lockout_fraction,
                debate_invoked=debate_invoked,
                message=f"Drawdown lockout active: drawdown ({current_drawdown_fraction:.1%}) "
                f"exceeds lockout threshold ({self.drawdown_lockout_fraction:.1%}).",
            )

        # Gate 2: Cooldown
        cooldown_remaining = self._cooldown_remaining(now)
        if cooldown_remaining > 0:
            return EnvelopeWideningResult(
                check=EnvelopeWideningCheck.FAIL_COOLDOWN,
                cooldown_hours_remaining=cooldown_remaining,
                hours_since_last_widening=self._hours_since_last_widening(now),
                hours_since_drawdown_event=self._hours_since_last_drawdown_event(now),
                drawdown_fraction_of_ceiling=current_drawdown_fraction,
                drawdown_lockout_fraction=self.drawdown_lockout_fraction,
                debate_invoked=debate_invoked,
                message=f"Cooldown active: {cooldown_remaining:.1f}h remain until next "
                f"widening is permitted (cooldown={self.cooldown_hours}h).",
            )

        # Gate 3: Drawdown event window
        hours_since_event = self._hours_since_last_drawdown_event(now)
        if hours_since_event is not None and hours_since_event < self.drawdown_event_window_hours:
            return EnvelopeWideningResult(
                check=EnvelopeWideningCheck.FAIL_DRAWDOWN_EVENT_WINDOW,
                cooldown_hours_remaining=cooldown_remaining,
                hours_since_last_widening=self._hours_since_last_widening(now),
                hours_since_drawdown_event=hours_since_event,
                drawdown_fraction_of_ceiling=current_drawdown_fraction,
                drawdown_lockout_fraction=self.drawdown_lockout_fraction,
                debate_invoked=debate_invoked,
                message=f"Recent drawdown event: only {hours_since_event:.1f}h since last "
                f"event (window={self.drawdown_event_window_hours}h).",
            )

        # Gate 4: Debate invocation
        if not debate_invoked:
            return EnvelopeWideningResult(
                check=EnvelopeWideningCheck.FAIL_NO_DEBATE_INVOKED,
                cooldown_hours_remaining=cooldown_remaining,
                hours_since_last_widening=self._hours_since_last_widening(now),
                hours_since_drawdown_event=hours_since_event,
                drawdown_fraction_of_ceiling=current_drawdown_fraction,
                drawdown_lockout_fraction=self.drawdown_lockout_fraction,
                debate_invoked=debate_invoked,
                message="Debate agent must be invoked before envelope widening is presentable.",
            )

        return EnvelopeWideningResult(
            check=EnvelopeWideningCheck.PASS,
            cooldown_hours_remaining=0.0,
            hours_since_last_widening=self._hours_since_last_widening(now),
            hours_since_drawdown_event=hours_since_event,
            drawdown_fraction_of_ceiling=current_drawdown_fraction,
            drawdown_lockout_fraction=self.drawdown_lockout_fraction,
            debate_invoked=debate_invoked,
            message="Envelope widening is permissible.",
        )

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _last_widening_time(self, now: datetime) -> datetime | None:
        widening_events = [r for r in self._widening_history if r.change_type == "widening"]
        if not widening_events:
            return None
        return max(widening_events, key=lambda r: r.change_time).change_time

    def _cooldown_remaining(self, now: datetime) -> float:
        last_time = self._last_widening_time(now)
        if last_time is None:
            return 0.0
        elapsed = (now - last_time).total_seconds() / 3600.0
        return max(0.0, self.cooldown_hours - elapsed)

    def _hours_since_last_widening(self, now: datetime) -> float:
        last_time = self._last_widening_time(now)
        if last_time is None:
            return float("inf")
        return (now - last_time).total_seconds() / 3600.0

    def _last_drawdown_event_time(self, now: datetime) -> datetime | None:
        qualifying = [
            e for e in self._drawdown_events if e.drawdown_fraction >= self.drawdown_event_threshold
        ]
        if not qualifying:
            return None
        return max(qualifying, key=lambda e: e.event_time).event_time

    def _hours_since_last_drawdown_event(self, now: datetime) -> float | None:
        last_time = self._last_drawdown_event_time(now)
        if last_time is None:
            return None
        return (now - last_time).total_seconds() / 3600.0
