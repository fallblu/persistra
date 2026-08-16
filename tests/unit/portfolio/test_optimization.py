from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.portfolio import (
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
    PortfolioProblem,
    PortfolioSolverProblem,
    PortfolioSolverResult,
    QuadraticTransactionCostPenalty,
    ScipySlsqpSolver,
    TrackingErrorConstraint,
    TurnoverConstraint,
    WeightBounds,
    optimize_portfolio,
    optimize_portfolio_path,
)
from persistra.research import build_factor_risk_model

if TYPE_CHECKING:
    from collections.abc import Callable


class RecordingSolver:
    """Record the neutral problem before delegating to the default backend."""

    name = "recording-solver"

    def __init__(self) -> None:
        self.problem: PortfolioSolverProblem | None = None

    def solve(self, problem: PortfolioSolverProblem) -> PortfolioSolverResult:
        self.problem = problem
        return ScipySlsqpSolver().solve(problem)


def _assets() -> pd.Index:
    return pd.Index(["a", "b"], name="asset")


def _covariance(first: float = 1.0, second: float = 1.0) -> pd.DataFrame:
    assets = _assets()
    return pd.DataFrame(np.diag([first, second]), index=assets, columns=assets)


def _fully_invested() -> tuple[WeightBounds, NetExposureConstraint]:
    return WeightBounds(0.0, 1.0), NetExposureConstraint(1.0, 1.0)


def test_minimum_variance_matches_inverse_variance_solution() -> None:
    problem = PortfolioProblem(
        covariance=_covariance(0.04, 0.01),
        objective=MinimumVarianceObjective(),
        constraints=_fully_invested(),
    )

    result = optimize_portfolio(problem)

    assert result.weights.to_dict() == pytest.approx({"a": 0.2, "b": 0.8})
    assert result.cash == pytest.approx(0.0)
    assert result.variance == pytest.approx(0.008)
    assert result.exposures.to_dict() == pytest.approx(
        {"long": 1.0, "short": 0.0, "gross": 1.0, "net": 1.0, "cash": 0.0}
    )
    assert result.solver == "scipy-slsqp"
    assert result.iterations > 0
    assert (result.constraint_diagnostics["residual"] >= -1e-9).all()


def test_mean_variance_and_active_objectives_use_expected_returns() -> None:
    expected = pd.Series([0.1, 0.0], index=_assets())
    mean_variance = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=MeanVarianceObjective(risk_aversion=1.0),
            expected_returns=expected,
            constraints=_fully_invested(),
        )
    )
    active = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=ActiveMeanVarianceObjective(risk_aversion=1.0),
            expected_returns=expected,
            benchmark_weights=pd.Series([0.5, 0.5], index=_assets()),
            constraints=_fully_invested(),
        )
    )

    assert mean_variance.weights.tolist() == pytest.approx([0.55, 0.45])
    assert active.weights.tolist() == pytest.approx([0.55, 0.45])
    assert mean_variance.objective_breakdown["expected_return_term"] == pytest.approx(-0.055)
    assert active.tracking_error == pytest.approx(np.sqrt(0.005))


def test_tracking_error_objective_and_constraint_use_benchmark() -> None:
    benchmark = pd.Series([0.25, 0.75], index=_assets())
    tracking = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=MinimumTrackingErrorObjective(),
            benchmark_weights=benchmark,
            constraints=_fully_invested(),
        )
    )
    constrained = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=MeanVarianceObjective(risk_aversion=0.01),
            expected_returns=pd.Series([1.0, 0.0], index=_assets()),
            benchmark_weights=benchmark,
            constraints=(*_fully_invested(), TrackingErrorConstraint(0.1)),
        )
    )

    assert tracking.weights.tolist() == pytest.approx(benchmark.tolist())
    assert tracking.tracking_error == pytest.approx(0.0)
    assert constrained.tracking_error == pytest.approx(0.1, abs=1e-6)
    assert constrained.constraint_diagnostics.loc["tracking_error", "binding"]


def test_factor_exposure_and_gross_constraints_are_composable() -> None:
    exposures = pd.DataFrame({"style": [1.0, -1.0]}, index=_assets())
    factor_bounds = FactorExposureConstraint(
        lower=pd.Series({"style": 0.0}),
        upper=pd.Series({"style": 0.0}),
    )
    result = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=MeanVarianceObjective(),
            expected_returns=pd.Series([0.2, 0.0], index=_assets()),
            factor_exposures=exposures,
            constraints=(
                WeightBounds(-1.0, 1.0),
                GrossExposureConstraint(1.0),
                NetExposureConstraint(1.0, 1.0),
                factor_bounds,
            ),
        )
    )

    assert result.weights.tolist() == pytest.approx([0.5, 0.5])
    assert result.factor_exposures.to_dict() == pytest.approx({"style": 0.0})
    assert "factor:style" in result.constraint_diagnostics.index
    assert result.constraint_diagnostics.loc["gross_exposure", "binding"]


