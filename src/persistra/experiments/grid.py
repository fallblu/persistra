"""Exhaustive grid search over a parameter grid."""

from __future__ import annotations

import datetime as _dt
import itertools
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from joblib import Parallel, delayed

from .runner import _run_one
from .sweep_result import SweepResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from persistra.core.engine import Engine
    from persistra.core.result import Result
    from persistra.strategy.base import Strategy


def enumerate_grid(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Cartesian product of param_grid with deterministic (sorted) key ordering."""
    if not param_grid:
        return [{}]
    keys = sorted(param_grid.keys())
    values = [list(param_grid[k]) for k in keys]
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*values)]


def resolve_sweep_dir(output_dir: str | Path | None) -> Path | None:
    """Create and return a timestamped sweep sub-directory, or None if no output is wanted.

    When ``output_dir`` is provided a subdirectory named
    ``sweep_<UTC-timestamp>-<uuid>`` is created inside it (parents created as
    needed).
    When ``output_dir`` is ``None`` nothing is written and ``None`` is returned.

    Args:
        output_dir: Parent directory under which the sweep subdirectory is
            created, or ``None`` to skip all file output.

    Returns:
        A ``Path`` to the newly created sweep directory, or ``None`` if
        ``output_dir`` was ``None``.
    """
    if output_dir is None:
        return None
    parent = Path(output_dir)
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        stamp = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H-%M-%S-%f")
        suffix = uuid.uuid4().hex[:6]
        sweep_dir = parent / f"sweep_{stamp}-{suffix}"
        try:
            sweep_dir.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return sweep_dir
    raise FileExistsError(f"could not create a unique sweep directory under {parent}")


def grid_search(
    strategy_factory: Callable[[dict[str, Any]], Strategy],
    param_grid: dict[str, list[Any]],
    *,
    engine_builder: Callable[..., Engine],
    n_jobs: int = 1,
    output_dir: str | Path | None = None,
    builder_kwargs: dict[str, Any] | None = None,
) -> SweepResult:
    """Run a backtest for every cell of param_grid and collect results.

    strategy_factory and engine_builder must be picklable when n_jobs > 1
    (joblib loky backend) — use named functions or functools.partial, not
    lambdas. The engine is deterministic, so there is no seed parameter.
    """
    param_sets = enumerate_grid(param_grid)
    sweep_dir = resolve_sweep_dir(output_dir)

    if n_jobs == 1:
        results: list[Result] = [
            _run_one(p, strategy_factory, engine_builder, sweep_dir, builder_kwargs)
            for p in param_sets
        ]
    else:
        results = cast(
            "list[Result]",
            list(
                Parallel(n_jobs=n_jobs, backend="loky")(
                    delayed(_run_one)(
                        p,
                        strategy_factory,
                        engine_builder,
                        sweep_dir,
                        builder_kwargs,
                    )
                    for p in param_sets
                )
            ),
        )

    sweep = SweepResult(params=param_sets, results=results)
    if sweep_dir is not None:
        sweep.summary_dataframe().to_parquet(sweep_dir / "summary.parquet")
    return sweep
