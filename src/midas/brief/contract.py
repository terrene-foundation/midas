"""Brief contract -- typed enforcement of the 7 mandatory brief sections.

Per specs/07-evidence-first-decision.md S2, every recommendation ships
with a brief containing all seven sections.  Missing sections are bugs.

The BriefContract dataclass validates that all sections are present and
non-empty before a brief reaches the user.  This is the structural
enforcement layer; semantic quality is the frontier LLM's responsibility.

Ref: specs/07-evidence-first-decision.md S2.1-S2.7
"""

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger("midas.brief.contract")


@dataclass
class BriefContract:
    """Typed contract for the 7 mandatory brief sections.

    Every field must be a non-empty string (except ``confidence`` which
    must be a finite float in [0, 1]).  A brief that fails validation
    is a bug -- it must never reach the Decisions surface.

    Parameters
    ----------
    thesis:
        The core causal claim in one sentence.  Per spec S2.1: not the
        action itself, but the causal sentence behind it.
    evidence:
        Structured list of data points the model used.  Per spec S2.2:
        each item carries a provenance pointer.
    if_approved:
        Consequence of taking the action.  Per spec S2.3: new allocation,
        estimated costs, expected risk metrics.
    if_rejected:
        Consequence of not taking the action.  Per spec S2.4: current
        position retained, drawdown profile, pool disagreement.
    historical_precedent:
        Comparable past decisions and their outcomes.  Per spec S2.5:
        top K analogues by state similarity, not cherry-picked.
    what_would_change_mind:
        The specific evidence or threshold that would flip the
        recommendation.  Per spec S2.6: mandatory, the forensic trail.
    confidence:
        Posterior over the recommendation's expected utility.  Per
        spec S2.7: not a single number -- accompanied by factors.
    """

    thesis: str = ""
    evidence: str = ""
    if_approved: str = ""
    if_rejected: str = ""
    historical_precedent: str = ""
    what_would_change_mind: str = ""
    confidence: float = 0.0

    # Optional metadata (not validated for presence)
    provenance_links: list[str] = field(default_factory=list)
    model_version: str = ""
    counter_evidence: str = ""
    risk_factors: str = ""

    def validate(self) -> list[str]:
        """Validate all 7 mandatory sections are present and non-empty.

        Returns
        -------
        list[str]
            List of validation errors.  Empty list means the brief
            contract is fully satisfied.
        """
        errors: list[str] = []

        # S2.1: Thesis
        if not self.thesis or not self.thesis.strip():
            errors.append("Thesis (S2.1) is empty -- core causal claim required")

        # S2.2: Evidence
        if not self.evidence or not self.evidence.strip():
            errors.append("Evidence (S2.2) is empty -- structured evidence list required")

        # S2.3: If Approved
        if not self.if_approved or not self.if_approved.strip():
            errors.append("If Approved (S2.3) is empty -- consequence of action required")

        # S2.4: If Rejected
        if not self.if_rejected or not self.if_rejected.strip():
            errors.append("If Rejected (S2.4) is empty -- consequence of inaction required")

        # S2.5: Historical Precedent
        if not self.historical_precedent or not self.historical_precedent.strip():
            errors.append(
                "Historical Precedent (S2.5) is empty -- top-K analogues required"
            )

        # S2.6: What Would Change My Mind (mandatory)
        if not self.what_would_change_mind or not self.what_would_change_mind.strip():
            errors.append(
                "What Would Change My Mind (S2.6) is empty -- "
                "flip threshold is mandatory per spec"
            )

        # S2.7: Confidence
        if not math.isfinite(self.confidence):
            errors.append(
                f"Confidence (S2.7) is not finite: {self.confidence} -- "
                f"posterior over expected utility required"
            )
        elif not (0.0 <= self.confidence <= 1.0):
            errors.append(
                f"Confidence (S2.7) out of range: {self.confidence} -- "
                f"must be in [0, 1]"
            )

        if errors:
            logger.warning(
                "brief.contract_validation_failed",
                error_count=len(errors),
                errors=errors,
            )
        else:
            logger.debug("brief.contract_validated", sections=7)

        return errors

    def is_valid(self) -> bool:
        """Return True if all 7 mandatory sections pass validation."""
        return len(self.validate()) == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the contract to a dict suitable for brief rendering."""
        return {
            "thesis": self.thesis,
            "evidence": self.evidence,
            "if_approved": self.if_approved,
            "if_rejected": self.if_rejected,
            "historical_precedent": self.historical_precedent,
            "what_would_change_mind": self.what_would_change_mind,
            "confidence": self.confidence,
            "provenance_links": self.provenance_links,
            "model_version": self.model_version,
            "counter_evidence": self.counter_evidence,
            "risk_factors": self.risk_factors,
        }

    @classmethod
    def from_sections(cls, sections: dict[str, Any]) -> "BriefContract":
        """Create a BriefContract from a sections dict (e.g. analyst output).

        Maps the analyst's section keys to the contract fields.  Tolerant
        of missing keys -- use ``validate()`` afterwards to check completeness.

        Parameters
        ----------
        sections:
            Dict with section content from the brief pipeline.

        Returns
        -------
        BriefContract
            Instance populated from the sections dict.
        """
        confidence_raw = sections.get("confidence", 0.0)
        try:
            confidence_val = float(confidence_raw)
        except (TypeError, ValueError):
            confidence_val = 0.0

        provenance = sections.get("provenance_links", [])
        if not isinstance(provenance, list):
            provenance = [str(provenance)]

        return cls(
            thesis=sections.get("situation_summary", ""),
            evidence=sections.get("evidence_assessment", ""),
            if_approved=sections.get("if_approved", ""),
            if_rejected=sections.get("if_rejected", ""),
            historical_precedent=sections.get("historical_precedent", ""),
            what_would_change_mind=sections.get("what_would_change_mind", ""),
            confidence=confidence_val,
            provenance_links=provenance,
            model_version=sections.get("model_version", ""),
            counter_evidence=sections.get("counter_evidence", ""),
            risk_factors=sections.get("risk_factors", ""),
        )
