"""Tests for market and economic analysis."""

from dataclasses import replace
from typing import cast

import numpy as np
import pandas as pd
import pytest

from persistra.analysis import (
    absolute_spread,
    bar_range,
    basis_point_change,
    growth_rate,
    midprice,
    realized_volatility,
    relative_spread,
    session_coverage,
    true_range,
    volume_summary,
    yield_curve,
    yield_curve_history,
)
from persistra.data import synthetic
from persistra.errors import AnalysisError
from persistra.model import BarSet, SeriesSet, TopOfBookSet


def test_market_spreads_ranges_volume_and_coverage() -> None:
    book = synthetic.top_of_book(("AAA",))
    assert midprice(book).loc[0, "midprice"] == 100
    assert absolute_spread(book).loc[0, "absolute_spread"] == pytest.approx(0.2)
    assert relative_spread(book).loc[0, "relative_spread"] == pytest.approx(0.002)
    bars = synthetic.bars(periods=3)
    assert bar_range(bars)["bar_range"].gt(0).all()
    true = true_range(bars)
    assert true.loc[0, "true_range"] == pytest.approx(
        cast("float", bars.frame.loc[0, "high"])
        - cast("float", bars.frame.loc[0, "low"])
    )
    assert volume_summary(bars)["count"] == 3
    assert session_coverage(bars).loc[0, "observed_count"] == 3
    values = pd.DataFrame({"return": [0.01, 0.02, -0.01]})
    assert realized_volatility(values, window=2, periods_per_year=12).iloc[-1].notna().all()


def test_market_spreads_preserve_locked_crossed_and_missing_states() -> None:
    book = synthetic.top_of_book(("LOCKED", "CROSSED", "ONE_SIDED", "MISSING"))
    frame = book.frame.copy()
    frame.loc[0, ["bid_price", "ask_price"]] = [100.0, 100.0]
    frame.loc[1, ["bid_price", "ask_price"]] = [101.0, 100.0]
    frame.loc[2, ["ask_price", "ask_size"]] = pd.NA
    frame.loc[3, ["bid_price", "bid_size", "ask_price", "ask_size"]] = pd.NA
    book = TopOfBookSet(frame, book.metadata)

    spread = absolute_spread(book)["absolute_spread"]

    assert spread.iloc[0] == 0
    assert spread.iloc[1] == -1
    assert pd.isna(spread.iloc[2])
    assert pd.isna(spread.iloc[3])


def test_true_range_isolates_every_normalized_bar_path() -> None:
    source = synthetic.bars("AAA", periods=2, interval="5min", session="all")
    frames: list[pd.DataFrame] = []
    paths = [
        ("5min", "all", "raw", 100.0),
        ("15min", "all", "raw", 10.0),
        ("5min", "regular", "raw", 30.0),
        ("5min", "all", "adjusted", 50.0),
    ]
    for interval, session, price_adjustment, first_close in paths:
        frame = source.frame.copy()
        frame["interval"] = pd.Series([interval] * len(frame), dtype="string")
        frame["session"] = pd.Series([session] * len(frame), dtype="string")
        frame["price_adjustment"] = pd.Series(
            [price_adjustment] * len(frame), dtype="string"
        )
        frame["open"] = [first_close, first_close + 10]
        frame["high"] = [first_close + 1, first_close + 12]
        frame["low"] = [first_close - 1, first_close + 8]
        frame["close"] = [first_close, first_close + 10]
        frames.append(frame)
    combined = (
        pd.concat(frames, ignore_index=True)
        .sort_values(
            [
                "instrument_id",
                "interval",
                "price_adjustment",
                "session",
                "date",
                "timestamp",
            ],
            kind="stable",
            na_position="last",
        )
        .reset_index(drop=True)
    )
    bars = BarSet(source.instrument, combined, source.metadata)

    result = true_range(bars)

    identity = [
        "instrument_id",
        "interval",
        "price_adjustment",
        "session",
        "date",
        "timestamp",
    ]
    pd.testing.assert_frame_equal(result[identity], bars.frame[identity])
    for _, values in result.groupby(
        ["instrument_id", "interval", "price_adjustment", "session"], sort=False
    ):
        assert values["true_range"].tolist() == [2.0, 12.0]


