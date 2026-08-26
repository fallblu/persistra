"""Tests for consistent public integer parameter contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd
import pytest

from persistra._validation import require_integer
from persistra.analysis import absolute_change, basis_point_change, growth_rate, rolling_mean
from persistra.data import synthetic
from persistra.portfolio import BacktestTiming, optimize_portfolio, rebalance_schedule
from persistra.research import (
    fit_time_series_factor_model,
    forward_returns,
    information_coefficients,
    quantile_portfolios,
    rolling_time_series_factor_model,
    rolling_window_splits,
    standardize_cross_section,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from persistra.portfolio import PortfolioProblem


@pytest.mark.parametrize(
    "value",
    [True, 2.0, 2.5, object()],
    ids=["boolean", "integral-float", "fractional-float", "other"],
)
def test_public_count_and_lag_parameters_reject_nonintegers(value: object) -> None:
    frame, signals, labels, factor = _research_inputs()
    integer = cast("int", value)
    calls: tuple[tuple[str, Callable[[], object]], ...] = (
        ("window", lambda: rolling_mean(frame, window=integer)),
        (
            "min_periods",
            lambda: rolling_mean(frame, window=3, min_periods=integer),
        ),
        ("periods", lambda: absolute_change(frame, periods=integer)),
        (
            "periods",
            lambda: basis_point_change(
                frame,
                rate_unit="decimal",
                periods=integer,
            ),
        ),
        ("lag", lambda: growth_rate(frame, lag=integer)),
        (
            "train_size",
            lambda: rolling_window_splits(
                labels,
                train_size=integer,
                evaluation_size=1,
            ),
        ),
        (
            "evaluation_size",
            lambda: rolling_window_splits(
                labels,
                train_size=3,
                evaluation_size=integer,
            ),
        ),
        (
            "step",
            lambda: rolling_window_splits(
                labels,
                train_size=3,
                evaluation_size=1,
                step=integer,
            ),
        ),
        (
            "embargo",
            lambda: rolling_window_splits(
                labels,
                train_size=3,
                evaluation_size=1,
                embargo=integer,
            ),
        ),
        (
            "quantiles",
            lambda: quantile_portfolios(signals, labels, quantiles=integer),
        ),
        (
            "minimum_count",
            lambda: information_coefficients(
                signals,
                labels,
                minimum_count=integer,
            ),
        ),
        ("holding_period", lambda: BacktestTiming(holding_period=integer)),
        ("decision_lag", lambda: BacktestTiming(decision_lag=integer)),
        ("execution_lag", lambda: BacktestTiming(execution_lag=integer)),
        (
            "maximum_iterations",
            lambda: optimize_portfolio(
                cast("PortfolioProblem", object()),
                maximum_iterations=integer,
            ),
        ),
        ("horizon", lambda: forward_returns(frame, horizon=integer)),
        ("periods", lambda: synthetic.bars(periods=integer)),
        ("periods", lambda: synthetic.series(periods=integer)),
        ("periods", lambda: synthetic.vintage_series(periods=integer)),
        ("periods", lambda: synthetic.treasury_curve(periods=integer)),
        (
            "window",
            lambda: rolling_time_series_factor_model(
                frame,
                factor,
                window=integer,
            ),
        ),
        (
            "minimum_observations",
            lambda: rolling_time_series_factor_model(
                frame,
                factor,
                window=None,
                minimum_observations=integer,
            ),
        ),
        (
            "hac_lags",
            lambda: fit_time_series_factor_model(
                frame,
                factor,
                covariance="newey_west",
                hac_lags=integer,
            ),
        ),
        ("ddof", lambda: standardize_cross_section(signals, ddof=integer)),
        (
            "frequency",
            lambda: rebalance_schedule(
                cast("pd.DatetimeIndex", frame.index),
                frequency=integer,
                anchor="start",
            ),
        ),
    )

    for name, call in calls:
        with pytest.raises(ValueError, match=rf"{name} must be an integer"):
            call()


@pytest.mark.parametrize("value", [np.int32(2), np.int64(2)])
def test_numpy_integers_are_normalized_at_public_boundaries(value: np.integer) -> None:
    frame, _, labels, _ = _research_inputs()

    assert require_integer(value, name="value") == 2
    assert type(require_integer(value, name="value")) is int
    assert len(rolling_mean(frame, window=cast("int", value))) == len(frame)
    assert len(synthetic.bars(periods=cast("int", value)).frame) == 2
    assert rolling_window_splits(
        labels,
        train_size=cast("int", value),
        evaluation_size=1,
    )
    timing = BacktestTiming(
        decision_lag=cast("int", value),
        execution_lag=cast("int", value),
        holding_period=cast("int", value),
    )
    assert type(timing.decision_lag) is int
    assert type(timing.execution_lag) is int
    assert type(timing.holding_period) is int


@pytest.mark.parametrize("value", [0, -1])
def test_positive_integer_contracts_reject_zero_and_negatives(value: int) -> None:
    frame, _, labels, _ = _research_inputs()

    with pytest.raises(ValueError, match="window must be a positive integer"):
        rolling_mean(frame, window=value)
    with pytest.raises(ValueError, match="lag must be a positive integer"):
        growth_rate(frame, lag=value)
    with pytest.raises(ValueError, match="min_periods must be a positive integer"):
        rolling_mean(frame, window=2, min_periods=value)
    with pytest.raises(ValueError, match="holding_period must be a positive integer"):
        BacktestTiming(holding_period=value)
    with pytest.raises(ValueError, match="train_size must be a positive integer"):
        rolling_window_splits(labels, train_size=value, evaluation_size=1)
    with pytest.raises(ValueError, match="maximum_iterations must be a positive integer"):
        optimize_portfolio(
            cast("PortfolioProblem", object()),
            maximum_iterations=value,
        )


def test_minimum_integer_contracts_enforce_their_declared_bounds() -> None:
    _, signals, labels, _ = _research_inputs()

    with pytest.raises(ValueError, match="quantiles must be an integer of at least 2"):
        quantile_portfolios(signals, labels, quantiles=1)
    with pytest.raises(ValueError, match="minimum_count must be an integer of at least 2"):
        information_coefficients(signals, labels, minimum_count=1)
    with pytest.raises(ValueError, match="embargo must be a nonnegative integer"):
        rolling_window_splits(
            labels,
            train_size=3,
            evaluation_size=1,
            embargo=-1,
        )


def test_nonnegative_integer_contracts_accept_zero_and_reject_negatives() -> None:
    assert synthetic.bars(periods=0).frame.empty
    assert BacktestTiming(decision_lag=0, execution_lag=0).decision_lag == 0

    with pytest.raises(ValueError, match="periods must be a nonnegative integer"):
        synthetic.bars(periods=-1)
    with pytest.raises(ValueError, match="decision_lag must be a nonnegative integer"):
        BacktestTiming(decision_lag=-1)
    with pytest.raises(ValueError, match="execution_lag must be a nonnegative integer"):
        BacktestTiming(execution_lag=-1)


@pytest.mark.parametrize(
    "factory",
    [
        synthetic.bars,
        synthetic.series,
        synthetic.vintage_series,
        synthetic.treasury_curve,
    ],
)
def test_every_synthetic_period_count_accepts_zero_and_rejects_negatives(
    factory: Callable[..., object],
) -> None:
    factory(periods=0)
    with pytest.raises(ValueError, match="periods must be a nonnegative integer"):
        factory(periods=-1)


def _research_inputs() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    Any,
    pd.DataFrame,
]:
    index = pd.date_range("2025-01-01", periods=8)
    frame = pd.DataFrame(
        {
            "AAA": np.linspace(100.0, 107.0, len(index)),
            "BBB": np.linspace(90.0, 97.0, len(index)),
            "CCC": np.linspace(110.0, 117.0, len(index)),
        },
        index=index,
    )
    signals = frame.pct_change(fill_method=None).fillna(0.0)
    labels = forward_returns(frame, horizon=1)
    factor = pd.DataFrame(
        {"market": np.linspace(-0.02, 0.02, len(index))},
        index=index,
    )
    return frame.pct_change(fill_method=None), signals, labels, factor
