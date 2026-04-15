"""
Tests for T-00-08: Top-Of-Fold Decide-In-10-Seconds Card.

Tier 2: validates the card schema, button presence, biometric requirement,
and dwell enforcement for high-weight decisions.

Ref: specs/07-evidence-first-decision.md §2
Ref: specs/09-surfaces-and-attention.md §4
Ref: T-00-08
"""

from __future__ import annotations

import pytest

from midas.evaluation.probes.top_of_fold_card import (
    TopOfFoldCardProtocol,
    TopOfFoldCard,
    TopOfFoldEvaluationResult,
    ButtonAction,
    CounterEvidence,
    WhatWouldChangeMind,
    make_top_of_fold_card,
)


class TestTopOfFoldCardProtocol:
    """Tier 2 tests for top-of-fold card protocol."""

    def test_valid_card_passes(self):
        """A properly formed card with all required fields → passes."""
        card = make_top_of_fold_card(
            decision_id="d-001",
            is_high_weight=False,
            dwell_seconds=0.0,
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is True, f"Expected pass, failures: {result.failures}"
        assert result.has_action is True
        assert result.has_counter_evidence is True
        assert result.has_what_would_change_mind is True
        assert result.approve_button_present is True
        assert result.debate_button_present is True
        assert result.decline_button_present is True
        assert result.biometric_on_approve is True

    def test_missing_action_fails(self):
        """Card with empty action → fails."""
        card = make_top_of_fold_card(decision_id="d-002", action="")
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "action_missing_or_empty" in result.failures

    def test_counter_evidence_over_one_line_fails(self):
        """Counter-evidence text exceeding 100 chars → fails."""
        long_text = (
            "Pool disagreement 0.31 — the classical risk-parity challenger "
            "disagrees with this recommendation on the basis of vol regime."
        )
        card = make_top_of_fold_card(
            decision_id="d-003",
            counter_evidence_text=long_text,
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "counter_evidence_not_one_line" in result.failures

    def test_what_would_change_over_one_line_fails(self):
        """What-would-change-mind text exceeding 100 chars → fails."""
        long_text = (
            "If implied vol contracted below 18% AND the yield curve flattened "
            "to a slope of less than 50bps, I would move from reduce to hold."
        )
        card = make_top_of_fold_card(
            decision_id="d-004",
            what_would_change_text=long_text,
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "what_would_change_mind_not_one_line" in result.failures

    def test_approve_button_missing_fails(self):
        """Card without Approve button → fails."""
        card = make_top_of_fold_card(decision_id="d-005")
        card.buttons = [ButtonAction.DEBATE, ButtonAction.DECLINE]
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "approve_button_missing" in result.failures

    def test_debate_button_missing_fails(self):
        """Card without Debate button → fails."""
        card = make_top_of_fold_card(decision_id="d-006")
        card.buttons = [ButtonAction.APPROVE, ButtonAction.DECLINE]
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "debate_button_missing" in result.failures

    def test_decline_button_missing_fails(self):
        """Card without Decline button → fails."""
        card = make_top_of_fold_card(decision_id="d-007")
        card.buttons = [ButtonAction.APPROVE, ButtonAction.DEBATE]
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "decline_button_missing" in result.failures

    def test_biometric_not_required_fails(self):
        """Card with biometric_required=False → fails."""
        card = make_top_of_fold_card(decision_id="d-008")
        card.biometric_required = False
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "biometric_not_required_on_approve" in result.failures

    def test_high_weight_without_dwell_fails(self):
        """High-weight card without 3-second dwell → fails."""
        card = make_top_of_fold_card(
            decision_id="d-009",
            is_high_weight=True,
            dwell_seconds=0.0,
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "high_weight_missing_dwell" in result.failures

    def test_high_weight_with_full_dwell_passes(self):
        """High-weight card with 3-second dwell → passes."""
        card = make_top_of_fold_card(
            decision_id="d-010",
            is_high_weight=True,
            dwell_seconds=3.0,
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is True
        assert result.dwell_enforced is True
        assert result.dwell_seconds == 3.0

    def test_non_high_weight_with_dwell_fails(self):
        """Non-high-weight card with dwell → fails (dwell not applicable)."""
        card = make_top_of_fold_card(
            decision_id="d-011",
            is_high_weight=False,
            dwell_seconds=3.0,  # should be 0 for non-high-weight
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "dwell_on_non_high_weight" in result.failures

    def test_counter_evidence_at_exactly_100_chars_passes(self):
        """Counter-evidence at exactly 100 chars → passes (boundary)."""
        text = "x" * 100
        card = make_top_of_fold_card(
            decision_id="d-012",
            counter_evidence_text=text,
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is True
        assert result.counter_evidence_one_line is True

    def test_counter_evidence_at_101_chars_fails(self):
        """Counter-evidence at 101 chars → fails (boundary)."""
        text = "x" * 101
        card = make_top_of_fold_card(
            decision_id="d-013",
            counter_evidence_text=text,
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert "counter_evidence_not_one_line" in result.failures

    def test_evaluate_and_raise_raises_on_failure(self):
        """evaluate_and_raise raises ValueError when card fails protocol."""
        card = make_top_of_fold_card(decision_id="d-014", action="")
        protocol = TopOfFoldCardProtocol()

        with pytest.raises(ValueError, match="action_missing_or_empty"):
            protocol.evaluate_and_raise(card)

    def test_all_failures_captured(self):
        """Multiple failures → all listed in result.failures."""
        card = TopOfFoldCard(
            decision_id="d-015",
            action="",  # missing
            counter_evidence=CounterEvidence(
                text="x" * 200,  # over one line
                source="test",
            ),
            what_would_change_mind=WhatWouldChangeMind(
                text="x" * 200,  # over one line
            ),
            buttons=[ButtonAction.APPROVE],  # missing debate + decline
            biometric_required=False,
            dwell_seconds=0.0,
            is_high_weight=False,
        )
        protocol = TopOfFoldCardProtocol()
        result = protocol.evaluate(card)

        assert result.passes is False
        assert len(result.failures) >= 5
        assert "action_missing_or_empty" in result.failures
        assert "counter_evidence_not_one_line" in result.failures
        assert "what_would_change_mind_not_one_line" in result.failures
        assert "debate_button_missing" in result.failures
        assert "decline_button_missing" in result.failures
