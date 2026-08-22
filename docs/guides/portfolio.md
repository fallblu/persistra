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

## Optimize an explicit portfolio problem

Use `PortfolioProblem` when the target comes from an objective rather than a fixed weighting
rule. Expected returns, covariance, current weights, benchmark weights, factor exposures,
objectives, constraints, and cost penalties remain separate inputs:

```python
import numpy as np
import pandas as pd

from persistra.portfolio import (
    FactorExposureConstraint,
    GrossExposureConstraint,
    LinearTransactionCostPenalty,
    MeanVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    TurnoverConstraint,
    WeightBounds,
    optimize_portfolio,
)

assets = pd.Index(["AAA", "BBB", "CCC", "DDD"], name="asset")
expected_returns = pd.Series([0.06, 0.04, 0.03, 0.02], index=assets)
covariance = pd.DataFrame(
    np.diag([0.04, 0.03, 0.02, 0.01]),
    index=assets,
    columns=assets,
)
current = pd.Series([0.25, 0.25, 0.25, 0.25], index=assets)
factor_exposures = pd.DataFrame(
    {"supplied_factor": [-1.0, -0.5, 0.5, 1.0]},
    index=assets,
)
problem = PortfolioProblem(
    covariance=covariance,
    expected_returns=expected_returns,
    current_weights=current,
    factor_exposures=factor_exposures,
    objective=MeanVarianceObjective(risk_aversion=4.0),
    constraints=(
        WeightBounds(0.0, 0.50),
        GrossExposureConstraint(1.0),
        NetExposureConstraint(1.0, 1.0),
        TurnoverConstraint(0.30),
        FactorExposureConstraint(
            lower=pd.Series({"supplied_factor": -0.10}),
            upper=pd.Series({"supplied_factor": 0.10}),
        ),
    ),
    penalties=(LinearTransactionCostPenalty(0.0005),),
)
optimized = optimize_portfolio(problem)

print(optimized.weights)
print(optimized.objective_breakdown)
print(optimized.constraint_diagnostics)
```

Minimum-variance, mean-variance, minimum-tracking-error, and active mean-variance objectives are
separate typed objects. Tracking-error objectives and ceilings require benchmark weights. A
factor constraint operates only on the caller's supplied exposure matrix. Persistra does not
assign factor meanings.

The covariance scale defines the scale of variance and tracking error. Expected returns and
linear cost rates must use compatible units. The optimizer treats cash as the residual
`1 - sum(weights)`. Use `NetExposureConstraint(1, 1)` for a fully invested risky portfolio.
One-way turnover includes changes in risky assets and residual cash.

The result records the complete problem, solver outcome, objective terms, realized exposures,
factor exposures, and lower/upper residual for every constraint. Persistra validates the solver
point after optimization and raises `AnalysisError` for failure, infeasibility, or an excessive
constraint violation. A `FactorRiskModel` can replace the dense covariance input directly.

`LinearExposureConstraint` applies named lower and upper bounds to any caller-defined asset
loading matrix. It supports multiple independent sector, country, duration, asset-class, or other
exposure systems without assigning meanings to their columns. The result records their realized
values under a `(constraint, exposure)` index.

`GroupedExposureConstraint` builds those linear loadings from a stable asset-to-group `Series`,
an asset-by-group exposure matrix, or a dated `(as_of, asset)` exposure matrix. Scalar or
group-indexed lower and upper bounds support sector, country, currency, and custom group limits.
Set `neutrality_target` to replace both bounds with an exact target. Dated loadings require the
portfolio problem's exact `as_of` date.

The default policies reject assets with no active group and rows active in more than one group.
Select `missing="zero"` to retain an unclassified asset with zero group loadings, or
`overlapping="allow"` when overlapping classifications are intentional. Use
`resolve_grouped_exposure` to inspect the generated `LinearExposureConstraint` and its loadings
before optimization. Optimization results expose realized values and residual diagnostics under
the grouped constraint's stable name.

Use `RiskParityObjective()` for equal risk contribution, or pass an asset-indexed `budgets`
series whose nonnegative values sum to one. The nonlinear objective minimizes squared residuals
between requested and realized fractional contributions to portfolio variance while preserving
weight, exposure, and turnover constraints. For a long-short portfolio, contributions retain
their sign: a hedge with a negative marginal contribution reports a negative realized budget
rather than being clipped to zero.

