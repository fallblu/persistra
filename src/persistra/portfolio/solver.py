"""Solver-neutral optimization boundaries and supported backends."""

# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

import numpy as np
from scipy.optimize import (
    minimize,  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]
)

from persistra._validation import require_integer

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from numpy.typing import NDArray

type SolverArray = NDArray[np.float64]
type SolverFeature = str
type PortfolioSolverStatus = Literal[
    "optimal",
    "feasible",
    "infeasible",
    "unbounded",
    "iteration_limit",
    "solver_error",
]


@dataclass(frozen=True, slots=True)
class PortfolioSolverCapabilities:
    """Features that one portfolio solver backend accepts exactly."""

    objectives: frozenset[SolverFeature]
    penalties: frozenset[SolverFeature]
    constraints: frozenset[SolverFeature]
    mixed_integer: bool = False

    def unsupported(self, problem: PortfolioSolverProblem) -> tuple[str, ...]:
        """Return stable descriptions of problem features the backend rejects."""
        missing: list[str] = []
        if problem.objective_name not in self.objectives:
            missing.append(f"objective:{problem.objective_name}")
        missing.extend(
            f"penalty:{name}" for name in sorted(problem.penalty_names - self.penalties)
        )
        missing.extend(
            f"constraint:{name}"
            for name in sorted(problem.constraint_names - self.constraints)
        )
        return tuple(missing)


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
    objective_name: SolverFeature
    penalty_names: frozenset[SolverFeature] = frozenset()
    constraint_names: frozenset[SolverFeature] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial", self.initial.copy())
        object.__setattr__(self, "bounds", tuple(self.bounds))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "penalty_names", frozenset(self.penalty_names))
        object.__setattr__(self, "constraint_names", frozenset(self.constraint_names))
        if not self.objective_name:
            raise ValueError("solver objective name must not be empty")
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
    status: PortfolioSolverStatus
    lower_bound: float | None = None
    upper_bound: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", self.values.copy())
        object.__setattr__(
            self,
            "iterations",
            require_integer(self.iterations, name="iterations", minimum=0),
        )
        object.__setattr__(self, "statistics", MappingProxyType(dict(self.statistics)))
        if self.status not in {
            "optimal",
            "feasible",
            "infeasible",
            "unbounded",
            "iteration_limit",
            "solver_error",
        }:
            raise ValueError("unsupported portfolio solver status")
        for name in ("lower_bound", "upper_bound"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int | float)
                or isinstance(value, bool)
                or not np.isfinite(float(value))
            ):
                raise ValueError(f"{name} must be finite when provided")
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("solver lower_bound must not exceed upper_bound")


class PortfolioSolver(Protocol):
    """Solve one continuous solver-neutral portfolio problem."""

    @property
    def name(self) -> str:
        """Return the stable solver identity."""

        ...

    @property
    def capabilities(self) -> PortfolioSolverCapabilities:
        """Return the exact problem features accepted by this backend."""

        ...

    def solve(self, problem: PortfolioSolverProblem) -> PortfolioSolverResult:
        """Return normalized values, termination state, and statistics."""

        ...


@dataclass(frozen=True, slots=True)
class DiscretePortfolioSolverProblem:
    """Convex mixed-integer quadratic problem in nonnegative integer lots."""

    hessian: SolverArray
    linear: SolverArray
    constant: float
    unit_weights: SolverArray
    maximum_lots: SolverArray
    maximum_positions: int
    minimum_position_weight: float
    minimum_invested_weight: float
    tolerance: float
    maximum_iterations: int

    def __post_init__(self) -> None:
        for name in ("hessian", "linear", "unit_weights", "maximum_lots"):
            object.__setattr__(self, name, np.asarray(getattr(self, name), dtype=float).copy())
        object.__setattr__(
            self,
            "maximum_positions",
            require_integer(self.maximum_positions, name="maximum_positions", minimum=1),
        )
        object.__setattr__(
            self,
            "maximum_iterations",
            require_integer(self.maximum_iterations, name="maximum_iterations", minimum=1),
        )


