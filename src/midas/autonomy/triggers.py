"""Demotion triggers — automatic degradation detection.

Triggers run on every decision cycle.  When a trigger fires it returns
a structured demotion payload that the autonomy ladder processes.

Ref: specs/08-autonomy-and-trust.md S4 (Demotion Protocol)
"""

from typing import Any

import structlog
from dataflow import DataFlow

from midas.autonomy.envelope import InvestmentEnvelope

logger = structlog.get_logger("midas.autonomy.triggers")


class DemotionTriggers:
    """Automatic demotion triggers.

    Each check method returns ``None`` when the trigger does not fire,
    or a dict with ``trigger``, ``reason``, and ``suggested_level``
    when it does.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = logger.bind(component="DemotionTriggers")

    async def check_drawdown_breach(
        self,
        envelope: InvestmentEnvelope,
        current_drawdown: float = 0.0,
    ) -> dict[str, Any] | None:
        """Check if drawdown exceeds ceiling.

        Parameters
        ----------
        envelope:
            The current investment envelope.
        current_drawdown:
            Current portfolio drawdown as a fraction (e.g. 0.12 for 12%).

        Returns
        -------
        Demotion payload if triggered, else None.
        """
        if current_drawdown > envelope.drawdown_ceiling:
            self._log.warning(
                "trigger.drawdown_breach",
                current=current_drawdown,
                ceiling=envelope.drawdown_ceiling,
            )
            return {
                "trigger": "drawdown_breach",
                "reason": (
                    f"Drawdown {current_drawdown:.2%} exceeds "
                    f"ceiling {envelope.drawdown_ceiling:.2%}"
                ),
                "suggested_level": 1,
                "details": {
                    "current_drawdown": current_drawdown,
                    "ceiling": envelope.drawdown_ceiling,
                },
            }
        return None

    async def check_model_health(
        self,
        champion_demoted: bool = False,
    ) -> dict[str, Any] | None:
        """Check if champion model was demoted.

        Parameters
        ----------
        champion_demoted:
            Whether the live champion model has been demoted.

        Returns
        -------
        Demotion payload if triggered, else None.
        """
        if champion_demoted:
            self._log.warning("trigger.model_demotion", champion_demoted=True)
            return {
                "trigger": "model_health",
                "reason": "Champion model was demoted",
                "suggested_level": 2,
                "details": {"champion_demoted": True},
            }
        return None

    async def check_override_rate(
        self,
        window_days: int = 30,
        override_rate: float = 0.0,
        threshold: float = 0.5,
    ) -> dict[str, Any] | None:
        """Check if user override rate exceeds threshold.

        Parameters
        ----------
        window_days:
            Trailing window in days.
        override_rate:
            Fraction of decisions overridden in the window.
        threshold:
            Maximum acceptable override rate.

        Returns
        -------
        Demotion payload if triggered, else None.
        """
        if override_rate > threshold:
            self._log.warning(
                "trigger.override_rate",
                rate=override_rate,
                threshold=threshold,
                window_days=window_days,
            )
            return {
                "trigger": "override_rate",
                "reason": (
                    f"Override rate {override_rate:.0%} over {window_days}d "
                    f"exceeds threshold {threshold:.0%}"
                ),
                "suggested_level": 1,
                "details": {
                    "override_rate": override_rate,
                    "threshold": threshold,
                    "window_days": window_days,
                },
            }
        return None

    async def check_all_triggers(
        self,
        envelope: InvestmentEnvelope,
        current_drawdown: float = 0.0,
        champion_demoted: bool = False,
        override_rate: float = 0.0,
        override_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Run all demotion checks. Returns list of triggered demotions.

        Each element is the payload from an individual trigger that fired.
        """
        results: list[dict[str, Any]] = []

        dd_result = await self.check_drawdown_breach(envelope, current_drawdown)
        if dd_result is not None:
            results.append(dd_result)

        model_result = await self.check_model_health(champion_demoted)
        if model_result is not None:
            results.append(model_result)

        override_result = await self.check_override_rate(
            window_days=30,
            override_rate=override_rate,
            threshold=override_threshold,
        )
        if override_result is not None:
            results.append(override_result)

        if results:
            self._log.info(
                "trigger.check_all",
                triggered=len(results),
                triggers=[r["trigger"] for r in results],
            )

        return results
