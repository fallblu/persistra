# Compare Runs

`compare(...)` builds side-by-side metrics for in-memory `Result` objects or saved run
directories.

```python no-run
from persistra.experiments import compare

comparison = compare([momentum_result, equal_weight_result])
print(comparison.metrics)
```

## Saved Runs

```python no-run
comparison = compare([
    "workspace/runs/momentum_001",
    "workspace/runs/equal_weight_001",
])
```

Saved paths are loaded with `persistra.core.artifacts.load`.

## Visual Comparisons

Comparison results provide Plotly overlays:

```python no-run
comparison.overlay_equity().show()
comparison.drawdown_overlay().show()
comparison.metric_bars("sharpe").show()
```

Use comparisons after a train/test split or walk-forward run. In-sample leaderboard
results are useful for selection, but out-of-sample comparisons are what should drive
research conclusions.
