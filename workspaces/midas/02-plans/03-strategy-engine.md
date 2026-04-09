# Plan: Strategy Engine

---

## Overview

The strategy engine is Midas's brain — it generates signals, constructs portfolios, manages risk, and runs backtests. It reads exclusively from the data fabric (never from external sources directly).

---

## 1. Signal Generation

### Six Signal Families

Each signal produces a value in [-1, +1] for each instrument (or at portfolio level), plus a confidence score.

**1. Time-Series Momentum** (`signals/momentum.py`)

- For each instrument: is the 10-month trailing return positive?
- Signal = +1 if above 10-month SMA, -1 if below
- Variant: smoothed signal using 1/3/6/12 month lookback average
- Reference: Faber (2007) "A Quantitative Approach to Tactical Asset Allocation"

**2. Cross-Sectional Momentum** (`signals/momentum.py`)

- Rank all instruments by 12-1 month return (skip most recent month to avoid reversal)
- Top quartile = +1, bottom quartile = -1, middle = 0
- Volatility-adjusted variant: rank by return/volatility instead of raw return
- Reference: Jegadeesh & Titman (1993)

**3. Carry** (`signals/carry.py`)

- Bonds: yield spread over short-term treasuries
- Equities: dividend yield (SCHD vs QQQ)
- Commodities: contango/backwardation signal
- Signal = normalized rank of carry across instruments

**4. Macro Regime** (`signals/macro.py`)

- Investment clock model:
  - Growth rising + inflation falling → overweight equities
  - Growth rising + inflation rising → overweight commodities, EM
  - Growth falling + inflation rising → overweight gold, TIPS, cash
  - Growth falling + inflation falling → overweight long bonds, defensive
- Inputs: yield curve slope (10Y-2Y), ISM PMI, CPI YoY, unemployment claims (4-week MA), credit spreads (HYG-Treasury)
- Signal = regime-specific tilt per asset class

**5. Volatility Regime** (`signals/volatility.py`)

- Realized vol (20-day) vs long-term vol (252-day)
- Portfolio-level signal: CONTINUOUS exposure scaling (no discrete VIX buckets — per SPEC-02 PC-1)
- Uses asymmetric response function from Layer 3 of dynamic risk system:
  - Scale DOWN fast (exponential decay) when vol exceeds adaptive target
  - Scale UP slow (linear ramp with lag) when vol falls below target
  - Adaptive vol target adjusts to opportunity set (not fixed)
- Signal output: continuous multiplier in [0.2, 1.5], not bucketed
- Reference: Moreira & Muir (2017), extended with asymmetric response (Harvey et al. 2018)

**6. Dual Momentum Filter** (applied post-combination)

- For each instrument: if trailing return < T-bill return → force signal to sell/underweight
- This is the absolute momentum filter (Antonacci 2014)
- Prevents holding assets in sustained downtrends regardless of other signals

### Signal Combination

Signals are combined via Black-Litterman:

```
1. Compute market-implied equilibrium returns (from market-cap weights + covariance)
2. Convert each signal into a "view":
   - View: "US equities will outperform EM by X% over next month"
   - Confidence: proportional to signal strength and historical accuracy
3. Blend views with equilibrium using Bayesian updating
4. Output: posterior expected returns for each instrument
```

**Confidence calibration**: Each signal family has a historical hit rate tracked through backtesting. Signal confidence = hit_rate \* signal_strength. This prevents high-confidence views from unreliable signals.

---

## 2. Portfolio Optimization

### Ensemble Approach

Three optimizers run independently, then results are averaged:

**Black-Litterman Optimizer** (`optimizer/black_litterman.py`)

- Input: posterior returns from signal combination, covariance matrix (Ledoit-Wolf shrinkage)
- Output: optimal weights that maximize expected utility
- Constraints: min 0%, max 20% per position; max 90% equities; min 5% cash

**Hierarchical Risk Parity** (`optimizer/hrp.py`)

- Input: covariance matrix only (no return estimates)
- Process: hierarchical clustering → quasi-diagonalization → recursive bisection
- Output: weights that equalize risk contribution within clusters
- No constraints needed — naturally diversified

**Risk Parity** (`optimizer/risk_parity.py`)

- Input: covariance matrix only
- Process: solve for weights where each asset's marginal risk contribution = 1/N
- Output: equal-risk-contribution weights
- Post-process: apply position size constraints

**Ensemble Combiner** (`optimizer/ensemble.py`)

