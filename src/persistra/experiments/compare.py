"""Multi-run comparison: build a side-by-side metric table."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from persistra.core.result import Result

from .sweep_result import (
    BENCHMARK_FREE_METRICS,
    ComparisonResult,
    result_metrics,
)

if TYPE_CHECKING:
    from pathlib import Path


def _resolve_run(run: Result | str | Path) -> Result:
    from persistra.core.artifacts import load

    if isinstance(run, Result):
        return run
    return load(run)


def _run_label(result: Result, fallback_index: int) -> str:
    run_id = result.meta.get("run_id")
    if isinstance(run_id, str) and run_id:
        return run_id
    return f"run_{fallback_index}"


def compare(
    runs: list[Result | str | Path],
    metrics: list[str] | None = None,
) -> ComparisonResult:
    """Build a side-by-side comparison of two or more runs.

    `runs` may be in-memory Result objects or paths to run directories produced
    by Engine.run(output_dir=...) (loaded via core.artifacts.load). `metrics`
    defaults to the nine benchmark-free result metrics.
    """
    if not runs:
        raise ValueError("compare() requires at least one run")

    resolved: list[Result] = [_resolve_run(r) for r in runs]
    run_ids: list[str] = []
    seen: dict[str, int] = {}
    for i, result in enumerate(resolved):
        label = _run_label(result, i)
        if label in seen:
            seen[label] += 1
            label = f"{label}#{seen[label]}"
        else:
            seen[label] = 0
        run_ids.append(label)

    keys = tuple(metrics) if metrics else BENCHMARK_FREE_METRICS

    rows: dict[str, dict[str, float]] = {}
    for run_id, result in zip(run_ids, resolved, strict=True):
        m = result_metrics(result)
        rows[run_id] = {k: float(m.get(k, float("nan"))) for k in keys}

    metrics_df = pd.DataFrame.from_dict(rows, orient="index")
    metrics_df.index.name = "run_id"

    return ComparisonResult(metrics=metrics_df, _results=resolved, _run_ids=run_ids)
