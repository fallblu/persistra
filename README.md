# Persistra

Persistra is a typed Python library for researching systematic strategies and replaying their
decisions with [Trading Engine](https://github.com/fallblu/trading-engine). It keeps data,
point-in-time features, factor regressions, portfolio optimization, strategy lifecycle, and
execution analysis connected without hiding the assumptions between them.

Use Persistra to:

- acquire or synthesize normalized market and economic data;
- build leakage-aware features, labels, and factor regression models;
- convert factor forecasts into constrained portfolio targets;
- implement strategies with warm-up, bounded history, security filtering, and schedules;
- compose alpha models, portfolio constructors, overlays, and rebalance guards;
- build deterministic Trading Engine scenarios and inspect their audit journals.

This offline example fits a factor model and produces constrained portfolio weights:

```python
import pandas as pd

from persistra.portfolio import (
    MeanVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    WeightBounds,
    optimize_portfolio,
)
from persistra.research import (
    build_factor_portfolio_forecast,
    build_factor_risk_model,
    fit_time_series_factor_model,
)

dates = pd.date_range("2025-01-01", periods=40, freq="D")
factors = pd.DataFrame(
    {
        "value": [((position % 7) - 3) / 100 for position in range(40)],
        "momentum": [((position % 5) - 2) / 120 for position in range(40)],
    },
    index=dates,
)
assets = pd.DataFrame(
    {
        "asset-a": 0.001 + 0.8 * factors["value"] + 0.2 * factors["momentum"],
        "asset-b": -0.0005 - 0.3 * factors["value"] + 1.1 * factors["momentum"],
    },
    index=dates,
)

regression = fit_time_series_factor_model(assets, factors, covariance="hc3")
risk = build_factor_risk_model(
    regression.coefficients[["value", "momentum"]],
    factors,
    regression.residuals.fillna(0.0001),
    shrinkage=0.2,
)
forecast = build_factor_portfolio_forecast(risk, factors.mean())
result = optimize_portfolio(
    PortfolioProblem(
        covariance=forecast.asset_covariance,
        expected_returns=forecast.expected_returns,
        objective=MeanVarianceObjective(risk_aversion=5.0),
        constraints=(WeightBounds(0.0, 0.8), NetExposureConstraint(1.0, 1.0)),
    )
)

print(result.weights)
```

Start with the [installation guide](https://fallblu.github.io/persistra/getting-started/installation/)
and [strategy quickstart](https://fallblu.github.io/persistra/getting-started/quickstart/). Then use
the [strategy development guide](https://fallblu.github.io/persistra/guides/strategy-development/),
the categorized [examples](https://fallblu.github.io/persistra/examples/), and the
[API reference](https://fallblu.github.io/persistra/reference/).

Persistra targets Python 3.12 or later on Linux. It is an offline research and replay library,
not a broker connection or live-trading system.