```
1. Run all three optimizers
2. REGIME-CONDITIONAL blending (not fixed weights — per SPEC-02 PC-1):
   Seed weights: w_BL=0.4, w_HRP=0.3, w_RP=0.3
   In crisis: shift toward HRP (does not depend on unreliable return estimates)
   In high-conviction calm: shift toward BL (signal views are most informative)
   Weights optimized by Layer 6 self-tuning (Bayesian optimization)
3. Apply final constraints:
   - No position > adaptive max_position (seed: 15%)
   - No asset class > 50%
   - Cash >= 5%
   - Sum = 100%
4. If any optimizer fails to converge, use remaining two (or HRP alone as fallback)
```

### Covariance Estimation

- Use **Ledoit-Wolf shrinkage** (shrink sample covariance toward constant-correlation target)
- Estimation window: 252 trading days (1 year)
- Update daily with new data
- For regime-conditional estimates: use only data from current regime (if sufficient observations) or regime-weighted full sample

---

## 3. Dynamic Risk Management (7-Layer System)

See SPEC-02 (Principal Considerations) and research/05-dynamic-risk.md for full framework. Every risk parameter adapts — nothing is static.

### Layer 1: Real-Time Risk Measurement

```python
# Per-asset volatility: GJR-GARCH (captures leverage effect)
# Library: arch
from arch import arch_model
model = arch_model(returns, vol='GARCH', p=1, o=1, q=1)  # GJR-GARCH
result = model.fit(disp='off')
forecast_vol = result.forecast(horizon=1).variance.iloc[-1].values[0] ** 0.5

# Intraday vol from OHLC: Yang-Zhang estimator (more efficient than close-to-close)
def yang_zhang_vol(ohlc_df, window=20):
    """Combines overnight + intraday volatility components."""
    log_oc = np.log(ohlc_df['open'] / ohlc_df['close'].shift(1))  # overnight
    log_co = np.log(ohlc_df['close'] / ohlc_df['open'])  # close-to-open
    log_hl = np.log(ohlc_df['high'] / ohlc_df['low'])  # range
    # Yang-Zhang combination
    sigma_o = log_oc.rolling(window).var()
    sigma_c = log_co.rolling(window).var()
    sigma_rs = (log_hl**2).rolling(window).mean() / (4 * np.log(2))
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    return np.sqrt(sigma_o + k * sigma_c + (1 - k) * sigma_rs)

# Tail risk: Extreme Value Theory (GPD for peaks-over-threshold)
from scipy.stats import genpareto
threshold = np.percentile(losses, 95)
exceedances = losses[losses > threshold] - threshold
shape, loc, scale = genpareto.fit(exceedances)
# CVaR at 99% = threshold + scale * ((1 + shape * (q/alpha - 1)) / shape)
```

### Layer 2: Regime Detection

**Market Regime** (strategy layer): 3-state HMM on multi-feature input

```python
from hmmlearn import hmm
# Features: returns, realized vol, credit spread change, yield curve slope
model = hmm.GaussianHMM(n_components=3, covariance_type='full', n_iter=200)
model.fit(feature_matrix)  # Trained on 15+ years including 2008, 2020, 2022
regime_probs = model.predict_proba(current_features)  # Probability per regime
```

**Operational Regime** (UI/approval layer): Derived from market regime + observable indicators

| Market Regime                                                   | Operational Regime | Mapping Logic        |
| --------------------------------------------------------------- | ------------------ | -------------------- |
| Bull / Low Vol (HMM state 0, VIX < 20)                          | Calm               | Low uncertainty      |
| Bull / High Vol or Sideways (HMM mixed, VIX 20-30)              | Elevated           | Moderate uncertainty |
| Bear onset (HMM state 2, VIX > 30 or spreads widening)          | Urgent             | High uncertainty     |
| Crisis (HMM state 2 high probability, VIX > 40, rapid drawdown) | Crisis             | Extreme uncertainty  |

**Ensemble validation**: Only declare regime change when ≥2 of (HMM, heuristic indicators, trend signals) agree. Reduces false transitions.

### Layer 3: Adaptive Risk Budgeting

