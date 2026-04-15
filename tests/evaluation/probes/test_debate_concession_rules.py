"""
Tests for T-00-10: Debate Concession-With-Evidence Rules.

Tier 2: validates evidence-gated concession rule, concession counter,
and disagreement floor enforcement.

Ref: specs/07-evidence-first-decision.md §3
Ref: specs/10-moments-of-truth.md §4
Ref: T-00-10
"""

from __future__ import annotations

import pytest

from midas.evaluation.probes.debate_concession_rules import (
    DebateConcessionRules,
    DebateRole,
    EvidenceTuple,
    ConcessionRecord,
    DebateThreadResult,
    DebateTurn,
)


def make_evidence(
    tool_call: str = "query_calibration",
    description: str = "calibration in z_region X is 0.52",
) -> EvidenceTuple:
    """Factory for EvidenceTuple in tests."""
    return EvidenceTuple(
        evidence_id="ev-001",
        tool_call=tool_call,
        description=description,
        produced_at=None,
    )


class TestDebateConcessionRules:
    """Tier 2 tests for debate concession-with-evidence rules."""

    def test_concession_with_evidence_allowed(self):
        """Concession backed by evidence tuple → allowed."""
        rules = DebateConcessionRules(
            concession_lookback_turns=3,
            min_disagreement_rate=0.30,
        )
        rules.begin_thread("t-001")
        evidence = rules.make_evidence_tuple(
            tool_call="query_calibration",
            description="calibration 0.52 in current z_region",
        )
        rules.add_turn(
            thread_id="t-001",
            role=DebateRole.REDTEAM,
            content="The calibration here is thin.",
            is_agent=True,
            produced_evidence=evidence,
        )

        allowed, reason = rules.can_mutate_decision(
            thread_id="t-001",
            proposed_new_position="reduce to 4%",
        )

        assert allowed is True, reason

    def test_concession_without_evidence_blocked(self):
        """Concession without preceding evidence tuple → blocked."""
        rules = DebateConcessionRules(
            concession_lookback_turns=3,
            min_disagreement_rate=0.30,
        )
        rules.begin_thread("t-002")
        # No evidence produced in any turn
        rules.add_turn(
            thread_id="t-002",
            role=DebateRole.STEELMAN,
            content="I think the recommendation stands.",
            is_agent=True,
            produced_evidence=None,
        )

        allowed, reason = rules.can_mutate_decision(
            thread_id="t-002",
            proposed_new_position="reduce to 4%",
        )

        assert allowed is False
        assert "requires evidence" in reason

    def test_evidence_must_be_recent(self):
        """Evidence older than lookback window → blocked."""
        rules = DebateConcessionRules(
            concession_lookback_turns=3,
            min_disagreement_rate=0.30,
        )
        rules.begin_thread("t-003")
        # First turn has evidence
        rules.add_turn(
            thread_id="t-003",
            role=DebateRole.REDTEAM,
            content="Counter-evidence here.",
            is_agent=True,
            produced_evidence=make_evidence(),
        )
        # Two more turns without evidence
        rules.add_turn(
            thread_id="t-003",
            role=DebateRole.STEELMAN,
            content="But our conviction is high.",
            is_agent=True,
            produced_evidence=None,
        )
        rules.add_turn(
            thread_id="t-003",
            role=DebateRole.REDTEAM,
            content="User pushing back.",
            is_agent=False,  # user
            produced_evidence=None,
        )
        # Fourth turn — evidence from turn 1 is now outside lookback of 3
        rules.add_turn(
            thread_id="t-003",
            role=DebateRole.STEELMAN,
            content="Still recommend hold.",
            is_agent=True,
            produced_evidence=None,
        )

        allowed, reason = rules.can_mutate_decision(
            thread_id="t-003",
            proposed_new_position="reduce to 4%",
        )

        assert allowed is False

    def test_concession_without_evidence_logged(self):
        """Every concession without evidence is recorded in the counter."""
        rules = DebateConcessionRules()
        rules.begin_thread("t-004")
        rules.add_turn(
            thread_id="t-004",
            role=DebateRole.STEELMAN,
            content="Conceding without evidence.",
            is_agent=True,
            produced_evidence=None,
        )

        concession = rules.record_concession(
            thread_id="t-004",
            role=DebateRole.STEELMAN,
            prior_position="hold at 8%",
            new_position="reduce to 4%",
            evidence_tuple=None,  # no evidence — logged
        )

        result = rules.evaluate_thread("t-004")
        assert result.concessions_without_evidence == 1
        assert concession.evidence_tuple is None

    def test_concession_with_evidence_does_not_fail(self):
        """Concession backed by evidence → does not fail the evidence gate."""
        rules = DebateConcessionRules()
        rules.begin_thread("t-005")
        rules.add_turn(
            thread_id="t-005",
            role=DebateRole.REDTEAM,
            content="Calibration is thin here.",
            is_agent=True,
            produced_evidence=make_evidence(),
        )

        concession = rules.record_concession(
            thread_id="t-005",
            role=DebateRole.REDTEAM,
            prior_position="reduce 8%",
            new_position="reduce 4%",
            evidence_tuple=make_evidence(),
        )

        result = rules.evaluate_thread("t-005")
        assert result.concessions_without_evidence == 0
        assert result.passes is True

    def test_disagreement_floor_enforced(self):
        """Agent disagrees in <30% of turns → thread fails."""
        rules = DebateConcessionRules(
            concession_lookback_turns=3,
            min_disagreement_rate=0.30,
            thread_window_turns=5,
        )
        rules.begin_thread("t-006")
        # 5 agent turns, only 1 disagreement (REDTEAM)
        roles = [
            DebateRole.STEELMAN,  # agree
            DebateRole.STEELMAN,  # agree
            DebateRole.REDTEAM,  # disagree
            DebateRole.STEELMAN,  # agree
            DebateRole.STEELMAN,  # agree
        ]
        for i, role in enumerate(roles):
            rules.add_turn(
                thread_id="t-006",
                role=role,
                content=f"Turn {i+1} content here.",
                is_agent=True,
            )

        result = rules.evaluate_thread("t-006")
        assert result.disagreement_floor_met is False
        assert result.passes is False
        assert "disagreement_floor_not_met" in result.failures

    def test_disagreement_floor_met(self):
        """Agent disagrees in ≥30% of turns → thread passes."""
        rules = DebateConcessionRules(
            concession_lookback_turns=3,
            min_disagreement_rate=0.30,
            thread_window_turns=5,
        )
        rules.begin_thread("t-007")
        # 5 agent turns, 2 disagreements (REDTEAM) = 40% → passes
        roles = [
            DebateRole.STEELMAN,  # agree
            DebateRole.REDTEAM,  # disagree
            DebateRole.STEELMAN,  # agree
            DebateRole.REDTEAM,  # disagree
            DebateRole.STEELMAN,  # agree
        ]
        for i, role in enumerate(roles):
            rules.add_turn(
                thread_id="t-007",
                role=role,
                content=f"Turn {i+1} content.",
                is_agent=True,
            )

        result = rules.evaluate_thread("t-007")
        assert result.disagreement_floor_met is True
        assert result.passes is True
        assert result.disagreement_rate >= 0.30

    def test_thread_not_found(self):
        """Evaluating unknown thread → returns failure result."""
        rules = DebateConcessionRules()
        result = rules.evaluate_thread("nonexistent")

        assert result.passes is False
        assert "thread_not_found" in result.failures

    def test_both_roles_present_in_thread(self):
        """Thread has both STEELMAN and REDTEAM turns → structural requirement met."""
        rules = DebateConcessionRules(
            thread_window_turns=5,
        )
        rules.begin_thread("t-008")
        rules.add_turn(
            thread_id="t-008",
            role=DebateRole.STEELMAN,
            content="Argument for the recommendation.",
            is_agent=True,
        )
        rules.add_turn(
            thread_id="t-008",
            role=DebateRole.REDTEAM,
            content="Argument against.",
            is_agent=True,
        )

        result = rules.evaluate_thread("t-008")
        assert result.total_agent_turns == 2
        # REDTEAM turns count as disagreements
        assert result.agent_disagreements == 1

    def test_concession_counter_total(self):
        """Multiple concessions tracked correctly."""
        rules = DebateConcessionRules()
        rules.begin_thread("t-009")
        rules.record_concession(
            thread_id="t-009",
            role=DebateRole.REDTEAM,
            prior_position="reduce 8%",
            new_position="reduce 6%",
            evidence_tuple=make_evidence(),
        )
        rules.record_concession(
            thread_id="t-009",
            role=DebateRole.REDTEAM,
            prior_position="reduce 6%",
            new_position="reduce 4%",
            evidence_tuple=None,  # no evidence
        )

        result = rules.evaluate_thread("t-009")
        assert result.total_concessions == 2
        assert result.concessions_with_evidence == 1
        assert result.concessions_without_evidence == 1
        assert result.evidence_gated_concession_rate == 0.5

    def test_update_decision_blocked_on_unknown_thread(self):
        """can_mutate_decision on unknown thread → False."""
        rules = DebateConcessionRules()
        allowed, reason = rules.can_mutate_decision(
            thread_id="nonexistent",
            proposed_new_position="reduce to 4%",
        )
        assert allowed is False
        assert "Thread not found" in reason