class DiscretePortfolioSolver(Protocol):
    """Solve one explicit mixed-integer portfolio problem without relaxation."""

    @property
    def name(self) -> str:
        """Return the stable solver identity."""

        ...

    @property
    def capabilities(self) -> PortfolioSolverCapabilities:
        """Return the exact mixed-integer capabilities."""

        ...

    def solve(self, problem: DiscretePortfolioSolverProblem) -> PortfolioSolverResult:
        """Return integer lots and normalized optimality diagnostics."""

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

    @property
    def capabilities(self) -> PortfolioSolverCapabilities:
        """Advertise every feature represented by the continuous boundary."""
        return PortfolioSolverCapabilities(
            objectives=frozenset(
                {
                    "active_mean_variance",
                    "mean_variance",
                    "minimum_tracking_error",
                    "minimum_variance",
                    "risk_parity",
                }
            ),
            penalties=frozenset(
                {
                    "asymmetric_transaction_cost",
                    "linear_transaction_cost",
                    "quadratic_transaction_cost",
                }
            ),
            constraints=frozenset(
                {
                    "factor_exposure",
                    "gross_exposure",
                    "grouped_exposure",
                    "linear_exposure",
                    "net_exposure",
                    "risk_budget",
                    "tracking_error",
                    "turnover",
                    "weight_bounds",
                }
            ),
        )

    def solve(self, problem: PortfolioSolverProblem) -> PortfolioSolverResult:
        """Translate neutral constraints and run SLSQP."""
        _require_supported(self.name, self.capabilities, problem)
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
            status="optimal" if result.success else "solver_error",
            lower_bound=float(result.fun) if result.success else None,
            upper_bound=float(result.fun) if result.success else None,
        )


