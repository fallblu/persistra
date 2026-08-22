"""Tests for deterministic Monte Carlo contracts and execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

import numpy as np
import pandas as pd
import pytest

from persistra.monte_carlo import (
    MonteCarloExecution,
    MonteCarloExperiment,
    MonteCarloResult,
    run_experiment,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.random import Generator
    from numpy.typing import NDArray


@dataclass(frozen=True)
class RandomWalkModel:
    """Small structural custom model for runner tests."""

    variables: tuple[str, ...] = ("asset",)
    invalid: Literal["none", "shape", "finite"] = "none"

    @property
    def name(self) -> str:
        return "test_random_walk"

    @property
    def version(self) -> str:
        return "1"

    @property
    def variable_names(self) -> tuple[str, ...]:
        return self.variables

    @property
    def output_semantics(self) -> str:
        return "level"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"invalid": self.invalid}

    def generate(
        self,
        generator: Generator,
        time_steps: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        shape = (len(time_steps), len(self.variables))
        result = generator.normal(size=shape).cumsum(axis=0)
        if self.invalid == "shape":
            return result[:-1]
        if self.invalid == "finite":
            result[0, 0] = np.inf
        return result


@dataclass(frozen=True)
class TerminalMetric:
    """Small structural custom metric for runner tests."""

    metric_name: str = "terminal"
    invalid: bool = False

    @property
    def name(self) -> str:
        return self.metric_name

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {}

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> float:
        del output_index, variable_names
        return float("nan") if self.invalid else float(path[-1, 0])


@dataclass(frozen=True)
class RangeEvaluator:
    """Small structural custom evaluator for runner tests."""

    keys: tuple[str, ...] = ("path_range",)
    returned_key: str = "path_range"

    @property
    def name(self) -> str:
        return "test_range"

    @property
    def version(self) -> str:
        return "1"

    @property
    def metric_names(self) -> tuple[str, ...]:
        return self.keys

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {}

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> Mapping[str, float]:
        del output_index, variable_names
        return {self.returned_key: float(path.max() - path.min())}


def experiment(
    *,
    path_count: int = 12,
    seed: int = 42,
    retain_paths: bool = True,
    model: RandomWalkModel | None = None,
) -> MonteCarloExperiment:
    """Return a compact deterministic experiment."""
    return MonteCarloExperiment(
        model=model or RandomWalkModel(("left", "right")),
        output_index=pd.RangeIndex(4, name="step"),
        time_steps=(0.25, 0.25, 0.25, 0.25),
        path_count=path_count,
        root_seed=seed,
        metrics=(TerminalMetric(),),
        retain_paths=retain_paths,
        convergence_checkpoints=(3, 7),
    )


def test_path_streams_are_stable_across_batches_workers_and_prefixes() -> None:
    serial = run_experiment(experiment(), MonteCarloExecution(batch_size=5))
    rebatched = run_experiment(experiment(), MonteCarloExecution(batch_size=2))
    threaded = run_experiment(
        experiment(),
        MonteCarloExecution(workers=3, batch_size=4, backend="threaded"),
    )
    extended = run_experiment(experiment(path_count=20), MonteCarloExecution(batch_size=6))
    different = run_experiment(experiment(seed=43))

    assert serial.paths is not None
    assert rebatched.paths is not None
    assert threaded.paths is not None
    assert extended.paths is not None
    assert different.paths is not None
    np.testing.assert_array_equal(serial.paths, rebatched.paths)
    np.testing.assert_array_equal(serial.paths, threaded.paths)
    np.testing.assert_array_equal(serial.paths, extended.paths[:12])
    assert not np.array_equal(serial.paths, different.paths)
    pd.testing.assert_frame_equal(serial.metrics, threaded.metrics)
    assert serial.manifest == threaded.manifest
    assert serial.execution_diagnostics != threaded.execution_diagnostics


def test_runner_does_not_mutate_numpy_global_random_state() -> None:
    np.random.seed(1234)
    expected = np.random.random(5)
    np.random.seed(1234)

    run_experiment(experiment())

    np.testing.assert_array_equal(np.random.random(5), expected)


def test_custom_metric_evaluator_summaries_and_convergence_are_ordered() -> None:
    result = run_experiment(experiment(), evaluator=RangeEvaluator())

    assert list(result.metrics.columns) == ["terminal", "path_range"]
    assert result.metrics.index.equals(pd.RangeIndex(12, name="path"))
    assert result.summary.loc["terminal", "count"] == 12
    lower = cast("float", result.summary.loc["terminal", "confidence_lower"])
    upper = cast("float", result.summary.loc["terminal", "confidence_upper"])
    assert lower < upper
    assert result.convergence.index.tolist() == [
        (checkpoint, metric)
        for checkpoint in (3, 7, 12)
        for metric in ("terminal", "path_range")
    ]
    assert result.manifest["root_seed"] == 42
    assert result.manifest["model"]["name"] == "test_random_walk"


def test_unretained_and_single_path_runs_keep_bounded_scalar_outputs() -> None:
    unretained = run_experiment(experiment(retain_paths=False), evaluator=RangeEvaluator())
    single = run_experiment(
        MonteCarloExperiment(
            model=RandomWalkModel(),
            output_index=pd.Index(["only"], name="step"),
            time_steps=(1.0,),
            path_count=1,
            root_seed=0,
            metrics=(TerminalMetric(),),
        )
    )

    assert unretained.paths is None
    assert unretained.metrics.shape == (12, 2)
    assert single.paths is not None and single.paths.shape == (1, 1, 1)
    assert pd.isna(single.summary.loc["terminal", "standard_deviation"])
    assert pd.isna(single.convergence.loc[(1, "terminal"), "standard_error"])


def test_result_accessors_are_defensive_and_validate_path_ids() -> None:
    result = run_experiment(experiment())
    assert result.paths is not None and not result.paths.flags.writeable
    path = result.path_array(0)
    path[0, 0] = 1000
    frame = result.path_frame(0)
    metrics = result.metric_frame()
    metrics.iloc[0, 0] = 1000

    assert result.path_array(0)[0, 0] != 1000
    assert frame.index.equals(pd.RangeIndex(4, name="step"))
    assert result.metrics.iloc[0, 0] != 1000
    with pytest.raises(IndexError, match="outside"):
        result.path_array(12)
    with pytest.raises(ValueError, match="not retained"):
        run_experiment(experiment(retain_paths=False)).path_array(0)
    with pytest.raises(ValueError, match="integer"):
        result.path_array(True)


@pytest.mark.parametrize(
    ("index", "steps", "message"),
    [
        (pd.Index([]), (), "must not be empty"),
        (pd.Index([1, 1]), (1.0, 1.0), "duplicates"),
        (pd.Index([2, 1]), (1.0, 1.0), "ordered"),
        (pd.Index([1, 2]), (1.0,), "one value"),
        (pd.Index([1]), (0.0,), "positive"),
    ],
)
def test_experiment_rejects_invalid_output_axes(
    index: pd.Index,
    steps: tuple[float, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MonteCarloExperiment(RandomWalkModel(), index, steps, 1, 0)


def test_experiment_rejects_invalid_identity_counts_metrics_and_checkpoints() -> None:
    index = pd.RangeIndex(2)
    with pytest.raises(ValueError, match="path_count"):
        MonteCarloExperiment(RandomWalkModel(), index, (1.0, 1.0), 0, 0)
    with pytest.raises(ValueError, match="root_seed"):
        MonteCarloExperiment(RandomWalkModel(), index, (1.0, 1.0), 1, True)
    with pytest.raises(TypeError, match="retain_paths"):
        MonteCarloExperiment(RandomWalkModel(), index, (1.0, 1.0), 1, 0, retain_paths=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="confidence_level"):
        MonteCarloExperiment(
            RandomWalkModel(), index, (1.0, 1.0), 1, 0, confidence_level=1.0
        )
    with pytest.raises(ValueError, match="metric names"):
        MonteCarloExperiment(
            RandomWalkModel(),
            index,
            (1.0, 1.0),
            1,
            0,
            metrics=(TerminalMetric(), TerminalMetric()),
        )
    with pytest.raises(ValueError, match="unique and ordered"):
        MonteCarloExperiment(
            RandomWalkModel(), index, (1.0, 1.0), 4, 0, convergence_checkpoints=(3, 2)
        )
    with pytest.raises(ValueError, match="exceed"):
        MonteCarloExperiment(
            RandomWalkModel(), index, (1.0, 1.0), 4, 0, convergence_checkpoints=(5,)
        )


def test_execution_and_generated_outputs_are_strictly_validated() -> None:
    with pytest.raises(ValueError, match="one worker"):
        MonteCarloExecution(workers=2)
    with pytest.raises(ValueError, match="backend"):
        MonteCarloExecution(backend="process")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="output shape"):
        run_experiment(experiment(model=RandomWalkModel(invalid="shape")))
    with pytest.raises(ValueError, match="output must be finite"):
        run_experiment(experiment(model=RandomWalkModel(invalid="finite")))
    invalid_metric = MonteCarloExperiment(
        RandomWalkModel(),
        pd.RangeIndex(2),
        (1.0, 1.0),
        1,
        0,
        metrics=(TerminalMetric(invalid=True),),
    )
    with pytest.raises(ValueError, match="must be finite"):
        run_experiment(invalid_metric)
    with pytest.raises(ValueError, match="differ"):
        run_experiment(experiment(), evaluator=RangeEvaluator(returned_key="other"))


def test_result_rejects_misaligned_retained_paths() -> None:
    empty = pd.DataFrame(index=pd.RangeIndex(1, name="path"))
    with pytest.raises(ValueError, match="axes"):
        MonteCarloResult(
            paths=np.zeros((1, 2, 1)),
            output_index=pd.RangeIndex(1),
            variable_names=("asset",),
            metrics=empty,
            summary=pd.DataFrame(),
            convergence=pd.DataFrame(),
            manifest={},
            execution_diagnostics={},
        )