def test_generic_linear_exposure_constraints_are_named_and_composable() -> None:
    groups = LinearExposureConstraint(
        name="groups",
        loadings=pd.DataFrame(
            {"first": [1.0, 0.0], "second": [0.0, 1.0]},
            index=_assets(),
        ),
        lower=pd.Series({"first": 0.0, "second": 0.0}),
        upper=pd.Series({"first": 0.6, "second": 0.6}),
    )
    result = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=MeanVarianceObjective(0.01),
            expected_returns=pd.Series([0.2, 0.0], index=_assets()),
            constraints=(*_fully_invested(), groups),
        )
    )

    assert result.weights.to_dict() == pytest.approx({"a": 0.6, "b": 0.4})
    assert result.linear_exposures.loc[("groups", "first")] == pytest.approx(0.6)
    assert "linear:groups:first" in result.constraint_diagnostics.index


def test_covariance_policy_conditions_and_reports_indefinite_input() -> None:
    indefinite = _covariance()
    indefinite.iloc[0, 1] = indefinite.iloc[1, 0] = 2.0
    result = optimize_portfolio(
        PortfolioProblem(
            covariance=indefinite,
            covariance_policy=CovariancePolicy(minimum_eigenvalue=0.01),
            objective=MinimumVarianceObjective(),
            constraints=_fully_invested(),
        )
    )

    assert result.covariance_diagnostics["raw_minimum_eigenvalue"] == pytest.approx(-1.0)
    assert result.covariance_diagnostics["conditioned_minimum_eigenvalue"] == pytest.approx(0.01)
    assert result.covariance_diagnostics["frobenius_adjustment"] > 0.0

    shrunk = optimize_portfolio(
        PortfolioProblem(
            covariance=indefinite,
            covariance_policy=CovariancePolicy(diagonal_shrinkage=0.5),
            objective=MinimumVarianceObjective(),
            constraints=_fully_invested(),
        )
    )
    assert shrunk.covariance_diagnostics["diagonal_shrinkage"] == pytest.approx(0.5)
    assert shrunk.covariance_diagnostics["conditioned_minimum_eigenvalue"] == pytest.approx(0.0)


def test_covariance_and_linear_constraint_policies_validate_controls() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        CovariancePolicy(diagonal_shrinkage=1.1)
    with pytest.raises(ValueError, match="minimum_eigenvalue"):
        CovariancePolicy(minimum_eigenvalue=-0.1)

    invalid = LinearExposureConstraint(
        name="reversed",
        loadings=pd.DataFrame({"group": [1.0, 0.0]}, index=_assets()[::-1]),
        lower=pd.Series({"group": 0.0}),
        upper=pd.Series({"group": 1.0}),
    )
    with pytest.raises(ValueError, match="covariance asset index"):
        optimize_portfolio(
            PortfolioProblem(
                covariance=_covariance(),
                objective=MinimumVarianceObjective(),
                constraints=(invalid,),
            )
        )

    valid = replace(invalid, loadings=invalid.loadings.reindex(_assets()))
    invalid_controls = (
        (replace(valid, upper=pd.Series({"wrong": 1.0})), "loading columns"),
        (replace(valid, loadings=valid.loadings.astype(str)), "must be numeric"),
        (replace(valid, lower=pd.Series({"group": np.nan})), "must be finite"),
        (
            replace(
                valid,
                lower=pd.Series({"group": 2.0}),
                upper=pd.Series({"group": 1.0}),
            ),
            "must not exceed",
        ),
    )
    for constraint, message in invalid_controls:
        with pytest.raises(ValueError, match=message):
            optimize_portfolio(
                PortfolioProblem(
                    covariance=_covariance(),
                    objective=MinimumVarianceObjective(),
                    constraints=(constraint,),
                )
            )


