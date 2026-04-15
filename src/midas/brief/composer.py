"""Brief composer — consumes decision context, selects template, produces final brief.

Orchestrates the brief composition pipeline:
1. Analyst produces the raw brief data
2. DensityMatrix selects the appropriate density level
3. BriefTemplates renders the brief at that density
4. TopOfFoldCard produces the decide-in-10s card
"""

import structlog

from midas.agents.analyst import AnalystAgent
from midas.brief.density_matrix import DensityMatrix
from midas.brief.templates import BriefTemplates
from midas.brief.top_of_fold import TopOfFoldCard

logger = structlog.get_logger("midas.brief.composer")


class BriefComposer:
    """Consumes decision context, selects template, produces final brief.

    Parameters
    ----------
    analyst:
        An AnalystAgent instance for producing the raw brief.
    """

    def __init__(self, analyst: AnalystAgent):
        self._analyst = analyst
        self._density = DensityMatrix()
        self._templates = BriefTemplates()

    async def compose(self, decision_context: dict) -> dict:
        """Compose brief from decision context.

        Parameters
        ----------
        decision_context:
            Dict with decision metadata including optional regime_band,
            dollar_impact, confidence_tier for density selection.

        Returns
        -------
        dict
            Keys: 'card', 'brief', 'density_level', 'provenance_links'.
        """
        # Step 1: Produce raw brief from analyst
        brief_data = await self._analyst.compose_brief(decision_context)

        # Step 2: Determine density level
        band = decision_context.get("regime_band", "calm")
        impact = decision_context.get("dollar_impact", "medium")
        confidence_tier = decision_context.get("confidence_tier", "medium")

        density_level = self._density.get_density_level(band, impact, confidence_tier)
        template_name = self._density.get_template(band, impact, confidence_tier)

        logger.info(
            "composer.density_selected",
            band=band,
            impact=impact,
            confidence_tier=confidence_tier,
            density_level=density_level,
            template=template_name,
        )

        # Step 3: Render brief at appropriate density
        template_methods = {
            "compressed": self._templates.render_compressed,
            "standard": self._templates.render_standard,
            "extreme": self._templates.render_extreme,
        }
        renderer = template_methods.get(template_name, self._templates.render_standard)
        rendered_brief = renderer(brief_data)

        # Step 4: Render top-of-fold card
        card_data = {
            "recommendation": brief_data.get("sections", {}).get("recommendation", ""),
            "counter_evidence": brief_data.get("sections", {}).get("counter_evidence", ""),
            "what_would_change_mind": brief_data.get("sections", {}).get(
                "what_would_change_mind", ""
            ),
            "instruments": decision_context.get("instruments", []),
            "action": decision_context.get("decision_type", ""),
            "confidence": brief_data.get("confidence", 0.0),
        }
        card = TopOfFoldCard.render_card(card_data)

        # Step 5: Extract provenance links
        provenance_links = brief_data.get("sections", {}).get("provenance_links", [])
        if not isinstance(provenance_links, list):
            provenance_links = [str(provenance_links)]

        logger.info(
            "composer.compose_complete",
            density_level=density_level,
            provenance_count=len(provenance_links),
        )

        return {
            "card": card,
            "brief": rendered_brief,
            "density_level": density_level,
            "provenance_links": provenance_links,
        }
