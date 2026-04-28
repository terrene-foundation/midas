"""Brief composer — consumes decision context, selects template, produces final brief.

Orchestrates the brief composition pipeline:
1. BriefEnricher fetches fabric grounding data (positions, risk, analogues)
2. Analyst produces the raw brief data (with grounding context injected)
3. DensityMatrix selects the appropriate density level
4. BriefTemplates renders the brief at that density
5. BriefSectionValidator validates grounding-prone sections
6. TopOfFoldCard produces the decide-in-10s card
"""

import structlog

from midas.agents.analyst import AnalystAgent
from midas.brief.density_matrix import DensityMatrix
from midas.brief.enricher import BriefEnricher
from midas.brief.templates import BriefTemplates
from midas.brief.top_of_fold import TopOfFoldCard
from midas.brief.validators import validate_all

logger = structlog.get_logger("midas.brief.composer")

# Sections validated for grounding quality
GROUNDING_SECTIONS = (
    "if_approved",
    "if_rejected",
    "historical_precedent",
    "what_would_change_mind",
)

MAX_VALIDATION_RETRIES = 2


class BriefComposer:
    """Consumes decision context, selects template, produces final brief.

    Parameters
    ----------
    analyst:
        An AnalystAgent instance for producing the raw brief.
    fabric_reader:
        A FabricReader instance for grounding data (positions, risk, analogues).
        If None, grounding enrichment is skipped.
    """

    def __init__(
        self,
        analyst: AnalystAgent,
        fabric_reader=None,
    ):
        self._analyst = analyst
        self._density = DensityMatrix()
        self._templates = BriefTemplates()
        self._enricher = BriefEnricher(fabric_reader) if fabric_reader else None

    async def _generate_brief_with_grounding(
        self,
        decision_context: dict,
        grounding_context: dict | None,
    ) -> dict:
        """Generate brief, optionally enriched with fabric grounding data."""
        context = dict(decision_context)
        if grounding_context:
            context["_grounding"] = grounding_context
        return await self._analyst.compose_brief(context)

    async def _validate_and_retry(
        self,
        brief_data: dict,
        retry_count: int,
    ) -> tuple[dict, int]:
        """Validate grounding-prone sections; store errors in brief_data for retry loop."""
        sections = brief_data.get("sections", {})
        validation_errors: list[str] = []

        for section_name in GROUNDING_SECTIONS:
            text = sections.get(section_name, "")
            issues = validate_all(section_name, text)
            if issues:
                validation_errors.extend(issues)
                logger.warning(
                    "composer.section_validation_failed",
                    section=section_name,
                    issues=issues,
                    retry=retry_count,
                )

        brief_data["_validation_errors"] = validation_errors

        if not validation_errors:
            return brief_data, retry_count

        if retry_count >= MAX_VALIDATION_RETRIES:
            logger.warning(
                "composer.validation_exhausted",
                errors=validation_errors,
            )

        return brief_data, retry_count

    async def compose(self, decision_context: dict) -> dict:
        """Compose brief from decision context.

        Parameters
        ----------
        decision_context:
            Dict with decision metadata including optional regime_band,
            dollar_impact, confidence_tier for density selection.
            May include 'instruments' and 'learner_family' for grounding.

        Returns
        -------
        dict
            Keys: 'card', 'brief', 'density_level', 'provenance_links',
            'grounding_applied', 'validation_issues'.
        """
        instruments = decision_context.get("instruments", [])
        learner_family = decision_context.get("learner_family", "ssl_transformer_v1")

        # Step 1: Fetch grounding context from fabric (positions, risk, analogues)
        grounding_context = None
        if self._enricher and instruments:
            try:
                grounding_context = await self._enricher.enrich(
                    instruments=instruments,
                    learner_family=learner_family,
                )
                logger.info(
                    "composer.grounding_enriched",
                    has_positions=bool(grounding_context.get("positions_text")),
                    has_risk=bool(grounding_context.get("risk_text")),
                    has_analogues=bool(grounding_context.get("analogues_text")),
                )
            except Exception as exc:
                logger.warning("composer.grounding_failed", error=str(exc))

        # Step 2: Produce raw brief from analyst (with grounding injected)
        brief_data = await self._generate_brief_with_grounding(decision_context, grounding_context)

        # Step 2b: Validate grounding-prone sections; retry on failure
        retry_count = 0
        for attempt in range(MAX_VALIDATION_RETRIES + 1):
            brief_data, retry_count = await self._validate_and_retry(brief_data, attempt)
            validation_errors = brief_data.get("_validation_errors", [])
            if retry_count >= MAX_VALIDATION_RETRIES or not validation_errors:
                break
            # Re-generate with validation feedback injected
            retry_context = dict(decision_context)
            retry_context["_validation_feedback"] = validation_errors
            brief_data = await self._analyst.compose_brief(retry_context)

        # Step 3: Determine density level
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

        # Step 4: Render brief at appropriate density
        template_methods = {
            "compressed": self._templates.render_compressed,
            "standard": self._templates.render_standard,
            "extreme": self._templates.render_extreme,
        }
        renderer = template_methods.get(template_name, self._templates.render_standard)
        rendered_brief = renderer(brief_data)

        # Step 5: Render top-of-fold card
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

        # Step 6: Extract provenance links
        provenance_links = brief_data.get("sections", {}).get("provenance_links", [])
        if not isinstance(provenance_links, list):
            provenance_links = [str(provenance_links)]

        # Collect final validation state
        final_validation_issues: list[str] = []
        for section_name in GROUNDING_SECTIONS:
            text = brief_data.get("sections", {}).get(section_name, "")
            final_validation_issues.extend(validate_all(section_name, text))

        logger.info(
            "composer.compose_complete",
            density_level=density_level,
            provenance_count=len(provenance_links),
            validation_issues=len(final_validation_issues),
            retries=retry_count,
        )

        return {
            "card": card,
            "brief": rendered_brief,
            "density_level": density_level,
            "provenance_links": provenance_links,
            "dollar_impact": decision_context.get("dollar_impact", 0),
            "thesis": brief_data.get("sections", {}).get("situation_summary", ""),
            "if_approved": brief_data.get("sections", {}).get("if_approved", ""),
            "if_rejected": brief_data.get("sections", {}).get("if_rejected", ""),
            "historical_precedent": brief_data.get("sections", {}).get("historical_precedent", ""),
            "what_would_change_mind": brief_data.get("sections", {}).get(
                "what_would_change_mind", ""
            ),
            "grounding_applied": grounding_context is not None,
            "validation_issues": final_validation_issues,
            "sections": [
                {
                    "title": "Thesis",
                    "content": brief_data.get("sections", {}).get("situation_summary", ""),
                    "type": "thesis",
                },
                {
                    "title": "Evidence",
                    "content": brief_data.get("sections", {}).get("evidence_assessment", ""),
                    "type": "evidence",
                },
                {
                    "title": "Recommendation",
                    "content": brief_data.get("sections", {}).get("recommendation", ""),
                    "type": "recommendation",
                },
                {
                    "title": "Counter-Evidence",
                    "content": brief_data.get("sections", {}).get("counter_evidence", ""),
                    "type": "counter",
                },
                {
                    "title": "If Approved",
                    "content": brief_data.get("sections", {}).get("if_approved", ""),
                    "type": "if_approved",
                },
                {
                    "title": "If Rejected",
                    "content": brief_data.get("sections", {}).get("if_rejected", ""),
                    "type": "if_rejected",
                },
                {
                    "title": "Historical Precedent",
                    "content": brief_data.get("sections", {}).get("historical_precedent", ""),
                    "type": "precedent",
                },
                {
                    "title": "What Would Change My Mind",
                    "content": brief_data.get("sections", {}).get("what_would_change_mind", ""),
                    "type": "flip_threshold",
                },
                {
                    "title": "Risk Factors",
                    "content": brief_data.get("sections", {}).get("risk_factors", ""),
                    "type": "risk",
                },
            ],
        }
