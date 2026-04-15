"""
Debate Concession-With-Evidence Rules Protocol.

T-00-10: The Debate agent can only mutate a pending decision if a new evidence tuple
has been produced (a tool call returning new data, not just user rhetoric). Every
concession without evidence is logged in a concession counter. The agent is expected
to disagree at a minimum rate over a thread window.

Ref: specs/07-evidence-first-decision.md §3
Ref: specs/10-moments-of-truth.md §4
Ref: T-00-10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
import uuid


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class DebateRole(Enum):
    STEELMAN = auto()  # argues FOR the current recommendation
    REDTEAM = auto()  # argues AGAINST the current recommendation


@dataclass
class EvidenceTuple:
    """A new evidence item produced during a debate thread.

    An evidence tuple is the only valid basis for a concession.
    The tool_call field identifies which tool produced the evidence.
    """

    evidence_id: str
    tool_call: str  # e.g., "query_calibration", "query_fabric", "backtest_scenario"
    description: str  # human-readable summary of what the tool returned
    produced_at: datetime


@dataclass
class ConcessionRecord:
    """A single concession event in a debate thread."""

    concession_id: str
    thread_id: str
    role: DebateRole  # who made the concession
    prior_position: str  # what the agent believed before
    new_position: str  # what the agent now believes
    evidence_tuple: EvidenceTuple | None  # None = concession without evidence
    made_at: datetime


@dataclass
class DebateTurn:
    """A single turn in a debate thread."""

    turn_id: str
    thread_id: str
    role: DebateRole
    content: str  # the agent's or user's statement
    made_at: datetime
    produced_evidence: EvidenceTuple | None = None  # evidence produced in this turn
    is_agent: bool = True  # True = agent turn, False = user turn


@dataclass
class DebateThreadResult:
    """Result of evaluating a single debate thread."""

    thread_id: str
    total_concessions: int
    concessions_with_evidence: int
    concessions_without_evidence: int
    evidence_gated_concession_rate: float  # concessions_with_evidence / total_concessions
    total_agent_turns: int
    agent_disagreements: int  # turns where agent pushed back against user
    disagreement_rate: float  # agent_disagreements / total_agent_turns
    min_required_disagreement_rate: float
    disagreement_floor_met: bool
    passes: bool
    failures: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class DebateConcessionRules:
    """Enforces concession-with-evidence rules in the Debate agent.

    The protocol enforces three invariants:
      1. Concession gate: a `update_decision` tool call is only valid if preceded
         by a new evidence tuple within N turns.
      2. Concession counter: every concession without evidence is logged.
      3. Disagreement floor: over a thread window, the agent must disagree at a
         minimum rate (prevents sycophancy drift).

    The steelman/red-team role split is tracked via DebateRole on each turn.
    """

    DEFAULT_CONCESSION_LOOKBACK_TURNS = 3  # evidence must appear within this window
    DEFAULT_MIN_DISAGREEMENT_RATE = 0.30  # agent must disagree in ≥30% of its turns
    DEFAULT_THREAD_WINDOW_TURNS = 5  # minimum turns before evaluating disagreement floor

    def __init__(
        self,
        concession_lookback_turns: int = DEFAULT_CONCESSION_LOOKBACK_TURNS,
        min_disagreement_rate: float = DEFAULT_MIN_DISAGREEMENT_RATE,
        thread_window_turns: int = DEFAULT_THREAD_WINDOW_TURNS,
    ) -> None:
        self.concession_lookback_turns = concession_lookback_turns
        self.min_disagreement_rate = min_disagreement_rate
        self.thread_window_turns = thread_window_turns
        self._threads: dict[str, list[DebateTurn]] = {}
        self._concessions: dict[str, list[ConcessionRecord]] = {}

    # -------------------------------------------------------------------------
    # Thread management
    # -------------------------------------------------------------------------

    def begin_thread(self, thread_id: str) -> None:
        """Initialize a new debate thread."""
        self._threads[thread_id] = []

    def add_turn(
        self,
        thread_id: str,
        role: DebateRole,
        content: str,
        is_agent: bool,
        produced_evidence: EvidenceTuple | None = None,
    ) -> DebateTurn:
        """Add a turn to a debate thread."""
        if thread_id not in self._threads:
            self.begin_thread(thread_id)

        turn = DebateTurn(
            turn_id=str(uuid.uuid4()),
            thread_id=thread_id,
            role=role,
            content=content,
            made_at=datetime.now(timezone.utc),
            produced_evidence=produced_evidence,
            is_agent=is_agent,
        )
        self._threads[thread_id].append(turn)
        return turn

    def record_concession(
        self,
        thread_id: str,
        role: DebateRole,
        prior_position: str,
        new_position: str,
        evidence_tuple: EvidenceTuple | None = None,
    ) -> ConcessionRecord:
        """Record a concession in the thread."""
        if thread_id not in self._threads:
            self.begin_thread(thread_id)

        concession = ConcessionRecord(
            concession_id=str(uuid.uuid4()),
            thread_id=thread_id,
            role=role,
            prior_position=prior_position,
            new_position=new_position,
            evidence_tuple=evidence_tuple,
            made_at=datetime.now(timezone.utc),
        )
        if thread_id not in self._concessions:
            self._concessions[thread_id] = []
        self._concessions[thread_id].append(concession)
        return concession

    # -------------------------------------------------------------------------
    # Core evaluation
    # -------------------------------------------------------------------------

    def can_mutate_decision(
        self,
        thread_id: str,
        proposed_new_position: str,
    ) -> tuple[bool, str]:
        """Check if the debate agent may call update_decision on this thread.

        Returns (allowed, reason). allowed=True only when:
          1. At least one evidence tuple was produced in the last N turns, AND
          2. The concession has an evidence basis.

        This enforces the evidence-gated concession rule from T-00-10.
        """
        if thread_id not in self._threads:
            return False, "Thread not found"

        turns = self._threads[thread_id]
        if len(turns) < self.concession_lookback_turns:
            # Not enough turns to evaluate — require evidence gate
            recent_evidence = [t for t in turns if t.produced_evidence is not None]
            if not recent_evidence:
                return False, (
                    f"Concession requires evidence; no evidence produced in "
                    f"{len(turns)} turns (need ≥{self.concession_lookback_turns})"
                )

        # Check lookback window for evidence
        lookback = min(self.concession_lookback_turns, len(turns))
        recent_turns = turns[-lookback:]
        has_evidence = any(t.produced_evidence is not None for t in recent_turns)

        if not has_evidence:
            return False, (
                f"update_decision requires evidence in the last "
                f"{self.concession_lookback_turns} turns; found none"
            )

        return True, "Evidence gate satisfied"

    def evaluate_thread(self, thread_id: str) -> DebateThreadResult:
        """Evaluate a debate thread against all T-00-10 invariants."""
        if thread_id not in self._threads:
            return DebateThreadResult(
                thread_id=thread_id,
                total_concessions=0,
                concessions_with_evidence=0,
                concessions_without_evidence=0,
                evidence_gated_concession_rate=0.0,
                total_agent_turns=0,
                agent_disagreements=0,
                disagreement_rate=0.0,
                min_required_disagreement_rate=self.min_disagreement_rate,
                disagreement_floor_met=False,
                passes=False,
                failures=["thread_not_found"],
            )

        turns = self._threads[thread_id]
        concessions = self._concessions.get(thread_id, [])

        total_concessions = len(concessions)
        concessions_with_evidence = sum(1 for c in concessions if c.evidence_tuple is not None)
        concessions_without_evidence = total_concessions - concessions_with_evidence
        evidence_gated_rate = (
            concessions_with_evidence / total_concessions if total_concessions > 0 else 1.0
        )

        # Disagreement rate: agent turns where agent pushed back
        agent_turns = [t for t in turns if t.is_agent]
        total_agent_turns = len(agent_turns)

        # A disagreement is an agent turn that: (a) produced evidence against
        # the user's position, OR (b) is a REDTEAM role turn with substance
        agent_disagreements = sum(
            1 for t in agent_turns if t.role == DebateRole.REDTEAM and len(t.content.strip()) > 10
        )
        disagreement_rate = (
            agent_disagreements / total_agent_turns
            if total_agent_turns >= self.thread_window_turns
            else 0.0  # not enough turns to evaluate
        )

        disagreement_floor_met = (
            disagreement_rate >= self.min_disagreement_rate
            if total_agent_turns >= self.thread_window_turns
            else True  # can't fail if not enough turns yet
        )

        failures = []
        if total_concessions > 0 and concessions_without_evidence > 0:
            failures.append("concessions_without_evidence")
        if not disagreement_floor_met:
            failures.append("disagreement_floor_not_met")

        return DebateThreadResult(
            thread_id=thread_id,
            total_concessions=total_concessions,
            concessions_with_evidence=concessions_with_evidence,
            concessions_without_evidence=concessions_without_evidence,
            evidence_gated_concession_rate=evidence_gated_rate,
            total_agent_turns=total_agent_turns,
            agent_disagreements=agent_disagreements,
            disagreement_rate=disagreement_rate,
            min_required_disagreement_rate=self.min_disagreement_rate,
            disagreement_floor_met=disagreement_floor_met,
            passes=len(failures) == 0,
            failures=failures,
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def make_evidence_tuple(
        self,
        tool_call: str,
        description: str,
    ) -> EvidenceTuple:
        """Create a new evidence tuple. Use this to inject evidence into threads."""
        return EvidenceTuple(
            evidence_id=str(uuid.uuid4()),
            tool_call=tool_call,
            description=description,
            produced_at=datetime.now(timezone.utc),
        )


def make_thread_result(
    thread_id: str,
    total_concessions: int,
    concessions_with_evidence: int,
    total_agent_turns: int,
    agent_disagreements: int,
    min_disagreement_rate: float = 0.30,
) -> DebateThreadResult:
    """Factory for constructing DebateThreadResult in tests."""
    return DebateThreadResult(
        thread_id=thread_id,
        total_concessions=total_concessions,
        concessions_with_evidence=concessions_with_evidence,
        concessions_without_evidence=total_concessions - concessions_with_evidence,
        evidence_gated_concession_rate=(
            concessions_with_evidence / total_concessions if total_concessions > 0 else 1.0
        ),
        total_agent_turns=total_agent_turns,
        agent_disagreements=agent_disagreements,
        disagreement_rate=(
            agent_disagreements / total_agent_turns if total_agent_turns > 0 else 0.0
        ),
        min_required_disagreement_rate=min_disagreement_rate,
        disagreement_floor_met=(
            (agent_disagreements / total_agent_turns >= min_disagreement_rate)
            if total_agent_turns > 0
            else True
        ),
        passes=True,
        failures=[],
    )
