"""Property tests for vintage-aware scalar-series intervals."""

from datetime import date

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from persistra.data import synthetic
from persistra.errors import DataValidationError
from persistra.model import VintageSeriesSet


@given(
    st.lists(
        st.dates(min_value=date(1900, 1, 1), max_value=date(2200, 1, 1)),
        min_size=2,
        max_size=12,
        unique=True,
    )
)
def test_daily_closed_intervals_accept_history_without_overlap(starts: list[date]) -> None:
    source, frame = _history(starts)

    result = VintageSeriesSet(source.definition, frame, source.metadata)

    for row in result.frame.itertuples(index=False):
        selected = result.frame[
            (result.frame["available_from"] <= row.available_from)
            & (
                result.frame["available_through"].isna()
                | (result.frame["available_through"] >= row.available_from)
            )
        ]
        assert len(selected) == 1


@given(
    st.lists(
        st.dates(min_value=date(1900, 1, 1), max_value=date(2200, 1, 1)),
        min_size=2,
        max_size=12,
        unique=True,
    )
)
def test_daily_closed_intervals_reject_shared_boundary(starts: list[date]) -> None:
    source, frame = _history(starts)
    frame.loc[0, "available_through"] = frame.loc[1, "available_from"]

    with pytest.raises(DataValidationError, match="must not overlap"):
        VintageSeriesSet(source.definition, frame, source.metadata)


def _history(starts: list[date]) -> tuple[VintageSeriesSet, pd.DataFrame]:
    source = synthetic.vintage_series(periods=1)
    ordered = pd.to_datetime(sorted(starts))
    frame = pd.concat([source.frame.iloc[[0]]] * len(ordered), ignore_index=True)
    frame["available_from"] = pd.Series(ordered, dtype="datetime64[ns]")
    frame["available_through"] = pd.Series(
        [*list(ordered[1:] - pd.Timedelta(days=1)), pd.NaT],
        dtype="datetime64[ns]",
    )
    frame["value"] = pd.Series(range(len(ordered)), dtype="Float64")
    return source, frame