```python
# Volatility targeting with ASYMMETRIC response
def compute_exposure_multiplier(current_vol, target_vol, direction):
    """Scale down FAST (exponential), scale up SLOW (linear with lag)."""
    ratio = target_vol / current_vol
    if current_vol > target_vol:  # Vol above target → reduce
        return np.exp(-2 * (current_vol / target_vol - 1))  # Exponential decay
    else:  # Vol below target → increase
        return min(1.0 + 0.3 * (target_vol / current_vol - 1), 1.5)  # Linear ramp, capped

# Conditional vol target: adjusts to opportunity set
def adaptive_vol_target(regime_probs, base_target=0.15):
    """Higher target when opportunity is rich, lower when danger signals appear."""
    opportunity_score = compute_opportunity_score(signals)  # Aggregate signal strength
    regime_adjustment = 1.0 + 0.3 * regime_probs[0] - 0.5 * regime_probs[2]  # Bull boosts, crisis cuts
    return base_target * regime_adjustment * (0.8 + 0.4 * opportunity_score)

# Bayesian Kelly for position sizing
def bayesian_kelly(expected_return, return_std, uncertainty):
    """Kelly fraction shrinks automatically when parameter uncertainty is high."""
    # Full Kelly: f = mu / sigma^2
    # Bayesian Kelly: integrate over posterior uncertainty
    kelly_full = expected_return / (return_std ** 2)
    shrinkage = 1.0 / (1.0 + uncertainty)  # Higher uncertainty → more shrinkage
    return 0.5 * kelly_full * shrinkage  # Half-Kelly with Bayesian adjustment
```

### Layer 4: Continuous Drawdown Management

```python
# Sigmoid response function — NO discrete thresholds
def drawdown_exposure(current_dd, recovery_velocity, regime_probs, recent_performance):
    """
    Continuous, differentiable drawdown response.
    Grossman-Zhou insight: tolerate small DD, cut aggressively near limit.
    """
    # Adaptive midpoint and steepness based on regime
    d_mid = 0.12 + 0.05 * regime_probs[0] - 0.03 * regime_probs[2]  # Shifts with regime
    k = 15 + 10 * regime_probs[2]  # Steeper in crisis

    # Recovery-aware: if recovering, relax response
    recovery_adjustment = 0.02 * max(0, recovery_velocity)  # Positive velocity = recovering
    effective_dd = current_dd - recovery_adjustment

    # Sigmoid response
    exposure = 1.0 / (1.0 + np.exp(k * (effective_dd - d_mid)))

    # CPPI-inspired floor ratchet: floor only goes UP with portfolio gains
    # floor = max(historical_floors) where floor_t = peak_t * (1 - max_acceptable_dd)
    return max(exposure, 0.05)  # Never fully zero — maintain minimum to re-enter

# HARD CIRCUIT BREAKER (non-adaptive, non-negotiable)
if current_dd > 0.30:
    return 0.0  # Full stop. 100% cash. Human review required.
```

### Layer 5: Position-Level Risk Governance

```python
# Component VaR: decompose portfolio risk into per-position contributions
def component_var(weights, cov_matrix, portfolio_var, confidence=0.95):
    marginal = cov_matrix @ weights / np.sqrt(weights @ cov_matrix @ weights)
    component = weights * marginal * norm.ppf(confidence)
    return component  # Sum equals total VaR

# Drawdown beta: how much does each position contribute during drawdowns?
def drawdown_beta(position_returns, portfolio_returns, dd_mask):
    """Regress position returns on portfolio returns, ONLY during drawdown periods."""
    dd_pos_returns = position_returns[dd_mask]
    dd_port_returns = portfolio_returns[dd_mask]
    if len(dd_pos_returns) < 20:
        return 1.0  # Insufficient data, assume market-like
    slope, _, _, _, _ = linregress(dd_port_returns, dd_pos_returns)
    return slope  # High drawdown beta = reduce first during drawdowns
```

### Layer 6: Self-Tuning (Quarterly Cycle)

```python
# Bayesian optimization of risk parameters on walk-forward backtest
import optuna

def objective(trial):
    # Sample risk parameters
    dd_midpoint = trial.suggest_float('dd_midpoint', 0.08, 0.25)
    vol_target = trial.suggest_float('vol_target', 0.08, 0.25)
    max_position = trial.suggest_float('max_position', 0.05, 0.25)

    # Run walk-forward backtest with these params
    result = walk_forward_backtest(strategy, params={'dd_midpoint': dd_midpoint, ...})

    # Multi-objective: maximize Calmar ratio (return/max_drawdown)
    return result.calmar_ratio

study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=200)
# Best params become new seeds; system continues adapting from there
```

### Layer 7: Correlation & Contagion Monitoring

```python
# Diversification ratio: drops toward 1 when diversification is failing
def diversification_ratio(weights, individual_vols, portfolio_vol):
    return np.dot(weights, individual_vols) / portfolio_vol
    # DR >> 1: strong diversification. DR → 1: no diversification benefit.
    # If DR drops below threshold → reduce total portfolio risk

# Diebold-Yilmaz spillover index: rising = systemic risk increasing
# Implementation: VAR model → forecast error variance decomposition → total spillover
```

### Pre-Trade Validation (Unchanged)

Before any rebalancing, validate:

1. Position limits (adaptive, but hard max exists)
2. Concentration by asset class
3. Expected alpha > transaction cost for each proposed trade
4. Portfolio vol within current adaptive target
5. CVaR within current adaptive constraint
6. Drawdown response curve position

