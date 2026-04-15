"""Investment envelope — user-owned boundary parameters.

The envelope defines the hard constraints within which Midas operates
autonomously.  Only the user can change the envelope; Midas may tighten
dynamically but never widen.

Ref: specs/08-autonomy-and-trust.md S1 (The Trust Boundary)
Ref: specs/11-compliance-and-risk.md S5 (Envelope Enforcement)
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.autonomy.envelope")


@dataclass
class InvestmentEnvelope:
    """Envelope parameters controlling what the system can do autonomously.

    All fields have conservative defaults aligned with spec 08 S1.
    """

    drawdown_ceiling: float = 0.15  # Max drawdown before kill switch
    vol_target_low: float = 0.08
    vol_target_high: float = 0.18
    concentration_position_max: float = 0.10  # Max single position
    concentration_sector_max: float = 0.30  # Max single sector
    universe_exclusions: list[str] = field(default_factory=list)
    cost_budget_annual: float = 0.005  # 50bps annual cost budget
    max_turnover_daily: float = 0.20

    def validate(self) -> list[str]:
        """Validate envelope parameters. Returns list of violations."""
        violations: list[str] = []

        if self.drawdown_ceiling <= 0:
            violations.append("drawdown_ceiling must be positive")

        if self.vol_target_low < 0:
            violations.append("vol_target_low must be non-negative")

        if self.vol_target_high <= 0:
            violations.append("vol_target_high must be positive")

        if self.vol_target_low > self.vol_target_high:
            violations.append("vol_target_low must not exceed vol_target_high")

        if not (0 < self.concentration_position_max <= 1.0):
            violations.append("concentration_position_max must be in (0, 1]")

        if not (0 < self.concentration_sector_max <= 1.0):
            violations.append("concentration_sector_max must be in (0, 1]")

        if self.concentration_position_max > self.concentration_sector_max:
            violations.append(
                "concentration_position_max should not exceed concentration_sector_max"
            )

        if self.cost_budget_annual < 0:
            violations.append("cost_budget_annual must be non-negative")

        if self.max_turnover_daily < 0:
            violations.append("max_turnover_daily must be non-negative")

        return violations

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InvestmentEnvelope":
        """Deserialize from dict.  Unknown keys are ignored."""
        known = {
            k: v
            for k, v in data.items()
            if k in cls.__dataclass_fields__  # type: ignore[attr-defined]
        }
        return cls(**known)


class EnvelopeStore:
    """Read/write envelope from fabric.

    The envelope is held in-memory within the instance.  Updates are
    persisted to the ``audit_log`` table for durable audit trail.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = logger.bind(component="EnvelopeStore")
        self._envelope: InvestmentEnvelope = InvestmentEnvelope()

    async def get_envelope(self) -> InvestmentEnvelope:
        """Read current envelope.

        Returns the current in-memory envelope, which is the default
        until explicitly updated.
        """
        self._log.info(
            "envelope.get",
            drawdown_ceiling=self._envelope.drawdown_ceiling,
        )
        return self._envelope

    async def update_envelope(
        self,
        envelope: InvestmentEnvelope,
        approved_by: str,
        reason: str,
    ) -> dict[str, Any]:
        """Update envelope with audit trail.

        Parameters
        ----------
        envelope:
            The new envelope to persist.
        approved_by:
            Identifier of the user who approved the change.
        reason:
            Human-readable reason for the change.

        Returns
        -------
        dict with ``success`` and metadata.
        """
        violations = envelope.validate()
        if violations:
            self._log.error("envelope.update_rejected", violations=violations)
            return {
                "success": False,
                "reason": "Envelope validation failed",
                "violations": violations,
            }

        now = datetime.now(timezone.utc).isoformat()

        # Update in-memory envelope
        self._envelope = envelope

        # Write audit log entry
        await self._db.express.create(
            "audit_log",
            {
                "rule_name": "envelope_update",
                "action": "envelope_update",
                "details": json.dumps(
                    {
                        "approved_by": approved_by,
                        "reason": reason,
                        "envelope": envelope.to_dict(),
                    }
                ),
                "severity": "info",
                "filed_at": now,
            },
        )

        self._log.info(
            "envelope.updated",
            approved_by=approved_by,
            drawdown_ceiling=envelope.drawdown_ceiling,
        )

        return {"success": True, "filed_at": now}
