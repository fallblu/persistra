"""Walk-forward validation: chained train/test windows over the full date range."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

import pandas as pd
from joblib import Parallel, delayed

from .grid import grid_search, resolve_sweep_dir
from .runner import _run_one
from .sweep_result import WalkForwardOptimizationResult, WalkForwardResult

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from persistra.core.engine import Engine
    from persistra.core.result import Result
    from persistra.strategy.base import Strategy


def enumerate_folds(
    sessions: pd.DatetimeIndex,
    train_window: int,
    test_window: int,
    step: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Return list of (test_start, test_end) timestamps.

    Each test window contains exactly `test_window` sessions; successive windows
    advance by `step` sessions (non-overlapping when step >= test_window).
    """
    n = len(sessions)
    folds: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    test_start_idx = train_window
    while test_start_idx + test_window <= n:
        test_end_idx = test_start_idx + test_window - 1
        folds.append((pd.Timestamp(sessions[test_start_idx]), pd.Timestamp(sessions[test_end_idx])))
        test_start_idx += step
    return folds


def _fold_schedule(
    sessions: pd.DatetimeIndex,
    train_window: int,
    test_window: int,
    step: int,
    mode: Literal["rolling", "expanding"],
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    fold_windows = enumerate_folds(sessions, train_window, test_window, step)
    if not fold_windows:
        return []

    first_session = pd.Timestamp(sessions[0])
    out: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    test_start_idx = train_window
    for test_start, test_end in fold_windows:
        if mode == "rolling":
            train_start = pd.Timestamp(sessions[test_start_idx - train_window])
        else:
            train_start = first_session
        train_end = pd.Timestamp(sessions[test_start_idx - 1])
        out.append((train_start, train_end, pd.Timestamp(test_start), pd.Timestamp(test_end)))
        test_start_idx += step
    return out


def walk_forward(
    strategy_factory: Callable[[dict[str, Any]], Strategy],
    *,
    engine_builder: Callable[..., Engine],
    train_window: int,
    test_window: int,
    step: int | None = None,
    mode: Literal["rolling", "expanding"] = "rolling",
    n_jobs: int = 1,
    params: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> WalkForwardResult:
    """Run a chained train/test backtest across the engine's date range.

    Each fold runs the engine from ``train_start`` to ``test_end`` so the
    strategy can warm up on training data. Only the test window is considered
    out-of-sample; use ``WalkForwardResult.test_results()`` to extract it.

    ``train_window`` determines where the first test window begins (burn-in)
    and the width of each rolling training window.

    Mode semantics:
    - ``"rolling"``: train_start advances by ``step`` each fold; the training
      window always spans exactly ``train_window`` sessions.
    - ``"expanding"``: train_start is fixed at the first available session;
      the training window grows each fold.
    """
    if mode not in ("rolling", "expanding"):
        raise ValueError(f"mode must be 'rolling' or 'expanding', got {mode!r}")
    if step is None:
        step = test_window
    if step <= 0:
        raise ValueError("step must be positive")
    if train_window < 0 or test_window <= 0:
        raise ValueError("train_window must be >= 0 and test_window > 0")

    params = dict(params or {})

    probe_strategy = strategy_factory(params)
    probe_engine = engine_builder(probe_strategy)
    sessions = probe_engine.sessions()

    schedule = _fold_schedule(sessions, train_window, test_window, step, mode)
    if not schedule:
        return WalkForwardResult(folds=[])

    sweep_dir = resolve_sweep_dir(output_dir)

    # Each job runs [train_start, test_end] so the strategy sees the full training period.
    jobs = [
        (params, strategy_factory, engine_builder, sweep_dir, {"start": tr_start, "end": te})
        for tr_start, _tr_end, _ts, te in schedule
    ]

    if n_jobs == 1:
        results: list[Result] = [_run_one(*job) for job in jobs]
    else:
        results = cast(
            "list[Result]",
            list(Parallel(n_jobs=n_jobs, backend="loky")(delayed(_run_one)(*job) for job in jobs)),
        )

    folds: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, Result]] = [
        (tr_start, ts, te, result)
        for (tr_start, _tr_end, ts, te), result in zip(schedule, results, strict=True)
    ]
    return WalkForwardResult(folds=folds)


def walk_forward_grid_search(
    strategy_factory: Callable[[dict[str, Any]], Strategy],
    param_grid: dict[str, list[Any]],
    *,
    engine_builder: Callable[..., Engine],
    train_window: int,
    test_window: int,
    step: int | None = None,
    mode: Literal["rolling", "expanding"] = "rolling",
    metric: str = "sharpe",
    maximize: bool = True,
    n_jobs: int = 1,
    output_dir: str | Path | None = None,
) -> WalkForwardOptimizationResult:
    """Optimize parameters on each train window and evaluate the next test window.

    For every fold, this helper:

    1. grid-searches ``param_grid`` on ``[train_start, train_end]``;
    2. selects ``SweepResult.best(metric, maximize=maximize)``;
    3. reruns the selected parameters on ``[train_start, test_end]`` so the
       strategy can warm up on training history;
    4. stores the full selected run, while
       ``WalkForwardOptimizationResult.test_results()`` exposes only the
       out-of-sample test windows.
    """
    if mode not in ("rolling", "expanding"):
        raise ValueError(f"mode must be 'rolling' or 'expanding', got {mode!r}")
    if step is None:
        step = test_window
    if step <= 0:
        raise ValueError("step must be positive")
    if train_window <= 0 or test_window <= 0:
        raise ValueError("train_window and test_window must be positive")

    probe_strategy = strategy_factory({})
    probe_engine = engine_builder(probe_strategy)
    sessions = probe_engine.sessions()
    schedule = _fold_schedule(sessions, train_window, test_window, step, mode)
    if not schedule:
        return WalkForwardOptimizationResult(folds=[], metric=metric, maximize=maximize)

    sweep_dir = resolve_sweep_dir(output_dir)
    folds: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, dict[str, Any], Any, Result]] = []
    for i, (train_start, train_end, test_start, test_end) in enumerate(schedule):
        fold_dir = sweep_dir / f"fold_{i:03d}" if sweep_dir is not None else None

        train_sweep = grid_search(
            strategy_factory,
            param_grid,
            engine_builder=engine_builder,
            n_jobs=n_jobs,
            output_dir=fold_dir,
            builder_kwargs={"start": train_start, "end": train_end},
        )
        best_params, _best_train_result = train_sweep.best(metric=metric, maximize=maximize)
        selected_result = _run_one(
            best_params,
            strategy_factory,
            engine_builder,
            fold_dir,
            {"start": train_start, "end": test_end},
        )
        selected_result.meta.update(
            {
                "selected_metric": metric,
                "selected_maximize": maximize,
                "selected_params": dict(best_params),
                "train_start": str(train_start),
                "train_end": str(train_end),
                "test_start": str(test_start),
                "test_end": str(test_end),
            }
        )
        folds.append(
            (
                train_start,
                test_start,
                test_end,
                dict(best_params),
                train_sweep,
                selected_result,
            )
        )

    result = WalkForwardOptimizationResult(folds=folds, metric=metric, maximize=maximize)
    if sweep_dir is not None:
        result.selected_params_dataframe().to_parquet(sweep_dir / "selected_params.parquet")
    return result
