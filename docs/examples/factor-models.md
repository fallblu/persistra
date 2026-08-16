# Factor-model examples

Persistra fits regression models from factors you supply. It does not define reference factors,
download factor libraries, infer economic meaning, or annualize results. The examples below use
arbitrary `value` and `momentum` columns to show the contracts.

## Build aligned return panels

Time-series regressions require one sorted date index shared by the date-by-asset and
date-by-factor panels:

```python
import pandas as pd

dates = pd.date_range("2025-01-01", periods=80, freq="D")
factor_returns = pd.DataFrame(
    {
        "value": [((position % 11) - 5) / 160 for position in range(80)],
        "momentum": [((position % 7) - 3) / 130 for position in range(80)],
    },
    index=dates,
)
noise = pd.Series([((position % 5) - 2) / 1200 for position in range(80)], index=dates)
asset_returns = pd.DataFrame(
    {
        "asset-a": 0.0005 + 1.0 * factor_returns["value"] + 0.2 * factor_returns["momentum"] + noise,
        "asset-b": -0.0003 - 0.4 * factor_returns["value"] + 0.9 * factor_returns["momentum"] - noise,
        "asset-c": 0.0001 + 0.3 * factor_returns["value"] - 0.6 * factor_returns["momentum"] + noise / 2,
    },
    index=dates,
)

assert asset_returns.index.equals(factor_returns.index)
```

Missing values are removed independently for each asset. Do not pre-fill unknown returns merely
to make a rectangle complete.

## Fit time-series regressions

```python
from persistra.research import fit_time_series_factor_model

static_model = fit_time_series_factor_model(
    asset_returns,
    factor_returns,
    covariance="newey_west",
    hac_lags=4,
)

print(static_model.coefficients)
print(static_model.standard_errors)
print(static_model.t_statistics)
print(static_model.diagnostics)
```

Choose `covariance="classical"`, `"hc3"`, or `"newey_west"`. Newey-West inference accepts an
explicit lag count or a data-dependent default. The coefficient estimates do not change when
only the covariance estimator changes.

Weighted least squares uses a positive date-by-asset panel on the same axes:

```python
regression_weights = pd.DataFrame(1.0, index=dates, columns=asset_returns.columns)
regression_weights.loc[dates[:10], "asset-c"] = 0.5

weighted_model = fit_time_series_factor_model(
    asset_returns,
    factor_returns,
    weights=regression_weights,
    covariance="hc3",
)

assert weighted_model.coefficients.index.equals(asset_returns.columns)
```

Inspect `diagnostics["status"]` before consuming inference. A rank-deficient design retains the
least-norm coefficient estimate but marks unavailable inference explicitly.

## Fit rolling or expanding regressions

```python
from persistra.research import rolling_time_series_factor_model

rolling_model = rolling_time_series_factor_model(
    asset_returns,
    factor_returns,
    window=40,
    minimum_observations=20,
    covariance="hc3",
)
expanding_model = rolling_time_series_factor_model(
    asset_returns,
    factor_returns,
    window=None,
    minimum_observations=20,
)

latest_date = dates[-1]
latest_betas = rolling_model.coefficients.xs(latest_date, level="date")
print(latest_betas)
```

An estimate dated `t` uses no observation later than `t`. Early rows remain on the result axis
with `insufficient_observations` status instead of disappearing.

## Estimate cross-sectional factor returns

Create forward-return labels separately from exposures. The label object records the horizon and
the actual end date of every label:

```python
from persistra.research import estimate_cross_sectional_factor_returns, forward_returns

prices = 100.0 * (1.0 + asset_returns).cumprod()
labels = forward_returns(prices, horizon=1)
exposure_index = pd.MultiIndex.from_product(
    [dates, asset_returns.columns],
    names=["date", "asset"],
)
cross_sectional_exposures = pd.DataFrame(
    {
        "value": [1.0, -0.5, 0.2] * len(dates),
        "momentum": [0.1, 0.8, -0.6] * len(dates),
    },
    index=exposure_index,
)

cross_sectional = estimate_cross_sectional_factor_returns(
    labels,
    cross_sectional_exposures,
    covariance="hc3",
)

assert cross_sectional.label_horizon == 1
print(cross_sectional.factor_returns.tail())
```

With only three assets and an intercept, this toy example has no residual degrees of freedom. It
is useful for demonstrating alignment, not for inference. A real cross-section needs enough
complete assets for the requested terms.

## Summarize premia and run Fama-MacBeth

```python
from persistra.research import fama_macbeth_regression, summarize_factor_premia

premia_summary = summarize_factor_premia(
    cross_sectional.factor_returns,
    covariance="newey_west",
    hac_lags=3,
)
fama_macbeth = fama_macbeth_regression(
    labels,
    cross_sectional_exposures,
    hac_lags=3,
)

print(premia_summary.statistics)
print(fama_macbeth.premia.statistics)
```

`summarize_factor_premia` also accepts any caller-supplied factor-return history. Fama-MacBeth
preserves the label horizon, per-date cross-sectional results, and time-series premium inference.

## Build a factor risk model

Use current exposures with a history of factor and residual returns:

```python
from persistra.research import build_factor_risk_model

current_exposures = static_model.coefficients[["value", "momentum"]]
risk_model = build_factor_risk_model(
    current_exposures,
    factor_returns,
    static_model.residuals,
    shrinkage=0.20,
    window=60,
    as_of=dates[-1],
)

assert risk_model.asset_covariance.index.equals(asset_returns.columns)
print(risk_model.factor_covariance)
print(risk_model.idiosyncratic_variance)
```

Diagonal shrinkage applies to factor covariance. The asset covariance reconciles factor and
idiosyncratic variance for the supplied exposure snapshot.

## Build a point-in-time portfolio forecast

```python
from persistra.research import build_factor_portfolio_forecast

estimated_premia = factor_returns.tail(30).mean()
asset_alpha = pd.Series(
    {"asset-a": 0.0002, "asset-b": 0.0, "asset-c": -0.0001}
)
forecast = build_factor_portfolio_forecast(
    risk_model,
    estimated_premia,
    alpha=asset_alpha,
)

print(forecast.expected_returns)
print(forecast.expected_return_contributions)
```

The function applies no hidden scaling. Factor contribution equals exposure times supplied
premium, and expected asset return equals alpha plus those contributions.

## Attribute absolute or active weights

```python
from persistra.research import attribute_factor_portfolio

portfolio_weights = pd.Series(
    {"asset-a": 0.45, "asset-b": 0.35, "asset-c": 0.20}
)
benchmark_weights = pd.Series(
    {"asset-a": 1 / 3, "asset-b": 1 / 3, "asset-c": 1 / 3}
)

absolute_attribution = attribute_factor_portfolio(forecast, portfolio_weights)
active_attribution = attribute_factor_portfolio(
    forecast,
    portfolio_weights,
    benchmark_weights=benchmark_weights,
)

print(absolute_attribution.factor_exposures)
print(active_attribution.expected_return_contributions)
print(active_attribution.variance_contributions)
```

Active attribution uses portfolio minus benchmark weights. Expected-return contributions include
alpha and every factor. Variance contributions include every factor and an idiosyncratic term.

## Carry model output into a strategy

Keep the model's `as_of`, factor definitions, estimation window, and input identities with the
target artifact. In an external strategy, update the model only from completed history visible in
`StrategyView`. In a precomputed-target workflow, place the dated target panel directly in a
scenario. Either route should use the same portfolio constraints and attribution checks that were
reviewed in research.