def test_turnover_and_transaction_costs_use_current_realized_weights() -> None:
    current = pd.Series([1.0, 0.0], index=_assets())
    expected = pd.Series([0.0, 1.0], index=_assets())
    limited = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=MeanVarianceObjective(risk_aversion=0.01),
            expected_returns=expected,
            current_weights=current,
            constraints=(*_fully_invested(), TurnoverConstraint(0.2)),
        )
    )
    costly = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=MeanVarianceObjective(risk_aversion=1.0),
            expected_returns=pd.Series([0.0, 0.05], index=_assets()),
            current_weights=current,
            constraints=_fully_invested(),
            penalties=(LinearTransactionCostPenalty(1.0),),
        )
    )

    assert limited.weights.tolist() == pytest.approx([0.8, 0.2], abs=1e-7)
    assert limited.turnover == pytest.approx(0.2)
    assert limited.constraint_diagnostics.loc["turnover", "binding"]
    assert costly.weights.tolist() == pytest.approx(current.tolist())
    assert costly.objective_breakdown["transaction_cost_term"] == pytest.approx(0.0)


def test_asymmetric_and_quadratic_costs_reconcile_through_solver_boundary() -> None:
    assets = _assets()
    fixed = pd.Series([0.5, 0.5], index=assets)
    solver = RecordingSolver()
    result = optimize_portfolio(
        PortfolioProblem(
            covariance=_covariance(),
            objective=MinimumVarianceObjective(),
            current_weights=pd.Series([1.0, 0.0], index=assets),
            constraints=(WeightBounds(fixed, fixed),),
            penalties=(
                AsymmetricTransactionCostPenalty(
                    buy_rates=pd.Series([0.0, 0.02], index=assets),
                    sell_rates=pd.Series([0.01, 0.0], index=assets),
                ),
                QuadraticTransactionCostPenalty(pd.Series([0.1, 0.2], index=assets)),
            ),
        ),
        solver=solver,
    )

    assert result.weights.tolist() == pytest.approx([0.5, 0.5])
    assert result.objective_breakdown["linear_transaction_cost_term"] == pytest.approx(0.015)
    assert result.objective_breakdown["quadratic_transaction_cost_term"] == pytest.approx(0.075)
    assert result.objective_breakdown["transaction_cost_term"] == pytest.approx(0.09)
    assert result.solver == "recording-solver"
    evaluations = result.solver_statistics["function_evaluations"]
    assert isinstance(evaluations, int) and evaluations >= 1
    assert solver.problem is not None
    assert any(constraint.kind == "equality" for constraint in solver.problem.constraints)


def test_factor_risk_model_is_accepted_without_rebuilding_dense_inputs() -> None:
    dates = pd.date_range("2025-01-01", periods=4)
    exposures = pd.DataFrame({"factor": [1.0, -1.0]}, index=_assets())
    factor_returns = pd.DataFrame({"factor": [-0.02, 0.01, 0.03, -0.01]}, index=dates)
    residuals = pd.DataFrame(
        {"a": [-0.01, 0.00, 0.01, 0.00], "b": [0.00, 0.01, 0.00, -0.01]},
        index=dates,
    )
    risk = build_factor_risk_model(exposures, factor_returns, residuals)

    result = optimize_portfolio(
        PortfolioProblem(
            covariance=risk,
            objective=MinimumVarianceObjective(),
            constraints=_fully_invested(),
        )
    )

    assert result.weights.sum() == pytest.approx(1.0)
    weights = result.weights.to_numpy(dtype=float)
    expected_variance = float(weights @ risk.asset_covariance.to_numpy(dtype=float) @ weights)
    assert result.variance == pytest.approx(expected_variance)


def test_optimizer_reports_infeasible_and_invalid_problem_data() -> None:
    infeasible = PortfolioProblem(
        covariance=_covariance(),
        objective=MinimumVarianceObjective(),
        constraints=(GrossExposureConstraint(0.5), NetExposureConstraint(1.0, 1.0)),
    )
    with pytest.raises(AnalysisError, match="optimization failed"):
        optimize_portfolio(infeasible)

    indefinite = _covariance()
    indefinite.iloc[0, 1] = indefinite.iloc[1, 0] = 2.0
    with pytest.raises(AnalysisError, match="positive semidefinite"):
        optimize_portfolio(
            PortfolioProblem(
                covariance=indefinite,
                objective=MinimumVarianceObjective(),
            )
        )
    with pytest.raises(ValueError, match="expected_returns"):
        optimize_portfolio(
            PortfolioProblem(
                covariance=_covariance(),
                objective=MeanVarianceObjective(),
            )
        )
    with pytest.raises(ValueError, match="benchmark_weights"):
        optimize_portfolio(
            PortfolioProblem(
                covariance=_covariance(),
                objective=MinimumTrackingErrorObjective(),
            )
        )
    with pytest.raises(ValueError, match="current_weights"):
        optimize_portfolio(
            PortfolioProblem(
                covariance=_covariance(),
                objective=MinimumVarianceObjective(),
                constraints=(TurnoverConstraint(0.1),),
            )
        )


