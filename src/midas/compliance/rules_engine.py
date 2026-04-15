"""Data-driven compliance rules engine with typed predicates.

Rules are data, not code.  Each rule has a predicate that returns True
when the rule is VIOLATED.  The engine evaluates all rules against a
context dict and produces typed evaluations.

Default-deny posture: if rule evaluation raises an exception the result
is treated as a violation (blocked).

Ref: specs/11-compliance-and-risk.md S2 (Pre-Trade Compliance Agent)
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

import structlog
from dataflow import DataFlow

logger = structlog.get_logger("midas.compliance")


class RuleSeverity(Enum):
    """Rule outcome severity levels."""

    PASS = "pass"
    WARN = "warn"
    ESCALATE = "escalate"
    BLOCK = "block"


@dataclass
class ComplianceRule:
    """A single compliance rule.

    The ``predicate`` callable receives a context dict and returns True
    if the rule is VIOLATED (i.e. the condition that should block/warn
    is met).
    """

    rule_id: str
    rule_name: str
    category: str  # env, data, state, autonomy, model, exec, api, escalate
    severity: RuleSeverity
    description: str
    predicate: Callable[..., bool]  # Returns True if VIOLATED
    parameters: dict[str, Any] | None = None


@dataclass
class RuleEvaluation:
    """Result of evaluating a rule."""

    rule_id: str
    rule_name: str
    severity: RuleSeverity
    passed: bool
    message: str
    details: dict[str, Any] | None = None


class RulesEngine:
    """Data-driven rules engine with typed predicates.

    Rules are registered via ``register_rule`` / ``register_rules`` and
    evaluated against a context dict.  Every evaluation can optionally
    be persisted to the audit_log table.
    """

    def __init__(self, db: DataFlow):
        self._db = db
        self._rules: dict[str, ComplianceRule] = {}
        self._log = logger.bind(component="RulesEngine")

    def register_rule(self, rule: ComplianceRule) -> None:
        """Register a compliance rule."""
        if rule.rule_id in self._rules:
            self._log.warning(
                "rules.register_duplicate",
                rule_id=rule.rule_id,
            )
        self._rules[rule.rule_id] = rule
        self._log.info(
            "rules.registered",
            rule_id=rule.rule_id,
            category=rule.category,
            severity=rule.severity.value,
        )

    def register_rules(self, rules: list[ComplianceRule]) -> None:
        """Register multiple rules."""
        for rule in rules:
            self.register_rule(rule)

    async def evaluate(self, context: dict[str, Any]) -> list[RuleEvaluation]:
        """Evaluate all rules against context.

        Returns one ``RuleEvaluation`` per registered rule.
        """
        results: list[RuleEvaluation] = []
        for rule_id, rule in self._rules.items():
            result = await self._evaluate_single(rule, context)
            results.append(result)

        self._log.info(
            "rules.evaluate_complete",
            total=len(results),
            passed=sum(1 for r in results if r.passed),
            failed=sum(1 for r in results if not r.passed),
        )
        return results

    async def evaluate_rule(self, rule_id: str, context: dict[str, Any]) -> RuleEvaluation:
        """Evaluate a single rule."""
        rule = self._rules.get(rule_id)
        if rule is None:
            self._log.error("rules.evaluate_unknown", rule_id=rule_id)
            # Default-deny: unknown rule = blocked
            return RuleEvaluation(
                rule_id=rule_id,
                rule_name="Unknown Rule",
                severity=RuleSeverity.BLOCK,
                passed=False,
                message=f"Rule {rule_id} not found; default-deny",
            )
        return await self._evaluate_single(rule, context)

    async def _evaluate_single(
        self, rule: ComplianceRule, context: dict[str, Any]
    ) -> RuleEvaluation:
        """Evaluate one rule with default-deny on exception."""
        try:
            violated = rule.predicate(context)
            passed = not violated
            message = f"{rule.rule_name}: OK" if passed else f"{rule.rule_name}: VIOLATED"
        except Exception as exc:
            # Default-deny: evaluation failure = blocked
            self._log.error(
                "rules.evaluation_exception",
                rule_id=rule.rule_id,
                error=str(exc),
            )
            return RuleEvaluation(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                severity=rule.severity,
                passed=False,
                message=f"{rule.rule_name}: evaluation error ({exc}); default-deny",
                details={"error": str(exc)},
            )

        return RuleEvaluation(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            severity=rule.severity,
            passed=passed,
            message=message,
        )

    async def get_blocking_violations(self, context: dict[str, Any]) -> list[RuleEvaluation]:
        """Get only blocking violations (severity=BLOCK and not passed)."""
        results = await self.evaluate(context)
        return [r for r in results if r.severity == RuleSeverity.BLOCK and not r.passed]

    async def audit_evaluation(
        self,
        evaluations: list[RuleEvaluation],
        decision_id: str | None = None,
    ) -> None:
        """Write evaluation results to audit_log.

        One audit_log row per evaluation.
        """
        now = datetime.now(timezone.utc).isoformat()

        for ev in evaluations:
            await self._db.express.create(
                "audit_log",
                {
                    "rule_name": ev.rule_name,
                    "action": "compliance_evaluation",
                    "details": json.dumps(
                        {
                            "rule_id": ev.rule_id,
                            "severity": ev.severity.value,
                            "passed": ev.passed,
                            "message": ev.message,
                            "details": ev.details,
                        }
                    ),
                    "severity": ev.severity.value,
                    "decision_id": decision_id or "",
                    "filed_at": now,
                },
            )

        self._log.info(
            "rules.audit_written",
            count=len(evaluations),
            decision_id=decision_id,
        )

    def list_rules(self) -> list[dict[str, Any]]:
        """List all registered rules as dicts."""
        result = []
        for rule in self._rules.values():
            d: dict[str, Any] = {
                "rule_id": rule.rule_id,
                "rule_name": rule.rule_name,
                "category": rule.category,
                "severity": rule.severity.value,
                "description": rule.description,
            }
            if rule.parameters is not None:
                d["parameters"] = rule.parameters
            result.append(d)
        return result
