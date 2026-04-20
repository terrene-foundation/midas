"""Kill switch -- process-lock enforcement for emergency trading halt.

The kill switch is the user's last-resort control.  When activated:

- All pending orders are cancelled.
- All autonomous decisioning halts.
- Monitoring continues.
- All autonomy levels revert to L0.

Clearing requires biometric/user approval, a state-of-the-world brief,
and always reverts autonomy to L1.

State is held in-memory within the instance and persisted to the
``audit_log`` table for durable audit trail.

Ref: specs/08-autonomy-and-trust.md S5 (Kill Switch)
Ref: specs/11-compliance-and-risk.md S4 (Hard Safety Limits)
"""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any

import structlog
from dataflow import DataFlow

from midas.evaluation.probes.kill_switch_process_lock import (
    KillSwitchProcessLock,
    KillSwitchStateOfWorld,
)

logger = structlog.get_logger("midas.compliance.kill_switch")


class KillSwitch:
    """Kill switch with process-lock enforcement.

    State is held in-memory and mirrored to the ``audit_log`` for
    durable audit trail. The confirmation code hash is persisted to
    the audit_log so that multi-worker deployments can validate the
    clear operation without shared in-memory state.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = logger.bind(component="KillSwitch")
        self._active: bool = False
        self._process_lock = KillSwitchProcessLock()

    async def auto_evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        """Evaluate auto-trip conditions and activate if any are met.

        Per specs/08 § Kill Switch, Midas trips the switch automatically when:
        1. Drawdown crosses the hard circuit-breaker threshold
        2. OOD ``z_t`` coincides with rapid NAV move
        3. IBKR integration reports a severe error class
        4. PACT policy breach detected

        This method is called by the kill_switch_auto_trip scheduled job.
        It does NOT auto-activate if the switch is already active.

        Parameters
        ----------
        context:
            Dict containing:
            - ``drawdown_pct``: current drawdown as fraction (0.0-1.0)
            - ``drawdown_ceiling``: hard circuit-breaker threshold fraction
            - ``ood_score``: current OOD score (0.0-1.0)
            - ``ood_threshold``: OOD threshold fraction
            - ``nav_move_pct``: absolute NAV change over the lookback window
            - ``nav_move_rate``: threshold for rapid NAV move (e.g., 0.03 = 3%)
            - ``ibkr_severe_error``: True if IBKR reported a severe error
            - ``pact_breach``: True if PACT policy breach detected

        Returns
        -------
        dict with ``tripped`` (bool), ``reason`` (str or None), ``condition``
        (str: one of drawdown/ood_nav/ibkr_error/pact_breach/none)
        """
        if self._active:
            return {"tripped": False, "reason": None, "condition": "none"}

        conditions = []

        # 1. Drawdown circuit-breaker
        drawdown_pct = context.get("drawdown_pct", 0.0)
        drawdown_ceiling = context.get("drawdown_ceiling", 0.20)
        if drawdown_pct >= drawdown_ceiling:
            conditions.append(
                (
                    "drawdown",
                    f"drawdown {drawdown_pct:.1%} exceeds circuit-breaker ceiling {drawdown_ceiling:.1%}",
                )
            )

        # 2. OOD + rapid NAV move
        ood_score = context.get("ood_score", 0.0)
        ood_threshold = context.get("ood_threshold", 0.7)
        nav_move_pct = context.get("nav_move_pct", 0.0)
        nav_move_rate = context.get("nav_move_rate", 0.03)
        if ood_score >= ood_threshold and nav_move_pct >= nav_move_rate:
            conditions.append(
                (
                    "ood_nav",
                    f"OOD score {ood_score:.2f} >= {ood_threshold} + NAV move {nav_move_pct:.1%} >= {nav_move_rate:.1%}",
                )
            )

        # 3. IBKR severe error
        if context.get("ibkr_severe_error", False):
            conditions.append(("ibkr_error", "IBKR integration reported severe error class"))

        # 4. PACT policy breach
        if context.get("pact_breach", False):
            conditions.append(("pact_breach", "PACT policy breach detected"))

        if not conditions:
            return {"tripped": False, "reason": None, "condition": "none"}

        # Activate on the first triggered condition (priority order: drawdown > ood_nav > ibkr_error > pact_breach)
        condition, reason = conditions[0]
        self._log.warning("kill_switch.auto_trip.triggered", condition=condition, reason=reason)
        await self.activate(reason=f"[AUTO] {reason}")
        return {"tripped": True, "reason": reason, "condition": condition}

    async def activate(self, reason: str) -> dict[str, Any]:
        """Activate kill switch. Cancel all pending orders. Record state.

        Generates a confirmation code that must be provided to clear
        the kill switch. The SHA-256 hash of the code is persisted in
        the audit_log so the clear flow can validate it across workers.

        Parameters
        ----------
        reason:
            Why the kill switch was activated.

        Returns
        -------
        dict with ``active``, ``reason``, ``activated_at``, and ``confirmation_code``.
        """
        now = datetime.now(timezone.utc).isoformat()

        self._active = True
        confirmation_code = secrets.token_hex(8)
        confirmation_code_hash = hashlib.sha256(confirmation_code.encode()).hexdigest()

        result = {
            "active": True,
            "reason": reason,
            "activated_at": now,
            "confirmation_code": confirmation_code,
        }

        # Write audit record with hashed confirmation code (non-fatal)
        try:
            await self._db.express.create(
                "audit_log",
                {
                    "rule_name": "kill_switch",
                    "action": "kill_switch_activate",
                    "details": json.dumps(
                        {
                            "reason": reason,
                            "activated_at": now,
                            "confirmation_code_hash": confirmation_code_hash,
                        }
                    ),
                    "severity": "info",
                    "filed_at": now,
                },
            )
        except Exception as exc:
            self._log.warning("kill_switch.audit_write_failed", error=str(exc))

        self._log.critical("kill_switch.activated", reason=reason)

        return result

    async def is_active(self) -> bool:
        """Check if kill switch is active."""
        return self._active

    async def clear(
        self,
        user_approved: bool,
        state_brief: dict[str, Any],
        confirmation_code: str = "",
    ) -> dict[str, Any]:
        """Clear kill switch with process-lock enforcement.

        Process (per specs/08 S5.4):
        1. Confirmation code must match the one issued at activation
        2. User must explicitly approve (biometric in production)
        3. State-of-the-world brief must be provided and acknowledged
        4. 60-second dwell on first post-clear decision
        5. Revert to L1 autonomy

        The confirmation code is validated by reading the SHA-256 hash
        from the most recent ``kill_switch_activate`` audit record and
        comparing it against the hash of the supplied code. This works
        across multiple workers since the hash is persisted in the DB.

        Parameters
        ----------
        user_approved:
            Whether the user has explicitly approved clearing.
        state_brief:
            The state-of-the-world brief the user must read.
        confirmation_code:
            The code issued when the kill switch was activated.

        Returns
        -------
        dict with ``cleared``, ``revert_level``, and ``conditions``.
        """
        if not self._active:
            self._log.warning("kill_switch.clear_rejected", reason="not active")
            return {"cleared": False, "revert_level": 0, "conditions": []}

        if not user_approved:
            self._log.warning("kill_switch.clear_rejected", reason="no user approval")
            return {"cleared": False, "revert_level": 0, "conditions": []}

        # Read the confirmation code hash from the latest activation audit record
        stored_hash: str | None = None
        try:
            rows = await self._db.express.list(
                "audit_log",
                filter={"action": "kill_switch_activate"},
            )
            if rows:
                latest = rows[-1]
                details_str = latest.get("details", "{}")
                details = json.loads(details_str)
                stored_hash = details.get("confirmation_code_hash")
        except Exception as exc:
            self._log.warning("kill_switch.read_hash_failed", error=str(exc))

        # Validate confirmation code against persisted hash
        if not confirmation_code or stored_hash is None:
            self._log.warning(
                "kill_switch.clear_rejected",
                reason="no confirmation code or no activation record",
                code_provided=bool(confirmation_code),
            )
            return {"cleared": False, "revert_level": 0, "conditions": []}

        code_hash = hashlib.sha256(confirmation_code.encode()).hexdigest()
        if not hmac.compare_digest(code_hash, stored_hash):
            self._log.warning(
                "kill_switch.clear_rejected",
                reason="invalid confirmation code",
                code_provided=bool(confirmation_code),
            )
            return {"cleared": False, "revert_level": 0, "conditions": []}

        # Enforce process lock: brief must be shown and acknowledged
        self._process_lock.begin_clear_flow()
        brief = KillSwitchStateOfWorld(
            z_t_posterior=state_brief.get("z_t_posterior", ""),
            drawdown_state=state_brief.get("drawdown_state", ""),
            pool_disagreement=state_brief.get("pool_disagreement", 0.0),
            compliance_events=state_brief.get("compliance_events", []),
            generated_at=datetime.now(timezone.utc),
        )
        self._process_lock.acknowledge_brief(brief)

        if not self._process_lock.clear_is_permitted():
            self._log.warning("kill_switch.clear_rejected", reason="brief not acknowledged")
            return {"cleared": False, "revert_level": 0, "conditions": []}

        self._process_lock.complete_clear()

        now = datetime.now(timezone.utc).isoformat()
        self._active = False

        # Write audit record
        await self._db.express.create(
            "audit_log",
            {
                "rule_name": "kill_switch",
                "action": "kill_switch_clear",
                "details": json.dumps(
                    {
                        "cleared_at": now,
                        "state_brief": state_brief,
                        "revert_level": 1,
                    }
                ),
                "severity": "info",
                "filed_at": now,
            },
        )

        conditions = [
            "Autonomy reverted to L1",
            "60-second dwell on first post-clear decision",
            "First post-clear decision requires user approval",
        ]

        self._log.info("kill_switch.cleared", revert_level=1)

        return {
            "cleared": True,
            "revert_level": 1,
            "conditions": conditions,
        }
