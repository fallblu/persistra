# Construct and backtest portfolios

The `persistra.portfolio` package turns explicit date-by-asset signals into target weights and
simulates portfolio-level rebalances. It keeps constraints, timing, missing observations, cash,
and costs visible. It does not model orders or exchange execution.

## Choose rebalance dates

Use `rebalance_schedule` to select observed dates. Calendar schedules choose the first or last
available observation in each bucket. Integer schedules count supplied observations instead of
calendar time:

```python
import pandas as pd

from persistra.portfolio import rebalance_schedule

dates = pd.bdate_range("2025-01-01", periods=80)
monthly = rebalance_schedule(dates, frequency="monthly", anchor="end")
every_ten_observations = rebalance_schedule(dates, frequency=10, anchor="start")
```

The function does not invent dates. A month-end schedule uses the last date present in the
input for each month.

## Construct target weights

Supply signals as a fixed-universe date-by-asset frame. Missing cells keep an asset in the
universe but make it ineligible on that date:

```python
import numpy as np
import pandas as pd

from persistra.portfolio import PortfolioConstraints, construct_portfolio

signals = pd.DataFrame(
    [
        [0.8, 0.3, -0.2, -0.7],
        [0.4, 0.6, -0.5, np.nan],
    ],
    index=pd.to_datetime(["2025-01-31", "2025-02-28"]),
    columns=["AAA", "BBB", "CCC", "DDD"],
)
constraints = PortfolioConstraints(
    gross_limit=1.0,
    net_minimum=0.0,
    net_maximum=0.0,
    position_limit=0.60,
    turnover_limit=0.30,
)
portfolio = construct_portfolio(
    signals,
    weighting="signal_proportional",
    configuration="long_short",
    gross_target=1.0,
    net_target=0.0,
    constraints=constraints,
)

print(portfolio.weights)
print(portfolio.cash)
print(portfolio.exposures)
```

Equal weighting ignores magnitude. It assigns equal long-only weights to every observed asset.
For a long-short portfolio, signal signs define the long and short sides. Signal-proportional
weighting uses positive magnitude in a long-only portfolio and absolute magnitude within each
side of a long-short portfolio.

Gross and net targets define each side's budget. The position limit uses capped redistribution
within a side. It preserves relative weights among uncapped positions. The constructor raises
`AnalysisError` when the observed assets cannot carry the requested exposure. It does not hide
infeasibility by dropping a limit.

`cash` is always `1 - net weight`. It is positive for an uninvested residual, greater than one
when short-sale proceeds increase cash, and negative when the risky portfolio uses net leverage.
One-way turnover includes changes to risky assets and residual cash. A turnover limit blends the
desired target with the preceding target. Pass `initial_weights` when the first target starts
from holdings other than cash.

`unconstrained_weights` records the signal-only allocation before position, risk, and turnover
controls. Use it as an explicit naive-signal benchmark when that comparison answers the research
question.

## Apply covariance risk controls

Supply one covariance matrix for each signal date. Each matrix must use the exact asset index and
columns. It must be finite, symmetric within tolerance, and positive semidefinite:

```python
from persistra.portfolio import PortfolioRiskControl

covariance = pd.DataFrame(
    np.diag([0.0004, 0.0003, 0.0005, 0.0004]),
    index=signals.columns,
    columns=signals.columns,
)
risk = PortfolioRiskControl(
    target_volatility=0.10,
    volatility_limit=0.12,
    periods_per_year=252,
)
risk_controlled = construct_portfolio(
    signals,
    weighting="signal_proportional",
    configuration="long_short",
    constraints=constraints,
    covariances={date: covariance for date in signals.index},
    risk_control=risk,
)
```

The risk control scales the complete risky portfolio. It does not change relative asset weights
or solve an optimization problem. Exposure and position limits cap upward scaling. A net floor,
turnover limit, and volatility ceiling can conflict; the constructor reports that combination as
infeasible.

`predicted_volatility` records the achieved annualized value. `risk_contributions` reports each
asset's fractional contribution to portfolio variance. Contributions can be negative when a
position hedges other risk. `constraint_utilization` reports gross, directional net, position,
turnover, and volatility-ceiling usage.

## Run a causal backtest

Pass target weights and exactly one return or price panel. Target row dates are signal-observation
dates. The default timing applies each target one observation later:

