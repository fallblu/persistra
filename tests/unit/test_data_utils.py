"""Tests for explicit data reshaping and alignment."""

import pandas as pd
import pytest

from persistra.data import align, asof_align, pivot_bars, pivot_series, resample_bars, synthetic
from persistra.errors import DataValidationError
from persistra.model import BarSet


def _labeled_intraday_bars(
    timestamps: list[str],
    *,
    timestamp_position: str,
    prices: list[float] | None = None,
) -> BarSet:
    source = synthetic.bars("DEMO", periods=len(timestamps), interval="5min")
    frame = source.frame.copy()
    frame["timestamp"] = pd.to_datetime(timestamps, utc=True).as_unit("ns")
    frame["timestamp_position"] = pd.Series(
        [timestamp_position] * len(frame), dtype="string"
    )
    if prices is not None:
        frame["open"] = prices
        frame["high"] = [price + 1 for price in prices]
        frame["low"] = [price - 1 for price in prices]
        frame["close"] = prices
    return BarSet(source.instrument, frame, source.metadata)


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


def test_pivots_reject_duplicate_output_identities() -> None:
    bars = synthetic.bars("AAA", periods=2)
    series = synthetic.series("GDP", periods=2)
    with pytest.raises(DataValidationError, match="duplicate bar pivot identity"):
        pivot_bars([bars, bars], field="close")
    with pytest.raises(DataValidationError, match="duplicate series pivot identity"):
        pivot_series([series, series])


def test_pivot_bars_rejects_mixed_temporal_rows_inside_one_input() -> None:
    daily = synthetic.bars("AAA", periods=2)
    intraday = synthetic.bars("AAA", periods=2, interval="5min")
    frame = (
        pd.concat([daily.frame, intraday.frame], ignore_index=True)
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
    mixed = BarSet(daily.instrument, frame, daily.metadata)

    with pytest.raises(DataValidationError, match="mixed temporal labels"):
        pivot_bars([mixed], field="close")


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


@pytest.mark.parametrize("how", ["intersection", "union"])
@pytest.mark.parametrize(
    "value",
    [
        pd.Series([1.0, 2.0], index=[1, 1]),
        pd.DataFrame({"value": [1.0, 2.0]}, index=[1, 1]),
    ],
)
def test_alignment_rejects_duplicate_input_indexes(
    how: str, value: pd.Series | pd.DataFrame
) -> None:
    with pytest.raises(DataValidationError, match=r"input 'duplicate'.*duplicate label"):
        align({"valid": pd.Series([3.0], index=[2]), "duplicate": value}, how=how)


def test_resample_bars_marks_output_as_derived() -> None:
    intraday = _labeled_intraday_bars(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
            "2025-01-03T00:00:00Z",
            "2025-01-04T00:00:00Z",
        ],
        timestamp_position="start",
    )
    result = resample_bars(
        intraday,
        frequency="2D",
        timezone="UTC",
        sessions={"all"},
    )
    assert result.metadata.provider == "persistra"
    assert set(result.frame["provider"]) == {"persistra"}
    assert result.metadata.retrieved_at == intraday.metadata.retrieved_at
    assert result.metadata.diagnostics[0].field == "derived"
    assert set(result.frame["timestamp_position"]) == {"start"}
    repeated = resample_bars(
        intraday,
        frequency="2D",
        timezone="UTC",
        sessions={"all"},
    )
    assert repeated.metadata == result.metadata
    pd.testing.assert_frame_equal(repeated.frame, result.frame)
    with pytest.raises(DataValidationError, match="intraday"):
        resample_bars(
            synthetic.bars(periods=3),
            frequency="2D",
            timezone="UTC",
            sessions={"not_applicable"},
        )


@pytest.mark.parametrize(
    ("timestamp_position", "timestamps"),
    [
        ("start", ["2025-01-02T14:30:00Z", "2025-01-02T14:35:00Z"]),
        ("end", ["2025-01-02T14:35:00Z", "2025-01-02T14:40:00Z"]),
    ],
)
def test_resample_bars_honors_source_timestamp_position(
    timestamp_position: str, timestamps: list[str]
) -> None:
    source = _labeled_intraday_bars(
        timestamps,
        timestamp_position=timestamp_position,
        prices=[100.0, 110.0],
    )

    result = resample_bars(
        source,
        frequency="10min",
        timezone="America/New_York",
        sessions={"all"},
    )

    assert result.frame["timestamp"].tolist() == [pd.Timestamp("2025-01-02T14:30:00Z")]
    assert result.frame.iloc[0]["open"] == 100.0
    assert result.frame.iloc[0]["close"] == 110.0
    assert result.metadata.request_parameters["source_timestamp_position"] == timestamp_position
    assert result.metadata.request_parameters["output_timestamp_position"] == "start"


@pytest.mark.parametrize(
    ("timestamp_position", "expected_label"),
    [
        ("start", "2025-01-02T14:30:00Z"),
        ("end", "2025-01-02T14:20:00Z"),
    ],
)
def test_resample_bars_assigns_session_boundary_labels(
    timestamp_position: str, expected_label: str
) -> None:
    source = _labeled_intraday_bars(
        ["2025-01-02T14:30:00Z"], timestamp_position=timestamp_position
    )

    result = resample_bars(
        source,
        frequency="10min",
        timezone="America/New_York",
        sessions={"all"},
    )

    assert result.frame.iloc[0]["timestamp"] == pd.Timestamp(expected_label)


