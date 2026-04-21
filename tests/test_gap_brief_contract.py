"""Tests for Gap 4: Brief contract enforcement.

Verifies that BriefContract validates all 7 mandatory sections,
rejects empty/missing sections, and handles edge cases correctly.
"""

import pytest

from midas.brief.contract import BriefContract


def _valid_contract() -> BriefContract:
    """Return a fully valid BriefContract instance."""
    return BriefContract(
        thesis="Tail risk posterior has widened; expected shortfall approaching envelope.",
        evidence="z_t shows higher distance-from-training; tail head calibration 0.78.",
        if_approved="Brings expected shortfall to Y; reduces upside capture by Z.",
        if_rejected="Current shortfall trajectory stays; envelope breach probability 12%.",
        historical_precedent="Three analogues in the last 10 years; two reduced, one held.",
        what_would_change_mind="If model agreement recovered to 0.8, would move to 'hold'.",
        confidence=0.66,
    )


class TestBriefContractValidation:
    """Tests for BriefContract section validation."""

    def test_valid_contract_passes(self):
        contract = _valid_contract()
        assert contract.is_valid()
        assert contract.validate() == []

    def test_missing_thesis_fails(self):
        contract = _valid_contract()
        contract.thesis = ""
        errors = contract.validate()
        assert len(errors) == 1
        assert "Thesis" in errors[0]
        assert "S2.1" in errors[0]

    def test_whitespace_only_thesis_fails(self):
        contract = _valid_contract()
        contract.thesis = "   "
        errors = contract.validate()
        assert len(errors) == 1

    def test_missing_evidence_fails(self):
        contract = _valid_contract()
        contract.evidence = ""
        errors = contract.validate()
        assert len(errors) == 1
        assert "S2.2" in errors[0]

    def test_missing_if_approved_fails(self):
        contract = _valid_contract()
        contract.if_approved = ""
        errors = contract.validate()
        assert len(errors) == 1
        assert "S2.3" in errors[0]

    def test_missing_if_rejected_fails(self):
        contract = _valid_contract()
        contract.if_rejected = ""
        errors = contract.validate()
        assert len(errors) == 1
        assert "S2.4" in errors[0]

    def test_missing_historical_precedent_fails(self):
        contract = _valid_contract()
        contract.historical_precedent = ""
        errors = contract.validate()
        assert len(errors) == 1
        assert "S2.5" in errors[0]

    def test_missing_what_would_change_mind_fails(self):
        contract = _valid_contract()
        contract.what_would_change_mind = ""
        errors = contract.validate()
        assert len(errors) == 1
        assert "S2.6" in errors[0]

    def test_confidence_nan_fails(self):
        contract = _valid_contract()
        contract.confidence = float("nan")
        errors = contract.validate()
        assert len(errors) == 1
        assert "S2.7" in errors[0]

    def test_confidence_inf_fails(self):
        contract = _valid_contract()
        contract.confidence = float("inf")
        errors = contract.validate()
        assert len(errors) == 1
        assert "not finite" in errors[0]

    def test_confidence_above_one_fails(self):
        contract = _valid_contract()
        contract.confidence = 1.5
        errors = contract.validate()
        assert len(errors) == 1
        assert "out of range" in errors[0]

    def test_confidence_negative_fails(self):
        contract = _valid_contract()
        contract.confidence = -0.1
        errors = contract.validate()
        assert len(errors) == 1
        assert "out of range" in errors[0]

    def test_confidence_zero_is_valid(self):
        contract = _valid_contract()
        contract.confidence = 0.0
        assert contract.is_valid()

    def test_confidence_one_is_valid(self):
        contract = _valid_contract()
        contract.confidence = 1.0
        assert contract.is_valid()

    def test_multiple_missing_fields_report_all(self):
        contract = BriefContract()  # all defaults empty
        errors = contract.validate()
        # At minimum: 6 empty-string sections + confidence=0.0 (which is valid)
        assert len(errors) == 6

    def test_all_empty_reports_all(self):
        contract = BriefContract(confidence=float("nan"))
        errors = contract.validate()
        assert len(errors) == 7  # 6 empty sections + 1 bad confidence


class TestBriefContractSerialization:
    """Tests for BriefContract dict conversion."""

    def test_to_dict_contains_all_fields(self):
        contract = _valid_contract()
        d = contract.to_dict()
        assert "thesis" in d
        assert "evidence" in d
        assert "if_approved" in d
        assert "if_rejected" in d
        assert "historical_precedent" in d
        assert "what_would_change_mind" in d
        assert "confidence" in d

    def test_to_dict_values_match(self):
        contract = _valid_contract()
        d = contract.to_dict()
        assert d["thesis"] == contract.thesis
        assert d["confidence"] == contract.confidence


class TestBriefContractFromSections:
    """Tests for creating BriefContract from a sections dict."""

    def test_from_sections_maps_keys(self):
        sections = {
            "situation_summary": "Market is volatile.",
            "evidence_assessment": "Three converging signals.",
            "if_approved": "Reduced risk exposure.",
            "if_rejected": "Higher downside risk.",
            "historical_precedent": "Similar regime in 2022.",
            "what_would_change_mind": "If VIX drops below 15.",
            "confidence": 0.72,
        }
        contract = BriefContract.from_sections(sections)
        assert contract.thesis == "Market is volatile."
        assert contract.evidence == "Three converging signals."
        assert contract.confidence == 0.72
        assert contract.is_valid()

    def test_from_sections_handles_missing_keys(self):
        sections = {}
        contract = BriefContract.from_sections(sections)
        assert contract.thesis == ""
        assert contract.confidence == 0.0
        assert not contract.is_valid()

    def test_from_sections_handles_provenance_list(self):
        sections = {
            "situation_summary": "Test thesis.",
            "provenance_links": ["news:1", "filing:2"],
        }
        contract = BriefContract.from_sections(sections)
        assert contract.provenance_links == ["news:1", "filing:2"]

    def test_from_sections_handles_provenance_string(self):
        sections = {
            "situation_summary": "Test thesis.",
            "provenance_links": "news:1",
        }
        contract = BriefContract.from_sections(sections)
        assert contract.provenance_links == ["news:1"]

    def test_from_sections_handles_non_numeric_confidence(self):
        sections = {
            "confidence": "not_a_number",
        }
        contract = BriefContract.from_sections(sections)
        assert contract.confidence == 0.0
