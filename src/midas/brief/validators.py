"""Brief section validators — enforce grounding standards on 4 placeholder-prone sections.

Per specs/07-evidence-first-decision.md S2.3-S2.6, four sections are particularly
prone to generic placeholder text when the LLM has no grounding data:

- if_approved        → MUST contain ≥1 dollar amount AND ≥1 risk metric
- if_rejected        → MUST reference current position AND drawdown probability
- historical_precedent → MUST contain ≥1 analogue with outcome
- what_would_change_mind → MUST contain ≥1 numeric threshold

Each validator returns a list of actionable missing-element descriptions.
Empty list means the section passes validation.

Ref: specs/07-evidence-first-decision.md S2.3-S2.6
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger("midas.brief.validators")


# Patterns ---------------------------------------------------------------

# Matches: $1,234.56 | $1B | $1.5M | USD 1,234 | 10000 USD | etc.
DOLLAR_AMOUNT_RE = re.compile(
    r"\$?\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*(?:USD|BPS|bps|million|billion|M|B|T)?",
    re.IGNORECASE,
)

# Risk metric keywords — these indicate quantitative risk assessment
RISK_METRIC_RE = re.compile(
    r"(?i)\b("
    r"VaR|Value at Risk|volatility|vol\b|"
    r"drawdown|max drawdown|"
    r"Sharpe|Sortino|Calarino|"
    r"beta|alpha|"
    r"expected shortfall|cvar|CVaR|"
    r"tail risk|risk parity|"
    r"std dev|standard deviation|variance|"
    r"downside deviation|"
    r"percentile|\bCV\b|"
    r"sharpe ratio|sortino ratio"
    r")\b",
)

# Position retention — references to keeping/holding/retaining current allocation
POSITION_RETAIN_RE = re.compile(
    r"(?i)\b("
    r"remain|retain|keep|maintain|"
    r"stay invested|stay in|hold|holding|"
    r"status quo|no change|unchanged|"
    r"current position|existing allocation|"
    r"persists|persistence|continues"
    r")\b",
)

# Drawdown probability keywords
DRAWDOWN_RE = re.compile(
    r"(?i)\b("
    r"drawdown|draw down|"
    r"loss given|"
    r"downside scenario|downside case|"
    r"worst case|loss scenario|"
    r"probability of|likelihood of.*(loss|drawdown|decline)|"
    r"\d+%?\s*(?:probability|chance|odds)"
    r")\b",
)

# Historical analogue — mentions of past decisions, similar regimes, prior trades
ANALOGUE_RE = re.compile(
    r"(?i)\b("
    r"when|in\s+200\d|back\s+in|prior|previous|last\s+time|"
    r"similar.*regime|regime.*similar|analogous|similar period|"
    r"episode|instance|case|"
    r"this\s+(happened|occurred|played\s+out)|"
    r"if\s+we\s+(bought|sold|rotated|allocated)"
    r")\b",
)

# Outcome keywords — result of a prior analogue
OUTCOME_RE = re.compile(
    r"(?i)\b("
    r"result|returned|gained|lost|performed|outcome|effect|impact|"
    r"ended\s+up|ended\s+down|"
    r"realized|realised|experienced|"
    r"profit|loss|return|decline|advance|gain|"
    r"by\s+\d|"
    r"[+-]\d|"
    r"\d+%|"
    r"\d+\s+bps|"
    r"was\s+\$|was\s+up|was\s+down|"
    r"up\s+\d|down\s+\d"
    r")\b",
)

# Numeric threshold — any specific number used as a decision boundary
# Structure: (operator_group + value) — top-level alternation always starts with operator
THRESHOLD_RE = re.compile(
    r"(?i)"
    r"(?:"
    # if/when/unless — complex continuation
    r"(if|when|unless)\s+(?:the\s+)?(?:price\s+)?(?:of\s+)?"
    r"|"
    # single-word operators followed directly by value (exceed/break allow -s)
    r"(?:above|below|over|under|exceed|break)(?:s)?\s+"
    r"|"
    # two-word operators (drop below, rise above, break below) — allow -s
    r"(?:drops?\s+below|rises?\s+above|breaks?\s+below)\s+"
    r"|"
    # comparative operators
    r"(?:greater|less|more|cross|surpass)\s+(?:the\s+)?"
    r")"
    # value patterns
    r"(?:"
    r"\$\d+|\d+\s*%|\d+\s*(?:percent|bps|bp)"
    r"|"
    # optional "the " + optional word + optional preposition + value
    r"(?:the\s+)?(?:price|level|value|threshold|trigger)?\s*(?:(?:at|of)\s+)?(?:\$\d+|\d+\s*%)"
    r"|"
    # bare number (no $ or %)
    r"\d+(?:\.\d+)?(?=\b|[,\s;.]|$)"
    r")"
    r"(?=\b|[,\s;.]|$)",
)


def _has_match(pattern, text: str) -> bool:
    return bool(pattern.search(text))


def validate_if_approved(text: str) -> list[str]:
    """Validate if_approved section has dollar amounts and risk metrics.

    Returns
    -------
    list[str]
        Actionable missing-element messages. Empty = section is grounded.
    """
    issues: list[str] = []

    has_dollar = _has_match(DOLLAR_AMOUNT_RE, text)
    has_risk_metric = _has_match(RISK_METRIC_RE, text)

    if not has_dollar:
        issues.append(
            "if_approved: no dollar amount found — "
            "expected allocation cost, estimated fees, or position size in USD"
        )
    if not has_risk_metric:
        issues.append(
            "if_approved: no risk metric found — "
            "expected volatility, drawdown, VaR, or Sharpe ratio"
        )

    if issues:
        logger.warning("brief.validate.if_approved_failed", issues=issues)
    else:
        logger.debug("brief.validate.if_approved_passed")

    return issues


def validate_if_rejected(text: str) -> list[str]:
    """Validate if_rejected section has position retention and drawdown probability.

    Returns
    -------
    list[str]
        Actionable missing-element messages. Empty = section is grounded.
    """
    issues: list[str] = []

    has_position = _has_match(POSITION_RETAIN_RE, text)
    has_drawdown = _has_match(DRAWDOWN_RE, text)

    if not has_position:
        issues.append(
            "if_rejected: no position retention reference found — "
            "expected 'retain', 'keep', 'hold', or 'status quo' for current allocation"
        )
    if not has_drawdown:
        issues.append(
            "if_rejected: no drawdown probability found — "
            "expected drawdown %, worst-case scenario, or loss probability"
        )

    if issues:
        logger.warning("brief.validate.if_rejected_failed", issues=issues)
    else:
        logger.debug("brief.validate.if_rejected_passed")

    return issues


def validate_historical_precedent(text: str) -> list[str]:
    """Validate historical_precedent has ≥1 analogue with outcome.

    Returns
    -------
    list[str]
        Actionable missing-element messages. Empty = section is grounded.
    """
    issues: list[str] = []

    has_analogue = _has_match(ANALOGUE_RE, text)
    has_outcome = _has_match(OUTCOME_RE, text)

    if not has_analogue:
        issues.append(
            "historical_precedent: no analogue found — "
            "expected reference to a prior decision, similar regime, or past trade"
        )
    if not has_outcome:
        issues.append(
            "historical_precedent: no outcome found — "
            "expected result, return %, or realized gain/loss from the analogue"
        )

    if issues:
        logger.warning("brief.validate.historical_precedent_failed", issues=issues)
    else:
        logger.debug("brief.validate.historical_precedent_passed")

    return issues


def validate_what_would_change_mind(text: str) -> list[str]:
    """Validate what_would_change_mind has ≥1 numeric threshold.

    Returns
    -------
    list[str]
        Actionable missing-element messages. Empty = section is grounded.
    """
    issues: list[str] = []

    has_threshold = _has_match(THRESHOLD_RE, text)

    if not has_threshold:
        issues.append(
            "what_would_change_mind: no numeric threshold found — "
            "expected a specific price, %, or level that would flip the recommendation"
        )

    if issues:
        logger.warning("brief.validate.what_would_change_mind_failed", issues=issues)
    else:
        logger.debug("brief.validate.what_would_change_mind_passed")

    return issues


def validate_all(section_name: str, text: str) -> list[str]:
    """Validate a section by name, dispatching to the appropriate validator.

    Parameters
    ----------
    section_name:
        One of: if_approved, if_rejected, historical_precedent, what_would_change_mind
    text:
        The section content string.

    Returns
    -------
    list[str]
        Combined validation issues from the dispatched validator.
    """
    validator_map = {
        "if_approved": validate_if_approved,
        "if_rejected": validate_if_rejected,
        "historical_precedent": validate_historical_precedent,
        "what_would_change_mind": validate_what_would_change_mind,
    }
    validator = validator_map.get(section_name)
    if validator is None:
        logger.warning("brief.validate.unknown_section", section=section_name)
        return [f"Unknown section: {section_name}"]
    return validator(text)
