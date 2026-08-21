"""Continuous portfolio optimization with explicit objectives and constraints."""

# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd

from persistra._validation import require_integer
from persistra.errors import AnalysisError
from persistra.portfolio.model import (
    ActiveMeanVarianceObjective,
    AsymmetricTransactionCostPenalty,
    CovariancePolicy,
    FactorExposureConstraint,
    GrossExposureConstraint,
    LinearExposureConstraint,
    LinearTransactionCostPenalty,
    MeanVarianceObjective,
    MinimumTrackingErrorObjective,
    MinimumVarianceObjective,
    NetExposureConstraint,
    OptimizationFailurePolicy,
    PortfolioConstraint,
    PortfolioOptimizationPathResult,
    PortfolioOptimizationResult,
    PortfolioOptimizationStep,
    PortfolioPenalty,
    PortfolioProblem,
    QuadraticTransactionCostPenalty,
    TrackingErrorConstraint,
    TurnoverConstraint,
    WeightBounds,
)
from persistra.portfolio.solver import (
    PortfolioSolver,
    PortfolioSolverProblem,
    ScipySlsqpSolver,
    SolverConstraint,
)
from persistra.research import FactorRiskModel

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

type _Array = NDArray[np.float64]
_DIAGNOSTIC_COLUMNS = ["value", "lower", "upper", "residual", "binding"]


@dataclass(frozen=True, slots=True)
class _Layout:
    assets: slice
    gross: slice | None
    buys: slice | None
    sells: slice | None
    cash_trade: int | None
    size: int


@dataclass(frozen=True, slots=True)
class _Inputs:
    assets: pd.Index
    covariance: _Array
    covariance_diagnostics: pd.Series
    expected_returns: _Array
    current_weights: _Array
    benchmark_weights: _Array | None
    factor_exposures: pd.DataFrame | None
    linear_constraints: tuple[LinearExposureConstraint, ...]
    lower_weights: _Array
    upper_weights: _Array
    buy_costs: _Array
    sell_costs: _Array
    quadratic_costs: _Array
    objective: (
        MinimumVarianceObjective
        | MeanVarianceObjective
        | MinimumTrackingErrorObjective
        | ActiveMeanVarianceObjective
    )
    constraints: tuple[PortfolioConstraint, ...]
    use_gross_variables: bool
    use_trade_variables: bool


def optimize_portfolio(
    problem: PortfolioProblem,
    *,
    tolerance: float = 1e-9,
    maximum_iterations: int = 1_000,
    initial_weights: pd.Series | None = None,
    solver: PortfolioSolver | None = None,
) -> PortfolioOptimizationResult:
    """Solve one continuous portfolio problem and validate the returned constraints.

    Covariance values use the caller's return frequency. Expected returns, variance,
    tracking error, and cost rates must use a compatible scale. The residual cash weight is
    always ``1 - sum(weights)``. A ``NetExposureConstraint(1, 1)`` therefore expresses a
    fully invested risky portfolio.

    The optimizer raises ``AnalysisError`` when the problem is infeasible, the numerical
    solver fails, or the returned point violates a requested constraint beyond tolerance.
    """
    checked_tolerance = _positive_float(tolerance, name="tolerance")
    maximum_iterations = require_integer(
        maximum_iterations,
        name="maximum_iterations",
        minimum=1,
    )
    inputs = _problem_inputs(problem)
    layout = _layout(
        len(inputs.assets),
        use_gross=inputs.use_gross_variables,
        use_trades=inputs.use_trade_variables,
    )
    initial = _initial_point(inputs, layout, initial_weights=initial_weights)
    bounds = _bounds(inputs, layout)
    constraints = _solver_constraints(inputs, layout)
    objective, gradient = _objective_functions(inputs, layout)

    selected_solver = ScipySlsqpSolver() if solver is None else solver
    result = selected_solver.solve(
        PortfolioSolverProblem(
            objective=objective,
            gradient=gradient,
            initial=initial,
            bounds=tuple(bounds),
            constraints=tuple(constraints),
            tolerance=checked_tolerance,
            maximum_iterations=maximum_iterations,
        )
    )
    if not result.success:
        raise AnalysisError(f"portfolio optimization failed: {result.message}")
    if result.values.shape != (layout.size,) or not np.isfinite(result.values).all():
        raise AnalysisError("portfolio solver returned invalid decision values")
    weights = np.asarray(result.values[layout.assets], dtype=float)
    diagnostics = _constraint_diagnostics(inputs, weights, tolerance=checked_tolerance)
    violated = diagnostics[diagnostics["residual"] < -checked_tolerance]
    if len(violated):
        names = ", ".join(str(name) for name in violated.index)
        raise AnalysisError(f"portfolio optimization violated constraints: {names}")

    expected_return = float(inputs.expected_returns @ weights)
    variance = float(weights @ inputs.covariance @ weights)
    benchmark_delta = (
        None if inputs.benchmark_weights is None else weights - inputs.benchmark_weights
    )
    tracking_error = (
        None
        if benchmark_delta is None
        else math.sqrt(max(0.0, float(benchmark_delta @ inputs.covariance @ benchmark_delta)))
    )
    turnover = _turnover(weights, inputs.current_weights)
    factor_exposure = _factor_exposure(inputs.factor_exposures, weights)
    linear_exposure = _linear_exposure(inputs.linear_constraints, weights)
    risky = pd.Series(weights, index=inputs.assets.copy(), name="weight")
    cash = 1.0 - float(weights.sum())
    exposures = pd.Series(
        {
            "long": float(np.maximum(weights, 0.0).sum()),
            "short": float(-np.minimum(weights, 0.0).sum()),
            "gross": float(np.abs(weights).sum()),
            "net": float(weights.sum()),
            "cash": cash,
        },
        dtype=float,
    )
    breakdown = _objective_breakdown(inputs, weights)
    return PortfolioOptimizationResult(
        weights=risky,
        cash=cash,
        expected_return=expected_return,
        variance=variance,
        tracking_error=tracking_error,
        turnover=turnover,
        exposures=exposures,
        factor_exposures=factor_exposure,
        linear_exposures=linear_exposure,
        covariance_diagnostics=inputs.covariance_diagnostics,
        objective_breakdown=breakdown,
        constraint_diagnostics=diagnostics,
        solver=selected_solver.name,
        solver_message=result.message,
        iterations=result.iterations,
        solver_statistics=result.statistics,
        problem=problem,
    )