@dataclass(frozen=True, slots=True)
class CvxpySolver:
    """Solve compatible convex quadratic problems through optional CVXPY."""

    solver: str = "CLARABEL"

    @property
    def name(self) -> str:
        """Return the stable backend and concrete solver identity."""
        return f"cvxpy-{self.solver.lower()}"

    @property
    def capabilities(self) -> PortfolioSolverCapabilities:
        """Advertise the affine-constrained convex problem subset."""
        return PortfolioSolverCapabilities(
            objectives=ScipySlsqpSolver().capabilities.objectives
            - frozenset({"risk_parity"}),
            penalties=ScipySlsqpSolver().capabilities.penalties,
            constraints=ScipySlsqpSolver().capabilities.constraints
            - frozenset({"risk_budget", "tracking_error"}),
        )

    def solve(self, problem: PortfolioSolverProblem) -> PortfolioSolverResult:
        """Canonicalize a quadratic problem and solve it through CVXPY."""
        _require_supported(self.name, self.capabilities, problem)
        cp = _cvxpy_module("CvxpySolver")
        hessian, linear, constant = _quadratic_objective(problem)
        values = cp.Variable(problem.initial.size)
        objective = cp.Minimize(
            0.5 * cp.quad_form(values, cp.psd_wrap(hessian))
            + linear @ values
            + constant
        )
        constraints: list[Any] = []
        for index, (lower, upper) in enumerate(problem.bounds):
            if lower is not None:
                constraints.append(values[index] >= lower)
            if upper is not None:
                constraints.append(values[index] <= upper)
        for item in problem.constraints:
            matrix, offset = _affine_constraint(item, problem.initial.size)
            expression = matrix @ values + offset
            constraints.append(expression == 0 if item.kind == "equality" else expression >= 0)
        model = cp.Problem(objective, constraints)
        try:
            model.solve(
                solver=self.solver,
                max_iter=problem.maximum_iterations,
                tol_gap_abs=problem.tolerance,
                tol_feas=problem.tolerance,
                verbose=False,
            )
        except Exception as exc:
            return _solver_error(problem.initial, exc)
        status = str(model.status)
        stats = model.solver_stats
        solution = values.value
        objective_value = (
            float(cast("float", model.value)) if model.value is not None else None
        )
        return PortfolioSolverResult(
            values=(
                problem.initial
                if solution is None
                else np.asarray(solution, dtype=float).reshape(problem.initial.shape)
            ),
            success=status in {"optimal", "optimal_inaccurate"},
            message=status,
            iterations=0 if stats.num_iters is None else int(stats.num_iters),
            statistics={
                "objective": objective_value if objective_value is not None else "unavailable",
                "solve_time": 0.0 if stats.solve_time is None else float(stats.solve_time),
                "status": status,
            },
            status=_cvxpy_status(status),
            lower_bound=objective_value if status == "optimal" else None,
            upper_bound=(
                objective_value
                if status in {"optimal", "optimal_inaccurate"}
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class CvxpyMixedIntegerSolver:
    """Solve convex mixed-integer quadratic portfolios with optional SCIP."""

    name: str = "cvxpy-scip"

    @property
    def capabilities(self) -> PortfolioSolverCapabilities:
        """Advertise the focused long-only discrete feature set."""
        return PortfolioSolverCapabilities(
            objectives=frozenset({"mean_variance", "minimum_variance"}),
            penalties=frozenset(),
            constraints=frozenset(
                {"cardinality", "lot_size", "minimum_position", "weight_bounds"}
            ),
            mixed_integer=True,
        )

    def solve(self, problem: DiscretePortfolioSolverProblem) -> PortfolioSolverResult:
        """Solve integer lots and retain primal and dual bounds when SCIP reports them."""
        try:
            import cvxpy as imported_cp
        except ImportError as exc:  # pragma: no cover - depends on optional environment
            raise ImportError(
                "CvxpyMixedIntegerSolver requires the 'portfolio-solver' optional dependency"
            ) from exc
        cp = cast("Any", imported_cp)
        size = problem.linear.size
        lots = cp.Variable(size, integer=True)
        selected = cp.Variable(size, boolean=True)
        objective = cp.Minimize(
            0.5 * cp.quad_form(lots, cp.psd_wrap(problem.hessian))
            + problem.linear @ lots
            + problem.constant
        )
        weights = cp.multiply(problem.unit_weights, lots)
        constraints = [
            lots >= 0,
            lots <= cp.multiply(problem.maximum_lots, selected),
            weights >= problem.minimum_position_weight * selected,
            cp.sum(selected) <= problem.maximum_positions,
            cp.sum(weights) <= 1.0,
            cp.sum(weights) >= problem.minimum_invested_weight,
        ]
        model = cp.Problem(objective, constraints)
        try:
            model.solve(
                solver="SCIP",
                verbose=False,
                scip_params={"limits/nodes": problem.maximum_iterations},
            )
        except Exception as exc:
            return PortfolioSolverResult(
                values=np.zeros(size, dtype=float),
                success=False,
                message=str(exc),
                iterations=0,
                statistics={"status": "solver_error"},
                status="solver_error",
            )
        status = str(model.status)
        statistics, lower_bound, upper_bound = _mixed_integer_statistics(model)
        solution = lots.value
        return PortfolioSolverResult(
            values=(
                np.zeros(size, dtype=float)
                if solution is None
                else np.rint(np.asarray(solution, dtype=float)).reshape((size,))
            ),
            success=status in {"optimal", "optimal_inaccurate", "user_limit"}
            and solution is not None,
            message=status,
            iterations=int(statistics.get("nodes", 0)),
            statistics=statistics,
            status=_cvxpy_status(status),
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        )

def _require_supported(
    name: str,
    capabilities: PortfolioSolverCapabilities,
    problem: PortfolioSolverProblem,
) -> None:
    unsupported = capabilities.unsupported(problem)
    if unsupported:
        joined = ", ".join(unsupported)
        raise ValueError(f"portfolio solver {name} does not support: {joined}")


def _cvxpy_module(backend: str) -> Any:
    try:
        import cvxpy as imported_cp
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise ImportError(
            f"{backend} requires the 'portfolio-solver' optional dependency"
        ) from exc
    return cast("Any", imported_cp)


def _solver_error(values: SolverArray, error: Exception) -> PortfolioSolverResult:
    return PortfolioSolverResult(
        values=values,
        success=False,
        message=str(error),
        iterations=0,
        statistics={"status": "solver_error"},
        status="solver_error",
    )


def _mixed_integer_statistics(
    model: Any,
) -> tuple[dict[str, float | int | str], float | None, float | None]:
    stats = model.solver_stats
    raw_extra = cast("object", stats.extra_stats)
    extra = cast("dict[str, object]", raw_extra) if isinstance(raw_extra, dict) else {}

    def optional_float(*names: str) -> float | None:
        for name in names:
            value = extra.get(name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
        return None

    lower = optional_float("dual_bound", "lower_bound")
    upper = optional_float("primal_bound", "upper_bound")
    objective = None if model.value is None else float(cast("float", model.value))
    if upper is None:
        upper = objective
    if lower is None and str(model.status) == "optimal":
        lower = objective
    nodes_value = extra.get("nodes", extra.get("node_count", 0))
    nodes = int(nodes_value) if isinstance(nodes_value, int | float) else 0
    result: dict[str, float | int | str] = {
        "status": str(model.status),
        "nodes": nodes,
        "solve_time": 0.0 if stats.solve_time is None else float(stats.solve_time),
    }
    if lower is not None:
        result["lower_bound"] = lower
    if upper is not None:
        result["upper_bound"] = upper
    if lower is not None and upper is not None:
        denominator = max(1.0, abs(upper))
        result["relative_gap"] = max(0.0, (upper - lower) / denominator)
    return result, lower, upper


def _cvxpy_status(status: str) -> PortfolioSolverStatus:
    if status == "optimal":
        return "optimal"
    if status == "optimal_inaccurate":
        return "feasible"
    if status in {"infeasible", "infeasible_inaccurate"}:
        return "infeasible"
    if status in {"unbounded", "unbounded_inaccurate"}:
        return "unbounded"
    if status == "user_limit":
        return "iteration_limit"
    return "solver_error"


def _quadratic_objective(problem: PortfolioSolverProblem) -> tuple[SolverArray, SolverArray, float]:
    """Recover the exact quadratic form exposed by the neutral gradient boundary."""
    size = problem.initial.size
    zero = np.zeros(size, dtype=float)
    linear = np.asarray(problem.gradient(zero), dtype=float)
    columns: list[SolverArray] = []
    for index in range(size):
        basis = zero.copy()
        basis[index] = 1.0
        columns.append(np.asarray(problem.gradient(basis), dtype=float) - linear)
    hessian = np.column_stack(columns)
    hessian = 0.5 * (hessian + hessian.T)
    if np.linalg.eigvalsh(hessian).min(initial=0.0) < -problem.tolerance:
        raise ValueError("CvxpySolver requires a convex quadratic objective")
    return hessian, linear, float(problem.objective(zero))


def _affine_constraint(
    constraint: SolverConstraint,
    size: int,
) -> tuple[SolverArray, SolverArray]:
    """Recover an affine constraint matrix from its solver-neutral function."""
    zero = np.zeros(size, dtype=float)
    offset = np.atleast_1d(np.asarray(constraint.function(zero), dtype=float))
    columns: list[SolverArray] = []
    for index in range(size):
        basis = zero.copy()
        basis[index] = 1.0
        value = np.atleast_1d(np.asarray(constraint.function(basis), dtype=float))
        columns.append(value - offset)
    return np.column_stack(columns), offset
