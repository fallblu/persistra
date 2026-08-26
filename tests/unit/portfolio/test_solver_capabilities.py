"""Alternative continuous and exact discrete portfolio solver coverage."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.portfolio import (
    CvxpyMixedIntegerSolver,
    CvxpySolver,
    DiscretePortfolioProblem,
    DiscretePortfolioSolverProblem,
    LinearTransactionCostPenalty,
    MeanVarianceObjective,
    MinimumVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    PortfolioSolverCapabilities,
    PortfolioSolverResult,
    QuadraticTransactionCostPenalty,
    ScipySlsqpSolver,
    TrackingErrorConstraint,
    TurnoverConstraint,
    WeightBounds,
    optimize_discrete_portfolio,
    optimize_portfolio,
)


def _assets() -> pd.Index:
    return pd.Index(["a", "b", "c"], name="asset")


def _covariance() -> pd.DataFrame:
    assets = _assets()
    return pd.DataFrame(np.diag([0.04, 0.01, 0.02]), index=assets, columns=assets)


def test_cvxpy_capabilities_and_reference_solution_match_slsqp() -> None:
    pytest.importorskip("cvxpy")
    problem = PortfolioProblem(
        covariance=_covariance(),
        objective=MeanVarianceObjective(risk_aversion=0.5),
        expected_returns=pd.Series([0.08, 0.04, 0.03], index=_assets()),
        constraints=(WeightBounds(0.0, 0.8), NetExposureConstraint(1.0, 1.0)),
    )

    slsqp = optimize_portfolio(problem, solver=ScipySlsqpSolver())
    convex = optimize_portfolio(problem, solver=CvxpySolver())

    assert convex.weights.tolist() == pytest.approx(slsqp.weights.tolist(), abs=2e-5)
    assert convex.solver == "cvxpy-clarabel"
    assert convex.solver_statistics["status"] == "optimal"
    assert "tracking_error" not in CvxpySolver().capabilities.constraints
    assert "tracking_error" in ScipySlsqpSolver().capabilities.constraints


def test_cvxpy_rejects_unsupported_tracking_error_constraint() -> None:
    assets = _assets()
    problem = PortfolioProblem(
        covariance=_covariance(),
        objective=MinimumVarianceObjective(),
        benchmark_weights=pd.Series([0.4, 0.3, 0.3], index=assets),
        constraints=(
            WeightBounds(0.0, 1.0),
            NetExposureConstraint(1.0, 1.0),
            TrackingErrorConstraint(0.2),
        ),
    )

    with pytest.raises(ValueError, match="constraint:tracking_error"):
        optimize_portfolio(problem, solver=CvxpySolver())


def test_cvxpy_cross_checks_trade_penalties_and_turnover_against_slsqp() -> None:
    pytest.importorskip("cvxpy")
    assets = _assets()
    problem = PortfolioProblem(
        covariance=_covariance(),
        objective=MeanVarianceObjective(risk_aversion=0.5),
        expected_returns=pd.Series([0.08, 0.04, 0.03], index=assets),
        current_weights=pd.Series([0.7, 0.2, 0.1], index=assets),
        constraints=(
            WeightBounds(0.0, 0.8),
            NetExposureConstraint(1.0, 1.0),
            TurnoverConstraint(0.2),
        ),
        penalties=(
            LinearTransactionCostPenalty(0.001),
            QuadraticTransactionCostPenalty(0.01),
        ),
    )

    slsqp = optimize_portfolio(problem, solver=ScipySlsqpSolver())
    convex = optimize_portfolio(problem, solver=CvxpySolver())

    assert convex.weights.tolist() == pytest.approx(slsqp.weights.tolist(), abs=2e-6)
    assert convex.objective_breakdown["total"] == pytest.approx(
        slsqp.objective_breakdown["total"], abs=1e-8
    )


def test_discrete_solver_enforces_cardinality_minimum_positions_and_lots() -> None:
    pytest.importorskip("cvxpy")
    assets = _assets()
    problem = DiscretePortfolioProblem(
        covariance=_covariance(),
        prices=pd.Series([10.0, 20.0, 25.0], index=assets),
        capital=100.0,
        objective=MeanVarianceObjective(risk_aversion=0.1),
        expected_returns=pd.Series([0.20, 0.10, 0.05], index=assets),
        maximum_positions=2,
        minimum_position_weight=0.2,
        maximum_position_weight=pd.Series([0.6, 0.6, 0.6], index=assets),
        lot_sizes=pd.Series([2, 1, 1], index=assets),
        minimum_invested_weight=0.9,
    )

    result = optimize_discrete_portfolio(problem)

    assert result.status == "optimal"
    assert result.solver == "cvxpy-scip"
    assert result.cash >= -1e-9
    assert result.weights.sum() >= 0.9 - 1e-9
    assert (result.holdings % problem.lot_sizes == 0).all()
    selected = result.weights[result.weights > 1e-9]
    assert len(selected) <= 2
    assert (selected >= 0.2 - 1e-9).all()
    assert (selected <= 0.6 + 1e-9).all()
    assert result.lower_bound == pytest.approx(result.upper_bound)
    assert result.solver_statistics["relative_gap"] == pytest.approx(0.0)
    assert CvxpyMixedIntegerSolver().capabilities.mixed_integer


def test_discrete_problem_rejects_infeasible_and_invalid_inputs() -> None:
    assets = _assets()
    base = DiscretePortfolioProblem(
        covariance=_covariance(),
        prices=pd.Series([60.0, 70.0, 80.0], index=assets),
        capital=100.0,
        objective=MinimumVarianceObjective(),
        maximum_positions=1,
        maximum_position_weight=0.5,
        minimum_invested_weight=0.9,
    )
    with pytest.raises(AnalysisError, match="infeasible"):
        optimize_discrete_portfolio(base)
    with pytest.raises(ValueError, match="positive integer"):
        optimize_discrete_portfolio(replace(base, lot_sizes=0, minimum_invested_weight=0.0))
    with pytest.raises(ValueError, match="expected_returns"):
        optimize_discrete_portfolio(
            replace(
                base,
                objective=MeanVarianceObjective(),
                minimum_invested_weight=0.0,
            )
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"prices": pd.Series([-1.0, 2.0, 3.0], index=_assets())}, "positive"),
        ({"prices": pd.Series([1.0, 2.0, 3.0], index=_assets()[::-1])}, "index"),
        ({"lot_sizes": pd.Series([1.0, 1.5, 2.0], index=_assets())}, "integers"),
        ({"lot_sizes": pd.Series([True, False, True], index=_assets())}, "integers"),
        ({"maximum_position_weight": 1.1}, "must not exceed"),
        ({"minimum_position_weight": 1.1}, "must not exceed"),
        (
            {
                "maximum_position_weight": pd.Series(
                    [0.1, 0.1, 0.1], index=_assets()
                ),
                "minimum_position_weight": 0.2,
            },
            "must not exceed maximum",
        ),
    ],
)
def test_discrete_problem_validates_exact_input_contracts(
    change: dict[str, object], message: str
) -> None:
    base = DiscretePortfolioProblem(
        covariance=_covariance(),
        prices=pd.Series([10.0, 20.0, 30.0], index=_assets()),
        capital=100.0,
        objective=MinimumVarianceObjective(),
    )
    with pytest.raises((TypeError, ValueError), match=message):
        optimize_discrete_portfolio(replace(base, **change))  # type: ignore[arg-type]


def test_discrete_solver_capabilities_and_return_values_are_enforced() -> None:
    assets = _assets()
    problem = DiscretePortfolioProblem(
        covariance=_covariance(),
        prices=pd.Series([10.0, 20.0, 25.0], index=assets),
        capital=100.0,
        objective=MinimumVarianceObjective(),
    )

    class ContinuousOnly:
        name = "continuous-only"
        capabilities = CvxpySolver().capabilities

        def solve(self, problem: DiscretePortfolioSolverProblem) -> PortfolioSolverResult:
            raise AssertionError(problem)

    with pytest.raises(ValueError, match="not mixed-integer capable"):
        optimize_discrete_portfolio(problem, solver=ContinuousOnly())

    class Unsupported:
        name = "unsupported"
        capabilities = PortfolioSolverCapabilities(
            objectives=frozenset(),
            penalties=frozenset(),
            constraints=frozenset(),
            mixed_integer=True,
        )

        def solve(self, problem: DiscretePortfolioSolverProblem) -> PortfolioSolverResult:
            raise AssertionError(problem)

    with pytest.raises(ValueError, match="objective:minimum_variance"):
        optimize_discrete_portfolio(problem, solver=Unsupported())


def test_normalized_solver_result_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unsupported portfolio solver status"):
        PortfolioSolverResult(
            values=np.zeros(1),
            success=False,
            message="bad",
            iterations=0,
            statistics={},
            status="unknown",  # type: ignore[arg-type]
        )