def optimize_portfolio_path(
    problems: tuple[PortfolioProblem, ...],
    *,
    failure_policy: OptimizationFailurePolicy = "raise",
    tolerance: float = 1e-9,
    maximum_iterations: int = 1_000,
    solver: PortfolioSolver | None = None,
) -> PortfolioOptimizationPathResult:
    """Solve ordered dated problems while carrying the preceding portfolio forward."""
    maximum_iterations = require_integer(
        maximum_iterations,
        name="maximum_iterations",
        minimum=1,
    )
    if not isinstance(cast("object", problems), tuple):
        raise TypeError("problems must be a tuple")
    if not problems:
        raise ValueError("problems must not be empty")
    if failure_policy not in {"raise", "hold_previous"}:
        raise ValueError("unsupported optimization failure policy")
    dated: list[tuple[pd.Timestamp, PortfolioProblem]] = []
    for problem in problems:
        if problem.as_of is None:
            raise ValueError("every path problem requires as_of")
        dated.append((pd.Timestamp(problem.as_of), problem))
    dates = pd.DatetimeIndex([item[0] for item in dated], name="as_of")
    if not dates.is_monotonic_increasing or dates.has_duplicates:
        raise ValueError("path problem as_of values must be strictly increasing")

    first_assets = _problem_assets(problems[0])
    previous: pd.Series | None = None
    steps: list[PortfolioOptimizationStep] = []
    for as_of, problem in dated:
        if not _problem_assets(problem).equals(first_assets):
            raise ValueError("path problems must use one fixed asset index")
        effective = problem if previous is None else replace(problem, current_weights=previous)
        try:
            result = optimize_portfolio(
                effective,
                tolerance=tolerance,
                maximum_iterations=maximum_iterations,
                initial_weights=previous,
                solver=solver,
            )
        except AnalysisError as exc:
            if failure_policy == "raise" or previous is None:
                raise
            weights = previous.copy(deep=True)
            steps.append(
                PortfolioOptimizationStep(
                    as_of=as_of,
                    problem=effective,
                    weights=weights,
                    cash=1.0 - float(weights.sum()),
                    result=None,
                    status="held",
                    message=str(exc),
                )
            )
            continue
        previous = result.weights
        steps.append(
            PortfolioOptimizationStep(
                as_of=as_of,
                problem=effective,
                weights=result.weights,
                cash=result.cash,
                result=result,
                status="optimized",
                message=result.solver_message,
            )
        )
    weights = pd.DataFrame(
        [step.weights.to_numpy(dtype=float) for step in steps],
        index=dates,
        columns=first_assets.copy(),
    )
    cash = pd.Series([step.cash for step in steps], index=dates, name="cash")
    return PortfolioOptimizationPathResult(
        steps=tuple(steps),
        weights=weights,
        cash=cash,
        failure_policy=failure_policy,
    )


