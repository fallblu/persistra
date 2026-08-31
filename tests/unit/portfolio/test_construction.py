"""Tests for transparent portfolio construction."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.portfolio import (
    PortfolioConstraints,
    PortfolioRiskControl,
    construct_portfolio,
    rebalance_schedule,
)


def test_equal_long_only_weights_cash_and_turnover_are_explicit() -> None:
    index = pd.date_range("2025-01-01", periods=2)
    signals = pd.DataFrame(
        [[1.0, 2.0, np.nan], [3.0, -1.0, 0.0]],
        index=index,
        columns=list("abc"),
    )

    result = construct_portfolio(
        signals,
        gross_target=0.75,
        constraints=PortfolioConstraints(
            gross_limit=1.0,
            net_minimum=0.0,
            net_maximum=1.0,
            position_limit=0.5,
        ),
    )

    assert result.weights.iloc[0].tolist() == pytest.approx([0.375, 0.375, 0.0])
    assert result.weights.iloc[1].tolist() == pytest.approx([0.25, 0.25, 0.25])
    assert result.cash.eq(0.25).all()
    assert result.exposures["gross"].eq(0.75).all()
    assert result.exposures["net"].eq(0.75).all()
    assert result.turnover.iloc[0] == pytest.approx(0.75)
    assert result.turnover.iloc[1] == pytest.approx(0.25)
    assert result.constraint_utilization.iloc[0]["gross"] == pytest.approx(0.75)


def test_constraint_tolerance_boundaries_are_inclusive() -> None:
    index = pd.date_range("2025-01-01", periods=1)
    positive = pd.DataFrame([[1.0]], index=index, columns=["asset"])
    upper = PortfolioConstraints(
        gross_limit=1.0,
        net_minimum=0.0,
        net_maximum=1.0,
        position_limit=2.0,
        tolerance=0.1,
    )

    long_result = construct_portfolio(positive, gross_target=1.1, constraints=upper)

    assert long_result.weights.iloc[0, 0] == pytest.approx(1.1)

    lower = PortfolioConstraints(
        gross_limit=1.0,
        net_minimum=-1.0,
        net_maximum=0.0,
        position_limit=2.0,
        tolerance=0.1,
    )
    short_result = construct_portfolio(
        -positive,
        configuration="long_short",
        gross_target=1.1,
        net_target=-1.1,
        constraints=lower,
    )

    assert short_result.weights.iloc[0, 0] == pytest.approx(-1.1)


def test_signal_proportional_long_short_redistributes_position_caps() -> None:
    signals = pd.DataFrame(
        [[1.0, 3.0, -1.0, -1.0]],
        index=pd.date_range("2025-01-01", periods=1),
        columns=list("abcd"),
    )
    constraints = PortfolioConstraints(
        gross_limit=1.0,
        net_minimum=0.0,
        net_maximum=0.0,
        position_limit=0.3,
    )

    result = construct_portfolio(
        signals,
        weighting="signal_proportional",
        configuration="long_short",
        constraints=constraints,
    )

    assert result.unconstrained_weights.iloc[0].tolist() == pytest.approx(
        [0.125, 0.375, -0.25, -0.25]
    )
    assert result.weights.iloc[0].tolist() == pytest.approx([0.2, 0.3, -0.25, -0.25])
    assert result.cash.iloc[0] == pytest.approx(1.0)
    assert result.exposures.iloc[0].to_dict() == pytest.approx(
        {"long": 0.5, "short": 0.5, "gross": 1.0, "net": 0.0, "cash": 1.0}
    )


def test_turnover_limit_blends_each_target_with_previous_weights() -> None:
    signals = pd.DataFrame(
        [[1.0, 1.0], [1.0, np.nan]],
        index=pd.date_range("2025-01-01", periods=2),
        columns=["a", "b"],
    )
    constraints = PortfolioConstraints(
        gross_limit=1.0,
        net_minimum=0.0,
        net_maximum=1.0,
        position_limit=1.0,
        turnover_limit=0.25,
    )

    result = construct_portfolio(signals, constraints=constraints)

    assert result.weights.iloc[0].tolist() == pytest.approx([0.125, 0.125])
    assert result.cash.iloc[0] == pytest.approx(0.75)
    assert result.weights.iloc[1].tolist() == pytest.approx([0.375, 0.089285714286])
    assert result.turnover.eq(0.25).all()
    assert result.constraint_utilization["turnover"].eq(1.0).all()


def test_covariance_target_scales_weights_and_reports_risk_contributions() -> None:
    date = pd.Timestamp("2025-01-01")
    signals = pd.DataFrame([[1.0, 1.0]], index=pd.DatetimeIndex([date]), columns=["a", "b"])
    covariance = pd.DataFrame(np.diag([0.04, 0.04]), index=signals.columns, columns=signals.columns)
    risk = PortfolioRiskControl(
        target_volatility=0.1,
        volatility_limit=0.1,
        periods_per_year=1,
    )

    result = construct_portfolio(
        signals,
        constraints=PortfolioConstraints(
            gross_limit=2.0,
            net_minimum=0.0,
            net_maximum=2.0,
            position_limit=1.0,
        ),
        covariances={date: covariance},
        risk_control=risk,
    )

    expected_scale = 0.1 / np.sqrt(0.02)
    assert result.weights.iloc[0].tolist() == pytest.approx(
        [0.5 * expected_scale, 0.5 * expected_scale]
    )
    assert result.predicted_volatility.iloc[0] == pytest.approx(0.1)
    assert result.risk_contributions.iloc[0].tolist() == pytest.approx([0.5, 0.5])
    assert result.cash.iloc[0] == pytest.approx(1.0 - expected_scale)
    assert result.constraint_utilization.iloc[0]["volatility"] == pytest.approx(1.0)


def test_construction_reports_clear_infeasibility_and_covariance_failures() -> None:
    date = pd.Timestamp("2025-01-01")
    signals = pd.DataFrame([[1.0, -1.0]], index=pd.DatetimeIndex([date]), columns=["a", "b"])
    with pytest.raises(AnalysisError, match="long-only portfolios"):
        construct_portfolio(signals, net_target=0.0)
    with pytest.raises(AnalysisError, match="gross target"):
        construct_portfolio(signals, gross_target=2.0)
    with pytest.raises(AnalysisError, match="long position capacity"):
        construct_portfolio(
            signals,
            configuration="long_short",
            constraints=PortfolioConstraints(position_limit=0.4),
        )
    with pytest.raises(ValueError, match="requires covariances"):
        construct_portfolio(signals, risk_control=PortfolioRiskControl(target_volatility=0.1))
    invalid_covariance = pd.DataFrame(
        [[1.0, 2.0], [0.0, 1.0]],
        index=signals.columns,
        columns=signals.columns,
    )
    with pytest.raises(AnalysisError, match="symmetric"):
        construct_portfolio(signals, covariances={date: invalid_covariance})


def test_construction_rejects_empty_sides_bad_axes_and_conflicting_risk_limits() -> None:
    date = pd.Timestamp("2025-01-01")
    signals = pd.DataFrame([[1.0, 2.0]], index=pd.DatetimeIndex([date]), columns=["a", "b"])
    with pytest.raises(AnalysisError, match="short side"):
        construct_portfolio(signals, configuration="long_short")
    with pytest.raises(ValueError, match="signal columns"):
        construct_portfolio(signals, initial_weights=pd.Series([0.0, 0.0], index=["b", "a"]))
    with pytest.raises(ValueError, match="target_volatility"):
        PortfolioRiskControl(target_volatility=0.2, volatility_limit=0.1)
    indefinite = pd.DataFrame(
        [[1.0, 2.0], [2.0, 1.0]],
        index=signals.columns,
        columns=signals.columns,
    )
    with pytest.raises(AnalysisError, match="positive semidefinite"):
        construct_portfolio(signals, covariances={date: indefinite})


def test_rebalance_schedules_choose_observed_calendar_boundaries() -> None:
    index = pd.bdate_range("2025-01-29", "2025-04-04")

    assert rebalance_schedule(index, frequency=10, anchor="start").equals(index[::10])
    assert rebalance_schedule(index, frequency="daily").equals(index)
    assert rebalance_schedule(index, frequency="monthly", anchor="start").tolist() == [
        pd.Timestamp("2025-01-29"),
        pd.Timestamp("2025-02-03"),
        pd.Timestamp("2025-03-03"),
        pd.Timestamp("2025-04-01"),
    ]
    assert rebalance_schedule(index, frequency="quarterly", anchor="end").tolist() == [
        pd.Timestamp("2025-03-31"),
        pd.Timestamp("2025-04-04"),
    ]
    with pytest.raises(ValueError, match="anchor='start'"):
        rebalance_schedule(index, frequency=5)
    with pytest.raises(ValueError, match="unsupported"):
        rebalance_schedule(index, frequency="yearly")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("signals", "error", "message"),
    [
        (pd.DataFrame([[1.0]], index=[0]), TypeError, "DatetimeIndex"),
        (
            pd.DataFrame([[1.0]], index=pd.DatetimeIndex([pd.NaT])),
            ValueError,
            "missing values",
        ),
        (
            pd.DataFrame([[1.0], [2.0]], index=pd.to_datetime(["2025-01-01"] * 2)),
            ValueError,
            "unique",
        ),
        (
            pd.DataFrame([[1.0], [2.0]], index=pd.to_datetime(["2025-01-02", "2025-01-01"])),
            ValueError,
            "sorted",
        ),
        (
            pd.DataFrame([[1.0]], index=pd.date_range("2025-01-01", periods=1), columns=[np.nan]),
            ValueError,
            "columns must not contain missing",
        ),
        (
            pd.DataFrame(
                [[1.0, 2.0]],
                index=pd.date_range("2025-01-01", periods=1),
                columns=["a", "a"],
            ),
            ValueError,
            "columns must be unique",
        ),
        (
            pd.DataFrame(index=pd.date_range("2025-01-01", periods=1)),
            ValueError,
            "at least one asset",
        ),
        (
            pd.DataFrame(
                index=pd.DatetimeIndex([]),
                columns=["a"],
                dtype=float,
            ),
            ValueError,
            "at least one observation",
        ),
        (
            pd.DataFrame([["x"]], index=pd.date_range("2025-01-01", periods=1)),
            AnalysisError,
            "numeric",
        ),
        (
            pd.DataFrame([[np.inf]], index=pd.date_range("2025-01-01", periods=1)),
            AnalysisError,
            "infinite",
        ),
    ],
)
def test_construction_validates_fixed_universe_panels(
    signals: pd.DataFrame,
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        construct_portfolio(signals)


def test_policy_models_reject_invalid_limits_and_timing_values() -> None:
    with pytest.raises(ValueError, match="net_minimum"):
        PortfolioConstraints(net_minimum=1.0, net_maximum=0.0)
    with pytest.raises(ValueError, match="gross_limit"):
        PortfolioConstraints(gross_limit=-1.0)
    with pytest.raises(ValueError, match="position_limit"):
        PortfolioConstraints(position_limit=-1.0)
    with pytest.raises(ValueError, match="turnover_limit"):
        PortfolioConstraints(turnover_limit=-1.0)
    with pytest.raises(ValueError, match="tolerance"):
        PortfolioConstraints(tolerance=np.inf)
    with pytest.raises(ValueError, match="periods_per_year"):
        PortfolioRiskControl(periods_per_year=0.0)
    with pytest.raises(ValueError, match="target_volatility"):
        PortfolioRiskControl(target_volatility=-0.1)
    with pytest.raises(ValueError, match="volatility_limit"):
        PortfolioRiskControl(volatility_limit=-0.1)
    with pytest.raises(ValueError, match="covariance_tolerance"):
        PortfolioRiskControl(covariance_tolerance=-1.0)


def test_additional_exposure_side_and_initial_weight_failures_are_explicit() -> None:
    date = pd.Timestamp("2025-01-01")
    signals = pd.DataFrame([[1.0, -1.0]], index=pd.DatetimeIndex([date]), columns=["a", "b"])
    with pytest.raises(ValueError, match="unsupported weighting"):
        construct_portfolio(signals, weighting="ranked")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported portfolio"):
        construct_portfolio(signals, configuration="market_neutral")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="gross_target"):
        construct_portfolio(signals, gross_target=-1.0)
    with pytest.raises(AnalysisError, match="absolute net"):
        construct_portfolio(signals, configuration="long_short", net_target=2.0)
    with pytest.raises(AnalysisError, match="net target"):
        construct_portfolio(
            signals,
            configuration="long_short",
            net_target=0.5,
            constraints=PortfolioConstraints(net_minimum=-0.1, net_maximum=0.1),
        )
    with pytest.raises(AnalysisError, match="finite"):
        construct_portfolio(
            signals,
            initial_weights=pd.Series([np.nan, 0.0], index=signals.columns),
        )
    with pytest.raises(AnalysisError, match="gross limit"):
        construct_portfolio(
            signals,
            initial_weights=pd.Series([2.0, 0.0], index=signals.columns),
        )
    with pytest.raises(AnalysisError, match="eligible assets"):
        construct_portfolio(
            signals.mul(-1).abs().mul(-1),
            weighting="signal_proportional",
        )


def test_zero_gross_negative_net_and_volatility_ceiling_paths_are_supported() -> None:
    date = pd.Timestamp("2025-01-01")
    signals = pd.DataFrame([[1.0, 1.0, -1.0, -1.0]], index=[date], columns=list("abcd"))
    all_cash = construct_portfolio(
        signals,
        gross_target=0.0,
        constraints=PortfolioConstraints(
            gross_limit=0.0,
            net_minimum=0.0,
            net_maximum=0.0,
            position_limit=0.0,
        ),
    )
    assert all_cash.weights.eq(0).all(axis=None)
    assert all_cash.cash.iloc[0] == 1.0
    negative_net = construct_portfolio(
        signals,
        configuration="long_short",
        net_target=-0.5,
        constraints=PortfolioConstraints(
            gross_limit=1.0,
            net_minimum=-1.0,
            net_maximum=0.0,
            position_limit=0.5,
        ),
    )
    assert negative_net.exposures.iloc[0]["net"] == pytest.approx(-0.5)
    assert negative_net.constraint_utilization.iloc[0]["net"] == pytest.approx(0.5)

    covariance = pd.DataFrame(np.eye(4) * 0.04, index=signals.columns, columns=signals.columns)
    limited = construct_portfolio(
        signals,
        configuration="long_short",
        covariances={date: covariance},
        risk_control=PortfolioRiskControl(volatility_limit=0.08, periods_per_year=1),
    )
    assert limited.predicted_volatility.iloc[0] == pytest.approx(0.08)


def test_covariance_and_interacting_risk_constraints_fail_transparently() -> None:
    date = pd.Timestamp("2025-01-01")
    signals = pd.DataFrame([[1.0, 1.0]], index=[date], columns=["a", "b"])
    covariance = pd.DataFrame(np.diag([0.04, 0.04]), index=signals.columns, columns=signals.columns)
    with pytest.raises(ValueError, match="missing for"):
        construct_portfolio(signals, covariances={})
    with pytest.raises(ValueError, match="axes"):
        construct_portfolio(signals, covariances={date: covariance.rename(columns={"a": "x"})})
    with pytest.raises(AnalysisError, match="numeric"):
        construct_portfolio(signals, covariances={date: covariance.astype(str)})
    nonfinite = covariance.copy()
    nonfinite.iloc[0, 0] = np.nan
    with pytest.raises(AnalysisError, match="finite"):
        construct_portfolio(signals, covariances={date: nonfinite})
    zero_covariance = covariance.mul(0.0)
    with pytest.raises(AnalysisError, match="positive volatility target"):
        construct_portfolio(
            signals,
            covariances={date: zero_covariance},
            risk_control=PortfolioRiskControl(target_volatility=0.1, periods_per_year=1),
        )
    zero_target = construct_portfolio(
        signals,
        covariances={date: zero_covariance},
        risk_control=PortfolioRiskControl(target_volatility=0.0, periods_per_year=1),
    )
    assert zero_target.weights.eq(0).all(axis=None)

    net_floor = PortfolioConstraints(
        gross_limit=1.0,
        net_minimum=0.8,
        net_maximum=1.0,
        position_limit=1.0,
    )
    with pytest.raises(AnalysisError, match="net and volatility"):
        construct_portfolio(
            signals,
            constraints=net_floor,
            covariances={date: covariance},
            risk_control=PortfolioRiskControl(
                target_volatility=0.05,
                volatility_limit=0.05,
                periods_per_year=1,
            ),
        )
    no_turnover = PortfolioConstraints(
        gross_limit=1.0,
        net_minimum=0.0,
        net_maximum=1.0,
        position_limit=1.0,
        turnover_limit=0.0,
    )
    with pytest.raises(AnalysisError, match="turnover and volatility"):
        construct_portfolio(
            signals,
            constraints=no_turnover,
            covariances={date: covariance},
            risk_control=PortfolioRiskControl(volatility_limit=0.1, periods_per_year=1),
            initial_weights=pd.Series([1.0, 0.0], index=signals.columns),
        )


def test_construction_result_rejects_misaligned_or_unfunded_outputs() -> None:
    signals = pd.DataFrame(
        [[1.0, 1.0], [2.0, 1.0]],
        index=pd.date_range("2025-01-01", periods=2),
        columns=["a", "b"],
    )
    result = construct_portfolio(signals)
    with pytest.raises(ValueError, match="target-weight axes"):
        replace(result, risk_contributions=result.risk_contributions.iloc[:-1])
    with pytest.raises(ValueError, match="target-weight index"):
        replace(result, turnover=result.turnover.iloc[:-1])
    with pytest.raises(ValueError, match="target-weight index"):
        replace(result, exposures=result.exposures.iloc[:-1])
    with pytest.raises(ValueError, match="sum to one"):
        replace(result, cash=result.cash.add(0.1))
