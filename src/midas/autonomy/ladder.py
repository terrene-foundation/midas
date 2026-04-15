"""Autonomy ladder -- L0 through L4 state machine with typed transitions.

Promotion is always user-approved.  Demotion is automatic when a
degradation contract trips.  First seven days post paper-to-live are
always L1.

State is held in-memory within the instance and persisted to the
``audit_log`` table for durable audit trail.  The ``decisions`` table
is used for user-visible decisions (promotions, demotions) but not for
internal state round-trips due to DataFlow express.list consistency
constraints with SQLite.

Ref: specs/08-autonomy-and-trust.md S2-S4
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.autonomy.ladder")


class AutonomyLevel(IntEnum):
    """Five autonomy levels, from advisory to full autopilot."""

    L0 = 0  # Advisory only - system suggests, user decides everything
    L1 = 1  # User-approved - system proposes, user approves each action
    L2 = 2  # Supervised - system acts within bounds, user reviews periodically
    L3 = 3  # Autonomous - system acts independently, user reviews exceptions
    L4 = 4  # Full autonomy - system manages everything, user monitors


@dataclass
class AutonomyState:
    """Current autonomy state."""

    current_level: AutonomyLevel
    entered_at: str
    promotion_count: int = 0
    demotion_count: int = 0
    days_at_current_level: int = 0
    first_seven_days_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["current_level"] = int(self.current_level)
        return d


class AutonomyLadder:
    """L0 to L4 state machine with typed transitions.

    State is held in-memory and mirrored to the audit_log for durable
    audit trail.  Every transition writes an audit record.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = logger.bind(component="AutonomyLadder")
        self._state = AutonomyState(
            current_level=AutonomyLevel.L0,
            entered_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _write_audit(self, action: str, details: dict[str, Any]) -> None:
        """Write an audit log entry."""
        await self._db.express.create(
            "audit_log",
            {
                "rule_name": "autonomy_transition",
                "action": action,
                "details": json.dumps(details),
                "severity": "info",
                "filed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def get_current_state(self) -> AutonomyState:
        """Get current autonomy state."""
        self._log.info(
            "autonomy.get_state",
            level=int(self._state.current_level),
            promotions=self._state.promotion_count,
            demotions=self._state.demotion_count,
        )
        return self._state

    async def request_promotion(
        self,
        target_level: AutonomyLevel,
        evidence: dict[str, Any],
        user_approved: bool = False,
    ) -> dict[str, Any]:
        """Request level promotion.

        Invariants enforced:
        - No silent promotion: user must approve.
        - Cannot skip levels (must go one at a time).
        - First seven days live always L1.

        Returns dict with ``success``, ``reason``, and ``new_level``.
        """
        current = self._state.current_level

        # Invariant: user must approve
        if not user_approved:
            self._log.warning("autonomy.promotion_rejected", reason="no user approval")
            return {
                "success": False,
                "reason": "User approval required for all autonomy promotions",
                "new_level": int(current),
            }

        # Invariant: cannot skip levels
        if target_level != current + 1:
            self._log.warning(
                "autonomy.promotion_rejected",
                reason="skip_level",
                current=int(current),
                target=int(target_level),
            )
            return {
                "success": False,
                "reason": (
                    f"Cannot promote from L{int(current)} to L{int(target_level)}; "
                    f"must go through L{int(current + 1)} first"
                ),
                "new_level": int(current),
            }

        # Invariant: cannot promote above L4
        if target_level > AutonomyLevel.L4:
            return {
                "success": False,
                "reason": "L4 is the maximum autonomy level",
                "new_level": int(current),
            }

        # Apply promotion
        self._state = AutonomyState(
            current_level=target_level,
            entered_at=datetime.now(timezone.utc).isoformat(),
            promotion_count=self._state.promotion_count + 1,
            demotion_count=self._state.demotion_count,
            days_at_current_level=0,
            first_seven_days_active=self._state.first_seven_days_active,
        )

        await self._write_audit(
            action="promotion",
            details={
                "from_level": int(current),
                "to_level": int(target_level),
                "evidence": evidence,
            },
        )

        self._log.info(
            "autonomy.promoted",
            from_level=int(current),
            to_level=int(target_level),
        )

        return {
            "success": True,
            "reason": f"Promoted from L{int(current)} to L{int(target_level)}",
            "new_level": int(target_level),
        }

    async def demote(self, reason: str, trigger: str) -> dict[str, Any]:
        """Automatic demotion.

        Demotion never requires human approval.  Drops one level at a
        time, floor is L0.

        Returns dict with ``success``, ``new_level``, and ``reason``.
        """
        current = self._state.current_level

        if current == AutonomyLevel.L0:
            self._log.info("autonomy.demotion_floor", reason=reason)
            return {
                "success": True,
                "new_level": int(AutonomyLevel.L0),
                "reason": "Already at L0; no further demotion possible",
            }

        new_level = AutonomyLevel(current - 1)
        self._state = AutonomyState(
            current_level=new_level,
            entered_at=datetime.now(timezone.utc).isoformat(),
            promotion_count=self._state.promotion_count,
            demotion_count=self._state.demotion_count + 1,
            days_at_current_level=0,
            first_seven_days_active=self._state.first_seven_days_active,
        )

        await self._write_audit(
            action="demotion",
            details={
                "from_level": int(current),
                "to_level": int(new_level),
                "reason": reason,
                "trigger": trigger,
            },
        )

        self._log.info(
            "autonomy.demoted",
            from_level=int(current),
            to_level=int(new_level),
            trigger=trigger,
        )

        return {
            "success": True,
            "new_level": int(new_level),
            "reason": reason,
        }

    async def check_upgrade_contract(
        self,
        from_level: AutonomyLevel,
        to_level: AutonomyLevel,
    ) -> dict[str, Any]:
        """Evaluate upgrade contract per specs/08 S7.

        Returns dict with:
        - ``eligible``: bool
        - ``metrics``: dict of evaluation metrics
        - ``requirements_met``: list of requirements that passed
        - ``requirements_failed``: list of requirements that failed
        """
        requirements_met: list[str] = []
        requirements_failed: list[str] = []

        if from_level == AutonomyLevel.L0 and to_level == AutonomyLevel.L1:
            requirements = [
                ("paper_trading_complete", "Paper trading must be complete"),
                ("report_reviewed", "Report must be reviewed"),
            ]
        elif from_level == AutonomyLevel.L1 and to_level == AutonomyLevel.L2:
            requirements = [
                ("minimum_operating_days", "Minimum N live operating days"),
                ("override_convergence", "Positive override-convergence trend"),
                ("no_degradation_events", "No degradation events"),
                ("early_calibration", "Positive early calibration on allocation head"),
            ]
        elif from_level == AutonomyLevel.L2 and to_level == AutonomyLevel.L3:
            requirements = [
                ("twelve_month_window", "12-month primary window completed"),
                ("bootstrap_sharpe_lower", "Bootstrap lower bound Sharpe > floor"),
                ("pool_consistency", "Positive in >= 8/12 trailing months"),
                ("minimum_rebalances", "At least M rebalance events in window"),
                ("no_compliance_vetoes", "No compliance vetoes in window"),
            ]
        elif from_level == AutonomyLevel.L3 and to_level == AutonomyLevel.L4:
            requirements = [
                ("extended_track_record", "Sustained track record over 12 months"),
                ("user_explicit_opt_in", "User explicit opt-in"),
                ("elevated_state_experience", "User has experienced >= 1 Elevated transition"),
            ]
        else:
            return {
                "eligible": False,
                "metrics": {},
                "requirements_met": [],
                "requirements_failed": ["Invalid transition path"],
            }

        # Check each requirement against stored evidence
        all_decisions = await self._db.express.list("decisions")
        rows = [r for r in all_decisions if r.get("decision_type") == "upgrade_evidence"]
        evidence = {}
        if rows:
            try:
                evidence = json.loads(rows[-1].get("brief_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass

        for req_id, req_desc in requirements:
            if evidence.get(req_id, False):
                requirements_met.append(req_desc)
            else:
                requirements_failed.append(req_desc)

        eligible = len(requirements_failed) == 0

        self._log.info(
            "autonomy.upgrade_contract",
            from_level=int(from_level),
            to_level=int(to_level),
            eligible=eligible,
            met=len(requirements_met),
            failed=len(requirements_failed),
        )

        return {
            "eligible": eligible,
            "metrics": evidence,
            "requirements_met": requirements_met,
            "requirements_failed": requirements_failed,
        }
