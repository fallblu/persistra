"""Built-in distributions that use only managed NumPy generators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from persistra.monte_carlo._validation import (
    covariance_matrix,
    finite_scalar,
    named_vector,
    sample_size,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    import pandas as pd
    from numpy.random import Generator
    from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class NormalDistribution:
    """Univariate normal draws with explicit location and scale."""

    mean: float = 0.0
    standard_deviation: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "mean", finite_scalar(self.mean, name="mean"))
        object.__setattr__(
            self,
            "standard_deviation",
            finite_scalar(self.standard_deviation, name="standard_deviation", positive=True),
        )

    @property
    def name(self) -> str:
        return "normal"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"mean": self.mean, "standard_deviation": self.standard_deviation}

    def sample(
        self,
        generator: Generator,
        size: tuple[int, ...],
    ) -> NDArray[np.float64]:
        return generator.normal(self.mean, self.standard_deviation, size=sample_size(size))


@dataclass(frozen=True, slots=True)
class StudentTDistribution:
    """Univariate shifted and scaled Student-t draws."""

    degrees_of_freedom: float
    location: float = 0.0
    scale: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "degrees_of_freedom",
            finite_scalar(
                self.degrees_of_freedom,
                name="degrees_of_freedom",
                positive=True,
            ),
        )
        object.__setattr__(self, "location", finite_scalar(self.location, name="location"))
        object.__setattr__(self, "scale", finite_scalar(self.scale, name="scale", positive=True))

    @property
    def name(self) -> str:
        return "student_t"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "degrees_of_freedom": self.degrees_of_freedom,
            "location": self.location,
            "scale": self.scale,
        }

    def sample(
        self,
        generator: Generator,
        size: tuple[int, ...],
    ) -> NDArray[np.float64]:
        draws = generator.standard_t(self.degrees_of_freedom, size=sample_size(size))
        return self.location + self.scale * draws


@dataclass(frozen=True, slots=True)
class EmpiricalDistribution:
    """Univariate sampling with replacement from explicit finite observations."""

    observations: tuple[float, ...]

    def __post_init__(self) -> None:
        values = tuple(
            finite_scalar(value, name="empirical observation") for value in self.observations
        )
        if not values:
            raise ValueError("empirical observations must not be empty")
        object.__setattr__(self, "observations", values)

    @property
    def name(self) -> str:
        return "empirical"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"observations": list(self.observations)}

    def sample(
        self,
        generator: Generator,
        size: tuple[int, ...],
    ) -> NDArray[np.float64]:
        return generator.choice(np.asarray(self.observations), size=sample_size(size), replace=True)


@dataclass(frozen=True, slots=True)
class MultivariateNormalDistribution:
    """Multivariate normal draws with strictly aligned labeled parameters."""

    mean: pd.Series
    covariance: pd.DataFrame

    def __post_init__(self) -> None:
        mean = named_vector(self.mean, name="multivariate normal mean")
        covariance = covariance_matrix(
            self.covariance,
            mean.index,
            name="multivariate normal covariance",
        )
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "covariance", covariance)

    @property
    def name(self) -> str:
        return "multivariate_normal"

    @property
    def version(self) -> str:
        return "1"

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(self.mean.index)

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "variable_names": list(self.variable_names),
            "mean": self.mean.tolist(),
            "covariance": self.covariance.to_numpy(dtype=float).tolist(),
        }

    def sample(
        self,
        generator: Generator,
        size: tuple[int, ...],
    ) -> NDArray[np.float64]:
        return generator.multivariate_normal(
            self.mean.to_numpy(dtype=float),
            self.covariance.to_numpy(dtype=float),
            size=sample_size(size),
            check_valid="raise",
        )
