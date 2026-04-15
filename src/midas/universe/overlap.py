"""
Holdings overlap analyzer for ETF universe deduplication.

Computes pairwise return correlation as a proxy for holdings overlap.
Deduplicates when overlap exceeds 80%.

Ref: T-02-03
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def compute_overlap(returns_a: list[float], returns_b: list[float]) -> float:
    """Compute Pearson correlation between two return series as overlap proxy."""
    n = min(len(returns_a), len(returns_b))
    if n < 2:
        return 0.0

    a = returns_a[:n]
    b = returns_b[:n]

    mean_a = sum(a) / n
    mean_b = sum(b) / n

    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / n
    var_a = sum((x - mean_a) ** 2 for x in a) / n
    var_b = sum((y - mean_b) ** 2 for y in b) / n

    if var_a == 0 or var_b == 0:
        return 0.0

    return cov / (var_a**0.5 * var_b**0.5)


def dedupe_overlapping(
    etfs: list[dict[str, Any]],
    returns_data: dict[str, list[float]],
    threshold: float = 0.8,
) -> list[dict[str, Any]]:
    """Remove ETFs with pairwise overlap above threshold.

    Keeps the ETF with higher score when overlap exceeds threshold.
    """
    kept: list[dict[str, Any]] = []
    removed_reasons: list[str] = []

    for etf in etfs:
        ticker = etf.get("ticker", "")
        etf_returns = returns_data.get(ticker, [])
        if not etf_returns:
            kept.append(etf)
            continue

        is_duplicate = False
        for existing in kept:
            existing_ticker = existing.get("ticker", "")
            existing_returns = returns_data.get(existing_ticker, [])
            if not existing_returns:
                continue

            overlap = compute_overlap(etf_returns, existing_returns)
            if overlap > threshold:
                existing_score = existing.get("score", 0)
                new_score = etf.get("score", 0)
                if new_score > existing_score:
                    kept.remove(existing)
                    kept.append(etf)
                    removed_reasons.append(
                        f"{existing_ticker} replaced by {ticker} (overlap={overlap:.2f})"
                    )
                else:
                    removed_reasons.append(
                        f"{ticker} dropped vs {existing_ticker} (overlap={overlap:.2f})"
                    )
                is_duplicate = True
                break

        if not is_duplicate:
            kept.append(etf)

    if removed_reasons:
        logger.info("overlap.deduped", removed=removed_reasons)

    return kept
