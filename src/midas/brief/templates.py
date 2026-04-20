"""Brief templates — render briefs at different density levels.

Three template renderers:
- compressed: single-paragraph summary for routine decisions
- standard: full 7-section brief
- extreme: full brief with honesty banner and OOD warning
"""


class BriefTemplates:
    """Brief template renderers.

    Each static method takes a brief_data dict (from AnalystAgent.compose_brief)
    and returns a formatted string suitable for display.
    """

    @staticmethod
    def render_compressed(brief_data: dict) -> str:
        """Render compressed brief for routine low-weight approvals.

        Produces a single paragraph with the key facts.

        Parameters
        ----------
        brief_data:
            Dict with 'sections', 'confidence', 'model_version'.

        Returns
        -------
        str
            Compressed brief text.
        """
        sections = brief_data.get("sections", {})
        confidence = brief_data.get("confidence", 0.0)

        thesis = sections.get("situation_summary", "No summary available.")
        recommendation = sections.get("recommendation", "No recommendation.")
        risk = sections.get("risk_factors", "No risk assessment.")
        change_mind = sections.get("what_would_change_mind", "")

        return (
            f"[Confidence: {confidence:.0%}] "
            f"{thesis} "
            f"Recommendation: {recommendation} "
            f"Key risk: {risk}" + (f" | Would change mind if: {change_mind}" if change_mind else "")
        )

    @staticmethod
    def render_standard(brief_data: dict) -> str:
        """Render full brief with all 10 sections per spec 07 S2.

        Parameters
        ----------
        brief_data:
            Dict with 'sections', 'confidence', 'model_version'.

        Returns
        -------
        str
            Full formatted brief with all 10 sections.
        """
        sections = brief_data.get("sections", {})
        confidence = brief_data.get("confidence", 0.0)
        model_version = brief_data.get("model_version", "unknown")

        provenance = sections.get("provenance_links", [])
        if isinstance(provenance, list):
            provenance_str = ", ".join(str(p) for p in provenance)
        else:
            provenance_str = str(provenance)

        lines = [
            "=" * 60,
            "INVESTMENT BRIEF",
            "=" * 60,
            "",
            f"Confidence: {confidence:.0%}  |  Model: {model_version}",
            "",
            "--- Thesis ---",
            sections.get("situation_summary", "N/A"),
            "",
            "--- Evidence Assessment ---",
            sections.get("evidence_assessment", "N/A"),
            "",
            "--- Recommendation ---",
            sections.get("recommendation", "N/A"),
            "",
            "--- Counter-Evidence ---",
            sections.get("counter_evidence", "N/A"),
            "",
            "--- If Approved ---",
            sections.get("if_approved", "N/A"),
            "",
            "--- If Rejected ---",
            sections.get("if_rejected", "N/A"),
            "",
            "--- Historical Precedent ---",
            sections.get("historical_precedent", "N/A"),
            "",
            "--- What Would Change My Mind ---",
            sections.get("what_would_change_mind", "N/A"),
            "",
            "--- Risk Factors ---",
            sections.get("risk_factors", "N/A"),
            "",
            "--- Provenance ---",
            provenance_str,
            "",
            "=" * 60,
        ]

        return "\n".join(lines)

    @staticmethod
    def render_extreme(brief_data: dict) -> str:
        """Render extreme-weight brief with honesty banner + OOD warning.

        Adds a prominent warning header indicating this is a high-stakes
        decision requiring extra scrutiny.

        Parameters
        ----------
        brief_data:
            Dict with 'sections', 'confidence', 'model_version'.

        Returns
        -------
        str
            Full brief with warning banners.
        """
        standard_brief = BriefTemplates.render_standard(brief_data)

        confidence = brief_data.get("confidence", 0.0)

        warning_header = [
            "!" * 60,
            "WARNING: EXTREME-WEIGHT DECISION BRIEF",
            "!" * 60,
            "",
            "This decision has been classified as extreme-weight.",
            "OOD WARNING: The current market regime may be out-of-distribution.",
            "Extra scrutiny is required before proceeding.",
            f"Model confidence: {confidence:.0%} — verify with independent analysis.",
            "",
            "!" * 60,
            "",
        ]

        return "\n".join(warning_header) + "\n" + standard_brief
