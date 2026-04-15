"""
Top-Of-Fold Decide-In-10-Seconds Card Protocol.

T-00-08: Every approval screen carries a top-of-fold card that renders an actionable
decision in 10 seconds. The card has: one-line action, one-line strongest counter-evidence,
"what would change my mind" one-liner, and spatially-separated Approve/Debate/Decline
buttons. High-weight briefs force a 3-second dwell before biometric unlock.

Ref: specs/07-evidence-first-decision.md §2
Ref: specs/09-surfaces-and-attention.md §4
Ref: T-00-08
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ButtonAction(Enum):
    APPROVE = auto()
    DEBATE = auto()
    DECLINE = auto()


class DwellState(Enum):
    NOT_STARTED = auto()
    DWELLING = auto()
    READY = auto()
    COMPLETED = auto()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass
class CounterEvidence:
    text: str  # one line — strongest single piece of counter-evidence
    source: str  # provenance pointer: "pool disagreement 0.31", "calibration 0.52 in z_region X"


@dataclass
class WhatWouldChangeMind:
    text: str  # one line — specific threshold or evidence that would flip the call


@dataclass
class TopOfFoldCard:
    """Schema for the top-of-fold decision card.

    The card is the universal header on every approval screen.
    It renders in 10 seconds and drives the user's initial decision.
    """

    decision_id: str
    # The actionable recommendation — one sentence
    action: str  # e.g., "Reduce AAPL by 8% (est. $12,400 impact)"
    # The single strongest piece of counter-evidence — one sentence
    counter_evidence: CounterEvidence
    # What would change Midas's mind — one sentence
    what_would_change_mind: WhatWouldChangeMind
    # Buttons present on the card
    buttons: list[ButtonAction] = field(
        default_factory=lambda: [
            ButtonAction.APPROVE,
            ButtonAction.DEBATE,
            ButtonAction.DECLINE,
        ]
    )
    # Biometric required on approve (always True per spec)
    biometric_required: bool = True
    # Dwell required before biometric unlocks (high-weight decisions only)
    dwell_seconds: float = 0.0  # 0 = no dwell; 3.0 = 3-second dwell required
    # Tags for usability-gate targeting
    is_high_weight: bool = False  # True when dollar impact exceeds threshold
    # Source of the counter-evidence (pool-disagreement | calibration | override-pattern)
    counter_evidence_source: str = ""


@dataclass
class TopOfFoldEvaluationResult:
    """Result of evaluating a TopOfFoldCard against the protocol's invariants."""

    decision_id: str
    has_action: bool
    has_counter_evidence: bool
    has_what_would_change_mind: bool
    approve_button_present: bool
    debate_button_present: bool
    decline_button_present: bool
    biometric_on_approve: bool
    dwell_enforced: bool  # True when dwell_seconds > 0 and is_high_weight
    dwell_seconds: float
    counter_evidence_one_line: bool  # counter-evidence text is <= 100 chars
    what_would_change_one_line: bool  # what-would-change text is <= 100 chars
    passes: bool
    failures: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class TopOfFoldCardProtocol:
    """Evaluates whether a top-of-fold card satisfies the T-00-08 schema.

    This is a schema and structural probe. It does not test UI rendering
    (that is M17/M18), but it verifies the data contract that the UI depends on.
    """

    MAX_LINE_CHARS = 100  # one-line threshold for card text
    HIGH_WEIGHT_DWELL_SECONDS = 3.0  # forced dwell for high-weight decisions
    HIGH_WEIGHT_DOLLAR_THRESHOLD = 10_000.0  # default threshold for "high weight"

    def __init__(
        self,
        high_weight_dwell_seconds: float = HIGH_WEIGHT_DWELL_SECONDS,
        high_weight_dollar_threshold: float = HIGH_WEIGHT_DOLLAR_THRESHOLD,
    ) -> None:
        self.high_weight_dwell_seconds = high_weight_dwell_seconds
        self.high_weight_dollar_threshold = high_weight_dollar_threshold

    def evaluate(self, card: TopOfFoldCard) -> TopOfFoldEvaluationResult:
        """Evaluate a TopOfFoldCard against the protocol invariants.

        Returns TopOfFoldEvaluationResult with pass/fail for each invariant.
        """
        failures: list[str] = []

        # Invariant 1: action is present and non-empty
        has_action = bool(card.action and card.action.strip())
        if not has_action:
            failures.append("action_missing_or_empty")

        # Invariant 2: counter-evidence is present and one-line
        has_counter_evidence = card.counter_evidence is not None and bool(
            card.counter_evidence.text and card.counter_evidence.text.strip()
        )
        counter_evidence_one_line = (
            has_counter_evidence and len(card.counter_evidence.text.strip()) <= self.MAX_LINE_CHARS
        )
        if not counter_evidence_one_line:
            failures.append("counter_evidence_not_one_line")

        # Invariant 3: what-would-change-mind is present and one-line
        has_what_would_change_mind = card.what_would_change_mind is not None and bool(
            card.what_would_change_mind.text and card.what_would_change_mind.text.strip()
        )
        what_would_change_one_line = (
            has_what_would_change_mind
            and len(card.what_would_change_mind.text.strip()) <= self.MAX_LINE_CHARS
        )
        if not what_would_change_one_line:
            failures.append("what_would_change_mind_not_one_line")

        # Invariant 4: all three buttons present
        approve_present = ButtonAction.APPROVE in card.buttons
        debate_present = ButtonAction.DEBATE in card.buttons
        decline_present = ButtonAction.DECLINE in card.buttons
        if not approve_present:
            failures.append("approve_button_missing")
        if not debate_present:
            failures.append("debate_button_missing")
        if not decline_present:
            failures.append("decline_button_missing")

        # Invariant 5: biometric required on approve
        biometric_on_approve = card.biometric_required is True
        if not biometric_on_approve:
            failures.append("biometric_not_required_on_approve")

        # Invariant 6: dwell enforced for high-weight decisions
        dwell_enforced = (
            card.is_high_weight and card.dwell_seconds >= self.high_weight_dwell_seconds
        )
        # Non-high-weight decisions must not have dwell (clean signal)
        if not card.is_high_weight and card.dwell_seconds > 0:
            failures.append("dwell_on_non_high_weight")
        # High-weight must have dwell
        if card.is_high_weight and card.dwell_seconds < self.high_weight_dwell_seconds:
            failures.append("high_weight_missing_dwell")

        all_pass = len(failures) == 0

        return TopOfFoldEvaluationResult(
            decision_id=card.decision_id,
            has_action=has_action,
            has_counter_evidence=has_counter_evidence,
            has_what_would_change_mind=has_what_would_change_mind,
            approve_button_present=approve_present,
            debate_button_present=debate_present,
            decline_button_present=decline_present,
            biometric_on_approve=biometric_on_approve,
            dwell_enforced=dwell_enforced,
            dwell_seconds=card.dwell_seconds,
            counter_evidence_one_line=counter_evidence_one_line,
            what_would_change_one_line=what_would_change_one_line,
            passes=all_pass,
            failures=failures,
        )

    def evaluate_and_raise(self, card: TopOfFoldCard) -> TopOfFoldEvaluationResult:
        """Evaluate and raise if any invariant fails."""
        result = self.evaluate(card)
        if not result.passes:
            failure_detail = "; ".join(result.failures)
            raise ValueError(
                f"TopOfFoldCard for decision {card.decision_id} failed protocol: {failure_detail}"
            )
        return result


def make_top_of_fold_card(
    decision_id: str,
    action: str = "Reduce equity exposure by 8% (est. $12,400 impact)",
    counter_evidence_text: str = "Pool disagreement 0.31 — classical risk-parity challenger disagrees",
    what_would_change_text: str = "If implied vol contracted below 18%, I would move to hold",
    is_high_weight: bool = False,
    dwell_seconds: float = 0.0,
) -> TopOfFoldCard:
    """Construct a valid TopOfFoldCard for tests."""
    return TopOfFoldCard(
        decision_id=decision_id,
        action=action,
        counter_evidence=CounterEvidence(
            text=counter_evidence_text,
            source="pool_disagreement",
        ),
        what_would_change_mind=WhatWouldChangeMind(
            text=what_would_change_text,
        ),
        buttons=[ButtonAction.APPROVE, ButtonAction.DEBATE, ButtonAction.DECLINE],
        biometric_required=True,
        dwell_seconds=dwell_seconds,
        is_high_weight=is_high_weight,
        counter_evidence_source="pool_disagreement",
    )
