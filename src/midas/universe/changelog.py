"""Universe changelog writer — records all add/remove actions."""

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)


async def record_addition(
    ticker: str, reason: str, effective_date: str, backtest_impact: str, fabric_db: DataFlow
) -> dict:
    row = {
        "ticker": ticker,
        "action": "added",
        "reason": reason,
        "effective_date": effective_date,
        "backtest_impact": backtest_impact,
    }
    try:
        return await fabric_db.express.create("universe_changelog", row)
    except Exception as exc:
        logger.error("changelog.addition_failed", ticker=ticker, error=str(exc))
        return {}


async def record_removal(
    ticker: str, reason: str, effective_date: str, backtest_impact: str, fabric_db: DataFlow
) -> dict:
    row = {
        "ticker": ticker,
        "action": "removed",
        "reason": reason,
        "effective_date": effective_date,
        "backtest_impact": backtest_impact,
    }
    try:
        return await fabric_db.express.create("universe_changelog", row)
    except Exception as exc:
        logger.error("changelog.removal_failed", ticker=ticker, error=str(exc))
        return {}


async def get_changelog(fabric_db: DataFlow, as_of_date: str | None = None) -> list[dict]:
    try:
        if as_of_date:
            return await fabric_db.express.list(
                "universe_changelog", filter={"effective_date": as_of_date}
            )
        return await fabric_db.express.list("universe_changelog")
    except Exception as exc:
        logger.error("changelog.fetch_failed", error=str(exc))
        return []
