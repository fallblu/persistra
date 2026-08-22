# Run Monte Carlo research

Use `persistra.monte_carlo` when a research question needs a distribution of paths and bounded
path-level outcomes. Keep data selection and calibration outside the experiment so those choices
remain visible.

## Choose and calibrate a model

For geometric Brownian motion, first construct a complete log-return sample and choose its
annualization explicitly:

```python
import pandas as pd

from persistra.monte_carlo import fit_geometric_brownian_motion

log_returns = pd.DataFrame(
    {
        "stock": [0.004, -0.002, 0.006, 0.001],
        "bond": [0.001, 0.002, -0.001, 0.001],
    },
    index=pd.date_range("2025-01-02", periods=4, freq="B"),
)
model = fit_geometric_brownian_motion(
    log_returns,
    initial_prices=pd.Series({"stock": 100.0, "bond": 100.0}),
    periods_per_year=252.0,
)
```

`MultivariateNormalReturns` accepts caller-supplied annual mean and covariance parameters and can
emit simple or log returns. Normal simple returns are unbounded and can fall below negative one;
choose the model and parameters accordingly before using level-based or portfolio calculations.

`MovingBlockBootstrap` jointly samples complete historical rows and preserves within-row
cross-asset dependence. Its time steps must all equal one because each generated row represents
one historical observation rather than a fraction of a year.

## Define the experiment

The output index, time-step sequence, and model variable names are exact ordered axes:

```python
from persistra.monte_carlo import (
    MaximumDrawdown,
    MonteCarloExperiment,
    TerminalReturn,
    ThresholdBreach,
)

future_index = pd.date_range("2025-02-03", periods=20, freq="B", name="date")
experiment = MonteCarloExperiment(
    model=model,
    output_index=future_index,
    time_steps=(1.0 / 252.0,) * len(future_index),
    path_count=1_000,
    root_seed=20250203,
    metrics=(
        TerminalReturn("stock", initial_level=100.0),
        MaximumDrawdown("stock"),
        ThresholdBreach("stock", threshold=90.0),
    ),
    retain_paths=False,
    convergence_checkpoints=(100, 250, 500),
)
```

The final path count is automatically included as a convergence checkpoint. The normal-approximate
confidence interval in `result.summary` estimates uncertainty in each metric mean; it is not a
prediction interval for an individual future outcome.

## Run serially or in threads

```python
from persistra.monte_carlo import MonteCarloExecution, run_experiment

result = run_experiment(
    experiment,
    MonteCarloExecution(backend="threaded", workers=4, batch_size=128),
)

print(result.summary)
print(result.convergence)
print(result.manifest)
```

Use serial execution for the simplest baseline. Threaded execution preserves exact path values
and row order but may or may not improve elapsed time. Changing workers or batch size does not
change experiment identity.

## Retain and inspect paths

Set `retain_paths=True` when later work needs full paths. `result.path_array(path_id)` and
`result.path_frame(path_id)` return defensive copies. A retained array has axes
`(path, time, variable)`.

`evaluate_paths(result, evaluator)` can apply a new bounded evaluator after generation. It rejects
results whose paths were not retained. For known evaluators, pass them directly to
`run_experiment(..., evaluator=...)` and leave retention disabled.

## Evaluate portfolio outcomes

`PortfolioBacktestEvaluator` interprets each path explicitly as returns or prices and runs the
existing vectorized portfolio backtester. Target columns must exactly equal the model variable
axis, and both paths and targets must use compatible `DatetimeIndex` values.

```python
from persistra.monte_carlo import PortfolioBacktestEvaluator

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
```

The evaluator returns terminal equity, terminal return, maximum drawdown, total turnover, and
total transaction cost. It retains none of the heavyweight per-path backtest objects. Portfolio
timing and missing/nontradeable policies remain explicit through optional `BacktestTiming` and
`BacktestPolicies` values. The default one-period execution lag also avoids holding a price path
on its initial, return-less observation.
