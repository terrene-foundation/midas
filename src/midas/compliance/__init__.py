"""Midas Compliance — Pre-Trade Compliance Agent and rules engine.

The compliance layer has veto power over every proposed trade, at every
autonomy level, regardless of which model produced it.

Ref: specs/11-compliance-and-risk.md
"""

from midas.compliance.blocking_rules import create_blocking_rules
from midas.compliance.escalation_rules import create_escalation_rules
from midas.compliance.kill_switch import KillSwitch
from midas.compliance.rules_engine import (
    ComplianceRule,
    RuleEvaluation,
    RuleSeverity,
    RulesEngine,
)
from midas.compliance.warning_rules import create_warning_rules

__all__ = [
    "ComplianceRule",
    "KillSwitch",
    "RuleEvaluation",
    "RuleSeverity",
    "RulesEngine",
    "create_blocking_rules",
    "create_escalation_rules",
    "create_warning_rules",
]