`RiskBudgetConstraint` adds exact asset targets, asset upper bounds, and equivalent grouped
targets or upper bounds. Group loadings are a nonnegative asset-by-group matrix and may overlap.
Results always expose asset `risk_contributions`; `risk_budget_diagnostics` records each realized
value, requested target or ceiling, residual, and binding status. Zero-risk portfolios are
rejected because fractional contributions are undefined, and covariance conditioning must make
an indefinite input positive semidefinite before either risk-budget feature is used.

```python
from persistra.portfolio import (
    NetExposureConstraint,
    PortfolioProblem,
    RiskParityObjective,
    WeightBounds,
    optimize_portfolio,
)

risk_parity = optimize_portfolio(
    PortfolioProblem(
        covariance=covariance,
        objective=RiskParityObjective(),
        constraints=(WeightBounds(0.0, 0.50), NetExposureConstraint(1.0, 1.0)),
    )
)
print(risk_parity.risk_contributions)
print(risk_parity.risk_budget_diagnostics)
```

For long-short construction, combine the existing signed exposure controls with upper budgets;
negative hedge contributions remain feasible because only contributions above each ceiling bind:

```python
from persistra.portfolio import RiskBudgetConstraint

long_short_problem = PortfolioProblem(
    covariance=covariance,
    expected_returns=expected_returns,
    objective=MeanVarianceObjective(risk_aversion=4.0),
    constraints=(
        WeightBounds(-0.25, 0.50),
        GrossExposureConstraint(1.50),
        NetExposureConstraint(1.0, 1.0),
        RiskBudgetConstraint(upper=pd.Series(0.60, index=assets)),
    ),
)
long_short = optimize_portfolio(long_short_problem)
print(long_short.risk_contributions)
```

For downside-focused construction, `ConditionalValueAtRiskObjective` minimizes empirical loss
CVaR from an explicit `scenario_returns` frame. Columns must exactly match the covariance asset
index; rows are caller-defined scenarios and are neither resampled nor assigned probabilities.
At confidence level `0.95`, CVaR is the equally weighted mean of the worst five percent of
scenario losses, with fractional weighting at the empirical tail boundary. Use
`ConditionalValueAtRiskConstraint` to cap that same measure while optimizing another objective:

```python
from persistra.portfolio import ConditionalValueAtRiskObjective

scenarios = pd.DataFrame(
    [
        [-0.08, -0.02, 0.01, 0.00],
        [0.01, -0.06, -0.02, 0.00],
        [0.02, 0.01, 0.00, -0.03],
        [0.01, 0.01, 0.01, 0.01],
    ],
    index=["equity_stress", "credit_stress", "rate_stress", "upside"],
    columns=assets,
)
downside = optimize_portfolio(
    PortfolioProblem(
        covariance=covariance,
        scenario_returns=scenarios,
        objective=ConditionalValueAtRiskObjective(confidence_level=0.75),
        constraints=(WeightBounds(0.0, 0.50), NetExposureConstraint(1.0, 1.0)),
    )
)
print(downside.downside_risk)
print(downside.downside_diagnostics.query("is_tail"))
```

`downside_diagnostics` reports every scenario loss, normalized tail weight, tail contribution,
and tail membership under a stable measure key. Scenario returns and the CVaR maximum use the
same return frequency and units; Persistra does not annualize them. A bound below the attainable
scenario loss is reported as infeasible.

`RobustMeanVarianceObjective` uses the established ellipsoidal uncertainty formulation. Its
worst-case expected-return penalty is `radius * sqrt(weights.T @ matrix @ weights)`, where the
typed `EllipsoidalExpectedReturnUncertainty` supplies a positive-semidefinite asset matrix and a
nonnegative radius. Radius zero exactly recovers nominal mean variance; increasing it penalizes
directions with greater estimation uncertainty while remaining compatible with linear
constraints and transaction costs. The objective breakdown separates nominal expected-return,
variance, uncertainty, and cost terms. Expected returns, covariance, and the uncertainty penalty
must be calibrated to compatible periods and units.