def _problem_inputs(problem: PortfolioProblem) -> _Inputs:
    raw_penalties = cast("tuple[object, ...]", cast("object", problem.penalties))
    supported_penalties = (
        LinearTransactionCostPenalty,
        AsymmetricTransactionCostPenalty,
        QuadraticTransactionCostPenalty,
    )
    if any(not isinstance(item, supported_penalties) for item in raw_penalties):
        raise TypeError("problem contains an unsupported portfolio penalty")
    covariance_frame = (
        problem.covariance.asset_covariance
        if isinstance(problem.covariance, FactorRiskModel)
        else problem.covariance
    )
    covariance, covariance_diagnostics = _covariance(
        covariance_frame,
        problem.covariance_policy,
    )
    assets = covariance_frame.index.copy()
    expected = _aligned_series(
        problem.expected_returns,
        assets,
        name="expected returns",
        default=0.0,
    )
    current = _aligned_series(
        problem.current_weights,
        assets,
        name="current weights",
        default=0.0,
    )
    benchmark = (
        None
        if problem.benchmark_weights is None
        else _aligned_series(
            problem.benchmark_weights,
            assets,
            name="benchmark weights",
            default=0.0,
        )
    )
    if isinstance(problem.objective, MeanVarianceObjective | ActiveMeanVarianceObjective):
        if problem.expected_returns is None:
            raise ValueError("the selected objective requires expected_returns")
    needs_benchmark = isinstance(
        problem.objective,
        MinimumTrackingErrorObjective | ActiveMeanVarianceObjective,
    ) or any(isinstance(item, TrackingErrorConstraint) for item in problem.constraints)
    if needs_benchmark and benchmark is None:
        raise ValueError("tracking-error objectives and constraints require benchmark_weights")
    _validate_constraint_types(problem.constraints)
    factor_exposures = _factor_exposure_frame(problem.factor_exposures, assets)
    linear_constraints = tuple(
        constraint
        for constraint in problem.constraints
        if isinstance(constraint, LinearExposureConstraint)
    )
    names = [constraint.name for constraint in linear_constraints]
    if len(names) != len(set(names)):
        raise ValueError("linear exposure constraint names must be unique")
    for constraint in linear_constraints:
        _linear_bounds(constraint, assets)
    lower, upper = _weight_bounds(problem.constraints, assets)
    buy_costs, sell_costs, quadratic_costs = _transaction_costs(problem.penalties, assets)
    if any(isinstance(item, TurnoverConstraint) for item in problem.constraints):
        if problem.current_weights is None:
            raise ValueError("turnover constraints require current_weights")
    if problem.penalties and problem.current_weights is None:
        raise ValueError("transaction-cost penalties require current_weights")
    for constraint in problem.constraints:
        if isinstance(constraint, FactorExposureConstraint):
            _factor_bounds(constraint, factor_exposures)
    return _Inputs(
        assets=assets,
        covariance=covariance,
        covariance_diagnostics=covariance_diagnostics,
        expected_returns=expected,
        current_weights=current,
        benchmark_weights=benchmark,
        factor_exposures=factor_exposures,
        linear_constraints=linear_constraints,
        lower_weights=lower,
        upper_weights=upper,
        buy_costs=buy_costs,
        sell_costs=sell_costs,
        quadratic_costs=quadratic_costs,
        objective=problem.objective,
        constraints=problem.constraints,
        use_gross_variables=any(
            isinstance(item, GrossExposureConstraint) for item in problem.constraints
        ),
        use_trade_variables=any(
            isinstance(
                item,
                LinearTransactionCostPenalty | AsymmetricTransactionCostPenalty,
            )
            for item in problem.penalties
        )
        or any(isinstance(item, TurnoverConstraint) for item in problem.constraints),
    )