---

## 4. Backtesting Framework

### Walk-Forward Engine

```python
def walk_forward_backtest(strategy, data, train_window=756, test_window=126):
    """
    756 trading days = ~3 years training
    126 trading days = ~6 months testing
    Rolling window (not anchored)
    """
    results = []
    for train_start, train_end, test_start, test_end in rolling_windows(data):
        # Train: fit covariance, calibrate signals
        model = strategy.fit(data[train_start:train_end])

        # Test: simulate trading with trained model
        period_result = simulate(model, data[test_start:test_end],
                                costs=TransactionCostModel(),
                                constraints=RiskConstraints())
        results.append(period_result)

    return aggregate_results(results)  # Only out-of-sample
```

### Transaction Cost Model

```python
class TransactionCostModel:
    def __init__(self, commission_schedule='ibkr_pro_tiered'):
        """Commission schedule is configurable — depends on IBKR plan (Lite vs Pro)."""
        self.commission_schedule = commission_schedule

    def estimate(self, ticker, shares, side, current_price):
        spread_cost = self.get_spread(ticker) / 2  # half spread per side
        impact_cost = self.market_impact(shares, ticker)  # sqrt model
        commission = self.get_commission(shares, ticker)  # IBKR plan-dependent
        gap_cost = self.estimate_gap_risk(ticker, side)  # weekend gaps
        # Note: No tax drag for Singapore domicile (no CGT)
        total = spread_cost + impact_cost + commission + gap_cost
        return total

    def get_commission(self, shares, ticker):
        """IBKR Pro tiered: $0.0035/share up to 300K shares/mo.
           IBKR Lite: $0 but worse execution (PFOF).
           Configurable per user's IBKR plan."""
        if self.commission_schedule == 'ibkr_lite':
            return 0
        # IBKR Pro tiered default
        per_share = 0.0035  # Up to 300K shares/mo
        return max(shares * per_share, 0.35)  # $0.35 minimum

    def market_impact(self, shares, ticker):
        adv = self.get_average_daily_volume(ticker)
        participation = (shares * self.get_price(ticker)) / adv
        # Impact = k * sqrt(participation_rate), k calibrated per liquidity tier
        k = self.get_impact_coefficient(ticker)  # 5-20 bps depending on tier
        return k * math.sqrt(participation)
```

### Metrics

- **Return metrics**: total return, annualized return, CAGR
- **Risk metrics**: volatility, max drawdown, max drawdown duration, VaR, CVaR
- **Risk-adjusted**: Sharpe ratio, Sortino ratio, Calmar ratio
- **Robustness**: deflated Sharpe ratio (multiple testing correction), parameter stability score
- **Cost metrics**: total costs, cost as % of gross alpha, turnover rate
- **Regime metrics**: all of the above broken down by regime

### Benchmarks

Every backtest reports results against:

1. **S&P 500** (SPY buy-and-hold) — equity benchmark
2. **60/40 Portfolio** (60% SPY + 40% BND) — balanced benchmark
3. **Risk Parity** (basic implementation) — sophisticated benchmark

---

## 5. Rebalancing Decision Engine

### When to Rebalance

```python
def should_rebalance(portfolio, target_weights, regime, last_rebalance_date):
    days_since = (today - last_rebalance_date).days

    # Never more than once per week
    if days_since < 7:
        return False, "Within weekly cap"

    # Check drift
    max_drift = max(abs(current - target) for current, target in zip(...))
    drift_threshold = settings.rebalance_drift  # default 0.05 (5%)

    if max_drift > drift_threshold:
        return True, f"Drift {max_drift:.1%} exceeds threshold"

    # Check regime change
    if regime_changed_since(last_rebalance_date):
        return True, "Regime change detected"

    # Check drawdown trigger
    if drawdown_trigger_active():
        return True, "Drawdown threshold breached"

    return False, "No rebalancing needed"
```

### Trade Generation

```python
def generate_trades(current_weights, target_weights, portfolio_value):
    trades = []
    for ticker in universe:
        delta = target_weights[ticker] - current_weights[ticker]
        if abs(delta) < 0.005:  # 0.5% minimum trade size
            continue

        trade_value = delta * portfolio_value
        shares = trade_value / current_price(ticker)
        cost = cost_model.estimate(ticker, shares, 'buy' if delta > 0 else 'sell')

        # Only trade if expected benefit > cost
        expected_benefit = signal_alpha(ticker) * abs(delta) * portfolio_value
        if expected_benefit < cost:
            continue

        trades.append(Trade(ticker, shares, delta, cost))

    return trades
```
