"""7 escalation compliance rules — user-facing escalations.

Escalation rules do not block the action; they escalate it to the
user-facing Decisions surface.  The predicate returns True when the
escalation condition is met (meaning the rule is VIOLATED in the sense
that the action needs human attention).

Ref: specs/11-compliance-and-risk.md S3.2 (Escalation Rules)
"""

from midas.compliance.rules_engine import ComplianceRule, RuleSeverity


def create_escalation_rules() -> list[ComplianceRule]:
    """Create the v1 set of 7 escalation rules."""
    rules: list[ComplianceRule] = []

    # -- 1. escalate.urgent_band ---------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="escalate.urgent_band",
            rule_name="Urgent Attention Band",
            category="escalate",
            severity=RuleSeverity.ESCALATE,
            description="Actions in URGENT band must be escalated when autonomy < L3",
            predicate=lambda ctx: (
                ctx.get("attention_band", "") == "urgent"
                and ctx.get("current_autonomy_level", 0) < 3
            ),
        )
    )

    # -- 2. escalate.crisis_band ---------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="escalate.crisis_band",
            rule_name="Crisis Attention Band",
            category="escalate",
            severity=RuleSeverity.ESCALATE,
            description="Actions in CRISIS band must always be escalated",
            predicate=lambda ctx: ctx.get("attention_band", "") == "crisis",
        )
    )

    # -- 3. escalate.envelope_change -----------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="escalate.envelope_change",
            rule_name="Envelope Change",
            category="escalate",
            severity=RuleSeverity.ESCALATE,
            description="Envelope modifications must be escalated to user",
            predicate=lambda ctx: ctx.get("action_type", "") == "envelope_change",
        )
    )

    # -- 4. escalate.model_promotion -----------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="escalate.model_promotion",
            rule_name="Model Promotion",
            category="escalate",
            severity=RuleSeverity.ESCALATE,
            description="Champion model promotions must be escalated",
            predicate=lambda ctx: ctx.get("action_type", "") == "model_promotion",
        )
    )

    # -- 5. escalate.autonomy_upgrade ----------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="escalate.autonomy_upgrade",
            rule_name="Autonomy Upgrade",
            category="escalate",
            severity=RuleSeverity.ESCALATE,
            description="Autonomy level upgrades must be escalated",
            predicate=lambda ctx: ctx.get("action_type", "") == "autonomy_upgrade",
        )
    )

    # -- 6. escalate.debate_open ---------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="escalate.debate_open",
            rule_name="Open Debate Thread",
            category="escalate",
            severity=RuleSeverity.ESCALATE,
            description="Actions related to a pending debate must be routed to the thread",
            predicate=lambda ctx: ctx.get("debate_open", False) is True,
        )
    )

    # -- 7. escalate.first_seven_days ----------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="escalate.first_seven_days",
            rule_name="First Seven Live Days",
            category="escalate",
            severity=RuleSeverity.ESCALATE,
            description=(
                "Every action is user-facing for the first 7 days "
                "post paper-to-live, regardless of autonomy level"
            ),
            predicate=lambda ctx: (
                ctx.get("days_since_live", 999) <= 7 and ctx.get("current_autonomy_level", 0) > 1
            ),
        )
    )

    return rules
