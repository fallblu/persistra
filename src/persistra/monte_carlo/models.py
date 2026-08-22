"""Focused built-in Monte Carlo path models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

import numpy as np
import pandas as pd

from persistra._validation import require_integer
from persistra.monte_carlo._validation import covariance_matrix, named_vector

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.random import Generator
    from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class MultivariateNormalReturns:
    """Correlated simple or log returns with per-year mean and covariance."""

    mean: pd.Series
    covariance: pd.DataFrame
    return_kind: Literal["simple", "log"] = "simple"

    def __post_init__(self) -> None:
        mean = named_vector(self.mean, name="return mean")
        covariance = covariance_matrix(self.covariance, mean.index, name="return covariance")
        if self.return_kind not in {"simple", "log"}:
            raise ValueError("return_kind must be simple or log")
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "covariance", covariance)

    @property
    def name(self) -> str:
        return "multivariate_normal_returns"

    @property
    def version(self) -> str:
        return "1"

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(self.mean.index)

    @property
    def output_semantics(self) -> str:
        return f"{self.return_kind}_return"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "mean_per_year": self.mean.tolist(),
            "covariance_per_year": self.covariance.to_numpy(dtype=float).tolist(),
            "return_kind": self.return_kind,
        }

    def generate(
        self,
        generator: Generator,
        time_steps: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        centered = generator.multivariate_normal(
            np.zeros(len(self.mean)),
            self.covariance.to_numpy(dtype=float),
            size=len(time_steps),
            check_valid="raise",
        )
        return (
            self.mean.to_numpy(dtype=float)[None, :] * time_steps[:, None]
            + centered * np.sqrt(time_steps[:, None])
        )


@dataclass(frozen=True, slots=True)
class GeometricBrownianMotion:
    """Correlated positive price paths with per-year drift and covariance."""

    initial_prices: pd.Series
    drift: pd.Series
    covariance: pd.DataFrame

    def __post_init__(self) -> None:
        initial = named_vector(self.initial_prices, name="initial_prices", positive=True)
        drift = named_vector(self.drift, name="drift")
        if not drift.index.equals(initial.index):
            raise ValueError("drift must use the initial price axis")
        covariance = covariance_matrix(self.covariance, initial.index, name="price covariance")
        object.__setattr__(self, "initial_prices", initial)
        object.__setattr__(self, "drift", drift)
        object.__setattr__(self, "covariance", covariance)

    @property
    def name(self) -> str:
        return "geometric_brownian_motion"

    @property
    def version(self) -> str:
        return "1"

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(self.initial_prices.index)

    @property
    def output_semantics(self) -> str:
        return "price"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "initial_prices": self.initial_prices.tolist(),
            "drift_per_year": self.drift.tolist(),
            "covariance_per_year": self.covariance.to_numpy(dtype=float).tolist(),
        }

    def generate(
        self,
        generator: Generator,
        time_steps: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        covariance = self.covariance.to_numpy(dtype=float)
        shocks = generator.multivariate_normal(
            np.zeros(len(self.initial_prices)),
            covariance,
            size=len(time_steps),
            check_valid="raise",
        )
        log_drift = self.drift.to_numpy(dtype=float) - np.diag(covariance) / 2.0
        increments = (
            log_drift[None, :] * time_steps[:, None]
            + shocks * np.sqrt(time_steps[:, None])
        )
        return self.initial_prices.to_numpy(dtype=float)[None, :] * np.exp(
            np.cumsum(increments, axis=0)
        )


@dataclass(frozen=True, slots=True)
class MovingBlockBootstrap:
    """Joint moving-block resampling of complete historical return rows."""

    history: pd.DataFrame
    block_length: int

    def __post_init__(self) -> None:
        block_length = require_integer(self.block_length, name="block_length", minimum=1)
        if self.history.empty or self.history.shape[1] == 0:
            raise ValueError("bootstrap history must not be empty")
        if not self.history.index.is_unique or not self.history.index.is_monotonic_increasing:
            raise ValueError("bootstrap history index must be unique and ordered")
        labels = cast("list[object]", self.history.columns.tolist())
        if len(set(labels)) != len(labels) or any(
            not isinstance(label, str) or not label for label in labels
        ):
            raise ValueError("bootstrap columns must be unique nonempty strings")
        if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in self.history.dtypes):
            raise TypeError("bootstrap history must be numeric")
        history = self.history.astype(float).copy(deep=True)
        if not np.isfinite(history.to_numpy(dtype=float)).all():
            raise ValueError("bootstrap history must be finite and complete")
        if block_length > len(history):
            raise ValueError("block_length must not exceed bootstrap history")
        object.__setattr__(self, "history", history)
        object.__setattr__(self, "block_length", block_length)

    @property
    def name(self) -> str:
        return "moving_block_bootstrap"

    @property
    def version(self) -> str:
        return "1"

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(self.history.columns)

    @property
    def output_semantics(self) -> str:
        return "historical_return_row"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "block_length": self.block_length,
            "history_rows": len(self.history),
            "variable_names": list(self.variable_names),
        }

    def generate(
        self,
        generator: Generator,
        time_steps: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        if not np.equal(time_steps, 1.0).all():
            raise ValueError("moving-block bootstrap time_steps must all equal one history row")
        history = self.history.to_numpy(dtype=float)
        result = np.empty((len(time_steps), history.shape[1]), dtype=float)
        position = 0
        maximum_start = len(history) - self.block_length
        while position < len(result):
            start = int(generator.integers(0, maximum_start + 1))
            count = min(self.block_length, len(result) - position)
            result[position : position + count] = history[start : start + count]
            position += count
        return result
