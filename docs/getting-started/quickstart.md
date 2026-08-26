# Strategy quickstart

This offline workflow turns caller-defined factor returns into expected asset returns, solves a
constrained portfolio, attributes the result, and places the target behind a reusable strategy
lifecycle. It requires no credentials, network access, or Trading Engine executable.

## Prepare factor and asset returns

Persistra does not provide reference factors. Supply factors whose definitions, timing, and
units match the research question. This deterministic sample uses two arbitrary factor series:

```python
import pandas as pd

dates = pd.date_range("2025-01-01", periods=60, freq="D")
factors = pd.DataFrame(
    {
        "value": [((position % 9) - 4) / 120 for position in range(60)],
        "momentum": [((position % 7) - 3) / 140 for position in range(60)],
    },
    index=dates,
)
noise = pd.Series([((position % 5) - 2) / 1000 for position in range(60)], index=dates)
asset_returns = pd.DataFrame(
    {
        "asset-a": 0.0008 + 0.9 * factors["value"] + 0.2 * factors["momentum"] + noise,
        "asset-b": -0.0002 - 0.2 * factors["value"] + 1.0 * factors["momentum"] - noise,
        "asset-c": 0.0004 + 0.4 * factors["value"] - 0.5 * factors["momentum"] + noise / 2,
    },
    index=dates,
)

assert asset_returns.index.equals(factors.index)
```

Real strategy research should construct both panels through point-in-time feature and label
rules. Exact date and asset axes are deliberate contracts, not data-cleaning conveniences.

## Fit a factor regression and risk model

Fit one time-series regression per asset. The result exposes coefficients, inference,
fitted values, residuals, and per-asset diagnostics:

```python
from persistra.research import fit_time_series_factor_model

regression = fit_time_series_factor_model(
    asset_returns,
    factors,
    covariance="newey_west",
    hac_lags=3,
)

print(regression.coefficients)
print(regression.diagnostics[["observations", "r_squared", "status"]])
```

Build a factor risk model from the fitted exposures, observed factor returns, and residuals.
The shrinkage choice is explicit:

```python
from persistra.research import build_factor_risk_model

exposures = regression.coefficients[["value", "momentum"]]
risk_model = build_factor_risk_model(
    exposures,
    factors,
    regression.residuals,
    shrinkage=0.25,
    window=40,
)

assert risk_model.asset_covariance.index.equals(asset_returns.columns)
```

## Convert the model into a forecast

Premia remain caller-supplied estimates. Here the recent factor mean is only a compact example:

```python
from persistra.research import build_factor_portfolio_forecast

premia = factors.tail(20).mean()
forecast = build_factor_portfolio_forecast(risk_model, premia)

print(forecast.expected_returns)
print(forecast.expected_return_contributions)
```

The forecast carries factor exposures, factor and asset covariance, idiosyncratic variance,
alpha, premia, contribution detail, and the risk model's `as_of` value.

## Optimize a constrained target

State the objective, constraints, covariance conditioning, current portfolio, and estimated
trading costs in one problem:

```python
from persistra.portfolio import (
    CovariancePolicy,
    LinearTransactionCostPenalty,
    MeanVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    TurnoverConstraint,
    WeightBounds,
    optimize_portfolio,
)

current = pd.Series(0.0, index=forecast.expected_returns.index)
problem = PortfolioProblem(
    covariance=forecast.asset_covariance,
    covariance_policy=CovariancePolicy(diagonal_shrinkage=0.1, minimum_eigenvalue=1e-8),
    expected_returns=forecast.expected_returns,
    current_weights=current,
    objective=MeanVarianceObjective(risk_aversion=10.0),
    constraints=(
        WeightBounds(0.0, 0.60),
        NetExposureConstraint(1.0, 1.0),
        TurnoverConstraint(1.0),
    ),
    penalties=(LinearTransactionCostPenalty(0.0005),),
    as_of=forecast.as_of,
)
optimization = optimize_portfolio(problem)

assert abs(float(optimization.weights.sum()) - 1.0) < 1e-8
print(optimization.weights)
print(optimization.constraint_diagnostics)
```

Optimization diagnostics expose binding constraints, covariance conditioning, objective terms,
solver identity, iterations, and normalized solver statistics.

## Attribute the target

```python
from persistra.research import attribute_factor_portfolio

attribution = attribute_factor_portfolio(forecast, optimization.weights)

print(attribution.factor_exposures)
print(attribution.expected_return_contributions)
print(attribution.variance_contributions)
```

Attribution reconciles the same forecast and covariance used to choose the weights.

## Continue developing

- [Factor-model examples](../examples/factor-models.md) cover static, rolling, cross-sectional,
  Fama-MacBeth, risk, forecast, and attribution workflows.
- [Portfolio examples](../examples/portfolio-optimization.md) cover constraints, costs, rolling
  decisions, custom solvers, and vectorized backtests.
- [Set up Trading Engine](trading-engine.md) when targets are ready for execution replay.
