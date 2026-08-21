"""Solver-neutral continuous optimization boundary for portfolio problems."""

# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, Protocol, cast

import numpy as np
from scipy.optimize import (
    minimize,  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]
)

from persistra._validation import require_integer

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from numpy.typing import NDArray

type SolverArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class SolverConstraint:
    """One equality or nonnegative inequality in solver-neutral form."""

    kind: Literal["equality", "inequality"]
    function: Callable[[SolverArray], SolverArray | float]

    def __post_init__(self) -> None:
        if self.kind not in {"equality", "inequality"}:
            raise ValueError("solver constraint kind must be equality or inequality")


@dataclass(frozen=True, slots=True)
class PortfolioSolverProblem:
    """One differentiable continuous problem ready for a numerical backend."""

    objective: Callable[[SolverArray], float]
    gradient: Callable[[SolverArray], SolverArray]
    initial: SolverArray
    bounds: tuple[tuple[float | None, float | None], ...]
    constraints: tuple[SolverConstraint, ...]
    tolerance: float
    maximum_iterations: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial", self.initial.copy())
        object.__setattr__(self, "bounds", tuple(self.bounds))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(
            self,
            "maximum_iterations",
            require_integer(
                self.maximum_iterations,
                name="maximum_iterations",
                minimum=1,
            ),
        )


@dataclass(frozen=True, slots=True)
class PortfolioSolverResult:
    """Normalized numerical result returned by a portfolio solver backend."""

    values: SolverArray
    success: bool
    message: str
    iterations: int
    statistics: Mapping[str, float | int | str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", self.values.copy())
        object.__setattr__(
            self,
            "iterations",
            require_integer(self.iterations, name="iterations", minimum=0),
        )
        object.__setattr__(self, "statistics", MappingProxyType(dict(self.statistics)))


class PortfolioSolver(Protocol):
    """Solve one continuous solver-neutral portfolio problem."""

    @property
    def name(self) -> str:
        """Return the stable solver identity."""

        ...

    def solve(self, problem: PortfolioSolverProblem) -> PortfolioSolverResult:
        """Return normalized values, termination state, and statistics."""

        ...


class _ScipyResult(Protocol):
    x: SolverArray
    success: bool
    message: str
    nit: int
    fun: float
    nfev: int
    njev: int


@dataclass(frozen=True, slots=True)
class ScipySlsqpSolver:
    """Solve continuous problems with SciPy's SLSQP implementation."""

    name: str = "scipy-slsqp"

    def solve(self, problem: PortfolioSolverProblem) -> PortfolioSolverResult:
        """Translate neutral constraints and run SLSQP."""
        constraints = tuple(
            {
                "type": "eq" if constraint.kind == "equality" else "ineq",
                "fun": constraint.function,
            }
            for constraint in problem.constraints
        )
        raw = minimize(  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            problem.objective,
            problem.initial,
            method="SLSQP",
            jac=problem.gradient,
            bounds=problem.bounds,
            constraints=constraints,
            options={
                "ftol": problem.tolerance,
                "maxiter": problem.maximum_iterations,
                "disp": False,
            },
        )
        result = cast("_ScipyResult", raw)
        return PortfolioSolverResult(
            values=np.asarray(result.x, dtype=float),
            success=result.success,
            message=result.message,
            iterations=result.nit,
            statistics={
                "objective": float(result.fun),
                "function_evaluations": result.nfev,
                "gradient_evaluations": result.njev,
            },
        )
