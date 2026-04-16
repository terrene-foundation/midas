"""Risk-adjusted performance metrics.

All static methods operate on numpy arrays of returns or equity curves.
Annualization uses 252 trading days per year by default.

Ref: M16 — Risk metrics
"""

import numpy as np

TRADING_DAYS_PER_YEAR = 252


class RiskMetrics:
    """Risk-adjusted performance metrics."""

    @staticmethod
    def sharpe_ratio(
        returns: np.ndarray,
        risk_free_rate: float = 0.0,
        annualize: bool = True,
    ) -> float:
        """Compute Sharpe ratio.

        Parameters
        ----------
        returns : np.ndarray
            Array of periodic returns.
        risk_free_rate : float
            Periodic risk-free rate (not annualized).
        annualize : bool
            If True, annualize using sqrt(252).

        Returns
        -------
        float
        """
        excess = returns - risk_free_rate
        mean_excess = float(np.mean(excess))
        std = float(np.std(excess, ddof=1))

        if std == 0.0:
            return 0.0

        sharpe = mean_excess / std

        if annualize:
            sharpe *= np.sqrt(TRADING_DAYS_PER_YEAR)

        return float(sharpe)

    @staticmethod
    def sortino_ratio(
        returns: np.ndarray,
        target_return: float = 0.0,
        annualize: bool = True,
    ) -> float:
        """Compute Sortino ratio.

        Uses only downside deviation (returns below target).

        Parameters
        ----------
        returns : np.ndarray
            Array of periodic returns.
        target_return : float
            Minimum acceptable return.
        annualize : bool
            If True, annualize using sqrt(252).

        Returns
        -------
        float
        """
        excess = returns - target_return
        mean_excess = float(np.mean(excess))

        # Downside deviation: only negative excess returns
        downside = returns[returns < target_return] - target_return
        if len(downside) == 0:
            # No downside returns: Sortino is infinite, but return a large number
            return float("inf") if mean_excess > 0 else 0.0

        downside_std = float(np.sqrt(np.mean(downside**2)))

        if downside_std == 0.0:
            return 0.0

        sortino = mean_excess / downside_std

        if annualize:
            sortino *= np.sqrt(TRADING_DAYS_PER_YEAR)

        return float(sortino)

    @staticmethod
    def calmar_ratio(returns: np.ndarray, annualize: bool = True) -> float:
        """Compute Calmar ratio (annualized return / max drawdown).

        Parameters
        ----------
        returns : np.ndarray
            Array of periodic returns.
        annualize : bool
            If True, annualize the return.

        Returns
        -------
        float
        """
        equity = np.cumprod(1 + returns)
        mdd = RiskMetrics.max_drawdown(equity)

        if mdd == 0.0:
            return float("inf")

        mean_return = float(np.mean(returns))
        if annualize:
            annual_return = mean_return * TRADING_DAYS_PER_YEAR
        else:
            annual_return = mean_return

        return float(annual_return / mdd)

    @staticmethod
    def max_drawdown(equity_curve: np.ndarray) -> float:
        """Compute maximum drawdown from an equity curve.

        Parameters
        ----------
        equity_curve : np.ndarray
            Array of equity values (e.g. portfolio value over time).

        Returns
        -------
        float
            Maximum drawdown as a fraction (0.0 to 1.0).
        """
        if len(equity_curve) < 2:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0

        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd

        return float(max_dd)

    @staticmethod
    def volatility(returns: np.ndarray, annualize: bool = True) -> float:
        """Compute volatility (standard deviation of returns).

        Parameters
        ----------
        returns : np.ndarray
            Array of periodic returns.
        annualize : bool
            If True, annualize using sqrt(252).

        Returns
        -------
        float
        """
        vol = float(np.std(returns, ddof=1))

        if annualize:
            vol *= np.sqrt(TRADING_DAYS_PER_YEAR)

        return vol

    @staticmethod
    def tracking_error(
        portfolio_returns: np.ndarray,
        benchmark_returns: np.ndarray,
        annualize: bool = True,
    ) -> float:
        """Compute tracking error (std of active returns).

        Parameters
        ----------
        portfolio_returns : np.ndarray
        benchmark_returns : np.ndarray
        annualize : bool

        Returns
        -------
        float
        """
        active = portfolio_returns - benchmark_returns
        te = float(np.std(active, ddof=1))

        if annualize:
            te *= np.sqrt(TRADING_DAYS_PER_YEAR)

        return te

    @staticmethod
    def information_ratio(
        portfolio_returns: np.ndarray,
        benchmark_returns: np.ndarray,
    ) -> float:
        """Compute information ratio (active return / tracking error).

        Parameters
        ----------
        portfolio_returns : np.ndarray
        benchmark_returns : np.ndarray

        Returns
        -------
        float
        """
        active = portfolio_returns - benchmark_returns
        mean_active = float(np.mean(active))

        te = float(np.std(active, ddof=1))

        if te == 0.0:
            # No tracking error: if active return is zero, return 0;
            # otherwise, return inf.
            if mean_active == 0.0:
                return float("nan")
            return float("inf") if mean_active > 0 else float("-inf")

        # Annualize both numerator and denominator consistently
        annualized_mean = mean_active * TRADING_DAYS_PER_YEAR
        annualized_te = te * np.sqrt(TRADING_DAYS_PER_YEAR)

        return float(annualized_mean / annualized_te)

    @staticmethod
    def jensens_alpha(
        portfolio_returns: np.ndarray,
        benchmark_returns: np.ndarray,
        risk_free_rate: float = 0.0,
    ) -> float:
        """Compute Jensen's alpha (risk-adjusted excess return).

        Alpha = mean(R_p - R_f) - beta * mean(R_b - R_f)
        where beta = cov(R_p, R_b) / var(R_b)

        Parameters
        ----------
        portfolio_returns : np.ndarray
        benchmark_returns : np.ndarray
        risk_free_rate : float

        Returns
        -------
        float
        """
        excess_p = portfolio_returns - risk_free_rate
        excess_b = benchmark_returns - risk_free_rate

        var_b = float(np.var(excess_b, ddof=1))
        if var_b == 0.0:
            return float(np.mean(excess_p))

        cov_pb = float(np.cov(excess_p, excess_b, ddof=1)[0, 1])
        beta = cov_pb / var_b

        alpha = float(np.mean(excess_p)) - beta * float(np.mean(excess_b))

        return float(alpha)

    @staticmethod
    def recovery_time(equity_curve: np.ndarray) -> int:
        """Days from max drawdown trough to recovery.

        If the equity curve never recovers to the previous peak after
        the maximum drawdown trough, returns the number of days from
        trough to end of series.

        Parameters
        ----------
        equity_curve : np.ndarray

        Returns
        -------
        int
            Number of periods from trough to recovery (or end).
        """
        if len(equity_curve) < 2:
            return 0

        peak = equity_curve[0]
        max_dd = 0.0
        peak_idx = 0
        trough_idx = 0

        # Find the peak and trough of the max drawdown
        for i, value in enumerate(equity_curve):
            if value > peak:
                peak = value
                peak_idx = i
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
                trough_idx = i

        if max_dd == 0.0:
            return 0

        # Recovery: first index after trough where equity >= previous peak
        prev_peak = equity_curve[peak_idx]
        for i in range(trough_idx + 1, len(equity_curve)):
            if equity_curve[i] >= prev_peak:
                return i - trough_idx

        # Never recovered: return days from trough to end
        return len(equity_curve) - 1 - trough_idx

    @staticmethod
    def m_squared(
        portfolio_return: float,
        portfolio_vol: float,
        benchmark_return: float,
        benchmark_vol: float,
        risk_free_rate: float = 0.0,
    ) -> float:
        """Compute M-squared (Modigliani-Modigliani) measure.

        Returns the portfolio return adjusted to the benchmark's risk level,
        making it directly comparable to the benchmark return.

        Formula: M2 = R_f + (Sharpe_p) * sigma_b
        where Sharpe_p = (R_p - R_f) / sigma_p

        Equivalently: M2 = R_b + (Sharpe_p - Sharpe_b) * sigma_b

        Parameters
        ----------
        portfolio_return : float
            Annualized portfolio return.
        portfolio_vol : float
            Annualized portfolio volatility (standard deviation).
        benchmark_return : float
            Annualized benchmark return.
        benchmark_vol : float
            Annualized benchmark volatility (standard deviation).
        risk_free_rate : float
            Risk-free rate (annualized).

        Returns
        -------
        float
            M-squared measure.
        """
        if portfolio_vol == 0.0:
            return portfolio_return

        portfolio_sharpe = (portfolio_return - risk_free_rate) / portfolio_vol
        return risk_free_rate + portfolio_sharpe * benchmark_vol

    @staticmethod
    def treynor_ratio(
        portfolio_return: float,
        risk_free_rate: float,
        beta: float,
    ) -> float:
        """Compute Treynor ratio (return per unit of systematic risk).

        Formula: (R_p - R_f) / beta

        Parameters
        ----------
        portfolio_return : float
            Annualized portfolio return.
        risk_free_rate : float
            Risk-free rate (annualized).
        beta : float
            Portfolio beta relative to benchmark.

        Returns
        -------
        float
            Treynor ratio.
        """
        if beta == 0.0:
            return 0.0
        return (portfolio_return - risk_free_rate) / beta