def _covariance(
    frame: pd.DataFrame,
    policy: CovariancePolicy,
) -> tuple[_Array, pd.Series]:
    if frame.empty or len(frame.index) == 0:
        raise AnalysisError("covariance must contain at least one asset")
    if not frame.index.equals(frame.columns):
        raise ValueError("covariance must use identical asset index and columns")
    if frame.index.hasnans or not frame.index.is_unique:
        raise ValueError("covariance assets must be unique and nonmissing")
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in frame.dtypes):
        raise AnalysisError("covariance must be numeric")
    values = frame.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        raise AnalysisError("covariance must be finite")
    if not np.allclose(values, values.T, atol=1e-10, rtol=0.0):
        raise AnalysisError("covariance must be symmetric")
    raw = (values + values.T) / 2.0
    raw_eigenvalues = np.linalg.eigvalsh(raw)
    conditioned = raw.copy()
    if policy.diagonal_shrinkage:
        diagonal = np.diag(np.diag(conditioned))
        conditioned = (
            1.0 - policy.diagonal_shrinkage
        ) * conditioned + policy.diagonal_shrinkage * diagonal
    if policy.minimum_eigenvalue is not None:
        eigenvalues, eigenvectors = np.linalg.eigh(conditioned)
        conditioned = (eigenvectors * np.maximum(eigenvalues, policy.minimum_eigenvalue)) @ (
            eigenvectors.T
        )
        conditioned = (conditioned + conditioned.T) / 2.0
    conditioned_eigenvalues = np.linalg.eigvalsh(conditioned)
    if conditioned_eigenvalues.min() < -1e-10:
        raise AnalysisError("covariance must be positive semidefinite")
    positive = conditioned_eigenvalues[conditioned_eigenvalues > 1e-15]
    condition_number = (
        math.inf if not len(positive) else float(conditioned_eigenvalues.max() / positive.min())
    )
    diagnostics = pd.Series(
        {
            "raw_minimum_eigenvalue": float(raw_eigenvalues.min()),
            "conditioned_minimum_eigenvalue": float(conditioned_eigenvalues.min()),
            "condition_number": condition_number,
            "frobenius_adjustment": float(np.linalg.norm(conditioned - raw, ord="fro")),
            "diagonal_shrinkage": policy.diagonal_shrinkage,
            "minimum_eigenvalue": (
                np.nan if policy.minimum_eigenvalue is None else policy.minimum_eigenvalue
            ),
        },
        dtype=float,
        name="covariance",
    )
    return conditioned, diagnostics


def _aligned_series(
    values: pd.Series | None,
    assets: pd.Index,
    *,
    name: str,
    default: float,
) -> _Array:
    if values is None:
        return np.full(len(assets), default, dtype=float)
    if not values.index.equals(assets):
        raise ValueError(f"{name} must use the covariance asset index")
    result = values.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(result).all():
        raise AnalysisError(f"{name} must be finite")
    return result


def _factor_exposure_frame(
    exposures: pd.DataFrame | None,
    assets: pd.Index,
) -> pd.DataFrame | None:
    if exposures is None:
        return None
    if not exposures.index.equals(assets):
        raise ValueError("factor exposures must use the covariance asset index")
    if exposures.columns.hasnans or not exposures.columns.is_unique:
        raise ValueError("factor exposure columns must be unique and nonmissing")
    factor_names = cast("list[object]", cast("object", exposures.columns.tolist()))
    if any(not isinstance(value, str) or not value for value in factor_names):
        raise TypeError("factor exposure names must be nonempty strings")
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in exposures.dtypes):
        raise AnalysisError("factor exposures must be numeric")
    values = exposures.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        raise AnalysisError("factor exposures must be finite")
    return exposures.copy(deep=True)


def _validate_constraint_types(constraints: tuple[PortfolioConstraint, ...]) -> None:
    supported = (
        WeightBounds,
        GrossExposureConstraint,
        NetExposureConstraint,
        TurnoverConstraint,
        FactorExposureConstraint,
        LinearExposureConstraint,
        TrackingErrorConstraint,
    )
    raw_constraints = cast("tuple[object, ...]", cast("object", constraints))
    if any(not isinstance(item, supported) for item in raw_constraints):
        raise TypeError("problem contains an unsupported portfolio constraint")
    types = [type(item) for item in constraints if not isinstance(item, LinearExposureConstraint)]
    if len(types) != len(set(types)):
        raise ValueError("problem must not repeat a constraint type")


def _linear_bounds(
    constraint: LinearExposureConstraint,
    assets: pd.Index,
) -> tuple[_Array, _Array]:
    loadings = constraint.loadings
    if not loadings.index.equals(assets):
        raise ValueError("linear constraint loadings must use the covariance asset index")
    if loadings.columns.hasnans or not loadings.columns.is_unique:
        raise ValueError("linear constraint columns must be unique and nonmissing")
    if not constraint.lower.index.equals(loadings.columns) or not constraint.upper.index.equals(
        loadings.columns
    ):
        raise ValueError("linear constraint bounds must use the loading columns")
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in loadings.dtypes):
        raise AnalysisError("linear constraint loadings must be numeric")
    matrix = loadings.to_numpy(dtype=float, na_value=np.nan)
    lower = constraint.lower.to_numpy(dtype=float, na_value=np.nan)
    upper = constraint.upper.to_numpy(dtype=float, na_value=np.nan)
    if (
        not np.isfinite(matrix).all()
        or not np.isfinite(lower).all()
        or not np.isfinite(upper).all()
    ):
        raise AnalysisError("linear constraint inputs must be finite")
    if (lower > upper).any():
        raise ValueError("linear constraint lower bounds must not exceed upper bounds")
    return lower, upper


