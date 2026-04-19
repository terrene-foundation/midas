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

import numpy as np
import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.autonomy.ladder")


class AutonomyLevel(IntEnum):
    """Five autonomy levels, per spec 08 §2."""

    L0 = 0  # Observer - default on install; mandatory during paper trading
    L1 = 1  # Co-Pilot - default after paper→live; briefs pre-loaded
    L2 = 2  # Delegated Routine - routine rebalances within bounds
    L3 = 3  # Delegated Tactical - Elevated-band tilts within pre-agreed constraints
    L4 = 4  # Envelope Autopilot - opt-in only; challenger model promotion


# Spec-compliant human-readable names per specs/08 §2.
LEVEL_NAMES: dict[int, str] = {
    0: "L0 Observer",
    1: "L1 Co-Pilot",
    2: "L2 Delegated Routine",
    3: "L3 Delegated Tactical",
    4: "L4 Envelope Autopilot",
}


@dataclass
class AutonomyState:
    """Current autonomy state."""

    current_level: AutonomyLevel
    entered_at: str
    promotion_count: int = 0
    demotion_count: int = 0
    days_at_current_level: int = 0
    first_seven_days_active: bool = False
    live_start_date: str = ""

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

    async def get_days_since_live(self) -> int:
        """Get the number of days since the paper-to-live transition.

        Looks up the audit_log for a paper-to-live transition record
        and computes days elapsed. Returns 999 if no transition found
        (meaning not yet live or no record).

        This value feeds the escalate.first_seven_days compliance rule
        context, ensuring every action is user-facing for the first 7
        live days regardless of autonomy level.
        """
        try:
            rows = await self._db.express.list(
                "audit_log",
                filter={"rule_name": "paper_trading_state"},
            )
            for row in reversed(rows):  # Most recent first
                action = row.get("action", "")
                if action == "live":
                    started_at = row.get("details", "")
                    if started_at:
                        try:
                            start_dt = datetime.fromisoformat(started_at)
                            days_elapsed = (datetime.now(timezone.utc) - start_dt).days
                            return days_elapsed
                        except (ValueError, TypeError):
                            pass
            # Not yet transitioned to live
            return 999
        except Exception as exc:
            self._log.warning("autonomy.get_days_since_live.error", error=str(exc))
            return 999

    def check_first_seven_days_elapsed(self) -> None:
        """Reset first_seven_days_active if 7 days have passed since live start.

        Per spec 08 S3: the first seven live days are always L1 (Co-Pilot).
        After 7 days, this flag is cleared so promotions beyond L1 are allowed.
        """
        if not self._state.first_seven_days_active:
            return
        if not self._state.live_start_date:
            return
        try:
            start_dt = datetime.fromisoformat(self._state.live_start_date)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            days_elapsed = (datetime.now(timezone.utc) - start_dt).days
            if days_elapsed >= 7:
                self._log.info(
                    "autonomy.first_seven_days_elapsed",
                    days_elapsed=days_elapsed,
                    live_start=self._state.live_start_date,
                )
                self._state.first_seven_days_active = False
        except (ValueError, TypeError):
            pass

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

        # Check whether the first-seven-days window has elapsed
        self.check_first_seven_days_elapsed()

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

        # Invariant: first seven live days require L1 Co-Pilot.
        # When promoting FROM L0 (paper-to-live transition), activate the
        # seven-day window.  When promoting above L1 while the window is
        # active, reject.
        if current == AutonomyLevel.L0 and target_level == AutonomyLevel.L1:
            # Paper-to-live transition: start the seven-day clock
            now_iso = datetime.now(timezone.utc).isoformat()
            self._state.first_seven_days_active = True
            self._state.live_start_date = now_iso
        elif self._state.first_seven_days_active and target_level > AutonomyLevel.L1:
            # Compute days remaining in the seven-day window
            days_remaining = 7
            if self._state.live_start_date:
                try:
                    start_dt = datetime.fromisoformat(self._state.live_start_date)
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                    elapsed = (datetime.now(timezone.utc) - start_dt).days
                    days_remaining = max(0, 7 - elapsed)
                except (ValueError, TypeError):
                    pass
            self._log.warning(
                "autonomy.promotion_rejected",
                reason="first_seven_days",
                target=int(target_level),
                days_remaining=days_remaining,
            )
            return {
                "success": False,
                "reason": (
                    f"First seven live days require L1 Co-Pilot — "
                    f"{days_remaining} days remaining"
                ),
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
            live_start_date=self._state.live_start_date,
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
            live_start_date=self._state.live_start_date,
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

        # L2→L3 and L3→L4: compute 12-month bootstrap CI from performance data
        if from_level >= AutonomyLevel.L2 and to_level >= AutonomyLevel.L3:
            bootstrap_result = self._compute_promotion_bootstrap(evidence)
            evidence.update(bootstrap_result)

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

    BOOTSTRAP_SAMPLES = 1000
    BOOTSTRAP_SEED = 42
    SHARPE_FLOOR = 0.5
    TWELVE_MONTH_DAYS = 252

    def _compute_promotion_bootstrap(self, evidence: dict) -> dict:
        """Compute 12-month bootstrap CI for promotion eligibility.

        Per spec 08 §S4: L3/L4 promotion requires 12-month primary window
        with bootstrap CI lower bound exceeding floor. 3-month window is
        context signal only, NOT a promotion trigger.
        """
        monthly_returns = evidence.get("monthly_returns", [])
        result: dict[str, Any] = {
            "bootstrap_n": self.BOOTSTRAP_SAMPLES,
            "twelve_month_days_required": self.TWELVE_MONTH_DAYS,
        }

        if len(monthly_returns) < 12:
            result["twelve_month_window"] = False
            result["bootstrap_sharpe_lower"] = False
            result["bootstrap_ci"] = None
            result["months_available"] = len(monthly_returns)
            return result

        returns = np.array(monthly_returns[-12:], dtype=float)
        if np.std(returns) == 0:
            result["twelve_month_window"] = True
            result["bootstrap_sharpe_lower"] = False
            result["bootstrap_ci"] = {"point": 0.0, "ci_lower": 0.0, "ci_upper": 0.0}
            result["months_available"] = len(returns)
            return result

        rng = np.random.default_rng(self.BOOTSTRAP_SEED)
        sharpe_samples = np.empty(self.BOOTSTRAP_SAMPLES)
        for i in range(self.BOOTSTRAP_SAMPLES):
            sample = rng.choice(returns, size=len(returns), replace=True)
            std = np.std(sample, ddof=1)
            sharpe_samples[i] = np.mean(sample) / std if std > 0 else 0.0

        ci_lower = float(np.percentile(sharpe_samples, 2.5))
        ci_upper = float(np.percentile(sharpe_samples, 97.5))
        point_sharpe = float(np.mean(returns) / np.std(returns, ddof=1))

        result["twelve_month_window"] = len(monthly_returns) >= 12
        result["bootstrap_sharpe_lower"] = ci_lower > self.SHARPE_FLOOR
        result["bootstrap_ci"] = {
            "point": point_sharpe,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "floor": self.SHARPE_FLOOR,
        }
        result["months_available"] = len(monthly_returns)
        return result
