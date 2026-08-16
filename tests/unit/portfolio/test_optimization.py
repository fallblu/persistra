from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.portfolio import (
    ActiveMeanVarianceObjective,
    FactorExposureConstraint,
    GrossExposureConstraint,
    LinearTransactionCostPenalty,
    MeanVarianceObjective,
    MinimumTrackingErrorObjective,
    MinimumVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    TrackingErrorConstraint,
    TurnoverConstraint,
    WeightBounds,
    optimize_portfolio,
)
from persistra.research import build_factor_risk_model

if TYPE_CHECKING:
    from collections.abc import Callable


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
    ],
)
def test_optimization_models_reject_invalid_scalars(
    factory: object,
    message: str,
) -> None:
    checked = cast("Callable[[], object]", factory)
    with pytest.raises(ValueError, match=message):
        checked()
