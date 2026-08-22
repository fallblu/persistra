"""Deterministic batched execution for Monte Carlo experiments."""

from __future__ import annotations

import platform
from concurrent.futures import ThreadPoolExecutor
from math import ceil, sqrt
from statistics import NormalDist
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd

from persistra._portable import freeze_portable_mapping, thaw_portable_mapping
from persistra.monte_carlo.contracts import (
    MonteCarloExecution,
    MonteCarloExperiment,
    MonteCarloResult,
    PathEvaluationResult,
    PathEvaluator,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import NDArray


def run_experiment(
    experiment: MonteCarloExperiment,
    execution: MonteCarloExecution | None = None,
    *,
    evaluator: PathEvaluator | None = None,
) -> MonteCarloResult:
    """Run stable per-path random streams in bounded serial or threaded batches."""
    controls = execution or MonteCarloExecution()
    evaluator_names: tuple[str, ...] = ()
    if evaluator is not None:
        _evaluator_identity(evaluator)
        evaluator_names = tuple(evaluator.metric_names)
    metric_names = tuple(metric.name for metric in experiment.metrics)
    all_names = (*metric_names, *evaluator_names)
    if len(set(all_names)) != len(all_names):
        raise ValueError("path metric and evaluator names must be unique")
    path_shape = (
        experiment.path_count,
        len(experiment.output_index),
        len(experiment.model.variable_names),
    )
    retained = np.empty(path_shape, dtype=float) if experiment.retain_paths else None
    rows: list[dict[str, float]] = []
    executor = (
        ThreadPoolExecutor(max_workers=controls.workers)
        if controls.backend == "threaded"
        else None
    )

    def generate_one(path_id: int) -> tuple[NDArray[np.float64], dict[str, float]]:
        return _generate_path(experiment, path_id, evaluator)

    try:
        for start in range(0, experiment.path_count, controls.batch_size):
            path_ids = range(start, min(start + controls.batch_size, experiment.path_count))
            if executor is None:
                batch = [generate_one(path_id) for path_id in path_ids]
            else:
                batch = list(executor.map(generate_one, path_ids))
            for path_id, (path, outcomes) in zip(path_ids, batch, strict=True):
                if retained is not None:
                    retained[path_id] = path
                rows.append(outcomes)
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
    metrics = pd.DataFrame(rows, columns=list(all_names), dtype=float)
    metrics.index = pd.RangeIndex(experiment.path_count, name="path")
    summary = _metric_summary(metrics, experiment.confidence_level)
    convergence = _convergence(metrics, experiment.convergence_checkpoints)
    return MonteCarloResult(
        paths=retained,
        output_index=experiment.output_index,
        variable_names=experiment.model.variable_names,
        metrics=metrics,
        summary=summary,
        convergence=convergence,
        manifest=_manifest(experiment, evaluator),
        execution_diagnostics={
            "backend": controls.backend,
            "workers": controls.workers,
            "batch_size": controls.batch_size,
            "batch_count": ceil(experiment.path_count / controls.batch_size),
            "retained_paths": experiment.retain_paths,
        },
    )


def evaluate_paths(
    result: MonteCarloResult,
    evaluator: PathEvaluator,
) -> PathEvaluationResult:
    """Evaluate every retained path without retaining heavyweight evaluator results."""
    _evaluator_identity(evaluator)
    if result.paths is None:
        raise ValueError("paths were not retained")
    rows: list[dict[str, float]] = []
    for path in result.paths:
        evaluated = evaluator.evaluate(
            path.copy(),
            result.output_index.copy(deep=True),
            result.variable_names,
        )
        if set(evaluated) != set(evaluator.metric_names):
            raise ValueError("evaluator outcomes differ from metric_names")
        rows.append(
            {
                name: _finite_outcome(evaluated[name], name=name)
                for name in evaluator.metric_names
            }
        )
    metrics = pd.DataFrame(rows, columns=list(evaluator.metric_names), dtype=float)
    metrics.index = pd.RangeIndex(len(metrics), name="path")
    confidence_level = cast("float", result.manifest["confidence_level"])
    return PathEvaluationResult(
        metrics=metrics,
        summary=_metric_summary(metrics, confidence_level),
        evaluator_name=evaluator.name,
        evaluator_version=evaluator.version,
        evaluator_parameters=evaluator.parameters,
    )


def _generate_path(
    experiment: MonteCarloExperiment,
    path_id: int,
    evaluator: PathEvaluator | None,
) -> tuple[NDArray[np.float64], dict[str, float]]:
    seed = np.random.SeedSequence(experiment.root_seed, spawn_key=(path_id,))
    generator = np.random.default_rng(seed)
    time_steps = np.asarray(experiment.time_steps, dtype=float)
    raw = experiment.model.generate(generator, time_steps.copy())
    path = np.asarray(raw, dtype=float)
    expected = (len(experiment.output_index), len(experiment.model.variable_names))
    if path.shape != expected:
        raise ValueError(f"model output shape must be {expected}")
    if not np.isfinite(path).all():
        raise ValueError("model output must be finite")
    outcomes: dict[str, float] = {}
    for metric in experiment.metrics:
        outcomes[metric.name] = _finite_outcome(
            metric.evaluate(
                path.copy(),
                experiment.output_index.copy(deep=True),
                experiment.model.variable_names,
            ),
            name=metric.name,
        )
    if evaluator is not None:
        evaluated = evaluator.evaluate(
            path.copy(),
            experiment.output_index.copy(deep=True),
            experiment.model.variable_names,
        )
        if set(evaluated) != set(evaluator.metric_names):
            raise ValueError("evaluator outcomes differ from metric_names")
        outcomes.update(
            {
                name: _finite_outcome(evaluated[name], name=name)
                for name in evaluator.metric_names
            }
        )
    return path, outcomes


def _finite_outcome(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not np.isscalar(value):
        raise TypeError(f"path outcome {name!r} must be a scalar")
    result = float(cast("float", value))
    if not np.isfinite(result):
        raise ValueError(f"path outcome {name!r} must be finite")
    return result


def _metric_summary(metrics: pd.DataFrame, confidence_level: float) -> pd.DataFrame:
    columns = [
        "count",
        "mean",
        "standard_deviation",
        "minimum",
        "median",
        "maximum",
        "confidence_lower",
        "confidence_upper",
    ]
    if metrics.shape[1] == 0:
        return pd.DataFrame(columns=columns, index=pd.Index([], name="metric"))
    critical = NormalDist().inv_cdf((1.0 + confidence_level) / 2.0)
    rows: list[dict[str, float | int | str]] = []
    for name in metrics.columns:
        values = metrics[name]
        count = len(values)
        mean = float(values.mean())
        standard_deviation = float(values.std(ddof=1)) if count > 1 else float("nan")
        half_width = critical * standard_deviation / sqrt(count) if count > 1 else float("nan")
        rows.append(
            {
                "metric": str(name),
                "count": count,
                "mean": mean,
                "standard_deviation": standard_deviation,
                "minimum": float(values.min()),
                "median": float(values.median()),
                "maximum": float(values.max()),
                "confidence_lower": mean - half_width,
                "confidence_upper": mean + half_width,
            }
        )
    return pd.DataFrame(rows).set_index("metric")[columns]


def _convergence(metrics: pd.DataFrame, checkpoints: tuple[int, ...]) -> pd.DataFrame:
    columns = ["count", "mean", "standard_error"]
    if metrics.shape[1] == 0:
        index = pd.MultiIndex.from_arrays([[], []], names=["checkpoint", "metric"])
        return pd.DataFrame(columns=columns, index=index)
    rows: list[dict[str, float | int | str]] = []
    for checkpoint in checkpoints:
        sample = metrics.iloc[:checkpoint]
        for name in metrics.columns:
            standard_deviation = float(sample[name].std(ddof=1))
            rows.append(
                {
                    "checkpoint": checkpoint,
                    "metric": str(name),
                    "count": checkpoint,
                    "mean": float(sample[name].mean()),
                    "standard_error": standard_deviation / sqrt(checkpoint)
                    if checkpoint > 1
                    else float("nan"),
                }
            )
    return pd.DataFrame(rows).set_index(["checkpoint", "metric"])[columns]


def _manifest(
    experiment: MonteCarloExperiment,
    evaluator: PathEvaluator | None,
) -> Mapping[str, Any]:
    metrics = [
        {
            "name": metric.name,
            "version": metric.version,
            "parameters": thaw_portable_mapping(metric.parameters),
        }
        for metric in experiment.metrics
    ]
    evaluator_description = None
    if evaluator is not None:
        evaluator_description = {
            "name": evaluator.name,
            "version": evaluator.version,
            "metric_names": list(evaluator.metric_names),
            "parameters": thaw_portable_mapping(evaluator.parameters),
        }
    return {
        "manifest_version": 1,
        "root_seed": experiment.root_seed,
        "path_count": experiment.path_count,
        "output_index": [str(value) for value in experiment.output_index],
        "time_steps": list(experiment.time_steps),
        "variable_names": list(experiment.model.variable_names),
        "model": {
            "name": experiment.model.name,
            "version": experiment.model.version,
            "output_semantics": experiment.model.output_semantics,
            "parameters": thaw_portable_mapping(experiment.model.parameters),
        },
        "metrics": metrics,
        "evaluator": evaluator_description,
        "retain_paths": experiment.retain_paths,
        "confidence_level": experiment.confidence_level,
        "convergence_checkpoints": list(experiment.convergence_checkpoints),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }


def _evaluator_identity(evaluator: PathEvaluator) -> None:
    if not evaluator.name or not evaluator.version:
        raise ValueError("evaluator name and version must not be empty")
    names = tuple(evaluator.metric_names)
    if not names or any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("evaluator metric_names must be nonempty and unique")
    freeze_portable_mapping(evaluator.parameters, name="evaluator parameters")