```python
from persistra.portfolio import BacktestTiming, backtest_portfolio

returns = pd.DataFrame(
    [
        [0.01, 0.00, -0.01, 0.02],
        [0.02, 0.01, 0.00, -0.01],
        [-0.01, 0.02, 0.01, 0.00],
    ],
    index=pd.to_datetime(["2025-01-31", "2025-02-03", "2025-02-28"]),
    columns=signals.columns,
)
result = backtest_portfolio(
    portfolio,
    returns=returns,
    timing=BacktestTiming(decision_lag=0, execution_lag=1),
    transaction_cost_bps=5.0,
)

print(result.returns)
print(result.equity)
print(result.drawdown)
```

`decision_lag` counts return-index observations from signal observation to decision.
`execution_lag` counts observations from decision to the first holding return. Set
`holding_period` to a positive observation count to exit to cash after a fixed period. Leave it
unset to hold until the next target or the end of the sample.

A zero total lag uses the signal-period return. Persistra rejects it unless you set
`signal_available_before_trade=True`. That field is an explicit assertion about the input
contract. It is not inferred from a timestamp label.

`rebalance_log` records the signal observation, decision, holding start, planned holding end,
execution status, and blocked assets. A target that cannot start before the sample ends remains
in the log with `outside_sample` status.

## Choose missing and nontradeable policies

The strict defaults raise when a held asset has a missing return or a required trade is blocked:

```python
from persistra.portfolio import BacktestPolicies

policies = BacktestPolicies(
    missing_return="zero",
    nontradeable="hold",
)
controlled = backtest_portfolio(
    portfolio,
    returns=returns,
    policies=policies,
    tradeable=pd.DataFrame(True, index=returns.index, columns=returns.columns),
)
```

The `zero` missing-return policy assumes a zero return for a held missing observation. It does not
fill a price. Price input uses `pct_change` without filling levels, so a missing price produces a
missing return and follows the same policy.

The `hold` nontradeable policy keeps the preceding realized weight for each blocked asset. Other
assets still move to their targets, and cash absorbs the difference. The `error` policy stops at
the first required blocked trade. The tradeability panel uses `True` for tradeable assets and
must match the return panel exactly.

## Reconcile costs and performance

Transaction cost rates can be one basis-point value for all assets or a series indexed by asset.
Costs equal absolute risky-asset traded notional times the asset rate. Residual cash does not
incur a trading cost. The simulator deducts costs from cash before it calculates ending weights.

The result exposes both sides of the accounting identity:

```python
gross = result.asset_return_attribution.sum(axis="columns")
gross = gross.add(result.cash_return_attribution)
net = gross.sub(result.costs)

assert np.allclose(gross, result.gross_returns)
assert np.allclose(net, result.returns)
assert np.allclose(result.cost_attribution.sum(axis="columns"), result.costs)
assert np.allclose(result.realized_weights.sum(axis="columns").add(result.cash), 1.0)
assert np.allclose(result.ending_weights.sum(axis="columns").add(result.ending_cash), 1.0)
```

`realized_weights` are beginning weights after a scheduled rebalance and any nontradeable hold.
`ending_weights` include market movement and cost deduction. `trades` record the difference from
the preceding ending weights. Turnover is one-half of absolute risky-asset and residual-cash
weight changes. `exposures` report beginning long, short, gross, net, and cash weights.

Cash returns can be a scalar or an aligned series. Negative cash earns or pays the supplied rate
with its sign, so a positive cash return becomes a borrowing cost for a leveraged portfolio.

## Compare static and naive benchmarks

Benchmark definitions stay caller-visible. Pass a series for static buy-and-hold weights or a
panel for changing targets:

```python
static_equal_weight = pd.Series(0.25, index=returns.columns)
compared = backtest_portfolio(
    portfolio,
    returns=returns,
    benchmarks={
        "static_equal_weight": static_equal_weight,
        "naive_signal": portfolio.unconstrained_weights,
    },
)

print(compared.benchmark_returns)
print(compared.benchmark_equity)
print(compared.benchmark_comparison)
```

Static weights enter on the first strategy signal date and drift thereafter. Panel benchmarks
use the strategy timing, policies, costs, cash returns, and tradeability assumptions. The
comparison reports aligned counts, mean returns, mean differences, tracking error, win rate, and
correlation.

## Keep the model boundary clear

The simulator operates on portfolio weights and period returns. It models target rebalances,
blocked assets, linear costs, cash, and leverage. It does not create orders, fills, partial
execution, market impact, intraday event loops, exchange latency, order books, broker state, or
live trading behavior.
