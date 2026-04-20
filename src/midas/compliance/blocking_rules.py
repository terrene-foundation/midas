"""21 blocking compliance rules — hard gates that veto proposed trades.

Each rule's predicate returns True when the rule is VIOLATED.
Rules are data: registered at startup, modifiable without a release.

Ref: specs/11-compliance-and-risk.md S3.1 (Blocking Rules)
Ref: specs/14-ibkr-integration.md S12 (API and Execution Rules)
"""

from midas.compliance.rules_engine import ComplianceRule, RuleSeverity


def create_blocking_rules() -> list[ComplianceRule]:
    """Create the v1 set of 19 blocking rules."""
    rules: list[ComplianceRule] = []

    # -- 1. env.drawdown_ceiling ---------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="env.drawdown_ceiling",
            rule_name="Drawdown Ceiling",
            category="env",
            severity=RuleSeverity.BLOCK,
            description="Current drawdown must not exceed envelope ceiling",
            predicate=lambda ctx: ctx.get("current_drawdown", 0)
            > ctx.get("envelope", {}).get("drawdown_ceiling", 0.15),
        )
    )

    # -- 2. env.vol_target ---------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="env.vol_target",
            rule_name="Volatility Target Band",
            category="env",
            severity=RuleSeverity.BLOCK,
            description="Current volatility must be within the target band",
            predicate=lambda ctx: (
                ctx.get("current_vol", 0) < ctx.get("envelope", {}).get("vol_target_low", 0.08)
                or ctx.get("current_vol", 0) > ctx.get("envelope", {}).get("vol_target_high", 0.18)
            ),
        )
    )

    # -- 3. env.concentration.position ---------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="env.concentration.position",
            rule_name="Position Concentration",
            category="env",
            severity=RuleSeverity.BLOCK,
            description="Single position must not exceed concentration cap",
            predicate=lambda ctx: ctx.get("position_weight", 0)
            > ctx.get("envelope", {}).get("concentration_position_max", 0.10),
        )
    )

    # -- 4. env.concentration.sector -----------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="env.concentration.sector",
            rule_name="Sector Concentration",
            category="env",
            severity=RuleSeverity.BLOCK,
            description="Sector concentration must not exceed cap",
            predicate=lambda ctx: ctx.get("sector_weight", 0)
            > ctx.get("envelope", {}).get("concentration_sector_max", 0.30),
        )
    )

    # -- 5. env.universe -----------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="env.universe",
            rule_name="Universe Membership",
            category="env",
            severity=RuleSeverity.BLOCK,
            description="Instrument must be in approved universe",
            predicate=lambda ctx: ctx.get("instrument", "") not in ctx.get("approved_universe", []),
        )
    )

    # -- 6. env.cost_budget --------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="env.cost_budget",
            rule_name="Cost Budget",
            category="env",
            severity=RuleSeverity.BLOCK,
            description="Annualized costs must not exceed budget",
            predicate=lambda ctx: ctx.get("annualized_costs", 0)
            > ctx.get("envelope", {}).get("cost_budget_annual", 0.005),
        )
    )

    # -- 7. data.stale_price -------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="data.stale_price",
            rule_name="Stale Price Data",
            category="data",
            severity=RuleSeverity.BLOCK,
            description="Price data must be fresh (> 1 day for daily, > 15min for intraday)",
            predicate=lambda ctx: (
                (
                    ctx.get("frequency", "daily") == "daily"
                    and ctx.get("price_age_seconds", 0) > 86400
                )
                or (
                    ctx.get("frequency", "daily") == "intraday"
                    and ctx.get("price_age_seconds", 0) > 900
                )
            ),
        )
    )

    # -- 8. data.stale_fundamental -------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="data.stale_fundamental",
            rule_name="Stale Fundamental Data",
            category="data",
            severity=RuleSeverity.BLOCK,
            description="Fundamental data must not be older than 90 days",
            predicate=lambda ctx: ctx.get("fundamental_age_days", 0) > 90,
        )
    )

    # -- 9. data.stale_cost_inputs ------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="data.stale_cost_inputs",
            rule_name="Stale Cost Model Inputs",
            category="data",
            severity=RuleSeverity.BLOCK,
            description="Cost model inputs (volatility, ADV, spread) must be fresh",
            predicate=lambda ctx: (ctx.get("cost_input_age_seconds", 0) > 86400),
        )
    )

    # -- 10. state.kill_switch ------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="state.kill_switch",
            rule_name="Kill Switch Active",
            category="state",
            severity=RuleSeverity.BLOCK,
            description="No trades when kill switch is active",
            predicate=lambda ctx: ctx.get("kill_switch_active", False) is True,
        )
    )

    # -- 11. state.paper_trading ---------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="state.paper_trading",
            rule_name="Paper Trading Active",
            category="state",
            severity=RuleSeverity.BLOCK,
            description="Live orders blocked when paper trading is active",
            predicate=lambda ctx: ctx.get("paper_trading", False) is True
            and ctx.get("order_type", "") == "live",
        )
    )

    # -- 12. state.ood -------------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="state.ood",
            rule_name="Out-of-Distribution",
            category="state",
            severity=RuleSeverity.BLOCK,
            description="OOD actions must be manually approved",
            predicate=lambda ctx: (
                ctx.get("ood_score", 0) > ctx.get("ood_threshold", 0.7)
                and not ctx.get("manually_approved", False)
            ),
        )
    )

    # -- 13. autonomy.level_breach -------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="autonomy.level_breach",
            rule_name="Autonomy Level Breach",
            category="autonomy",
            severity=RuleSeverity.BLOCK,
            description="Action must not exceed current autonomy level",
            predicate=lambda ctx: ctx.get("action_required_level", 0)
            > ctx.get("current_autonomy_level", 0),
        )
    )

    # -- 14. model.confidence_floor ------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="model.confidence_floor",
            rule_name="Model Confidence Floor",
            category="model",
            severity=RuleSeverity.BLOCK,
            description="Model confidence must be above floor (0.3)",
            predicate=lambda ctx: ctx.get("model_confidence", 0) < ctx.get("confidence_floor", 0.3),
        )
    )

    # -- 15. model.pool_disagreement -----------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="model.pool_disagreement",
            rule_name="Pool Disagreement",
            category="model",
            severity=RuleSeverity.BLOCK,
            description="Pool disagreement must be below ceiling unless manually approved",
            predicate=lambda ctx: (
                ctx.get("pool_disagreement", 0) > ctx.get("disagreement_ceiling", 0.5)
                and not ctx.get("manually_approved", False)
            ),
        )
    )

    # -- 16. exec.freshness_at_execution -------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="exec.freshness_at_execution",
            rule_name="Execution Price Freshness",
            category="exec",
            severity=RuleSeverity.BLOCK,
            description="Price must not have moved beyond threshold since decision",
            predicate=lambda ctx: abs(ctx.get("price_change_pct", 0))
            > ctx.get("freshness_threshold", 0.005),
        )
    )

    # -- 17. api.ibkr_health -------------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="api.ibkr_health",
            rule_name="IBKR Health Check",
            category="api",
            severity=RuleSeverity.BLOCK,
            description="IBKR integration must report healthy",
            predicate=lambda ctx: ctx.get("ibkr_healthy", True) is False,
        )
    )

    # -- 18. api.ibkr_rate_limit ----------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="api.ibkr_rate_limit",
            rule_name="IBKR Rate Limit",
            category="api",
            severity=RuleSeverity.BLOCK,
            description="Block when IBKR API rate limit is approaching or breached",
            predicate=lambda ctx: ctx.get("ibkr_rate_limit_remaining", 100)
            <= ctx.get("ibkr_rate_limit_threshold", 5),
        )
    )

    # -- 19. api.ibkr_session_invalid -----------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="api.ibkr_session_invalid",
            rule_name="IBKR Session Invalid",
            category="api",
            severity=RuleSeverity.BLOCK,
            description="Block when IBKR OAuth session is invalid or expired",
            predicate=lambda ctx: ctx.get("ibkr_session_valid", True) is False,
        )
    )

    # -- 20. exec.quote_moved_since_brief -------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="exec.quote_moved_since_brief",
            rule_name="Quote Moved Since Brief",
            category="exec",
            severity=RuleSeverity.BLOCK,
            description="Block when price moved beyond regime-adaptive threshold since brief",
            predicate=lambda ctx: abs(ctx.get("price_change_since_brief_pct", 0))
            > ctx.get("regime_adaptive_threshold", 0.003),
        )
    )

    # -- 21. exec.participation_cap -------------------------------------------
    rules.append(
        ComplianceRule(
            rule_id="exec.participation_cap",
            rule_name="Participation Cap",
            category="exec",
            severity=RuleSeverity.BLOCK,
            description="Order size must not exceed tier-adjusted ADV participation cap",
            predicate=lambda ctx: (
                (
                    lambda order_size=float(ctx.get("order_size", 0)), adv=float(
                        ctx.get("avg_daily_volume", 1)
                    ), cap=float(ctx.get("participation_cap", 0.05)): adv
                    <= 0
                    or (abs(order_size) / adv) > cap
                )()
            ),
        )
    )

    return rules
