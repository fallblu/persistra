from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from persistra.metrics.perf import benchmark_free_summary

from .result import Result, _empty_diagnostics, _empty_orders


class IncompleteRunError(RuntimeError):
    """Raised when load() is pointed at a run directory missing summary.json."""


def save(result: Result, run_dir: str | Path) -> None:
    """Write a completed Result to a run directory.

    Writes the parquet artifacts and meta.json, then summary.json last.
    summary.json is the "run is complete" marker checked by load() and includes
    the benchmark-free numeric metrics for quick inspection.
    """

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    result.equity_curve.to_parquet(run_dir / "equity_curve.parquet")
    result.trades.to_parquet(run_dir / "trades.parquet")
    result.orders.to_parquet(run_dir / "orders.parquet")
    result.positions.to_parquet(run_dir / "positions.parquet")
    if not result.diagnostics.empty:
        result.diagnostics.to_parquet(run_dir / "diagnostics.parquet")
    clean_meta = {k: v for k, v in result.meta.items() if k != "run_dir"}
    with open(run_dir / "meta.json", "w") as f:
        json.dump(clean_meta, f, indent=2, default=str)

    eq = result.equity_curve
    date_range = [str(eq.index.min()), str(eq.index.max())] if not eq.empty else [None, None]
    summary: dict[str, Any] = {
        "metrics": benchmark_free_summary(eq["equity"]) if "equity" in eq else {},
        "meta": clean_meta,
        "date_range": date_range,
    }
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)


def load(run_dir: str | Path) -> Result:
    """Reload a past run from its directory.

    Raises IncompleteRunError if summary.json is missing (a partial write from
    a crashed or interrupted run).
    """
    p = Path(run_dir)
    if not (p / "summary.json").exists():
        raise IncompleteRunError(
            f"Run directory {p} is missing summary.json - the run did not "
            f"complete cleanly. Delete the directory or re-run."
        )
    equity_curve = pd.read_parquet(p / "equity_curve.parquet")
    trades = pd.read_parquet(p / "trades.parquet")
    orders_path = p / "orders.parquet"
    orders = pd.read_parquet(orders_path) if orders_path.exists() else _empty_orders()
    positions = pd.read_parquet(p / "positions.parquet")
    diag_path = p / "diagnostics.parquet"
    diagnostics = pd.read_parquet(diag_path) if diag_path.exists() else _empty_diagnostics()
    with open(p / "meta.json") as f:
        meta = json.load(f)
    meta["run_dir"] = str(p)
    return Result(
        equity_curve=equity_curve,
        trades=trades,
        positions=positions,
        orders=orders,
        diagnostics=diagnostics,
        meta=meta,
    )
