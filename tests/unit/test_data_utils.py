"""Tests for explicit data reshaping and alignment."""

import pandas as pd
import pytest

from persistra.data import align, asof_align, pivot_bars, pivot_series, resample_bars, synthetic
from persistra.errors import DataValidationError


def test_pivot_bars_and_series_require_explicit_compatibility() -> None:
    first = synthetic.bars("AAA", periods=3)
    second = synthetic.bars("BBB", periods=3)
    wide = pivot_bars([first, second], field="close")
    assert wide.shape == (3, 2)
    with pytest.raises(ValueError, match="supported"):
        pivot_bars([first], field="return")
    with pytest.raises(DataValidationError, match="temporal"):
        pivot_bars([first, synthetic.bars("INTRA", periods=3, interval="5min")], field="close")
    series = pivot_series([synthetic.series("A"), synthetic.series("B")])
    assert series.shape[1] == 2
    incompatible = synthetic.series("C", frequency="annual")
    with pytest.raises(DataValidationError, match="frequencies"):
        pivot_series([synthetic.series("A"), incompatible])
    assert pivot_bars([], field="close").empty
    assert pivot_series([]).empty


def test_alignment_never_fills_values() -> None:
    first = pd.Series([1.0, 2.0], index=[1, 2])
    second = pd.Series([3.0, 4.0], index=[2, 3])
    intersection = align({"a": first, "b": second}, how="intersection")
    assert list(intersection["a"].index) == [2]
    union = align({"a": first, "b": second}, how="union")
    assert isinstance(union["a"], pd.Series)
    assert pd.isna(union["a"].loc[3])
    assert len(align({})) == 0
    with pytest.raises(ValueError, match="how"):
        align({"a": first}, how="left")


def test_resample_bars_marks_output_as_derived() -> None:
    intraday = synthetic.bars(periods=4, interval="5min")
    result = resample_bars(
        intraday,
        frequency="2D",
        timezone="UTC",
        sessions={"all"},
    )
    assert result.metadata.provider == "persistra"
    assert result.metadata.diagnostics[0].field == "derived"
    assert set(result.frame["timestamp_position"]) == {"start"}
    with pytest.raises(DataValidationError, match="intraday"):
        resample_bars(
            synthetic.bars(periods=3),
            frequency="2D",
            timezone="UTC",
            sessions={"not_applicable"},
        )


def test_asof_alignment_reports_age_and_staleness() -> None:
    left = pd.DataFrame({"market": [1.0, 2.0]}, index=pd.to_datetime(["2025-01-02", "2025-01-05"]))
    right = pd.DataFrame({"economic": [10.0]}, index=pd.to_datetime(["2025-01-01"]))
    result = asof_align(left, right, maximum_staleness=pd.Timedelta(days=2))
    assert result.iloc[0]["matched_age"] == pd.Timedelta(days=1)
    assert pd.isna(result.iloc[1]["economic"])
    with pytest.raises(ValueError, match="positive"):
        asof_align(left, right, maximum_staleness=pd.Timedelta(0))
    with pytest.raises(TypeError, match="DatetimeIndex"):
        asof_align(left.reset_index(drop=True), right, maximum_staleness=pd.Timedelta(days=1))
