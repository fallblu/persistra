# Parameter Sweeps

Use `grid_search` when you want to evaluate every combination in a parameter grid.

```python no-run
from persistra import CrossSectionalMomentum, Engine, ParquetMarketData, Portfolio
from persistra.experiments import grid_search


def strategy_factory(params):
    return CrossSectionalMomentum(
        lookback=int(params["lookback"]),
        skip=int(params["skip"]),
    )


def engine_builder(strategy, *, start="2021-01-04", end="2023-12-29"):
    return Engine(
        data=ParquetMarketData("examples/sample_data"),
        strategy=strategy,
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start=start,
        end=end,
    )


sweep = grid_search(
    strategy_factory,
    {"lookback": [63, 126, 252], "skip": [0, 10, 21]},
    engine_builder=engine_builder,
)

best_params, best_result = sweep.best("sharpe")
summary = sweep.summary_dataframe()
```

## Parallel Runs

Set `n_jobs` above `1` to use joblib parallel execution. The strategy factory and engine
builder must be picklable, so prefer top-level named functions over lambdas.

## Persist Sweep Artifacts

```python no-run
sweep = grid_search(
    strategy_factory,
    param_grid,
    engine_builder=engine_builder,
    output_dir="workspace/sweeps",
)
```

When `output_dir` is provided, persistra creates a timestamped sweep directory and writes
run artifacts plus a sweep summary.

## Other Sweep Types

- `random_search`: sample parameter distributions.
- `bayes_search`: Bayesian optimization through the optional `bayes` extra.
