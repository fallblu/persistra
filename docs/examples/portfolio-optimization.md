# Portfolio-optimization examples

Portfolio optimization turns forecasts and risk estimates into explicit target weights. The
problem object keeps objective, constraints, costs, covariance policy, benchmark, current
portfolio, and decision time separate.

## Define aligned inputs

```python
from dataclasses import replace

import numpy as np
import pandas as pd

assets = pd.Index(["asset-a", "asset-b", "asset-c", "asset-d"], name="asset")
expected_returns = pd.Series([0.07, 0.05, 0.03, 0.01], index=assets)
covariance = pd.DataFrame(
    [
        [0.040, 0.010, 0.004, 0.002],
        [0.010, 0.030, 0.006, 0.003],
        [0.004, 0.006, 0.020, 0.004],
        [0.002, 0.003, 0.004, 0.015],
    ],
    index=assets,
    columns=assets,
)
current_weights = pd.Series([0.25, 0.25, 0.25, 0.25], index=assets)
benchmark_weights = pd.Series([0.25, 0.25, 0.25, 0.25], index=assets)

assert covariance.index.equals(covariance.columns)
assert expected_returns.index.equals(covariance.index)
```

Persistra uses axis equality, not set equality. Reindex deliberately before constructing the
problem.

## Solve a long-only mean-variance problem

```python
from persistra.portfolio import (
    MeanVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    WeightBounds,
    optimize_portfolio,
)

base_problem = PortfolioProblem(
    covariance=covariance,
    expected_returns=expected_returns,
    current_weights=current_weights,
    benchmark_weights=benchmark_weights,
    objective=MeanVarianceObjective(risk_aversion=4.0),
    constraints=(
        WeightBounds(0.0, 0.50),
        NetExposureConstraint(1.0, 1.0),
    ),
    as_of=pd.Timestamp("2025-03-31"),
)
base_result = optimize_portfolio(base_problem)

assert abs(float(base_result.weights.sum()) - 1.0) < 1e-8
print(base_result.weights)
print(base_result.objective_breakdown)
```

Cash is the residual `1 - sum(weights)`. A fixed net exposure of one makes this example fully
invested. Without that constraint, the objective may retain cash.

## Compare supported objectives

```python
from persistra.portfolio import (
    ActiveMeanVarianceObjective,
    MinimumTrackingErrorObjective,
    MinimumVarianceObjective,
)

minimum_variance = optimize_portfolio(
    replace(base_problem, objective=MinimumVarianceObjective(), expected_returns=None)
)
minimum_tracking_error = optimize_portfolio(
    replace(base_problem, objective=MinimumTrackingErrorObjective(), expected_returns=None)
)
active_mean_variance = optimize_portfolio(
    replace(base_problem, objective=ActiveMeanVarianceObjective(risk_aversion=4.0))
)

print(minimum_variance.variance)
print(minimum_tracking_error.tracking_error)
print(active_mean_variance.expected_return)
```

Tracking-error objectives operate on weights relative to `benchmark_weights`. Active
mean-variance maximizes expected active return against tracking-error variance.

## Constrain gross, net, turnover, and tracking error

```python
from persistra.portfolio import (
    GrossExposureConstraint,
    TrackingErrorConstraint,
    TurnoverConstraint,
)

controlled_problem = replace(
    base_problem,
    constraints=(
        WeightBounds(-0.30, 0.50),
        GrossExposureConstraint(1.20),
        NetExposureConstraint(0.95, 1.00),
        TurnoverConstraint(0.30),
        TrackingErrorConstraint(0.15),
    ),
)
controlled_result = optimize_portfolio(controlled_problem)

print(controlled_result.exposures)
print(controlled_result.turnover)
print(controlled_result.constraint_diagnostics)
```

One-way turnover includes risky assets and residual cash. Constraint diagnostics report lower
and upper residuals and whether each boundary is binding.

## Constrain factor and general linear exposures

```python
from persistra.portfolio import FactorExposureConstraint, LinearExposureConstraint

factor_exposures = pd.DataFrame(
    {
        "value": [1.0, 0.5, -0.4, -0.8],
        "momentum": [-0.2, 0.8, 0.4, -0.6],
    },
    index=assets,
)
sector_loadings = pd.DataFrame(
    {
        "technology": [1.0, 1.0, 0.0, 0.0],
        "defensive": [0.0, 0.0, 1.0, 1.0],
    },
    index=assets,
)
exposure_problem = replace(
    base_problem,
    factor_exposures=factor_exposures,
    constraints=(
        WeightBounds(0.0, 0.50),
        NetExposureConstraint(1.0, 1.0),
        FactorExposureConstraint(
            lower=pd.Series({"value": -0.10, "momentum": -0.10}),
            upper=pd.Series({"value": 0.30, "momentum": 0.30}),
        ),
        LinearExposureConstraint(
            name="sector",
            loadings=sector_loadings,
            lower=pd.Series({"technology": 0.30, "defensive": 0.30}),
            upper=pd.Series({"technology": 0.70, "defensive": 0.70}),
        ),
    ),
)
exposure_result = optimize_portfolio(exposure_problem)

print(exposure_result.factor_exposures)
print(exposure_result.linear_exposures)
```

