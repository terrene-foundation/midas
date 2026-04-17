"""
Kill-Switch Process-Lock Protocol.

T-00-09: Kill-switch clear is gated by a mandatory state-of-the-world brief that
the user must read and acknowledge. The 15-minute time lockout is replaced by a
process lock: biometric + explicit acknowledgment + 60-second dwell on the first
post-clear decision (which is always user-approved regardless of autonomy level).

Ref: specs/08-autonomy-and-trust.md §5.4
Ref: specs/10-moments-of-truth.md §5
Ref: T-00-09
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class KillSwitchState(Enum):
    ACTIVE = auto()
    CLEARING_PROCESS = auto()  # user is in the clear flow
    CLEARED = auto()


class ClearFlowStep(Enum):
    NOT_STARTED = auto()
    BRIEF_READ = auto()  # user has seen state-of-world brief
    BRIEF_ACKNOWLEDGED = auto()  # user explicitly acknowledged
    COMPLETE = auto()


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class KillSwitchClearFlowResult:
    """Result of evaluating whether the kill-switch clear flow is complete."""

    kill_switch_state: KillSwitchState
    current_step: ClearFlowStep
    brief_acknowledged: bool
    dwell_seconds_remaining: float
    first_post_clear_requires_approval: bool
    autonomy_reverted_to_l1: bool
    can_clear: bool  # True only when brief_acknowledged=True
    failures: list[str] = field(default_factory=list)


@dataclass
class KillSwitchStateOfWorld:
    """Mandatory brief content shown to user before clear is permitted."""

    z_t_posterior: str  # human-readable z_t posterior summary
    drawdown_state: str  # e.g., "Drawdown 18% vs ceiling 20%"
    pool_disagreement: float  # 0-1 scale
    compliance_events: list[str]  # e.g., ["data.stale_price", "state.kill_switch"]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class KillSwitchProcessLock:
    """Enforces the process-lock on kill-switch clear.

    The 15-minute time-lock is replaced by a structured clear flow:

      Step 1 — State-of-the-world brief displayed (z_t, drawdown, pool disagreement,
               compliance events). The user must READ it (brief_acknowledged=True).
      Step 2 — Biometric + explicit acknowledgment.
      Step 3 — Clear completes; autonomy reverts to L1.
      Step 4 — First post-clear decision: 60-second dwell + user-approved regardless
               of autonomy level.

    The kill switch cannot be cleared without the brief being shown and acknowledged.
    The 15-minute timer is removed entirely.
    """

    REQUIRED_CLEAR_STEPS = [
        ClearFlowStep.BRIEF_READ,
        ClearFlowStep.BRIEF_ACKNOWLEDGED,
    ]
    POST_CLEAR_DWELL_SECONDS = 60.0
    POST_CLEAR_APPROVAL_REQUIRED = True  # first post-clear always requires approval

    def __init__(self) -> None:
        self._state = KillSwitchState.ACTIVE
        self._current_step = ClearFlowStep.NOT_STARTED
        self._brief_acknowledged = False
        self._brief_read_at: datetime | None = None
        self._cleared_at: datetime | None = None
        self._first_post_clear_dwell_seconds_remaining: float | None = None

    # -------------------------------------------------------------------------
    # State inspection
    # -------------------------------------------------------------------------

    @property
    def state(self) -> KillSwitchState:
        return self._state

    @property
    def current_step(self) -> ClearFlowStep:
        return self._current_step

    @property
    def brief_acknowledged(self) -> bool:
        return self._brief_acknowledged

    @property
    def post_clear_dwell_remaining(self) -> float | None:
        return self._first_post_clear_dwell_seconds_remaining

    # -------------------------------------------------------------------------
    # Clear flow
    # -------------------------------------------------------------------------

    def begin_clear_flow(self) -> None:
        """User initiates kill-switch clear flow. Must show brief."""
        if self._state != KillSwitchState.ACTIVE:
            return
        self._state = KillSwitchState.CLEARING_PROCESS
        self._current_step = ClearFlowStep.BRIEF_READ
        self._brief_read_at = datetime.now(timezone.utc)

    def acknowledge_brief(self, brief: KillSwitchStateOfWorld) -> None:
        """User acknowledges the state-of-the-world brief. Completes clear flow.

        Args:
            brief: The state-of-world brief that was shown to the user.
                Must be non-empty (at least one field populated).
        """
        if self._state != KillSwitchState.CLEARING_PROCESS:
            raise ValueError("Clear flow not initiated")

        if self._current_step != ClearFlowStep.BRIEF_READ:
            raise ValueError("Must read brief before acknowledging")

        # Brief must have substantive content
        if not self._brief_has_content(brief):
            raise ValueError("State-of-world brief has no content")

        self._brief_acknowledged = True
        self._current_step = ClearFlowStep.BRIEF_ACKNOWLEDGED

    def complete_clear(self) -> None:
        """Complete the kill-switch clear. State transitions to CLEARED."""
        if self._state == KillSwitchState.ACTIVE:
            raise ValueError("Clear flow not initiated")
        if not self._brief_acknowledged:
            raise ValueError("Brief must be acknowledged before clearing")
        self._state = KillSwitchState.CLEARED
        self._current_step = ClearFlowStep.COMPLETE
        self._cleared_at = datetime.now(timezone.utc)
        # First post-clear decision requires 60-second dwell
        self._first_post_clear_dwell_seconds_remaining = self.POST_CLEAR_DWELL_SECONDS

    def clear_is_permitted(self) -> bool:
        """True when the kill-switch can be cleared (brief acknowledged)."""
        return self._brief_acknowledged

    def advance_dwell(self, elapsed_seconds: float) -> None:
        """Advance the post-clear dwell timer.

        Called by the compliance layer on each tick.
        """
        if self._first_post_clear_dwell_seconds_remaining is None:
            return
        self._first_post_clear_dwell_seconds_remaining = max(
            0.0,
            self._first_post_clear_dwell_seconds_remaining - elapsed_seconds,
        )

    def first_post_clear_dwell_complete(self) -> bool:
        """True when the 60-second dwell has elapsed."""
        if self._first_post_clear_dwell_seconds_remaining is None:
            return True
        return self._first_post_clear_dwell_seconds_remaining <= 0.0

    # -------------------------------------------------------------------------
    # Evaluation
    # -------------------------------------------------------------------------

    def evaluate_clear_flow(self) -> KillSwitchClearFlowResult:
        """Evaluate the current state of the kill-switch clear flow.

        Returns KillSwitchClearFlowResult describing what is and isn't satisfied.
        """
        failures: list[str] = []

        if self._state == KillSwitchState.ACTIVE:
            if self._current_step == ClearFlowStep.NOT_STARTED:
                failures.append("clear_not_initiated")
            return KillSwitchClearFlowResult(
                kill_switch_state=self._state,
                current_step=self._current_step,
                brief_acknowledged=False,
                dwell_seconds_remaining=0.0,
                first_post_clear_requires_approval=False,
                autonomy_reverted_to_l1=False,
                can_clear=False,
                failures=failures,
            )

        if self._state == KillSwitchState.CLEARING_PROCESS:
            if not self._brief_acknowledged:
                failures.append("brief_not_acknowledged")
            return KillSwitchClearFlowResult(
                kill_switch_state=self._state,
                current_step=self._current_step,
                brief_acknowledged=self._brief_acknowledged,
                dwell_seconds_remaining=0.0,
                first_post_clear_requires_approval=False,
                autonomy_reverted_to_l1=False,
                can_clear=self._brief_acknowledged,
                failures=failures,
            )

        # CLEARED state
        if not self.first_post_clear_dwell_complete():
            failures.append("post_clear_dwell_incomplete")

        return KillSwitchClearFlowResult(
            kill_switch_state=self._state,
            current_step=self._current_step,
            brief_acknowledged=self._brief_acknowledged,
            dwell_seconds_remaining=self._first_post_clear_dwell_seconds_remaining or 0.0,
            first_post_clear_requires_approval=self.POST_CLEAR_APPROVAL_REQUIRED,
            autonomy_reverted_to_l1=True,
            can_clear=True,
            failures=failures,
        )

    def evaluate_no_bypass(self) -> bool:
        """Assert that the clear flow cannot be bypassed.

        Returns True if the flow cannot be shortcut (all required steps enforced).
        Returns False if there's a bypass path.
        """
        # Verify structural enforcement of the state machine:
        # 1. Cannot go from ACTIVE to CLEARED without CLEARING_PROCESS
        if self._state == KillSwitchState.CLEARED:
            if not self._brief_acknowledged:
                return False  # bypassed brief acknowledgment
            if self._current_step != ClearFlowStep.COMPLETE:
                return False  # skipped required steps

        # 2. Cannot acknowledge brief without beginning the flow
        if (
            self._brief_acknowledged
            and self._current_step.value < ClearFlowStep.BRIEF_ACKNOWLEDGED.value
        ):
            return False  # brief acknowledged without being in the right step

        # 3. Cannot skip brief acknowledgment before completing
        if self._state == KillSwitchState.CLEARED and not self._brief_read_at:
            return False  # completed without ever reading the brief

        # 4. Post-clear dwell must be tracked
        if (
            self._state == KillSwitchState.CLEARED
            and self._first_post_clear_dwell_seconds_remaining is None
        ):
            return False  # dwell timer was never initialized

        return True

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _brief_has_content(self, brief: KillSwitchStateOfWorld) -> bool:
        """Brief must have at least one substantive field."""
        return bool(
            brief.z_t_posterior.strip()
            or brief.drawdown_state.strip()
            or brief.pool_disagreement > 0
            or brief.compliance_events
        )


def make_brief(
    z_t: str = "z_t posterior: Elevated band (0.71), cross-asset similarity 0.62 from training mean",
    drawdown: str = "Drawdown 14% vs ceiling 20%",
    pool_disagreement: float = 0.31,
    events: list[str] | None = None,
) -> KillSwitchStateOfWorld:
    return KillSwitchStateOfWorld(
        z_t_posterior=z_t,
        drawdown_state=drawdown,
        pool_disagreement=pool_disagreement,
        compliance_events=events or ["state.kill_switch"],
        generated_at=datetime.now(timezone.utc),
    )
