"""Exact mixed-integer portfolio optimization in caller-defined trade lots."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd

from persistra._validation import require_integer
from persistra.errors import AnalysisError
from persistra.portfolio.model import (
    DiscretePortfolioProblem,
    DiscretePortfolioResult,
    MeanVarianceObjective,
)
from persistra.portfolio.solver import (
    CvxpyMixedIntegerSolver,
    DiscretePortfolioSolver,
    DiscretePortfolioSolverProblem,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

type _Array = NDArray[np.float64]


def optimize_discrete_portfolio(
    problem: DiscretePortfolioProblem,
    *,
    tolerance: float = 1e-9,
    maximum_iterations: int = 100_000,
    solver: DiscretePortfolioSolver | None = None,
) -> DiscretePortfolioResult:
    """Solve long-only integer holdings without relaxing lots or cardinality."""
    if not isinstance(cast("object", problem), DiscretePortfolioProblem):
        raise TypeError("problem must be DiscretePortfolioProblem")
    if not isinstance(cast("object", tolerance), int | float) or isinstance(
        cast("object", tolerance), bool
    ):
        raise TypeError("tolerance must be a real number")
    checked_tolerance = float(tolerance)
    if not np.isfinite(checked_tolerance) or checked_tolerance <= 0.0:
        raise ValueError("tolerance must be positive and finite")
    maximum_iterations = require_integer(
        maximum_iterations,
        name="maximum_iterations",
        minimum=1,
    )
    assets, covariance, expected, prices, lot_sizes, maximum_weights = _inputs(problem)
    unit_weights = prices * lot_sizes / problem.capital
    maximum_lots = np.floor((maximum_weights + checked_tolerance) / unit_weights)
    if problem.minimum_invested_weight > float(np.sum(maximum_lots * unit_weights)):
        raise AnalysisError("discrete portfolio minimum invested weight is infeasible")
    scale = np.diag(unit_weights)
    risk_aversion = (
        problem.objective.risk_aversion
        if isinstance(problem.objective, MeanVarianceObjective)
        else 1.0
    )
    hessian = 2.0 * risk_aversion * scale @ covariance @ scale
    linear = -expected * unit_weights
    selected_solver = CvxpyMixedIntegerSolver() if solver is None else solver
    if not selected_solver.capabilities.mixed_integer:
        raise ValueError(f"portfolio solver {selected_solver.name} is not mixed-integer capable")
    objective_name = (
        "mean_variance"
        if isinstance(problem.objective, MeanVarianceObjective)
        else "minimum_variance"
    )
    required_constraints = {"lot_size", "weight_bounds"}
    if problem.maximum_positions is not None:
        required_constraints.add("cardinality")
    if problem.minimum_position_weight > 0.0:
        required_constraints.add("minimum_position")
    unsupported: list[str] = []
    if objective_name not in selected_solver.capabilities.objectives:
        unsupported.append(f"objective:{objective_name}")
    unsupported.extend(
        f"constraint:{name}"
        for name in sorted(required_constraints - selected_solver.capabilities.constraints)
    )
    if unsupported:
        raise ValueError(
            f"portfolio solver {selected_solver.name} does not support: "
            + ", ".join(unsupported)
        )
    result = selected_solver.solve(
        DiscretePortfolioSolverProblem(
            hessian=hessian,
            linear=linear,
            constant=0.0,
            unit_weights=unit_weights,
            maximum_lots=maximum_lots,
            maximum_positions=(
                len(assets)
                if problem.maximum_positions is None
                else problem.maximum_positions
            ),
            minimum_position_weight=problem.minimum_position_weight,
            minimum_invested_weight=problem.minimum_invested_weight,
            tolerance=checked_tolerance,
            maximum_iterations=maximum_iterations,
        )
    )
    if not result.success:
        raise AnalysisError(
            f"discrete portfolio optimization failed ({result.status}): {result.message}"
        )
    lots_array = np.rint(result.values).astype(np.int64)
    if np.any(lots_array < 0) or not np.allclose(
        result.values, lots_array, atol=checked_tolerance, rtol=0.0
    ):
        raise AnalysisError("mixed-integer solver returned invalid lot quantities")
    weights_array = unit_weights * lots_array
    holdings_array = lot_sizes.astype(np.int64) * lots_array
    selected = weights_array > checked_tolerance
    if int(selected.sum()) > (
        len(assets) if problem.maximum_positions is None else problem.maximum_positions
    ):
        raise AnalysisError("mixed-integer solver violated the cardinality constraint")
    if np.any(
        selected
        & (weights_array + checked_tolerance < problem.minimum_position_weight)
    ):
        raise AnalysisError("mixed-integer solver violated the minimum position constraint")
    invested = float(weights_array.sum())
    if invested > 1.0 + checked_tolerance or invested < (
        problem.minimum_invested_weight - checked_tolerance
    ):
        raise AnalysisError("mixed-integer solver violated the invested-weight constraints")
    objective_value = float(
        risk_aversion * weights_array @ covariance @ weights_array
        - expected @ weights_array
    )
    return DiscretePortfolioResult(
        holdings=pd.Series(holdings_array, index=assets.copy(), name="holding"),
        lots=pd.Series(lots_array, index=assets.copy(), name="lots"),
        weights=pd.Series(weights_array, index=assets.copy(), name="weight"),
        cash=1.0 - invested,
        objective_value=objective_value,
        status=result.status,
        lower_bound=result.lower_bound,
        upper_bound=result.upper_bound,
        solver=selected_solver.name,
        solver_message=result.message,
        iterations=result.iterations,
        solver_statistics=result.statistics,
        problem=problem,
    )


def _inputs(
    problem: DiscretePortfolioProblem,
) -> tuple[pd.Index, _Array, _Array, _Array, _Array, _Array]:
    covariance = problem.covariance
    if covariance.empty or not covariance.index.equals(covariance.columns):
        raise ValueError("covariance must be a nonempty square asset matrix")
    if not covariance.index.is_unique:
        raise ValueError("covariance asset index must be unique")
    assets = covariance.index.copy()
    covariance_array = _numeric_aligned_frame(covariance, assets, name="covariance")
    if not np.allclose(covariance_array, covariance_array.T, atol=1e-10, rtol=0.0):
        raise ValueError("covariance must be symmetric")
    if np.linalg.eigvalsh(covariance_array).min(initial=0.0) < -1e-10:
        raise ValueError("covariance must be positive semidefinite")
    prices = _positive_series(problem.prices, assets, name="prices")
    if isinstance(problem.lot_sizes, pd.Series):
        raw_lots = _aligned_series(problem.lot_sizes, assets, name="lot_sizes")
    else:
        raw_lots = np.full(len(assets), problem.lot_sizes, dtype=float)
    if not np.equal(raw_lots, np.floor(raw_lots)).all() or np.any(raw_lots < 1.0):
        raise ValueError("lot_sizes must contain positive integers")
    if isinstance(problem.maximum_position_weight, pd.Series):
        maximum_weights = _aligned_series(
            problem.maximum_position_weight,
            assets,
            name="maximum_position_weight",
        )
    else:
        maximum_weights = np.full(
            len(assets), problem.maximum_position_weight, dtype=float
        )
    if np.any(maximum_weights < 0.0) or np.any(maximum_weights > 1.0):
        raise ValueError("maximum_position_weight must be between zero and one")
    if np.any(maximum_weights + 1e-12 < problem.minimum_position_weight):
        raise ValueError("minimum position weight must not exceed maximum position weights")
    if isinstance(problem.objective, MeanVarianceObjective):
        if problem.expected_returns is None:
            raise ValueError("mean-variance discrete problems require expected_returns")
        expected = _aligned_series(
            problem.expected_returns,
            assets,
            name="expected_returns",
        )
    else:
        expected = np.zeros(len(assets), dtype=float)
    return assets, covariance_array, expected, prices, raw_lots, maximum_weights


def _numeric_aligned_frame(frame: pd.DataFrame, assets: pd.Index, *, name: str) -> _Array:
    if not frame.index.equals(assets) or not frame.columns.equals(assets):
        raise ValueError(f"{name} axes must match the covariance asset index")
    try:
        values = frame.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not np.isfinite(values).all():
        raise ValueError(f"{name} must be finite")
    return values


def _aligned_series(values: pd.Series, assets: pd.Index, *, name: str) -> _Array:
    if not values.index.equals(assets):
        raise ValueError(f"{name} index must match the covariance asset index")
    try:
        array = values.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite")
    return array


def _positive_series(values: pd.Series, assets: pd.Index, *, name: str) -> _Array:
    array = _aligned_series(values, assets, name=name)
    if np.any(array <= 0.0):
        raise ValueError(f"{name} must be positive")
    return array
