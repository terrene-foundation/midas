"""5 warning compliance rules — non-blocking informational alerts.

Warning rules do not block or escalate; they surface information in
the decision brief.  The predicate returns True when the warning
condition is met (meaning the rule is VIOLATED in the sense that
the condition warrants surfacing).

Ref: specs/11-compliance-and-risk.md S3.3 (Warning Rules)
"""

from midas.compliance.rules_engine import ComplianceRule, RuleSeverity


def create_warning_rules() -> list[ComplianceRule]:
    """Create the v1 set of 5 warning rules."""
    rules: list[ComplianceRule] = []

    # -- 1. warn.high_volatility ---------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.high_volatility",
            rule_name="High Volatility",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when current vol exceeds 80th percentile",
            predicate=lambda ctx: ctx.get("current_vol", 0)
            > ctx.get("vol_80th_percentile", float("inf")),
        )
    )

    # -- 2. warn.elevated_attention ------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.elevated_attention",
            rule_name="Elevated Attention Band",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when a_t enters ELEVATED band",
            predicate=lambda ctx: ctx.get("attention_band", "") == "ELEVATED",
        )
    )

    # -- 3. warn.model_calibration_drift -------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.model_calibration_drift",
            rule_name="Model Calibration Drift",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when model calibration drifts beyond threshold",
            predicate=lambda ctx: ctx.get("calibration_drift", 0)
            > ctx.get("drift_threshold", 0.10),
        )
    )

    # -- 4. warn.high_cost_ratio ---------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.high_cost_ratio",
            rule_name="High Cost Ratio",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when cost ratio exceeds threshold",
            predicate=lambda ctx: ctx.get("cost_ratio", 0) > ctx.get("cost_ratio_threshold", 0.5),
        )
    )

    # -- 5. warn.approaching_concentration_limit -----------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.approaching_concentration_limit",
            rule_name="Approaching Concentration Limit",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn at 80% of concentration limit",
            predicate=lambda ctx: (
                ctx.get("position_weight", 0) > ctx.get("concentration_limit", 1.0) * 0.80
            ),
        )
    )

    return rules