Covariance validation remains strict by default. Set `CovariancePolicy.diagonal_shrinkage` to
shrink toward the supplied covariance diagonal, `minimum_eigenvalue` to floor its eigenvalues, or
both to apply them in that order. The optimization result records the raw and conditioned minimum
eigenvalues, condition number, adjustment norm, and policy values.

Use `optimize_portfolio_path` for an ordered tuple of dated `PortfolioProblem` values. Every
problem must declare a strictly increasing `as_of` value and use one fixed asset index. Each
successful result becomes the next problem's current portfolio and numerical starting point.
The default `raise` failure policy stops immediately. Select `hold_previous` to record a failed
step and carry the last successful portfolio; the first step must still solve successfully.

`optimize_portfolio` and `optimize_portfolio_path` accept any `PortfolioSolver` implementation.
Persistra translates portfolio objectives and constraints into a `PortfolioSolverProblem`, and
`ScipySlsqpSolver` remains the default backend. Results retain the selected solver's identity,
termination message, iterations, and normalized evaluation statistics. Supplying
`initial_weights` gives a backend an explicit warm start; optimization paths do this
automatically after their first step.

Install `persistra[portfolio-solver]` to add the CVXPY backends. `CvxpySolver` uses Clarabel for
convex quadratic objectives with affine constraints. Its `capabilities` property lists every
accepted objective, penalty, and constraint. Unsupported features fail before a solver runs;
for example, the initial convex backend rejects nonlinear CVaR, robust mean-variance,
risk-parity, risk-budget, and tracking-error formulations. Both backends return normalized
status, iteration, objective, and bound fields through
`PortfolioSolverResult`. CVXPY is optional because its modeling and solver packages are much
larger than the default SLSQP dependency path.

Use `DiscretePortfolioProblem` and `optimize_discrete_portfolio` when portfolio decisions must be
actual nonnegative integer holdings. Prices and capital convert each caller-defined trade lot to
an exact weight. The focused initial model supports minimum and maximum position weights, a
maximum position count, a minimum invested weight, and asset-specific integer lot sizes:

```python
from persistra.portfolio import (
    DiscretePortfolioProblem,
    MeanVarianceObjective,
    optimize_discrete_portfolio,
)

discrete = optimize_discrete_portfolio(
    DiscretePortfolioProblem(
        covariance=covariance,
        prices=pd.Series([25.0, 40.0, 50.0, 20.0], index=assets),
        capital=100_000.0,
        objective=MeanVarianceObjective(risk_aversion=4.0),
        expected_returns=expected_returns,
        maximum_positions=3,
        minimum_position_weight=0.10,
        lot_sizes=pd.Series([10, 5, 10, 25], index=assets),
        minimum_invested_weight=0.95,
    )
)
```

The mixed-integer backend uses SCIP through CVXPY and never substitutes continuous weights for
discrete constraints. The result includes integer lots and holdings, residual cash, normalized
termination status, primal and dual bounds, relative gap, and node diagnostics. Mixed-integer
solve time can grow sharply with asset count and cardinality; use the continuous solver when the
integer contract is unnecessary.

`LinearTransactionCostPenalty` uses one symmetric rate. Use
`AsymmetricTransactionCostPenalty` for separate buy and sell rates, and
`QuadraticTransactionCostPenalty` for market impact proportional to squared weight changes.
All rates remain asset-specific or scalar, require current weights, and contribute separately to
the objective breakdown before reconciling to its total transaction-cost term.

## Construct target weights

For simple nonoptimized weighting, supply signals as a fixed-universe date-by-asset frame.
The frame must contain at least one asset and one decision date. Missing cells keep an asset in
the universe but make it ineligible on that date:

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
dates. Every portfolio panel must contain at least one observation; an empty target or market
date axis is rejected before simulation. The default timing applies each target one observation
later:

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

Use [Replay a strategy with Trading Engine](trading-engine.md) when supported raw intraday bars
and target positions need an external execution replay with orders, fills, fees, and event-time
valuation.

Use [Develop a strategy](strategy-development.md) when targets must be recomputed from completed
history, filtered securities, fills, working orders, or marked portfolio state. The
[portfolio-optimization examples](../examples/portfolio-optimization.md) show how to carry dated
optimizer results into either path.