def _weight_bounds(
    constraints: tuple[PortfolioConstraint, ...],
    assets: pd.Index,
) -> tuple[_Array, _Array]:
    lower = np.full(len(assets), -np.inf)
    upper = np.full(len(assets), np.inf)
    selected = next((item for item in constraints if isinstance(item, WeightBounds)), None)
    if selected is None:
        return lower, upper
    lower = _bound_values(selected.lower, assets, name="lower weight bounds")
    upper = _bound_values(selected.upper, assets, name="upper weight bounds")
    if (lower > upper).any():
        raise ValueError("lower weight bounds must not exceed upper bounds")
    return lower, upper


def _bound_values(values: float | pd.Series, assets: pd.Index, *, name: str) -> _Array:
    if isinstance(values, pd.Series):
        return _aligned_series(values, assets, name=name, default=0.0)
    if isinstance(values, bool) or not math.isfinite(values):
        raise ValueError(f"{name} must be finite")
    return np.full(len(assets), float(values), dtype=float)


def _transaction_costs(
    penalties: tuple[PortfolioPenalty, ...],
    assets: pd.Index,
) -> tuple[_Array, _Array, _Array]:
    buys = np.zeros(len(assets), dtype=float)
    sells = np.zeros(len(assets), dtype=float)
    quadratic = np.zeros(len(assets), dtype=float)
    for penalty in penalties:
        if isinstance(penalty, LinearTransactionCostPenalty):
            rates = _nonnegative_values(penalty.rates, assets, name="transaction cost rates")
            buys += penalty.multiplier * rates
            sells += penalty.multiplier * rates
        elif isinstance(penalty, AsymmetricTransactionCostPenalty):
            buy_rates = _nonnegative_values(
                penalty.buy_rates,
                assets,
                name="buy transaction cost rates",
            )
            sell_rates = _nonnegative_values(
                penalty.sell_rates,
                assets,
                name="sell transaction cost rates",
            )
            buys += penalty.multiplier * buy_rates
            sells += penalty.multiplier * sell_rates
        else:
            rates = _nonnegative_values(
                penalty.rates,
                assets,
                name="quadratic transaction cost rates",
            )
            quadratic += penalty.multiplier * rates
    return buys, sells, quadratic


def _nonnegative_values(values: float | pd.Series, assets: pd.Index, *, name: str) -> _Array:
    if isinstance(values, pd.Series):
        result = _aligned_series(values, assets, name=name, default=0.0)
    else:
        if isinstance(values, bool) or not math.isfinite(values):
            raise ValueError(f"{name} must be finite")
        result = np.full(len(assets), float(values), dtype=float)
    if (result < 0.0).any():
        raise ValueError(f"{name} must be nonnegative")
    return result


def _factor_bounds(
    constraint: FactorExposureConstraint,
    exposures: pd.DataFrame | None,
) -> tuple[_Array, _Array]:
    if exposures is None:
        raise ValueError("factor exposure constraints require factor_exposures")
    lower = _aligned_series(
        constraint.lower,
        exposures.columns,
        name="factor exposure lower bounds",
        default=0.0,
    )
    upper = _aligned_series(
        constraint.upper,
        exposures.columns,
        name="factor exposure upper bounds",
        default=0.0,
    )
    if (lower > upper).any():
        raise ValueError("factor exposure lower bounds must not exceed upper bounds")
    return lower, upper


def _layout(assets: int, *, use_gross: bool, use_trades: bool) -> _Layout:
    position = assets
    gross = None
    if use_gross:
        gross = slice(position, position + assets)
        position += assets
    buys = None
    sells = None
    cash_trade = None
    if use_trades:
        buys = slice(position, position + assets)
        position += assets
        sells = slice(position, position + assets)
        position += assets
        cash_trade = position
        position += 1
    return _Layout(slice(0, assets), gross, buys, sells, cash_trade, position)


def _initial_point(
    inputs: _Inputs,
    layout: _Layout,
    *,
    initial_weights: pd.Series | None,
) -> _Array:
    initial = np.zeros(layout.size, dtype=float)
    starting = (
        _aligned_series(
            initial_weights,
            inputs.assets,
            name="initial weights",
            default=0.0,
        )
        if initial_weights is not None
        else (
            inputs.benchmark_weights.copy()
            if isinstance(
                inputs.objective,
                MinimumTrackingErrorObjective | ActiveMeanVarianceObjective,
            )
            and inputs.benchmark_weights is not None
            else inputs.current_weights.copy()
        )
    )
    starting = np.minimum(np.maximum(starting, inputs.lower_weights), inputs.upper_weights)
    initial[layout.assets] = starting
    if layout.gross is not None:
        initial[layout.gross] = np.abs(starting)
    if layout.buys is not None and layout.sells is not None and layout.cash_trade is not None:
        delta = starting - inputs.current_weights
        initial[layout.buys] = np.maximum(delta, 0.0)
        initial[layout.sells] = np.maximum(-delta, 0.0)
        initial[layout.cash_trade] = abs(float(delta.sum()))
    return initial


