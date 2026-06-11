"""Bayesian search via optuna. Available only with the [bayes] extra."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .grid import resolve_sweep_dir
from .runner import _run_one
from .sweep_result import SweepResult, result_metrics

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from persistra.core.engine import Engine
    from persistra.strategy.base import Strategy


_INSTALL_HINT = (
    "bayes_search requires optuna. Install the bayes extra: "
    "`pip install 'persistra[bayes]'` or `pip install optuna`."
)


def _require_optuna() -> Any:
    try:
        import optuna
    except ImportError as exc:  # pragma: no cover - import-error path
        raise ImportError(_INSTALL_HINT) from exc
    return optuna


def bayes_search(
    strategy_factory: Callable[[dict[str, Any]], Strategy],
    search_space: Callable[[Any], dict[str, Any]],
    n_trials: int,
    *,
    engine_builder: Callable[..., Engine],
    metric: str = "sharpe",
    direction: str = "maximize",
    seed: int | None = None,
    output_dir: str | Path | None = None,
) -> SweepResult:
    """Run an optuna study and return its trials packaged as a SweepResult.

    `search_space` takes an optuna.Trial and returns a parameter dict (using
    trial.suggest_*). `metric` must be a result metric key. `seed` seeds the
    TPE sampler only; the engine is deterministic.
    """
    optuna = _require_optuna()

    sweep_dir = resolve_sweep_dir(output_dir)
    params_collected: list[dict[str, Any]] = []
    results_collected: list[Any] = []

    def _objective(trial: Any) -> float:
        params = search_space(trial)
        result = _run_one(params, strategy_factory, engine_builder, sweep_dir)
        params_collected.append(params)
        results_collected.append(result)
        m = result_metrics(result)
        if metric not in m:
            raise KeyError(f"metric {metric!r} not found in result metrics ({sorted(m)})")
        return float(m[metric])

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction=direction, sampler=sampler)
    study.optimize(_objective, n_trials=n_trials)

    sweep = SweepResult(params=params_collected, results=results_collected)
    if sweep_dir is not None:
        sweep.summary_dataframe().to_parquet(sweep_dir / "summary.parquet")
    return sweep
