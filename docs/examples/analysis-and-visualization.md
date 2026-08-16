# Analysis and visualization examples

Persistra plotting functions consume prepared results and return caller-owned Matplotlib axes.
They do not fetch data, calculate hidden signals, change global style, or call `show`.

## Inspect factor-regression diagnostics

Regression result frames are already suitable for ordinary pandas reporting:

```python
diagnostics = static_model.diagnostics[
    ["observations", "rank", "r_squared", "condition_number", "status"]
]
significant = static_model.p_values.where(static_model.p_values < 0.05)

print(diagnostics.sort_values("r_squared"))
print(significant.dropna(how="all"))
```

Do not select coefficients only by magnitude. Review sample counts, rank, condition number,
covariance estimator, and the model's `as_of` boundary.

## Plot a signal distribution

```python
import matplotlib.pyplot as plt

from persistra.viz import plot_signal_distribution

figure, axis = plt.subplots(figsize=(8, 4))
plot_signal_distribution(raw_signal, ax=axis)
axis.set_title("Cross-sectional signal distribution")
figure.tight_layout()
```

The returned axis is the same object passed by the caller. Add labels, annotations, and output
formatting with Matplotlib.

## Plot ranks and information coefficients

```python
from persistra.viz import (
    plot_information_coefficients,
    plot_signal_ranks,
)

figure, axes = plt.subplots(2, 1, figsize=(10, 7))
plot_signal_ranks(ranked_signal, ax=axes[0])
plot_information_coefficients(ic_result, ax=axes[1])
axes[0].set_title("Signal ranks")
axes[1].set_title("Information coefficients")
figure.tight_layout()
```

Calculate `ic_result` with `information_coefficients` first so horizon, minimum sample, and
grouping policy remain visible.

## Plot quantile diagnostics

```python
from persistra.viz import (
    plot_cumulative_quantile_returns,
    plot_quantile_capacity,
    plot_quantile_counts,
    plot_quantile_spread,
    plot_quantile_turnover,
)

figure, axes = plt.subplots(3, 2, figsize=(12, 10))
plot_cumulative_quantile_returns(quantile_result, ax=axes[0, 0])
plot_quantile_spread(quantile_result, ax=axes[0, 1])
plot_quantile_counts(quantile_result, ax=axes[1, 0])
plot_quantile_turnover(quantile_result, ax=axes[1, 1])
plot_quantile_capacity(quantile_result, ax=axes[2, 0])
axes[2, 1].axis("off")
figure.tight_layout()
```

Quantile portfolios evaluate signal ordering without an execution model. Their turnover and
volume fields are diagnostics, not estimates of actual fill capacity.

## Inspect optimization results

Before plotting, read the constraint and objective tables:

```python
print(optimization_result.weights)
print(optimization_result.objective_breakdown)
print(optimization_result.constraint_diagnostics)
print(optimization_result.covariance_diagnostics)
print(optimization_result.solver_statistics)
```

A solver success flag alone is insufficient. Persistra validates the returned weights and
reports realized exposures and residuals against the original problem.

## Plot portfolio targets and exposures

```python
from persistra.viz import (
    plot_portfolio_exposures,
    plot_portfolio_turnover,
    plot_portfolio_weights,
)

figure, axes = plt.subplots(3, 1, figsize=(11, 9))
plot_portfolio_weights(portfolio_result, ax=axes[0])
plot_portfolio_exposures(portfolio_result, ax=axes[1])
plot_portfolio_turnover(portfolio_result, ax=axes[2])
figure.tight_layout()
```

Both simple `PortfolioConstructionResult` and rolling optimization paths expose dated weights.
Use tabular optimization diagnostics for individual solver steps.

## Plot vectorized backtest performance

```python
from persistra.viz import (
    plot_backtest_drawdowns,
    plot_backtest_performance,
    plot_portfolio_turnover,
    plot_transaction_costs,
)

figure, axes = plt.subplots(4, 1, figsize=(11, 12))
plot_backtest_performance(backtest, ax=axes[0])
plot_backtest_drawdowns(backtest, ax=axes[1])
plot_portfolio_turnover(backtest, ax=axes[2])
plot_transaction_costs(backtest, ax=axes[3])
figure.tight_layout()
```

Inspect `rebalance_log`, `trades`, realized and ending weights, cash, return attribution, cost
attribution, and benchmark comparison alongside the chart.

## Plot portfolio attribution

```python
from persistra.viz import plot_cost_attribution, plot_return_attribution

figure, axes = plt.subplots(2, 1, figsize=(10, 7))
plot_return_attribution(backtest, ax=axes[0])
plot_cost_attribution(backtest, ax=axes[1])
figure.tight_layout()
```

Asset, cash, and cost components reconcile to the reported portfolio return under the selected
backtest policy.

## Plot Trading Engine execution results

```python
from persistra.viz import (
    plot_execution_diagnostics,
    plot_execution_performance,
)

performance_axis = plot_execution_performance(execution_analysis)
performance_axis.set_title("Trading Engine performance")

diagnostic_axes = plot_execution_diagnostics(execution_analysis)
diagnostic_axes[0].set_title("Order and fill diagnostics")
```

Execution performance uses journal valuation events, which may be irregular or repeated at one
timestamp. Annualized statistics remain undefined unless the analysis policy supplies a justified
`periods_per_year`.

## Compare vectorized and engine outcomes

```python
print(execution_comparison.terminal_summary)
print(execution_comparison.pnl_bridge)
print(execution_comparison.caveat)
```

The bridge separates observed decision-to-open movement, eligible-open fill effects, and fees.
The balancing residual can include timing, partial fills, target persistence, cash, borrow,
margin, or other model differences and is not automatically called slippage.

## Save deterministic figures

```python
from pathlib import Path

output = Path("artifacts") / "strategy-diagnostics.png"
output.parent.mkdir(parents=True, exist_ok=True)
figure.savefig(output, dpi=150, bbox_inches="tight")
plt.close(figure)
```

Record the underlying result artifact and plotting configuration with a report. A figure is a
view of the result, not a replacement for the model, scenario, journal, or diagnostics table.
