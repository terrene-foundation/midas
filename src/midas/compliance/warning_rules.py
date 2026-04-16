"""7 warning compliance rules — non-blocking informational alerts.

Warning rules do not block or escalate; they surface information in
the decision brief.  The predicate returns True when the warning
condition is met (meaning the rule is VIOLATED in the sense that
the condition warrants surfacing).

Ref: specs/11-compliance-and-risk.md S3.3 (Warning Rules)
Ref: specs/14-ibkr-integration.md S12 (Execution Warning Rules)
"""

from midas.compliance.rules_engine import ComplianceRule, RuleSeverity


def create_warning_rules() -> list[ComplianceRule]:
    """Create the v1 set of 7 warning rules."""
    rules: list[ComplianceRule] = []

    # -- 1. warn.turnover_high ------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.turnover_high",
            rule_name="High Turnover",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when monthly turnover exceeds threshold",
            predicate=lambda ctx: ctx.get("monthly_turnover", 0)
            > ctx.get("turnover_threshold", float("inf")),
        )
    )

    # -- 2. warn.fee_intensity -------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.fee_intensity",
            rule_name="Fee Intensity",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when fee ratio exceeds threshold",
            predicate=lambda ctx: ctx.get("fee_ratio", 0) > ctx.get("fee_ratio_threshold", 0.5),
        )
    )

    # -- 3. warn.model_calibration_drift --------------------------------------
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

    # -- 4. warn.user_override_pattern ----------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.user_override_pattern",
            rule_name="User Override Pattern",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when user override rate exceeds threshold",
            predicate=lambda ctx: ctx.get("override_rate", 0)
            > ctx.get("override_rate_threshold", 0.5),
        )
    )

    # -- 5. warn.fx_exposure ---------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.fx_exposure",
            rule_name="FX Exposure",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when FX concentration exceeds threshold",
            predicate=lambda ctx: ctx.get("fx_exposure", 0)
            > ctx.get("fx_exposure_threshold", 0.30),
        )
    )

    # -- 6. warn.halted --------------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.halted",
            rule_name="Instrument Halted",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when instrument is halted",
            predicate=lambda ctx: ctx.get("instrument_halted", False) is True,
        )
    )

    # -- 7. warn.auction_window -----------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="warn.auction_window",
            rule_name="Auction Window",
            category="warn",
            severity=RuleSeverity.WARN,
            description="Warn when order submitted during auction window",
            predicate=lambda ctx: ctx.get("in_auction_window", False) is True,
        )
    )

    return rules
