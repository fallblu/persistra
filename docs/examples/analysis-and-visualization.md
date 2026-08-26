# Analysis and visualization examples

Persistra plotting functions consume prepared results and return caller-owned Plotly figures.
They do not fetch data, calculate hidden signals, change global Plotly configuration, or call
`show`.

## Inspect factor-regression diagnostics

Regression result frames are suitable for ordinary pandas reporting:

```python
diagnostics = static_model.diagnostics[
    ["observations", "rank", "r_squared", "condition_number", "status"]
]
significant = static_model.p_values.where(static_model.p_values < 0.05)

print(diagnostics.sort_values("r_squared"))
print(significant.dropna(how="all"))
```

Review sample counts, rank, condition number, covariance estimator, and the model's `as_of`
boundary. Do not select coefficients only by magnitude.

## Plot a signal distribution

```python
from persistra.viz import plot_signal_distribution

distribution = plot_signal_distribution(raw_signal, date=plot_date)
distribution.update_layout(title="Cross-sectional signal distribution", width=800, height=400)
```

The returned figure owns its traces and layout. Add labels, annotations, hover templates, and
output formatting with Plotly figure methods.

## Plot ranks and information coefficients

```python
from persistra.viz import plot_information_coefficients, plot_signal_ranks

ranks_figure = plot_signal_ranks(ranked_signal, date=plot_date)
ranks_figure.update_layout(title="Signal ranks")

ic_figure = plot_information_coefficients(ic_result)
ic_figure.update_layout(title="Information coefficients")
```

Calculate `ic_result` first so horizon, minimum sample, and grouping policy remain visible.
Each helper returns a complete figure instead of accepting a caller-supplied subplot.

## Plot quantile diagnostics

```python
from persistra.viz import (
    plot_cumulative_quantile_returns,
    plot_quantile_capacity,
    plot_quantile_counts,
    plot_quantile_spread,
    plot_quantile_turnover,
)

quantile_figures = {
    "performance": plot_cumulative_quantile_returns(quantile_result),
    "spread": plot_quantile_spread(quantile_result),
    "counts": plot_quantile_counts(quantile_result),
    "turnover": plot_quantile_turnover(quantile_result),
    "capacity": plot_quantile_capacity(quantile_result),
}
```

Quantile portfolios evaluate signal ordering without an execution model. Their turnover and
volume fields are diagnostics, not estimates of actual fill capacity.

## Inspect optimization results

```python
print(optimization_result.weights)
print(optimization_result.objective_breakdown)
print(optimization_result.constraint_diagnostics)
print(optimization_result.covariance_diagnostics)
print(optimization_result.solver_statistics)
```

A solver success flag alone is insufficient. Persistra validates returned weights and reports
realized exposures and residuals against the original problem.

## Plot portfolio targets and exposures

```python
from persistra.viz import (
    plot_portfolio_exposures,
    plot_portfolio_turnover,
    plot_portfolio_weights,
)

weights_figure = plot_portfolio_weights(portfolio_result)
exposures_figure = plot_portfolio_exposures(portfolio_result)
turnover_figure = plot_portfolio_turnover(portfolio_result)
```

Both simple construction results and rolling optimization paths expose dated weights. Use
tabular optimization diagnostics for individual solver steps.

## Plot vectorized backtest performance

```python
from persistra.viz import (
    plot_backtest_drawdowns,
    plot_backtest_performance,
    plot_transaction_costs,
)

performance_figure = plot_backtest_performance(backtest)
drawdown_figure = plot_backtest_drawdowns(backtest)
cost_figure = plot_transaction_costs(backtest)
```

Inspect `rebalance_log`, trades, realized and ending weights, cash, attribution, and benchmark
comparison alongside the figures.

## Plot portfolio attribution

```python
from persistra.viz import plot_cost_attribution, plot_return_attribution

return_attribution = plot_return_attribution(backtest)
cost_attribution = plot_cost_attribution(backtest)
```

Asset, cash, and cost components reconcile to the reported portfolio return under the selected
backtest policy.

## Export interactive figures

```python
from pathlib import Path

output = Path("artifacts") / "strategy-diagnostics.html"
output.parent.mkdir(parents=True, exist_ok=True)
performance_figure.write_html(output, include_plotlyjs=True)
```

Use `write_image` only after separately installing Plotly's compatible Kaleido integration.
Record the underlying result artifact and plotting configuration with a report. A figure is a
view of the result, not a replacement for the model, scenario, journal, or diagnostics table.
