"""
Factor gap detector.

Runs factor regression on current universe to identify missing exposures
and surfaces candidate additions.

Ref: specs/03-universe-and-data.md §1.2
Ref: T-02-04
"""

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FactorGap:
    factor_name: str
    current_exposure: float
    target_exposure: float
    gap: float
    candidate_tickers: list[str]


# Known factor definitions mapped to ETF proxies
FACTOR_ETFS: dict[str, list[str]] = {
    "momentum": ["MTUM", "SPY"],
    "quality": ["QUAL", "SPY"],
    "low_volatility": ["USMV", "SPY"],
    "value": ["VTV", "SPY"],
    "size": ["IWM", "SPY"],
}


async def detect_factor_gaps(
    current_tickers: list[str],
    target_factors: list[str],
    returns_data: dict[str, list[float]],
) -> list[FactorGap]:
    """Detect missing factor exposures in the current universe.

    Uses return-based regression to estimate factor exposures.
    """
    gaps: list[FactorGap] = []

    for factor in target_factors:
        factor_etfs = FACTOR_ETFS.get(factor, [])
        if not factor_etfs:
            continue

        # Proxy factor returns
        proxy_returns = returns_data.get(factor_etfs[0], [])
        if not proxy_returns:
            gaps.append(
                FactorGap(
                    factor_name=factor,
                    current_exposure=0.0,
                    target_exposure=1.0,
                    gap=1.0,
                    candidate_tickers=[],
                )
            )
            continue

        # Estimate current universe's exposure to this factor
        total_exposure = 0.0
        count = 0
        for ticker in current_tickers:
            ticker_returns = returns_data.get(ticker, [])
            if len(ticker_returns) < 10:
                continue
            exposure = _estimate_exposure(ticker_returns, proxy_returns)
            total_exposure += exposure
            count += 1

        avg_exposure = total_exposure / count if count > 0 else 0.0
        gap = 1.0 - avg_exposure

        # Find candidate tickers that fill the gap
        candidates = []
        all_ticker_returns = returns_data.keys()
        for ticker in all_ticker_returns:
            if ticker in current_tickers:
                continue
            ticker_returns_data = returns_data.get(ticker, [])
            if not ticker_returns_data:
                continue
            candidate_exposure = _estimate_exposure(ticker_returns_data, proxy_returns)
            if candidate_exposure > avg_exposure * 1.2:  # 20% improvement threshold
                candidates.append(ticker)

        gaps.append(
            FactorGap(
                factor_name=factor,
                current_exposure=avg_exposure,
                target_exposure=1.0,
                gap=gap,
                candidate_tickers=candidates[:5],
            )
        )

    logger.info("factor_gap.detected", factors=len(gaps))
    return gaps


def _estimate_exposure(returns: list[float], factor_returns: list[float]) -> float:
    """Estimate the beta/exposure of returns to factor_returns using OLS."""
    n = min(len(returns), len(factor_returns))
    if n < 2:
        return 0.0

    y = returns[:n]
    x = factor_returns[:n]

    x_mean = sum(x) / n
    y_mean = sum(y) / n

    cov = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y)) / n
    var_x = sum((xi - x_mean) ** 2 for xi in x) / n

    if var_x == 0:
        return 0.0

    return cov / var_x
