"""Density matrix — maps (regime band, impact tier, confidence tier) to brief density.

Controls how much detail the brief contains based on the urgency and
significance of the decision. Extreme-weight decisions get full analysis
with OOD warnings; routine decisions get compressed one-liners.
"""


class DensityMatrix:
    """Matrix over (a_t band x dollar-impact tier x confidence tier) -> brief density template.

    The density level determines which brief template is used:
    - compressed: routine low-weight approvals (single paragraph)
    - standard: normal decisions (7-section brief)
    - full: high-stakes decisions (detailed analysis)
    - extreme: crisis/ultra-high-weight (full analysis + OOD warning)
    """

    BANDS = ["calm", "elevated", "urgent", "crisis"]
    IMPACT_TIERS = ["low", "medium", "high"]
    CONFIDENCE_TIERS = ["low", "medium", "high"]

    # Density level lookup: (band_index, impact_index, confidence_index)
    # Indexing: BANDS[row], IMPACT_TIERS[col], CONFIDENCE_TIERS[depth]
    # Priority: crisis + high + high = extreme; calm + low + low = compressed
    _DENSITY_MAP: dict[str, str] = {
        # calm: mostly compressed/standard
        "calm:low:low": "compressed",
        "calm:low:medium": "compressed",
        "calm:low:high": "standard",
        "calm:medium:low": "compressed",
        "calm:medium:medium": "standard",
        "calm:medium:high": "standard",
        "calm:high:low": "standard",
        "calm:high:medium": "standard",
        "calm:high:high": "full",
        # elevated: standard/full mix
        "elevated:low:low": "compressed",
        "elevated:low:medium": "standard",
        "elevated:low:high": "standard",
        "elevated:medium:low": "standard",
        "elevated:medium:medium": "standard",
        "elevated:medium:high": "full",
        "elevated:high:low": "standard",
        "elevated:high:medium": "full",
        "elevated:high:high": "full",
        # urgent: full/extreme mix
        "urgent:low:low": "standard",
        "urgent:low:medium": "standard",
        "urgent:low:high": "full",
        "urgent:medium:low": "standard",
        "urgent:medium:medium": "full",
        "urgent:medium:high": "full",
        "urgent:high:low": "full",
        "urgent:high:medium": "full",
        "urgent:high:high": "extreme",
        # crisis: mostly extreme
        "crisis:low:low": "standard",
        "crisis:low:medium": "full",
        "crisis:low:high": "full",
        "crisis:medium:low": "full",
        "crisis:medium:medium": "full",
        "crisis:medium:high": "extreme",
        "crisis:high:low": "full",
        "crisis:high:medium": "extreme",
        "crisis:high:high": "extreme",
    }

    def _validate_cell(self, band: str, impact: str, confidence: str) -> None:
        """Validate inputs against allowed values."""
        if band not in self.BANDS:
            raise ValueError(f"Invalid band '{band}'. Must be one of: {self.BANDS}")
        if impact not in self.IMPACT_TIERS:
            raise ValueError(f"Invalid impact '{impact}'. Must be one of: {self.IMPACT_TIERS}")
        if confidence not in self.CONFIDENCE_TIERS:
            raise ValueError(
                f"Invalid confidence '{confidence}'. Must be one of: {self.CONFIDENCE_TIERS}"
            )

    def get_template(self, band: str, impact: str, confidence: str) -> str:
        """Return brief template name for the cell.

        Parameters
        ----------
        band:
            Regime band: calm, elevated, urgent, crisis.
        impact:
            Dollar-impact tier: low, medium, high.
        confidence:
            Confidence tier: low, medium, high.

        Returns
        -------
        str
            Template name corresponding to the density level.
        """
        self._validate_cell(band, impact, confidence)
        density = self.get_density_level(band, impact, confidence)
        template_map = {
            "compressed": "compressed",
            "standard": "standard",
            "full": "standard",
            "extreme": "extreme",
        }
        return template_map[density]

    def get_density_level(self, band: str, impact: str, confidence: str) -> str:
        """Return density level for the cell.

        Parameters
        ----------
        band:
            Regime band: calm, elevated, urgent, crisis.
        impact:
            Dollar-impact tier: low, medium, high.
        confidence:
            Confidence tier: low, medium, high.

        Returns
        -------
        str
            One of: 'compressed', 'standard', 'full', 'extreme'.
        """
        self._validate_cell(band, impact, confidence)
        key = f"{band}:{impact}:{confidence}"
        return self._DENSITY_MAP[key]
