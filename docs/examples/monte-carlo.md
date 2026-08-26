# Monte Carlo example

This offline example fits a price-path model to a small caller-owned sample, generates stable
paths, inspects convergence, and computes portfolio outcomes without retaining per-path backtests.

## Fit an explicit model

```python
import pandas as pd

from persistra.monte_carlo import (
    MaximumDrawdown,
    MonteCarloExecution,
    MonteCarloExperiment,
    PortfolioBacktestEvaluator,
    TerminalReturn,
    ThresholdBreach,
    fit_geometric_brownian_motion,
    run_experiment,
)

historical_log_returns = pd.DataFrame(
    {
        "stock": [0.004, -0.002, 0.006, 0.001, -0.003, 0.005],
        "bond": [0.001, 0.002, -0.001, 0.001, 0.000, 0.002],
    },
    index=pd.date_range("2025-01-02", periods=6, freq="B"),
)
initial_prices = pd.Series({"stock": 100.0, "bond": 100.0})
model = fit_geometric_brownian_motion(
    historical_log_returns,
    initial_prices=initial_prices,
    periods_per_year=252.0,
)
```

## Generate reproducible paths

```python
future_index = pd.date_range("2025-02-03", periods=12, freq="B", name="date")
experiment = MonteCarloExperiment(
    model=model,
    output_index=future_index,
    time_steps=(1.0 / 252.0,) * len(future_index),
    path_count=32,
    root_seed=50,
    metrics=(
        TerminalReturn("stock", initial_level=100.0),
        MaximumDrawdown("stock"),
        ThresholdBreach("stock", threshold=95.0),
    ),
    retain_paths=True,
    convergence_checkpoints=(8, 16),
)
result = run_experiment(
    experiment,
    MonteCarloExecution(backend="threaded", workers=2, batch_size=7),
)

assert result.paths is not None
assert result.paths.shape == (32, 12, 2)
assert result.convergence.index.get_level_values("checkpoint").unique().tolist() == [8, 16, 32]
first_path = result.path_frame(0)
assert first_path.index.equals(future_index)
assert first_path.columns.tolist() == ["stock", "bond"]
```

## Evaluate portfolio outcomes

```python
targets = pd.DataFrame(
    [[0.6, 0.4]],
    index=pd.DatetimeIndex([future_index[0]], name="date"),
    columns=["stock", "bond"],
)
evaluator = PortfolioBacktestEvaluator(
    targets,
    transaction_cost_bps=pd.Series({"stock": 2.0, "bond": 1.0}),
    path_kind="prices",
)
portfolio_result = run_experiment(
    MonteCarloExperiment(
        model=model,
        output_index=future_index,
        time_steps=(1.0 / 252.0,) * len(future_index),
        path_count=32,
        root_seed=50,
        retain_paths=False,
    ),
    MonteCarloExecution(batch_size=5),
    evaluator=evaluator,
)

assert portfolio_result.paths is None
assert portfolio_result.metrics.columns.tolist() == list(evaluator.metric_names)
assert portfolio_result.summary.loc["portfolio_terminal_equity", "count"] == 32
```

The second run uses the same seed, axes, and model, so it evaluates the same 32 paths regardless
of its different batch size. Only bounded metric tables, summary statistics, convergence, and
provenance remain in memory.
