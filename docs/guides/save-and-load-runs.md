# Save and Load Runs

Pass `output_dir` to `Engine.run(...)` to persist a completed result.

```python no-run
result = engine.run(
    output_dir="workspace/runs",
    meta_extra={"lookback": 126, "skip": 21},
)
print(result.meta["run_dir"])
```

The engine writes a run directory containing:

- `equity_curve.parquet`
- `trades.parquet`
- `positions.parquet`
- `diagnostics.parquet` when diagnostics exist
- `meta.json`
- `summary.json`

`summary.json` is written last and marks the run as complete.

## Reload a Run

```python no-run
from persistra.core.artifacts import load

loaded = load(result.meta["run_dir"])
```

`load(...)` raises `IncompleteRunError` if `summary.json` is missing. That usually means
the process was interrupted while writing artifacts.

## Metadata

Persisted metadata can include:

- run id
- start and end dates
- strategy id
- parameter values
- data hash
- git information
- dependency versions

Use `meta_extra` for values you want to carry through comparisons and reports.