def test_resample_bars_handles_daylight_saving_boundary() -> None:
    source = _labeled_intraday_bars(
        ["2025-03-09T06:55:00Z", "2025-03-09T07:00:00Z"],
        timestamp_position="start",
    )

    result = resample_bars(
        source,
        frequency="10min",
        timezone="America/New_York",
        sessions={"all"},
    )

    local_labels = result.frame["timestamp"].dt.tz_convert("America/New_York")
    assert local_labels.tolist() == [
        pd.Timestamp("2025-03-09T01:50:00-05:00"),
        pd.Timestamp("2025-03-09T03:00:00-04:00"),
    ]


def test_resample_bars_rejects_ambiguous_source_timestamp_positions() -> None:
    provider_labeled = synthetic.bars("DEMO", periods=2, interval="5min")
    with pytest.raises(DataValidationError, match="provider_label"):
        resample_bars(
            provider_labeled,
            frequency="10min",
            timezone="UTC",
            sessions={"all"},
        )

    mixed = provider_labeled.frame.copy()
    mixed["timestamp_position"] = pd.Series(["start", "end"], dtype="string")
    with pytest.raises(DataValidationError, match="one supported"):
        resample_bars(
            BarSet(provider_labeled.instrument, mixed, provider_labeled.metadata),
            frequency="10min",
            timezone="UTC",
            sessions={"all"},
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


@pytest.mark.parametrize("timezone", [None, "UTC"])
@pytest.mark.parametrize(("left_unit", "right_unit"), [("ns", "us"), ("us", "ns")])
def test_asof_alignment_normalizes_datetime_resolutions(
    timezone: str | None,
    left_unit: str,
    right_unit: str,
) -> None:
    timezone_suffix = "" if timezone is None else f", {timezone}"
    left = pd.DataFrame(
        {"market": [1.0, 2.0]},
        index=pd.DatetimeIndex(
            ["2026-01-02T00:00:00", "2026-01-10T00:00:00"],
            dtype=f"datetime64[{left_unit}{timezone_suffix}]",
        ),
    )
    right = pd.DataFrame(
        {"economic": [10.0]},
        index=pd.DatetimeIndex(
            ["2026-01-01T00:00:00"],
            dtype=f"datetime64[{right_unit}{timezone_suffix}]",
        ),
    )
    original_left = left.copy(deep=True)
    original_right = right.copy(deep=True)

    result = asof_align(left, right, maximum_staleness=pd.Timedelta(days=2))

    assert result.index.dtype == left.index.dtype
    assert result.index.equals(left.index)
    assert result["matched_label"].dtype == right.index.dtype
    assert result.iloc[0]["matched_label"] == right.index[0]
    assert result.iloc[0]["matched_age"] == pd.Timedelta(days=1)
    assert pd.isna(result.iloc[1]["matched_label"])
    assert pd.isna(result.iloc[1]["matched_age"])
    pd.testing.assert_frame_equal(left, original_left)
    pd.testing.assert_frame_equal(right, original_right)


@pytest.mark.parametrize(
    "right_dtype",
    ["datetime64[us]", "datetime64[us, America/New_York]"],
)
def test_asof_alignment_rejects_incompatible_timezones(right_dtype: str) -> None:
    left = pd.DataFrame(
        {"market": [1.0]},
        index=pd.DatetimeIndex(["2026-01-02T00:00:00Z"], dtype="datetime64[ns, UTC]"),
    )
    right = pd.DataFrame(
        {"economic": [10.0]},
        index=pd.DatetimeIndex(["2026-01-01T00:00:00"], dtype=right_dtype),
    )

    with pytest.raises(pd.errors.MergeError, match="incompatible merge keys"):
        asof_align(left, right, maximum_staleness=pd.Timedelta(days=2))


def test_asof_alignment_rejects_duplicate_source_labels() -> None:
    left = pd.DataFrame({"market": [1.0]}, index=pd.to_datetime(["2025-01-02"]))
    right = pd.DataFrame(
        {"signal": [10.0, 20.0]},
        index=pd.to_datetime(["2025-01-01", "2025-01-01"]),
    )

    for source in (right, right.iloc[::-1]):
        with pytest.raises(DataValidationError, match=r"source index.*duplicate label"):
            asof_align(left, source, maximum_staleness=pd.Timedelta(days=2))


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("name", ["left_label", "matched_label", "matched_age"])
def test_asof_alignment_rejects_reserved_input_columns(side: str, name: str) -> None:
    left = pd.DataFrame({"market": [1.0]}, index=pd.to_datetime(["2025-01-02"]))
    right = pd.DataFrame({"signal": [10.0]}, index=pd.to_datetime(["2025-01-01"]))
    target = left if side == "left" else right
    target[name] = 99.0

    with pytest.raises(DataValidationError, match="reserved output names"):
        asof_align(left, right, maximum_staleness=pd.Timedelta(days=2))


def test_asof_alignment_rejects_suffix_collisions() -> None:
    left = pd.DataFrame(
        {"value": [1.0], "value_right": [2.0]},
        index=pd.to_datetime(["2025-01-02"]),
    )
    right = pd.DataFrame({"value": [10.0]}, index=pd.to_datetime(["2025-01-01"]))

    with pytest.raises(DataValidationError, match=r"collide after suffixing.*value_right"):
        asof_align(left, right, maximum_staleness=pd.Timedelta(days=2))
