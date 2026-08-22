"""Public contracts for deterministic Monte Carlo experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

import numpy as np
import pandas as pd

from persistra._portable import freeze_portable_mapping
from persistra._validation import require_integer

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.random import Generator
    from numpy.typing import NDArray


class MonteCarloModel(Protocol):
    """Structural contract for one-path generation from a managed random stream."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def variable_names(self) -> tuple[str, ...]: ...

    @property
    def output_semantics(self) -> str: ...

    @property
    def parameters(self) -> Mapping[str, Any]: ...

    def generate(
        self,
        generator: Generator,
        time_steps: NDArray[np.float64],
    ) -> NDArray[np.float64]: ...


class Distribution(Protocol):
    """Structural contract for sampling only from a caller-managed generator."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def parameters(self) -> Mapping[str, Any]: ...

    def sample(
        self,
        generator: Generator,
        size: tuple[int, ...],
    ) -> NDArray[np.float64]: ...


class PathMetric(Protocol):
    """Structural contract for one named scalar outcome from one generated path."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def parameters(self) -> Mapping[str, Any]: ...

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> float: ...


class PathEvaluator(Protocol):
    """Structural contract for a bounded set of scalar outcomes from one path."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def metric_names(self) -> tuple[str, ...]: ...

    @property
    def parameters(self) -> Mapping[str, Any]: ...

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> Mapping[str, float]: ...


@dataclass(frozen=True, slots=True)
class MonteCarloExperiment:
    """Execution-independent identity and outputs for a Monte Carlo experiment."""

    model: MonteCarloModel
    output_index: pd.Index
    time_steps: tuple[float, ...]
    path_count: int
    root_seed: int
    metrics: tuple[PathMetric, ...] = ()
    retain_paths: bool = True
    confidence_level: float = 0.95
    convergence_checkpoints: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        output_index = self.output_index.copy(deep=True)
        if output_index.empty:
            raise ValueError("output_index must not be empty")
        if not output_index.is_unique:
            raise ValueError("output_index must not contain duplicates")
        if not output_index.is_monotonic_increasing:
            raise ValueError("output_index must be ordered")
        steps = tuple(float(value) for value in self.time_steps)
        if len(steps) != len(output_index):
            raise ValueError("time_steps must have one value per output index entry")
        if not np.isfinite(steps).all() or any(value <= 0.0 for value in steps):
            raise ValueError("time_steps must be finite and positive")
        path_count = require_integer(self.path_count, name="path_count", minimum=1)
        root_seed = require_integer(self.root_seed, name="root_seed", minimum=0)
        if not isinstance(cast("object", self.retain_paths), bool):
            raise TypeError("retain_paths must be a boolean")
        if (
            isinstance(self.confidence_level, bool)
            or not np.isfinite(self.confidence_level)
            or not 0.0 < self.confidence_level < 1.0
        ):
            raise ValueError("confidence_level must be between zero and one")
        _component_identity(
            self.model.name,
            self.model.version,
            self.model.parameters,
            name="model",
        )
        _ordered_names(self.model.variable_names, name="model variable_names")
        if not self.model.output_semantics:
            raise ValueError("model output_semantics must not be empty")
        metrics = tuple(self.metrics)
        metric_names = tuple(metric.name for metric in metrics)
        _ordered_names(metric_names, name="metric names", allow_empty=True)
        for metric in metrics:
            _component_identity(metric.name, metric.version, metric.parameters, name="metric")
        checkpoints = tuple(
            require_integer(value, name="convergence checkpoint", minimum=1)
            for value in self.convergence_checkpoints
        )
        if tuple(sorted(set(checkpoints))) != checkpoints:
            raise ValueError("convergence_checkpoints must be unique and ordered")
        if checkpoints and checkpoints[-1] > path_count:
            raise ValueError("convergence checkpoints must not exceed path_count")
        if not checkpoints or checkpoints[-1] != path_count:
            checkpoints = (*checkpoints, path_count)
        object.__setattr__(self, "output_index", output_index)
        object.__setattr__(self, "time_steps", steps)
        object.__setattr__(self, "path_count", path_count)
        object.__setattr__(self, "root_seed", root_seed)
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "confidence_level", float(self.confidence_level))
        object.__setattr__(self, "convergence_checkpoints", checkpoints)


@dataclass(frozen=True, slots=True)
class MonteCarloExecution:
    """Execution controls kept outside experiment identity."""

    workers: int = 1
    batch_size: int = 256
    backend: Literal["serial", "threaded"] = "serial"

    def __post_init__(self) -> None:
        workers = require_integer(self.workers, name="workers", minimum=1)
        batch_size = require_integer(self.batch_size, name="batch_size", minimum=1)
        if self.backend not in {"serial", "threaded"}:
            raise ValueError("unsupported Monte Carlo execution backend")
        if self.backend == "serial" and workers != 1:
            raise ValueError("serial execution requires one worker")
        object.__setattr__(self, "workers", workers)
        object.__setattr__(self, "batch_size", batch_size)


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    """Paths, scalar outcomes, summaries, convergence, and provenance for one run."""

    paths: NDArray[np.float64] | None
    output_index: pd.Index
    variable_names: tuple[str, ...]
    metrics: pd.DataFrame
    summary: pd.DataFrame
    convergence: pd.DataFrame
    manifest: Mapping[str, Any]
    execution_diagnostics: Mapping[str, Any]

    def __post_init__(self) -> None:
        output_index = self.output_index.copy(deep=True)
        variables = tuple(self.variable_names)
        _ordered_names(variables, name="result variable_names")
        paths = None if self.paths is None else np.array(self.paths, dtype=float, copy=True)
        if paths is not None:
            expected = (len(self.metrics), len(output_index), len(variables))
            if paths.shape != expected:
                raise ValueError("retained paths differ from the result axes")
            if not np.isfinite(paths).all():
                raise ValueError("retained paths must be finite")
            paths.flags.writeable = False
        metrics = self.metrics.copy(deep=True)
        if not metrics.index.equals(pd.RangeIndex(len(metrics), name="path")):
            raise ValueError("metric rows must use the ordered path index")
        object.__setattr__(self, "paths", paths)
        object.__setattr__(self, "output_index", output_index)
        object.__setattr__(self, "variable_names", variables)
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "summary", self.summary.copy(deep=True))
        object.__setattr__(self, "convergence", self.convergence.copy(deep=True))
        object.__setattr__(
            self,
            "manifest",
            freeze_portable_mapping(self.manifest, name="Monte Carlo manifest"),
        )
        object.__setattr__(
            self,
            "execution_diagnostics",
            freeze_portable_mapping(
                self.execution_diagnostics,
                name="Monte Carlo execution diagnostics",
            ),
        )

    def path_array(self, path_id: int) -> NDArray[np.float64]:
        """Return a defensive array copy for one retained path."""
        path_id = require_integer(path_id, name="path_id", minimum=0)
        if self.paths is None:
            raise ValueError("paths were not retained")
        if path_id >= len(self.paths):
            raise IndexError("path_id is outside the retained path range")
        return self.paths[path_id].copy()

    def path_frame(self, path_id: int) -> pd.DataFrame:
        """Return one retained path as an ordinary defensive pandas frame."""
        return pd.DataFrame(
            self.path_array(path_id),
            index=self.output_index.copy(deep=True),
            columns=list(self.variable_names),
        )

    def metric_frame(self) -> pd.DataFrame:
        """Return a defensive copy of path-level scalar outcomes."""
        return self.metrics.copy(deep=True)


def _component_identity(
    component_name: str,
    version: str,
    parameters: Mapping[str, Any],
    *,
    name: str,
) -> None:
    if not component_name or not version:
        raise ValueError(f"{name} name and version must not be empty")
    freeze_portable_mapping(parameters, name=f"{name} parameters")


def _ordered_names(
    values: tuple[str, ...],
    *,
    name: str,
    allow_empty: bool = False,
) -> None:
    if not values and not allow_empty:
        raise ValueError(f"{name} must not be empty")
    objects = cast("tuple[object, ...]", values)
    if any(not isinstance(value, str) or not value for value in objects):
        raise ValueError(f"{name} must contain nonempty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")
