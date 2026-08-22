"""Built-in scalar outcomes for generated Monte Carlo paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from persistra.monte_carlo._validation import finite_scalar

if TYPE_CHECKING:
    from collections.abc import Mapping

    import pandas as pd
    from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class TerminalLevel:
    """Terminal value of one named path variable."""

    variable: str

    def __post_init__(self) -> None:
        _variable_name(self.variable)

    @property
    def name(self) -> str:
        return f"terminal_level:{self.variable}"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"variable": self.variable}

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> float:
        del output_index
        return float(path[-1, _variable_position(self.variable, variable_names)])


@dataclass(frozen=True, slots=True)
class TerminalReturn:
    """Simple terminal return from one explicit initial level."""

    variable: str
    initial_level: float

    def __post_init__(self) -> None:
        _variable_name(self.variable)
        object.__setattr__(
            self,
            "initial_level",
            finite_scalar(self.initial_level, name="initial_level", positive=True),
        )

    @property
    def name(self) -> str:
        return f"terminal_return:{self.variable}"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"variable": self.variable, "initial_level": self.initial_level}

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> float:
        del output_index
        terminal = path[-1, _variable_position(self.variable, variable_names)]
        return float(terminal / self.initial_level - 1.0)


@dataclass(frozen=True, slots=True)
class PathVolatility:
    """Annualized sample volatility of one path variable."""

    variable: str
    periods_per_year: float

    def __post_init__(self) -> None:
        _variable_name(self.variable)
        object.__setattr__(
            self,
            "periods_per_year",
            finite_scalar(self.periods_per_year, name="periods_per_year", positive=True),
        )

    @property
    def name(self) -> str:
        return f"volatility:{self.variable}"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"variable": self.variable, "periods_per_year": self.periods_per_year}

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> float:
        del output_index
        if len(path) < 2:
            raise ValueError("path volatility requires at least two observations")
        values = path[:, _variable_position(self.variable, variable_names)]
        return float(values.std(ddof=1) * np.sqrt(self.periods_per_year))


@dataclass(frozen=True, slots=True)
class MaximumDrawdown:
    """Maximum drawdown magnitude for levels or simple returns."""

    variable: str
    input_kind: Literal["level", "simple_return"] = "level"

    def __post_init__(self) -> None:
        _variable_name(self.variable)
        if self.input_kind not in {"level", "simple_return"}:
            raise ValueError("input_kind must be level or simple_return")

    @property
    def name(self) -> str:
        return f"maximum_drawdown:{self.variable}"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"variable": self.variable, "input_kind": self.input_kind}

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> float:
        del output_index
        values = path[:, _variable_position(self.variable, variable_names)]
        if self.input_kind == "simple_return":
            if (values < -1.0).any():
                raise ValueError("simple returns must not be less than -1")
            levels = np.cumprod(1.0 + values)
            peaks = np.maximum.accumulate(np.concatenate(([1.0], levels)))[1:]
        else:
            if (values <= 0.0).any():
                raise ValueError("drawdown levels must be positive")
            levels = values
            peaks = np.maximum.accumulate(levels)
        return float(-np.min(levels / peaks - 1.0))


@dataclass(frozen=True, slots=True)
class MinimumLevel:
    """Minimum value reached by one named path variable."""

    variable: str

    def __post_init__(self) -> None:
        _variable_name(self.variable)

    @property
    def name(self) -> str:
        return f"minimum_level:{self.variable}"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"variable": self.variable}

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> float:
        del output_index
        return float(path[:, _variable_position(self.variable, variable_names)].min())


@dataclass(frozen=True, slots=True)
class ThresholdBreach:
    """Indicator that one path variable crossed an explicit threshold."""

    variable: str
    threshold: float
    direction: Literal["above", "below"] = "below"

    def __post_init__(self) -> None:
        _variable_name(self.variable)
        object.__setattr__(self, "threshold", finite_scalar(self.threshold, name="threshold"))
        if self.direction not in {"above", "below"}:
            raise ValueError("direction must be above or below")

    @property
    def name(self) -> str:
        return f"threshold_breach_{self.direction}:{self.variable}:{self.threshold:.12g}"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "variable": self.variable,
            "threshold": self.threshold,
            "direction": self.direction,
        }

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> float:
        del output_index
        values = path[:, _variable_position(self.variable, variable_names)]
        breached = (
            (values > self.threshold).any()
            if self.direction == "above"
            else (values < self.threshold).any()
        )
        return float(breached)


def _variable_name(variable: object) -> None:
    if not isinstance(variable, str) or not variable:
        raise ValueError("metric variable must be a nonempty string")


def _variable_position(variable: str, variable_names: tuple[str, ...]) -> int:
    try:
        return variable_names.index(variable)
    except ValueError as error:
        raise ValueError(f"metric variable {variable!r} is not present in the path") from error