`FactorExposureConstraint` uses `PortfolioProblem.factor_exposures`.
`LinearExposureConstraint` carries its own named loading system, making it suitable for sector,
country, duration, asset-class, or other caller-defined linear controls.

## Condition a covariance matrix explicitly

```python
from persistra.portfolio import CovariancePolicy

conditioned_result = optimize_portfolio(
    replace(
        base_problem,
        covariance_policy=CovariancePolicy(
            diagonal_shrinkage=0.20,
            minimum_eigenvalue=1e-6,
        ),
    )
)

print(conditioned_result.covariance_diagnostics)
```

The policy first shrinks toward the supplied diagonal and then floors eigenvalues. The result
records raw and conditioned eigenvalues, condition numbers, and adjustment magnitude.

## Model symmetric, asymmetric, and quadratic costs

```python
from persistra.portfolio import (
    AsymmetricTransactionCostPenalty,
    LinearTransactionCostPenalty,
    QuadraticTransactionCostPenalty,
)

cost_problem = replace(
    base_problem,
    penalties=(
        LinearTransactionCostPenalty(0.0002),
        AsymmetricTransactionCostPenalty(
            buy_rates=pd.Series(0.0004, index=assets),
            sell_rates=pd.Series(0.0007, index=assets),
        ),
        QuadraticTransactionCostPenalty(
            rates=pd.Series([0.002, 0.002, 0.003, 0.004], index=assets)
        ),
    ),
)
cost_result = optimize_portfolio(cost_problem)

print(cost_result.objective_breakdown[
    [
        "linear_transaction_cost_term",
        "quadratic_transaction_cost_term",
        "transaction_cost_term",
    ]
])
```

Rates must use units compatible with expected returns and covariance. Every penalty requires
current weights. The aggregate cost term reconciles its linear and quadratic components.

## Optimize a dated path

```python
from persistra.portfolio import optimize_portfolio_path

path_problems = tuple(
    replace(
        base_problem,
        expected_returns=expected_returns.shift(position, fill_value=expected_returns.iloc[-1]),
        as_of=pd.Timestamp("2025-03-31") + pd.offsets.MonthEnd(position),
    )
    for position in range(3)
)
path = optimize_portfolio_path(path_problems, failure_policy="hold_previous")

assert len(path.steps) == 3
print(path.weights)
print([step.status for step in path.steps])
```

Every step uses one fixed ordered asset axis and a strictly increasing `as_of`. A successful
solution becomes the next step's current weights and numerical warm start. `hold_previous`
records later infeasibility without fabricating a solution.

## Supply a solver backend

Implement `PortfolioSolver` to connect another continuous optimizer. This wrapper records the
neutral problem and delegates to the default backend:

```python
from persistra.portfolio import (
    PortfolioSolverProblem,
    PortfolioSolverResult,
    ScipySlsqpSolver,
)


class RecordingSolver:
    name = "recording-slsqp"

    def __init__(self) -> None:
        self.problem: PortfolioSolverProblem | None = None

    def solve(self, problem: PortfolioSolverProblem) -> PortfolioSolverResult:
        self.problem = problem
        return ScipySlsqpSolver().solve(problem)


solver = RecordingSolver()
custom_result = optimize_portfolio(base_problem, solver=solver)

assert solver.problem is not None
assert custom_result.solver == "recording-slsqp"
print(custom_result.solver_statistics)
```

A backend receives differentiable objective and gradient callables, variable bounds,
solver-neutral equality and nonnegative-inequality constraints, an initial point, tolerance, and
iteration limit. It returns normalized values, status, iterations, and statistics. Persistra
still validates the returned portfolio against the original problem.

## Backtest dated targets

Vectorized backtesting starts from target rows and a return or price panel. It does not model
orders or fills:

```python
from persistra.portfolio import BacktestTiming, backtest_portfolio

market_dates = pd.date_range("2025-03-31", periods=8, freq="D")
market_returns = pd.DataFrame(
    [
        [0.002, 0.001, -0.001, 0.000],
        [0.001, -0.002, 0.001, 0.000],
        [-0.001, 0.002, 0.000, 0.001],
        [0.003, 0.001, -0.001, 0.001],
        [0.000, -0.001, 0.002, 0.001],
        [0.001, 0.001, 0.001, -0.001],
        [-0.002, 0.000, 0.002, 0.001],
        [0.001, 0.002, 0.000, -0.001],
    ],
    index=market_dates,
    columns=assets,
)
targets = pd.DataFrame(
    [base_result.weights, cost_result.weights],
    index=market_dates[[0, 3]],
)
backtest = backtest_portfolio(
    targets,
    returns=market_returns,
    timing=BacktestTiming(decision_lag=0, execution_lag=1),
    transaction_cost_bps=5.0,
    benchmarks={"equal-weight": benchmark_weights},
)

print(backtest.equity)
print(backtest.turnover)
print(backtest.benchmark_comparison)
```

Targets are signal-observation dates. Timing maps them to decisions and first holding periods.
Use Trading Engine replay when partial fills, direct orders, fees, margin, or execution-model
behavior can change the conclusion.
