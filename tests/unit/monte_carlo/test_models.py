"""Tests for Monte Carlo distributions, models, and calibration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import pytest

from persistra.monte_carlo import (
    Distribution,
    EmpiricalDistribution,
    GeometricBrownianMotion,
    MonteCarloExperiment,
    MovingBlockBootstrap,
    MultivariateNormalDistribution,
    MultivariateNormalReturns,
    NormalDistribution,
    StudentTDistribution,
    fit_geometric_brownian_motion,
    run_experiment,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.random import Generator
    from numpy.typing import NDArray


@dataclass(frozen=True)
class FixedDistribution:
    """Structural custom distribution used to verify the public protocol."""

    value: float

    @property
    def name(self) -> str:
        return "fixed"

    @property
    def version(self) -> str:
        return "1"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"value": self.value}

    def sample(
        self,
        generator: Generator,
        size: tuple[int, ...],
    ) -> NDArray[np.float64]:
        del generator
        return np.full(size, self.value)


def labeled_parameters() -> tuple[pd.Series, pd.DataFrame]:
    """Return aligned two-variable annual moments."""
    labels = pd.Index(["left", "right"])
    mean = pd.Series([0.08, 0.12], index=labels)
    covariance = pd.DataFrame([[0.04, 0.015], [0.015, 0.09]], index=labels, columns=labels)
    return mean, covariance


def test_univariate_and_custom_distributions_follow_declared_moments() -> None:
    generator = np.random.default_rng(11)
    normal = NormalDistribution(mean=2.0, standard_deviation=3.0)
    student = StudentTDistribution(5.0, location=-1.0, scale=2.0)
    empirical = EmpiricalDistribution((-2.0, 1.0, 4.0))
    custom: Distribution = FixedDistribution(7.0)

    normal_draws = normal.sample(generator, (100_000,))
    student_draws = student.sample(generator, (100_000,))
    empirical_draws = empirical.sample(generator, (10_000,))
    custom_draws = custom.sample(generator, (2, 3))

    assert normal_draws.mean() == pytest.approx(2.0, abs=0.03)
    assert normal_draws.std() == pytest.approx(3.0, abs=0.03)
    assert student_draws.mean() == pytest.approx(-1.0, abs=0.04)
    assert student_draws.var() == pytest.approx(20.0 / 3.0, rel=0.05)
    assert set(np.unique(empirical_draws)) <= {-2.0, 1.0, 4.0}
    np.testing.assert_array_equal(custom_draws, np.full((2, 3), 7.0))
    assert normal.parameters == {"mean": 2.0, "standard_deviation": 3.0}
    assert student.name == "student_t" and empirical.version == "1"


def test_multivariate_distribution_matches_labeled_moments() -> None:
    mean, covariance = labeled_parameters()
    distribution = MultivariateNormalDistribution(mean, covariance)

    draws = distribution.sample(np.random.default_rng(13), (120_000,))

    assert draws.shape == (120_000, 2)
    np.testing.assert_allclose(draws.mean(axis=0), mean, atol=0.002)
    np.testing.assert_allclose(np.cov(draws, rowvar=False), covariance, atol=0.0015)
    assert distribution.variable_names == ("left", "right")


def test_multivariate_return_model_matches_scaled_moments() -> None:
    mean, covariance = labeled_parameters()
    result = run_experiment(
        MonteCarloExperiment(
            MultivariateNormalReturns(mean, covariance, return_kind="log"),
            pd.Index(["year"], name="time"),
            (0.5,),
            path_count=20_000,
            root_seed=21,
        )
    )

    assert result.paths is not None
    draws = result.paths[:, 0, :]
    np.testing.assert_allclose(draws.mean(axis=0), mean.to_numpy() * 0.5, atol=0.003)
    np.testing.assert_allclose(np.cov(draws, rowvar=False), covariance * 0.5, atol=0.002)
    assert result.manifest["model"]["output_semantics"] == "log_return"


def test_geometric_brownian_motion_is_positive_and_matches_expected_level() -> None:
    mean, covariance = labeled_parameters()
    initial = pd.Series([100.0, 50.0], index=mean.index)
    result = run_experiment(
        MonteCarloExperiment(
            GeometricBrownianMotion(initial, mean, covariance),
            pd.Index(["year"], name="time"),
            (1.0,),
            path_count=20_000,
            root_seed=23,
        )
    )

    assert result.paths is not None
    terminal = result.paths[:, 0, :]
    assert (terminal > 0).all()
    expected = initial.to_numpy() * np.exp(mean.to_numpy())
    np.testing.assert_allclose(terminal.mean(axis=0), expected, rtol=0.015)


def test_moving_block_bootstrap_preserves_joint_rows_and_short_sequences() -> None:
    history = pd.DataFrame(
        {"left": [1.0, 2.0, 3.0, 4.0], "right": [10.0, 20.0, 30.0, 40.0]},
        index=pd.RangeIndex(4),
    )
    model = MovingBlockBootstrap(history, block_length=2)

    path = model.generate(np.random.default_rng(5), np.ones(7))

    assert path.shape == (7, 2)
    assert all(tuple(row) in {(1.0, 10.0), (2.0, 20.0), (3.0, 30.0), (4.0, 40.0)} for row in path)
    for position in (0, 2, 4):
        assert path[position + 1, 0] == path[position, 0] + 1.0
    with pytest.raises(ValueError, match="time_steps"):
        model.generate(np.random.default_rng(5), np.array([0.5]))


def test_gbm_calibration_uses_caller_log_returns_and_annualization() -> None:
    log_returns = pd.DataFrame(
        {"left": [0.01, 0.03, -0.01], "right": [0.02, -0.01, 0.04]},
        index=pd.date_range("2025-01-01", periods=3),
    )
    initial = pd.Series({"left": 102.0, "right": 55.0})

    model = fit_geometric_brownian_motion(
        log_returns,
        initial_prices=initial,
        periods_per_year=12,
    )

    expected_covariance = log_returns.cov() * 12
    expected_drift = log_returns.mean() * 12 + np.diag(expected_covariance) / 2
    pd.testing.assert_series_equal(model.initial_prices, initial)
    pd.testing.assert_frame_equal(model.covariance, expected_covariance)
    np.testing.assert_allclose(model.drift, expected_drift)


@pytest.mark.parametrize(
    "covariance",
    [
        pd.DataFrame([[1.0, 0.0]], index=["left"], columns=["left", "right"]),
        pd.DataFrame([[1.0, 0.5], [0.0, 1.0]], index=["left", "right"], columns=["left", "right"]),
        pd.DataFrame([[1.0, 2.0], [2.0, 1.0]], index=["left", "right"], columns=["left", "right"]),
    ],
)
def test_models_reject_misaligned_nonsymmetric_and_non_psd_covariance(
    covariance: pd.DataFrame,
) -> None:
    mean = pd.Series([0.0, 0.0], index=["left", "right"])
    with pytest.raises(ValueError):
        MultivariateNormalReturns(mean, covariance)


def test_distributions_and_models_reject_invalid_parameters() -> None:
    mean, covariance = labeled_parameters()
    with pytest.raises(ValueError, match="positive"):
        NormalDistribution(standard_deviation=0)
    with pytest.raises(ValueError, match="positive"):
        StudentTDistribution(0)
    with pytest.raises(ValueError, match="must not be empty"):
        EmpiricalDistribution(())
    with pytest.raises(ValueError, match="dimensions"):
        NormalDistribution().sample(np.random.default_rng(), (-1,))
    with pytest.raises(ValueError, match="return_kind"):
        MultivariateNormalReturns(mean, covariance, return_kind="level")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="initial price axis"):
        GeometricBrownianMotion(
            pd.Series([100.0, 50.0], index=mean.index),
            mean.rename(index={"left": "other"}),
            covariance,
        )
    with pytest.raises(ValueError, match="must not exceed"):
        MovingBlockBootstrap(pd.DataFrame({"asset": [0.1]}), block_length=2)
    history = pd.DataFrame({"asset": [0.1, np.nan]})
    with pytest.raises(ValueError, match="finite and complete"):
        MovingBlockBootstrap(history, block_length=1)


def test_model_parameters_are_defensive_copies() -> None:
    mean, covariance = labeled_parameters()
    model = MultivariateNormalReturns(mean, covariance)
    mean.iloc[0] = 999.0
    covariance.iloc[0, 0] = 999.0

    assert model.mean.iloc[0] == 0.08
    assert model.covariance.iloc[0, 0] == 0.04


def test_calibration_rejects_implicit_missing_policy_and_invalid_axes() -> None:
    initial = pd.Series({"left": 100.0})
    with pytest.raises(ValueError, match="at least two"):
        fit_geometric_brownian_motion(
            pd.DataFrame({"left": [0.01]}),
            initial_prices=initial,
            periods_per_year=252,
        )
    with pytest.raises(ValueError, match="finite and complete"):
        fit_geometric_brownian_motion(
            pd.DataFrame({"left": [0.01, np.nan]}),
            initial_prices=initial,
            periods_per_year=252,
        )
    with pytest.raises(ValueError, match="initial price axis"):
        fit_geometric_brownian_motion(
            pd.DataFrame({"other": [0.01, 0.02]}),
            initial_prices=initial,
            periods_per_year=252,
        )