def _problem_assets(problem: PortfolioProblem) -> pd.Index:
    covariance = (
        problem.covariance.asset_covariance
        if isinstance(problem.covariance, FactorRiskModel)
        else problem.covariance
    )
    return covariance.index


def _bounds(inputs: _Inputs, layout: _Layout) -> list[tuple[float | None, float | None]]:
    result = [
        (
            None if not math.isfinite(lower) else float(lower),
            None if not math.isfinite(upper) else float(upper),
        )
        for lower, upper in zip(inputs.lower_weights, inputs.upper_weights, strict=True)
    ]
    result.extend((0.0, None) for _ in range(layout.size - len(result)))
    return result


def _solver_constraints(inputs: _Inputs, layout: _Layout) -> list[SolverConstraint]:
    constraints: list[SolverConstraint] = []
    if layout.gross is not None:
        gross_slice = layout.gross
        constraints.extend(
            [
                _inequality(lambda value: value[gross_slice] - value[layout.assets]),
                _inequality(lambda value: value[gross_slice] + value[layout.assets]),
            ]
        )
    if layout.buys is not None and layout.sells is not None and layout.cash_trade is not None:
        buy_slice = layout.buys
        sell_slice = layout.sells
        cash_position = layout.cash_trade
        current = inputs.current_weights
        constraints.extend(
            [
                _equality(
                    lambda value: (
                        value[layout.assets] - current - value[buy_slice] + value[sell_slice]
                    )
                ),
                _inequality(
                    lambda value: (
                        value[cash_position] - float((value[layout.assets] - current).sum())
                    )
                ),
                _inequality(
                    lambda value: (
                        value[cash_position] + float((value[layout.assets] - current).sum())
                    )
                ),
            ]
        )
    for constraint in inputs.constraints:
        if isinstance(constraint, GrossExposureConstraint):
            assert layout.gross is not None
            gross_slice = layout.gross
            constraints.append(
                _inequality(
                    lambda value, limit=constraint.maximum, selected=gross_slice: (
                        limit - value[selected].sum()
                    )
                )
            )
        elif isinstance(constraint, NetExposureConstraint):
            constraints.extend(
                [
                    _inequality(
                        lambda value, lower=constraint.minimum: value[layout.assets].sum() - lower
                    ),
                    _inequality(
                        lambda value, upper=constraint.maximum: upper - value[layout.assets].sum()
                    ),
                ]
            )
        elif isinstance(constraint, TurnoverConstraint):
            assert (
                layout.buys is not None
                and layout.sells is not None
                and layout.cash_trade is not None
            )
            buy_slice = layout.buys
            sell_slice = layout.sells
            cash_position = layout.cash_trade
            limit = constraint.maximum

            def turnover_limit(
                value: _Array,
                *,
                selected_buys: slice = buy_slice,
                selected_sells: slice = sell_slice,
                cash_index: int = cash_position,
                maximum: float = limit,
            ) -> float:
                return maximum - (
                    0.5
                    * (value[selected_buys].sum() + value[selected_sells].sum() + value[cash_index])
                )

            constraints.append(_inequality(turnover_limit))
        elif isinstance(constraint, FactorExposureConstraint):
            assert inputs.factor_exposures is not None
            exposure_values = inputs.factor_exposures.to_numpy(dtype=float)
            lower, upper = _factor_bounds(constraint, inputs.factor_exposures)
            constraints.extend(
                [
                    _inequality(
                        lambda value, matrix=exposure_values, bound=lower: (
                            (value[layout.assets] @ matrix) - bound
                        )
                    ),
                    _inequality(
                        lambda value, matrix=exposure_values, bound=upper: (
                            bound - (value[layout.assets] @ matrix)
                        )
                    ),
                ]
            )
        elif isinstance(constraint, LinearExposureConstraint):
            exposure_values = constraint.loadings.to_numpy(dtype=float)
            lower, upper = _linear_bounds(constraint, inputs.assets)
            constraints.extend(
                [
                    _inequality(
                        lambda value, matrix=exposure_values, bound=lower: (
                            (value[layout.assets] @ matrix) - bound
                        )
                    ),
                    _inequality(
                        lambda value, matrix=exposure_values, bound=upper: (
                            bound - (value[layout.assets] @ matrix)
                        )
                    ),
                ]
            )
        elif isinstance(constraint, TrackingErrorConstraint):
            assert inputs.benchmark_weights is not None
            benchmark = inputs.benchmark_weights
            covariance = inputs.covariance
            limit = constraint.maximum

            def tracking_limit(
                value: _Array,
                *,
                selected_benchmark: _Array = benchmark,
                selected_covariance: _Array = covariance,
                maximum: float = limit,
            ) -> float:
                difference = value[layout.assets] - selected_benchmark
                return (maximum * maximum) - float(difference @ selected_covariance @ difference)

            constraints.append(_inequality(tracking_limit))
    return constraints


