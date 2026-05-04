"""BacktestEngine -- pure-computation backtest over actual weights and price data.

Computes regime-segmented portfolio return series from decision weights and
price data.  All metric formulas match ``src/midas/attribution/metrics.py``
(RiskMetrics) so results are consistent across the codebase.

No database access, no async -- takes DataFrames and lists as input.

Ref: T-23-07, specs/09 S9.2
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog

from midas.attribution.metrics import RiskMetrics

logger = structlog.get_logger("midas.backtest.engine")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR = 252

# z_scale band thresholds -- maps posterior width proxy to attention regimes.
_Z_SCALE_BANDS: list[tuple[str, float, float]] = [
    # (name, lower_bound_inclusive, upper_bound_exclusive)
    ("CALM", 0.0, 0.3),
    ("ELEVATED", 0.3, 0.6),
    ("URGENT", 0.6, 0.85),
    ("CRISIS", 0.85, float("inf")),
]

_MIN_CONFIDENCE = 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_z_scale(z: float) -> str:
    """Return the regime name for a given z_scale value."""
    for name, lo, hi in _Z_SCALE_BANDS:
        if lo <= z < hi:
            return name
    return "CRISIS"


def _empty_result() -> dict[str, Any]:
    """Return the canonical empty-result structure."""
    return {
        "equity_curve": [],
        "daily_returns": [],
        "headline": {
            "cagr": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
            "max_drawdown": 0.0,
            "volatility": 0.0,
            "turnover": 0.0,
            "win_rate": 0.0,
        },
        "regime_breakdown": [],
        "sub_horizons": {
            "monthly_positive_pct": 0.0,
            "quarterly_positive_pct": 0.0,
            "annual_positive_pct": 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Computes regime-segmented portfolio return series from actual weights
    and price data.

    Parameters
    ----------
    prices:
        DataFrame with columns ``[ticker, period_end, close, adj_close]``.
    weights:
        List of dicts with ``[decision_id, instruments, confidence,
        created_at_day]``.  ``confidence`` is used as position weight.
    regime_labels:
        Optional list of dicts with ``[period_end, z_scale]``.
        If ``None``, falls back to return-percentile banding.
    """

    def __init__(
        self,
        prices: pd.DataFrame,
        weights: list[dict[str, Any]],
        regime_labels: list[dict[str, Any]] | None = None,
    ) -> None:
        self._prices = (
            prices.copy()
            if isinstance(prices, pd.DataFrame) and not prices.empty
            else pd.DataFrame()
        )
        self._weights = list(weights) if weights else []
        self._regime_labels = list(regime_labels) if regime_labels else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(self) -> dict[str, Any]:
        """Run the full backtest computation.

        Returns a dict with equity_curve, daily_returns, headline metrics,
        regime_breakdown, and sub_horizons.
        """
        if self._prices.empty or not self._weights:
            logger.info(
                "backtest.engine.empty_input",
                prices_rows=len(self._prices),
                weights_count=len(self._weights),
            )
            return _empty_result()

        # 1. Build price lookup: ticker -> sorted list of (date_str, close)
        price_map = self._build_price_map()
        if not price_map:
            logger.info("backtest.engine.no_valid_prices")
            return _empty_result()

        # 2. Group decisions by day
        decisions_by_day = self._group_decisions_by_day()
        if not decisions_by_day:
            logger.info("backtest.engine.no_valid_decisions")
            return _empty_result()

        sorted_days = sorted(decisions_by_day.keys())

        # 3. Compute daily portfolio returns
        daily_returns = self._compute_daily_returns(
            decisions_by_day,
            sorted_days,
            price_map,
        )

        if not daily_returns:
            return _empty_result()

        rets = np.array(daily_returns)

        # 4. Equity curve
        equity_curve = np.cumprod(1 + rets)
        equity_list = [float(v) for v in equity_curve]

        # Prepend 1.0 so the curve starts at initial capital
        equity_list = [1.0] + equity_list

        # 5. Headline metrics (matching RiskMetrics formulas)
        headline = self._compute_headline(rets, equity_curve)

        # 6. Regime breakdown
        regime_breakdown = self._compute_regime_breakdown(
            rets,
            sorted_days,
            decisions_by_day,
        )

        # 7. Sub-horizon consistency
        sub_horizons = self._compute_sub_horizons(rets)

        return {
            "equity_curve": equity_list,
            "daily_returns": daily_returns,
            "headline": headline,
            "regime_breakdown": regime_breakdown,
            "sub_horizons": sub_horizons,
        }

    # ------------------------------------------------------------------
    # Internal: price map
    # ------------------------------------------------------------------

    def _build_price_map(self) -> dict[str, list[tuple[str, float]]]:
        """Build ticker -> [(date, close)] sorted by date."""
        price_map: dict[str, list[tuple[str, float]]] = {}

        if self._prices.empty:
            return price_map

        required = {"ticker", "period_end", "close"}
        if not required.issubset(set(self._prices.columns)):
            logger.warning(
                "backtest.engine.missing_price_columns", columns=list(self._prices.columns)
            )
            return price_map

        for _, row in self._prices.iterrows():
            ticker = str(row.get("ticker", "")).strip()
            day = str(row.get("period_end", ""))[:10]
            close = float(row.get("close", 0) or 0)
            if ticker and day and close > 0:
                price_map.setdefault(ticker, []).append((day, close))

        for ticker in price_map:
            price_map[ticker].sort(key=lambda x: x[0])

        return price_map

    # ------------------------------------------------------------------
    # Internal: group decisions by day
    # ------------------------------------------------------------------

    def _group_decisions_by_day(self) -> dict[str, list[dict]]:
        """Group weight decisions by their created_at_day."""
        by_day: dict[str, list[dict]] = {}
        for w in self._weights:
            day = str(w.get("created_at_day", ""))[:10]
            if day:
                by_day.setdefault(day, []).append(w)
        return by_day

    # ------------------------------------------------------------------
    # Internal: daily returns
    # ------------------------------------------------------------------

    def _compute_daily_returns(
        self,
        decisions_by_day: dict[str, list[dict]],
        sorted_days: list[str],
        price_map: dict[str, list[tuple[str, float]]],
    ) -> list[float]:
        """Compute daily portfolio returns from decisions and prices.

        For each trading day, compute sum(w_i * r_i) where w_i comes from
        decision confidence and r_i = (close_t - close_{t-1}) / close_{t-1}.
        """
        daily_returns: list[float] = []

        for day in sorted_days:
            # Build position weights for this day
            positions: dict[str, float] = {}
            for d in decisions_by_day[day]:
                action = str(d.get("action", "")).lower().strip()
                confidence = float(d.get("confidence", 0.0) or 0.0)
                confidence = max(confidence, _MIN_CONFIDENCE)
                instruments = str(d.get("instruments", ""))
                tickers = [t.strip() for t in instruments.split(",") if t.strip()]
                per_ticker_weight = confidence / len(tickers) if tickers else confidence

                for ticker in tickers:
                    if action == "buy":
                        positions[ticker] = positions.get(ticker, 0.0) + per_ticker_weight
                    elif action == "sell":
                        positions[ticker] = positions.get(ticker, 0.0) - per_ticker_weight

            if not positions:
                daily_returns.append(0.0)
                continue

            # Compute weighted return across all tickers
            day_return = 0.0
            for ticker, weight in positions.items():
                prices = price_map.get(ticker, [])
                if not prices:
                    continue

                # Find price for this day or the closest prior day
                curr_price = self._find_price(prices, day)
                prev_price = self._find_prev_price(prices, day)

                if curr_price is None or prev_price is None:
                    continue
                if prev_price <= 0:
                    continue

                ticker_return = (curr_price - prev_price) / prev_price
                day_return += weight * ticker_return

            daily_returns.append(day_return)

        return daily_returns

    def _find_price(
        self,
        prices: list[tuple[str, float]],
        day: str,
    ) -> float | None:
        """Find the close price for *day*, or the most recent prior day."""
        result: float | None = None
        for date_str, close in prices:
            if date_str <= day:
                result = close
            else:
                break
        return result

    def _find_prev_price(
        self,
        prices: list[tuple[str, float]],
        day: str,
    ) -> float | None:
        """Find the close price for the day *before* the best match for *day*.

        This gives us the return: (close_t - close_{t-1}) / close_{t-1}.
        """
        # Find the index of the best match
        best_idx = -1
        for idx, (date_str, _) in enumerate(prices):
            if date_str <= day:
                best_idx = idx
            else:
                break

        if best_idx <= 0:
            # No prior price available
            return None

        return prices[best_idx - 1][1]

    # ------------------------------------------------------------------
    # Internal: headline metrics
    # ------------------------------------------------------------------

    def _compute_headline(
        self,
        rets: np.ndarray,
        equity_curve: np.ndarray,
    ) -> dict[str, float]:
        """Compute headline metrics using RiskMetrics formulas."""
        n = len(rets)

        # CAGR: (total_return) ^ (1/years) - 1
        total_return = float(np.prod(1 + rets))
        years = n / TRADING_DAYS_PER_YEAR
        if years > 0 and total_return > 0:
            cagr = total_return ** (1 / years) - 1
        else:
            cagr = 0.0

        # Sharpe: annualized, rf=0 -- matches RiskMetrics.sharpe_ratio
        # Guard single-element arrays: Sharpe is undefined for n=1
        if n > 1:
            sharpe = RiskMetrics.sharpe_ratio(rets, risk_free_rate=0.0, annualize=True)
        else:
            sharpe = 0.0

        # Max drawdown -- matches RiskMetrics.max_drawdown
        # equity_curve already starts at 1.0 implicitly via cumprod(1+rets)
        max_drawdown = RiskMetrics.max_drawdown(equity_curve)

        # Calmar: annualized return / max drawdown
        if n > 1:
            calmar = RiskMetrics.calmar_ratio(rets, annualize=True)
        else:
            calmar = 0.0

        # Volatility: annualized std -- matches RiskMetrics.volatility
        if n > 1:
            volatility = RiskMetrics.volatility(rets, annualize=True)
        else:
            volatility = 0.0

        # Turnover: sum of abs weight changes / 2
        # Approximated as mean of absolute daily returns (consistent with
        # existing BacktestDetailRouter._compute_metrics).
        turnover = float(np.mean(np.abs(rets)))

        # Win rate: positive days / total days
        win_rate = float(np.sum(rets > 0) / n) if n > 0 else 0.0

        return {
            "cagr": float(cagr),
            "sharpe": float(sharpe),
            "calmar": float(calmar),
            "max_drawdown": float(max_drawdown),
            "volatility": float(volatility),
            "turnover": float(turnover),
            "win_rate": float(win_rate),
        }

    # ------------------------------------------------------------------
    # Internal: regime breakdown
    # ------------------------------------------------------------------

    def _compute_regime_breakdown(
        self,
        rets: np.ndarray,
        sorted_days: list[str],
        _decisions_by_day: dict[str, list[dict]],
    ) -> list[dict[str, Any]]:
        """Compute per-regime performance breakdown.

        Uses z_scale from regime_labels when available.
        Falls back to return-percentile banding otherwise.
        """
        n = len(rets)
        regime_names = ["CALM", "ELEVATED", "URGENT", "CRISIS"]
        regime_rets: dict[str, list[float]] = {name: [] for name in regime_names}

        if self._regime_labels:
            # Build a date -> z_scale lookup
            z_scale_map: dict[str, float] = {}
            for entry in self._regime_labels:
                day = str(entry.get("period_end", ""))[:10]
                z = float(entry.get("z_scale", 0.0) or 0.0)
                if day:
                    z_scale_map[day] = z

            # Assign each return to a regime
            for i, day in enumerate(sorted_days):
                z = z_scale_map.get(day, 0.0)
                regime = _classify_z_scale(z)
                regime_rets[regime].append(float(rets[i]))
        else:
            # Fallback: return-percentile banding
            # Bottom 30%, 30-60%, 60-85%, top 15%
            abs_rets = np.abs(rets)
            p30 = float(np.percentile(abs_rets, 30))
            p60 = float(np.percentile(abs_rets, 60))
            p85 = float(np.percentile(abs_rets, 85))

            for r in rets:
                ar = abs(float(r))
                if ar <= p30:
                    regime_rets["CALM"].append(float(r))
                elif ar <= p60:
                    regime_rets["ELEVATED"].append(float(r))
                elif ar <= p85:
                    regime_rets["URGENT"].append(float(r))
                else:
                    regime_rets["CRISIS"].append(float(r))

        result: list[dict[str, Any]] = []
        for name in regime_names:
            vals = regime_rets[name]
            cnt = len(vals)
            if cnt > 1:
                vals_arr = np.array(vals)
                ret_pct = float(np.mean(vals_arr)) * 100
                sharpe = RiskMetrics.sharpe_ratio(vals_arr, annualize=True)
            elif cnt == 1:
                vals_arr = np.array(vals)
                ret_pct = float(np.mean(vals_arr)) * 100
                sharpe = 0.0  # Sharpe undefined for single observation
            else:
                ret_pct = 0.0
                sharpe = 0.0

            result.append(
                {
                    "name": name,
                    "return_pct": ret_pct,
                    "sharpe": float(sharpe),
                    "time_pct": cnt / n if n > 0 else 0.0,
                }
            )

        return result

    # ------------------------------------------------------------------
    # Internal: sub-horizon consistency
    # ------------------------------------------------------------------

    def _compute_sub_horizons(self, rets: np.ndarray) -> dict[str, float]:
        """Compute monthly, quarterly, and annual positive-return fractions."""
        n = len(rets)
        result = {
            "monthly_positive_pct": 0.0,
            "quarterly_positive_pct": 0.0,
            "annual_positive_pct": 0.0,
        }

        if n == 0:
            return result

        # Monthly: ~21 trading days
        result["monthly_positive_pct"] = self._positive_period_fraction(
            rets,
            period_length=21,
        )

        # Quarterly: ~63 trading days
        result["quarterly_positive_pct"] = self._positive_period_fraction(
            rets,
            period_length=63,
        )

        # Annual: ~252 trading days
        result["annual_positive_pct"] = self._positive_period_fraction(
            rets,
            period_length=252,
        )

        return result

    @staticmethod
    def _positive_period_fraction(
        rets: np.ndarray,
        period_length: int,
    ) -> float:
        """Fraction of non-overlapping periods with positive cumulative return."""
        n = len(rets)
        if n < period_length:
            period_ret = float(np.prod(1 + rets) - 1)
            return 1.0 if period_ret > 0 else 0.0

        num_periods = n // period_length
        if num_periods == 0:
            return 0.0

        positive = 0
        for i in range(num_periods):
            start = i * period_length
            end = start + period_length
            period_ret = float(np.prod(1 + rets[start:end]) - 1)
            if period_ret > 0:
                positive += 1

        return positive / num_periods