def test_optimization_path_carries_weights_and_holds_explicit_failures() -> None:
    dates = pd.date_range("2026-01-01", periods=3)
    first = PortfolioProblem(
        covariance=_covariance(),
        objective=MeanVarianceObjective(0.01),
        expected_returns=pd.Series([0.1, 0.0], index=_assets()),
        constraints=_fully_invested(),
        as_of=dates[0],
    )
    second = replace(
        first,
        expected_returns=pd.Series([0.0, 0.1], index=_assets()),
        as_of=dates[1],
    )
    infeasible = replace(
        first,
        constraints=(GrossExposureConstraint(0.5), NetExposureConstraint(1.0, 1.0)),
        as_of=dates[2],
    )

    path = optimize_portfolio_path(
        (first, second, infeasible),
        failure_policy="hold_previous",
    )

    assert [step.status for step in path.steps] == ["optimized", "optimized", "held"]
    assert path.steps[1].problem.current_weights is not None
    np.testing.assert_allclose(path.steps[1].problem.current_weights, path.weights.iloc[0])
    np.testing.assert_allclose(path.weights.iloc[2], path.weights.iloc[1])
    assert path.steps[2].result is None
    assert path.cash.index.equals(pd.DatetimeIndex(dates, name="as_of"))


def test_optimization_path_requires_ordered_dated_fixed_universe_problems() -> None:
    dated = PortfolioProblem(
        covariance=_covariance(),
        objective=MinimumVarianceObjective(),
        as_of=pd.Timestamp("2026-01-02"),
    )
    with pytest.raises(ValueError, match="as_of"):
        optimize_portfolio_path((replace(dated, as_of=None),))
    with pytest.raises(ValueError, match="strictly increasing"):
        optimize_portfolio_path((dated, replace(dated, as_of=pd.Timestamp("2026-01-01"))))
    changed_covariance = _covariance().rename(index={"b": "c"}, columns={"b": "c"})
    with pytest.raises(ValueError, match="fixed asset"):
        optimize_portfolio_path(
            (
                dated,
                replace(
                    dated,
                    covariance=changed_covariance,
                    as_of=pd.Timestamp("2026-01-03"),
                ),
            )
        )


def test_optimizer_validates_axes_bounds_controls_and_result_funding() -> None:
    covariance = _covariance()
    reversed_assets = _assets()[::-1]
    with pytest.raises(ValueError, match="covariance asset index"):
        optimize_portfolio(
            PortfolioProblem(
                covariance=covariance,
                objective=MeanVarianceObjective(),
                expected_returns=pd.Series([0.1, 0.2], index=reversed_assets),
            )
        )
    with pytest.raises(ValueError, match="lower weight bounds"):
        optimize_portfolio(
            PortfolioProblem(
                covariance=covariance,
                objective=MinimumVarianceObjective(),
                constraints=(WeightBounds(1.0, 0.0),),
            )
        )
    with pytest.raises(ValueError, match="repeat"):
        optimize_portfolio(
            PortfolioProblem(
                covariance=covariance,
                objective=MinimumVarianceObjective(),
                constraints=(WeightBounds(), WeightBounds()),
            )
        )
    with pytest.raises(ValueError, match="positive finite"):
        optimize_portfolio(
            PortfolioProblem(covariance=covariance, objective=MinimumVarianceObjective()),
            tolerance=0.0,
        )

    result = optimize_portfolio(
        PortfolioProblem(
            covariance=covariance,
            objective=MinimumVarianceObjective(),
            constraints=_fully_invested(),
        )
    )
    with pytest.raises(ValueError, match="sum to one"):
        replace(result, cash=0.5)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: MeanVarianceObjective(0.0), "risk_aversion"),
        (lambda: ActiveMeanVarianceObjective(-1.0), "risk_aversion"),
        (lambda: GrossExposureConstraint(-1.0), "gross exposure"),
        (lambda: NetExposureConstraint(1.0, 0.0), "must not exceed"),
        (lambda: TurnoverConstraint(-1.0), "turnover"),
        (lambda: TrackingErrorConstraint(-1.0), "tracking error"),
        (lambda: LinearTransactionCostPenalty(-1.0), "transaction cost"),
        (lambda: AsymmetricTransactionCostPenalty(-1.0, 0.0), "buy_rates"),
        (lambda: QuadraticTransactionCostPenalty(-1.0), "quadratic cost"),
    ],
)
def test_optimization_models_reject_invalid_scalars(
    factory: object,
    message: str,
) -> None:
    checked = cast("Callable[[], object]", factory)
    with pytest.raises(ValueError, match=message):
        checked()