def _inequality(
    function: Callable[[_Array], _Array | float],
) -> SolverConstraint:
    return SolverConstraint("inequality", function)


def _equality(
    function: Callable[[_Array], _Array | float],
) -> SolverConstraint:
    return SolverConstraint("equality", function)


def _objective_functions(
    inputs: _Inputs,
    layout: _Layout,
) -> tuple[Callable[[_Array], float], Callable[[_Array], _Array]]:
    def objective(value: _Array) -> float:
        weights = value[layout.assets]
        base, _gradient = _base_objective(inputs, weights)
        delta = weights - inputs.current_weights
        base += float(inputs.quadratic_costs @ np.square(delta))
        if layout.buys is not None and layout.sells is not None:
            base += float(inputs.buy_costs @ value[layout.buys])
            base += float(inputs.sell_costs @ value[layout.sells])
        return base

    def gradient(value: _Array) -> _Array:
        weights = value[layout.assets]
        _base, weight_gradient = _base_objective(inputs, weights)
        result = np.zeros(layout.size, dtype=float)
        delta = weights - inputs.current_weights
        result[layout.assets] = weight_gradient + (2.0 * inputs.quadratic_costs * delta)
        if layout.buys is not None and layout.sells is not None:
            result[layout.buys] = inputs.buy_costs
            result[layout.sells] = inputs.sell_costs
        return result

    return objective, gradient


def _base_objective(inputs: _Inputs, weights: _Array) -> tuple[float, _Array]:
    if isinstance(inputs.objective, MinimumVarianceObjective):
        return (
            0.5 * float(weights @ inputs.covariance @ weights),
            inputs.covariance @ weights,
        )
    if isinstance(inputs.objective, MeanVarianceObjective):
        risk = inputs.objective.risk_aversion
        return (
            (0.5 * risk * float(weights @ inputs.covariance @ weights))
            - float(inputs.expected_returns @ weights),
            (risk * (inputs.covariance @ weights)) - inputs.expected_returns,
        )
    assert inputs.benchmark_weights is not None
    delta = weights - inputs.benchmark_weights
    if isinstance(inputs.objective, MinimumTrackingErrorObjective):
        return (
            0.5 * float(delta @ inputs.covariance @ delta),
            inputs.covariance @ delta,
        )
    risk = inputs.objective.risk_aversion
    return (
        (0.5 * risk * float(delta @ inputs.covariance @ delta))
        - float(inputs.expected_returns @ weights),
        (risk * (inputs.covariance @ delta)) - inputs.expected_returns,
    )


def _constraint_diagnostics(
    inputs: _Inputs,
    weights: _Array,
    *,
    tolerance: float,
) -> pd.DataFrame:
    rows: list[dict[str, float | bool]] = []
    names: list[str] = []
    for position, asset in enumerate(inputs.assets):
        _diagnostic_row(
            rows,
            names,
            name=f"weight:{asset}",
            value=float(weights[position]),
            lower=float(inputs.lower_weights[position]),
            upper=float(inputs.upper_weights[position]),
            tolerance=tolerance,
        )
    for constraint in inputs.constraints:
        if isinstance(constraint, GrossExposureConstraint):
            _diagnostic_row(
                rows,
                names,
                name="gross_exposure",
                value=float(np.abs(weights).sum()),
                lower=-math.inf,
                upper=constraint.maximum,
                tolerance=tolerance,
            )
        elif isinstance(constraint, NetExposureConstraint):
            _diagnostic_row(
                rows,
                names,
                name="net_exposure",
                value=float(weights.sum()),
                lower=constraint.minimum,
                upper=constraint.maximum,
                tolerance=tolerance,
            )
        elif isinstance(constraint, TurnoverConstraint):
            _diagnostic_row(
                rows,
                names,
                name="turnover",
                value=_turnover(weights, inputs.current_weights),
                lower=-math.inf,
                upper=constraint.maximum,
                tolerance=tolerance,
            )
        elif isinstance(constraint, FactorExposureConstraint):
            assert inputs.factor_exposures is not None
            values = weights @ inputs.factor_exposures.to_numpy(dtype=float)
            lower, upper = _factor_bounds(constraint, inputs.factor_exposures)
            for factor_position, factor in enumerate(inputs.factor_exposures.columns):
                _diagnostic_row(
                    rows,
                    names,
                    name=f"factor:{factor}",
                    value=float(values[factor_position]),
                    lower=float(lower[factor_position]),
                    upper=float(upper[factor_position]),
                    tolerance=tolerance,
                )
        elif isinstance(constraint, LinearExposureConstraint):
            values = weights @ constraint.loadings.to_numpy(dtype=float)
            lower, upper = _linear_bounds(constraint, inputs.assets)
            for exposure_position, exposure in enumerate(constraint.loadings.columns):
                _diagnostic_row(
                    rows,
                    names,
                    name=f"linear:{constraint.name}:{exposure}",
                    value=float(values[exposure_position]),
                    lower=float(lower[exposure_position]),
                    upper=float(upper[exposure_position]),
                    tolerance=tolerance,
                )
        elif isinstance(constraint, TrackingErrorConstraint):
            assert inputs.benchmark_weights is not None
            delta = weights - inputs.benchmark_weights
            value = math.sqrt(max(0.0, float(delta @ inputs.covariance @ delta)))
            _diagnostic_row(
                rows,
                names,
                name="tracking_error",
                value=value,
                lower=-math.inf,
                upper=constraint.maximum,
                tolerance=tolerance,
            )
    return pd.DataFrame(rows, index=pd.Index(names, name="constraint"), columns=_DIAGNOSTIC_COLUMNS)