def test_rate_change_and_growth_conventions() -> None:
    rates = pd.DataFrame({"rate": [4.0, 4.25, 4.0]})
    assert basis_point_change(rates, rate_unit="percent").loc[1, "rate"] == 25
    assert basis_point_change(rates / 100, rate_unit="decimal").loc[1, "rate"] == pytest.approx(25)
    assert basis_point_change(rates * 100, rate_unit="basis_points").loc[1, "rate"] == 25
    assert growth_rate(pd.DataFrame({"x": [100.0, 110.0]})).loc[1, "x"] == pytest.approx(0.1)
    with pytest.raises(ValueError, match="rate_unit"):
        basis_point_change(rates, rate_unit="percentage")
    with pytest.raises(ValueError, match="lag"):
        growth_rate(rates, lag=0)


@pytest.mark.parametrize(
    "invalid",
    [
        pd.DataFrame({"x": ["100", "110"]}),
        pd.DataFrame({"x": [False, True]}),
        pd.DataFrame({"x": [1.0, np.inf]}),
        pd.DataFrame({"x": [1.0, -np.inf]}),
    ],
)
def test_economic_changes_reject_invalid_wide_frames(invalid: pd.DataFrame) -> None:
    with pytest.raises(AnalysisError, match=r"numeric|infinite"):
        growth_rate(invalid)
    with pytest.raises(AnalysisError, match=r"numeric|infinite"):
        basis_point_change(invalid, rate_unit="percent")


def test_growth_masks_zero_bases_and_preserves_missing_values() -> None:
    levels = pd.DataFrame({"x": [0.0, 1.0, np.nan, 2.0, 4.0]})

    growth = growth_rate(levels)
    changes = basis_point_change(levels, rate_unit="basis_points")

    assert growth["x"].iloc[:4].isna().all()
    assert growth.loc[4, "x"] == 1.0
    assert not np.isinf(growth.to_numpy(dtype=float, na_value=np.nan)).any()
    assert changes["x"].iloc[2:4].isna().all()


def treasury(maturity: str) -> SeriesSet:
    """Create a synthetic Treasury series with one explicit maturity."""
    result = synthetic.series(f"TREASURY_{maturity}", periods=2)
    definition = replace(result.definition, maturity=maturity, unit="percent")
    frame = result.frame.copy()
    frame["maturity"] = maturity
    frame["maturity"] = frame["maturity"].astype("string")
    frame["unit"] = "percent"
    frame["unit"] = frame["unit"].astype("string")
    return SeriesSet(definition, frame, result.metadata)


def test_yield_curve_and_history_preserve_observations() -> None:
    series = [treasury("3month"), treasury("10year")]
    label = series[0].frame.loc[0, "period_label"]
    assert isinstance(label, str)
    curve = yield_curve(series, period_label=label)
    assert list(curve["maturity_years"]) == [0.25, 10.0]
    history = yield_curve_history(series)
    assert set(history.columns) == {"3month", "10year"}
    with pytest.raises(AnalysisError, match="no Treasury"):
        yield_curve(series, period_label="1900-01-01")
    with pytest.raises(AnalysisError, match="at least one"):
        yield_curve_history([])
    with pytest.raises(AnalysisError, match="supported"):
        yield_curve_history([treasury("1year")])
    incompatible = treasury("2year")
    incompatible = SeriesSet(
        replace(incompatible.definition, unit="decimal"),
        incompatible.frame.assign(unit="decimal").astype({"unit": "string"}),
        incompatible.metadata,
    )
    with pytest.raises(AnalysisError, match="compatible"):
        yield_curve_history([treasury("3month"), incompatible])
