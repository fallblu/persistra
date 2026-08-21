"""Tests for market and economic analysis."""

from dataclasses import replace
from typing import cast

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
from persistra.model import SeriesSet


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