def _diagnostic_row(
    rows: list[dict[str, float | bool]],
    names: list[str],
    *,
    name: str,
    value: float,
    lower: float,
    upper: float,
    tolerance: float,
) -> None:
    residuals: list[float] = []
    if math.isfinite(lower):
        residuals.append(value - lower)
    if math.isfinite(upper):
        residuals.append(upper - value)
    residual = min(residuals) if residuals else math.inf
    rows.append(
        {
            "value": value,
            "lower": lower,
            "upper": upper,
            "residual": residual,
            "binding": abs(residual) <= tolerance,
        }
    )
    names.append(name)


def _turnover(weights: _Array, current: _Array) -> float:
    difference = weights - current
    return 0.5 * (float(np.abs(difference).sum()) + abs(float(difference.sum())))


def _factor_exposure(exposures: pd.DataFrame | None, weights: _Array) -> pd.Series:
    if exposures is None:
        return pd.Series(dtype=float, name="factor_exposure")
    values = weights @ exposures.to_numpy(dtype=float)
    return pd.Series(values, index=exposures.columns.copy(), name="factor_exposure")


def _linear_exposure(
    constraints: tuple[LinearExposureConstraint, ...],
    weights: _Array,
) -> pd.Series:
    if not constraints:
        return pd.Series(dtype=float, name="linear_exposure")
    values: list[float] = []
    keys: list[tuple[str, object]] = []
    for constraint in constraints:
        exposure_values = weights @ constraint.loadings.to_numpy(dtype=float)
        values.extend(float(value) for value in exposure_values)
        keys.extend((constraint.name, column) for column in constraint.loadings.columns)
    index = pd.MultiIndex.from_tuples(keys, names=["constraint", "exposure"])
    return pd.Series(values, index=index, name="linear_exposure")


def _objective_breakdown(inputs: _Inputs, weights: _Array) -> pd.Series:
    variance = float(weights @ inputs.covariance @ weights)
    expected_term = 0.0
    risk_term = 0.5 * variance
    if isinstance(inputs.objective, MeanVarianceObjective):
        expected_term = -float(inputs.expected_returns @ weights)
        risk_term *= inputs.objective.risk_aversion
    elif isinstance(inputs.objective, MinimumTrackingErrorObjective | ActiveMeanVarianceObjective):
        assert inputs.benchmark_weights is not None
        delta = weights - inputs.benchmark_weights
        risk_term = 0.5 * float(delta @ inputs.covariance @ delta)
        if isinstance(inputs.objective, ActiveMeanVarianceObjective):
            expected_term = -float(inputs.expected_returns @ weights)
            risk_term *= inputs.objective.risk_aversion
    delta = weights - inputs.current_weights
    linear_cost = float(
        (inputs.buy_costs @ np.maximum(delta, 0.0)) + (inputs.sell_costs @ np.maximum(-delta, 0.0))
    )
    quadratic_cost = float(inputs.quadratic_costs @ np.square(delta))
    transaction_cost = linear_cost + quadratic_cost
    return pd.Series(
        {
            "expected_return_term": expected_term,
            "risk_term": risk_term,
            "linear_transaction_cost_term": linear_cost,
            "quadratic_transaction_cost_term": quadratic_cost,
            "transaction_cost_term": transaction_cost,
            "total": expected_term + risk_term + transaction_cost,
        },
        dtype=float,
    )


def _positive_float(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return float(value)
