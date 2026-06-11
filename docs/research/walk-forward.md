# Walk-Forward Validation

Use walk-forward validation when parameter selection must happen inside each training
window before evaluating the next out-of-sample window.

## Fixed-Parameter Walk-Forward

`walk_forward` runs the same parameters across chained train/test windows. Each fold runs
from `train_start` through `test_end`, then exposes only the test window for evaluation.

```python no-run
from persistra.experiments import walk_forward

wf = walk_forward(
    strategy_factory,
    engine_builder=engine_builder,
    params={"lookback": 126, "skip": 21},
    train_window=252,
    test_window=63,
    mode="rolling",
)

test_results = wf.test_results()
```

## Per-Fold Optimization

`walk_forward_grid_search` grid-searches each training window, selects the best parameter
set, then evaluates that selected configuration on the following test window.

```python no-run
from persistra.experiments import walk_forward_grid_search

wf_opt = walk_forward_grid_search(
    strategy_factory,
    {"lookback": [63, 126, 252], "skip": [0, 10, 21]},
    engine_builder=engine_builder,
    train_window=252,
    test_window=63,
    metric="sharpe",
)

selected = wf_opt.selected_params_dataframe()
oos_results = wf_opt.test_results()
```

## Modes

- `rolling`: training window advances with each fold.
- `expanding`: training starts at the first available session and grows over time.

Use rolling mode when you want fixed-length training history. Use expanding mode when
older data should remain eligible for parameter selection.
