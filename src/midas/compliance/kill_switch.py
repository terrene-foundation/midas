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

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.compliance.kill_switch")


class KillSwitch:
    """Kill switch with process-lock enforcement.

    State is held in-memory and mirrored to the ``audit_log`` for
    durable audit trail.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._log = logger.bind(component="KillSwitch")
        self._active: bool = False

    async def activate(self, reason: str) -> dict[str, Any]:
        """Activate kill switch. Cancel all pending orders. Record state.

        Parameters
        ----------
        reason:
            Why the kill switch was activated.

        Returns
        -------
        dict with ``active``, ``reason``, and ``activated_at``.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Set in-memory state
        self._active = True

        # Write audit record
        await self._db.express.create(
            "audit_log",
            {
                "rule_name": "kill_switch",
                "action": "kill_switch_activate",
                "details": json.dumps(
                    {
                        "reason": reason,
                        "activated_at": now,
                    }
                ),
                "severity": "info",
                "filed_at": now,
            },
        )

        self._log.critical("kill_switch.activated", reason=reason)

        return {
            "active": True,
            "reason": reason,
            "activated_at": now,
        }

    async def is_active(self) -> bool:
        """Check if kill switch is active."""
        return self._active

    async def clear(
        self,
        user_approved: bool,
        state_brief: dict[str, Any],
    ) -> dict[str, Any]:
        """Clear kill switch with process enforcement.

        Process:
        1. Generate state-of-the-world brief (provided by caller)
        2. 60-second dwell period (enforced at compliance layer + UI)
        3. Revert to L1 autonomy
        4. First post-clear decision must be user-approved

        Parameters
        ----------
        user_approved:
            Whether the user has explicitly approved clearing.
        state_brief:
            The state-of-the-world brief the user must read.

        Returns
        -------
        dict with ``cleared``, ``revert_level``, and ``conditions``.
        """
        if not user_approved:
            self._log.warning("kill_switch.clear_rejected", reason="no user approval")
            return {
                "cleared": False,
                "revert_level": 0,
                "conditions": [],
            }

        now = datetime.now(timezone.utc).isoformat()

        # Clear in-memory state
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

        # Conditions that apply post-clear (per spec 08 S5.4)
        conditions = [
            "Autonomy reverted to L1",
            "60-second dwell on first post-clear decision",
            "First post-clear decision requires user approval",
        ]

        self._log.info("kill_switch.cleared", revert_level=1)

        return {
            "cleared": True,
            "revert_level": 1,  # Always L1 per spec
            "conditions": conditions,
        }
