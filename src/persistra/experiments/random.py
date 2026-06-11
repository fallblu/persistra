"""Random search over scipy.stats-style distributions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import numpy as np
from joblib import Parallel, delayed

from .grid import resolve_sweep_dir
from .runner import _run_one
from .sweep_result import SweepResult

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from persistra.core.engine import Engine
    from persistra.core.result import Result
    from persistra.strategy.base import Strategy


def _sample_one(distributions: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    """Draw one parameter dict from `distributions`.

    Each value may be: a scipy.stats-style distribution with ``.rvs(random_state=)``,
    a list/tuple of categorical choices (sampled uniformly), or a fixed scalar.
    """
    params: dict[str, Any] = {}
    for key in sorted(distributions.keys()):
        spec = distributions[key]
        if hasattr(spec, "rvs"):
            params[key] = spec.rvs(random_state=rng)
        elif isinstance(spec, (list, tuple)):
            seq = cast("list[Any] | tuple[Any, ...]", spec)
            params[key] = seq[int(rng.integers(0, len(seq)))]
        else:
            params[key] = spec
    return params


def random_search(
    strategy_factory: Callable[[dict[str, Any]], Strategy],
    param_distributions: dict[str, Any],
    n_iter: int,
    *,
    engine_builder: Callable[..., Engine],
    n_jobs: int = 1,
    seed: int | None = None,
    output_dir: str | Path | None = None,
) -> SweepResult:
    """Sample `n_iter` random parameter sets and run a backtest for each.

    `seed` seeds the parameter sampler only; the engine itself is deterministic.
    """
    rng = np.random.default_rng(seed)
    param_sets = [_sample_one(param_distributions, rng) for _ in range(n_iter)]
    sweep_dir = resolve_sweep_dir(output_dir)

    if n_jobs == 1:
        results: list[Result] = [
            _run_one(p, strategy_factory, engine_builder, sweep_dir) for p in param_sets
        ]
    else:
        results = cast(
            "list[Result]",
            list(
                Parallel(n_jobs=n_jobs, backend="loky")(
                    delayed(_run_one)(p, strategy_factory, engine_builder, sweep_dir)
                    for p in param_sets
                )
            ),
        )

    sweep = SweepResult(params=param_sets, results=results)
    if sweep_dir is not None:
        sweep.summary_dataframe().to_parquet(sweep_dir / "summary.parquet")
    return sweep
