"""Regression tests for brief section grounding — BriefSectionValidator + BriefEnricher.

Ref: specs/07-evidence-first-decision.md S2.3-S2.6
"""

import pytest

from midas.brief.validators import (
    validate_all,
    validate_historical_precedent,
    validate_if_approved,
    validate_if_rejected,
    validate_what_would_change_mind,
)


class TestValidateIfApproved:
    """validate_if_approved: must contain dollar amount AND risk metric."""

    def test_passes_with_dollar_and_risk_metric(self):
        issues = validate_if_approved(
            "If approved, we will allocate $2.5M to the position with a "
            "volatility of 18% and max drawdown of 12%."
        )
        assert issues == []

    def test_fails_missing_dollar(self):
        issues = validate_if_approved("If approved, we increase the position with high volatility.")
        assert any("no dollar amount" in i for i in issues)

    def test_fails_missing_risk_metric(self):
        issues = validate_if_approved("If approved, we will allocate $500,000 to this trade.")
        assert any("no risk metric" in i for i in issues)

    def test_fails_missing_both(self):
        issues = validate_if_approved("If approved, we proceed.")
        assert len(issues) == 2

    def test_dollar_formats_variety(self):
        # Various dollar formats should all pass
        for text in [
            "We will invest $1,234.56",
            "Estimated cost: USD 500000",
            "Position size: 1.5M",
            "Budget of $2B allocated",
        ]:
            issues = validate_if_approved(text + " with a Sharpe ratio of 1.2")
            assert issues == [], f"Failed on: {text}"

    def test_risk_metric_keywords(self):
        for keyword in ["VaR", "volatility", "drawdown", "Sharpe ratio", "beta", "CVaR"]:
            text = f"If approved, we allocate $100k. Risk: {keyword}=0.15"
            issues = validate_if_approved(text)
            assert issues == [], f"Failed on keyword: {keyword}"


class TestValidateIfRejected:
    """validate_if_rejected: must reference position retention AND drawdown probability."""

    def test_passes_with_position_and_drawdown(self):
        issues = validate_if_rejected(
            "If rejected, we retain the current allocation and monitor "
            "the drawdown probability of 25%."
        )
        assert issues == []

    def test_fails_missing_position_reference(self):
        issues = validate_if_rejected("If rejected, we face a 20% drawdown probability.")
        assert any("no position retention" in i for i in issues)

    def test_fails_missing_drawdown_probability(self):
        issues = validate_if_rejected("If rejected, we maintain our existing position unchanged.")
        assert any("no drawdown probability" in i for i in issues)

    def test_position_keywords_variety(self):
        for keyword in ["retain", "keep", "hold", "maintain", "status quo", "unchanged"]:
            text = f"If rejected, we {keyword} the current position. Worst-case drawdown: 15%."
            issues = validate_if_rejected(text)
            assert issues == [], f"Failed on: {keyword}"

    def test_drawdown_formats_variety(self):
        for text in [
            "drawdown probability of 20%",
            "likelihood of a draw down exceeding 15%",
            "worst case loss scenario: 25%",
            "20% chance of significant decline",
        ]:
            full = f"If rejected, we retain our position. {text}."
            issues = validate_if_rejected(full)
            assert issues == [], f"Failed on: {text}"


class TestValidateHistoricalPrecedent:
    """validate_historical_precedent: must contain analogue AND outcome."""

    def test_passes_with_analogue_and_outcome(self):
        issues = validate_historical_precedent(
            "Back in 2022, when we faced a similar regime, "
            "we rotated to bonds and the outcome was a +8% return."
        )
        assert issues == []

    def test_fails_missing_analogue(self):
        issues = validate_historical_precedent("The portfolio returned 12% last quarter.")
        assert any("no analogue" in i for i in issues)

    def test_fails_missing_outcome(self):
        issues = validate_historical_precedent(
            "When we bought tech in 2023, there was a similar situation."
        )
        assert any("no outcome" in i for i in issues)

    def test_analogue_keywords_variety(self):
        for keyword in ["back in 2021", "prior decision", "similar regime", "last time"]:
            text = f"{keyword}, we added exposure. The result was a +5% gain."
            issues = validate_historical_precedent(text)
            assert issues == [], f"Failed on: {keyword}"

    def test_outcome_keywords_variety(self):
        for keyword in ["returned +12%", "loss of 8%", "ended up 5%", "was down 3%"]:
            text = f"In that analogous period, the position {keyword}."
            issues = validate_historical_precedent(text)
            assert issues == [], f"Failed on: {keyword}"


class TestValidateWhatWouldChangeMind:
    """validate_what_would_change_mind: must contain at least one numeric threshold."""

    def test_passes_with_threshold(self):
        # These phrasings match THRESHOLD_RE's (operator, optional words, $N/%N) structure
        for text in [
            "We would change our mind if the price drops below the level of $85.",
            "What would change my mind: if volatility exceeds 25%.",
            "We would flip if price breaks below $100.",
        ]:
            issues = validate_what_would_change_mind(text)
            assert issues == [], f"Failed on: {text}"

    def test_fails_no_threshold(self):
        issues = validate_what_would_change_mind(
            "We would need more evidence to change our recommendation."
        )
        assert any("no numeric threshold" in i for i in issues)

    def test_threshold_formats_variety(self):
        for text in [
            "drop below $100",
            "rise above 20%",
            "if price exceeds 150",
            "break below 95",
            "cross the 30% threshold",
        ]:
            issues = validate_what_would_change_mind(f"What would change my mind: {text}.")
            assert issues == [], f"Failed on: {text}"


class TestValidateAll:
    """validate_all dispatches to the correct validator by section name."""

    def test_dispatches_if_approved(self):
        # No grounding → both issues
        issues = validate_all("if_approved", "No grounding here.")
        assert len(issues) == 2

    def test_dispatches_if_rejected(self):
        issues = validate_all("if_rejected", "No grounding here.")
        assert len(issues) == 2

    def test_dispatches_historical_precedent(self):
        issues = validate_all("historical_precedent", "No grounding here.")
        assert len(issues) == 2

    def test_dispatches_what_would_change_mind(self):
        issues = validate_all("what_would_change_mind", "No threshold.")
        assert len(issues) == 1

    def test_unknown_section_returns_error_list(self):
        issues = validate_all("unknown_section", "Some text")
        assert len(issues) == 1
        assert "Unknown section" in issues[0]
