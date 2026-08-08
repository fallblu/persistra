"""Tests for point-in-time vintage selection and feature construction."""

from datetime import date

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from persistra.data import synthetic
from persistra.errors import AnalysisError
from persistra.model import VintageSeriesSet
from persistra.research import FeatureSpec, build_feature_panel, select_vintage


def test_select_vintage_uses_availability_and_explicit_lag() -> None:
    source = synthetic.vintage_series(periods=1)

    assert select_vintage(source, known_on="2023-02-14").frame.empty
    initial = select_vintage(source, known_on="2023-02-15")
    assert initial.frame.iloc[0]["value"] == 100.0
    assert initial.known_on == pd.Timestamp("2023-02-15")
    revised = select_vintage(source, known_on="2023-05-16")
    assert revised.frame.iloc[0]["value"] == 100.25

    lagged = select_vintage(
        source,
        known_on="2023-02-16",
        publication_lag=pd.Timedelta(days=2),
    )
    assert lagged.frame.empty
    assert lagged.publication_lag == pd.Timedelta(days=2)


def test_feature_panel_records_policy_and_selected_source_versions() -> None:
    source = synthetic.vintage_series(periods=4)
    spec = FeatureSpec(
        "growth",
        source,
        maximum_staleness=pd.Timedelta(days=61),
        publication_lag=pd.Timedelta(days=1),
    )
    dates = pd.DatetimeIndex(["2023-02-15", "2023-02-16", "2023-06-01"])

    result = build_feature_panel([spec], decision_dates=dates)

    assert pd.isna(result.frame.loc["2023-02-15", "growth"])
    assert result.frame.loc["2023-02-16", "growth"] == 100.0
    assert result.frame.loc["2023-06-01", "growth"] == 103.0
    assert len(result.provenance) == len(dates)
    selected = result.provenance.iloc[-1]
    assert selected["period_label"] == "2023-04-01"
    assert selected["observation_date"] == pd.Timestamp("2023-04-01")
    assert selected["available_from"] == pd.Timestamp("2023-05-16")
    assert selected["matched_age"] == pd.Timedelta(days=61)
    assert selected["publication_lag"] == pd.Timedelta(days=1)
    assert selected["maximum_staleness"] == pd.Timedelta(days=61)
    assert selected["source_retrieved_at"] == source.metadata.retrieved_at
    assert result.policies[0].provider_series == "SYNTH_GDP"
    assert result.policies[0].observation_date_column == "period_start"


def test_feature_panel_preserves_missing_and_deleted_latest_observations() -> None:
    source = synthetic.vintage_series(periods=2)
    frame = source.frame.copy()
    latest = frame["period_start"].eq(pd.Timestamp("2023-02-01"))
    frame.loc[latest, "value"] = pd.NA
    frame.loc[latest, "is_deleted"] = True
    deleted = VintageSeriesSet(source.definition, frame, source.metadata)

    result = build_feature_panel(
        [FeatureSpec("value", deleted, pd.Timedelta(days=90))],
        decision_dates=pd.DatetimeIndex(["2023-04-01"]),
    )

    assert pd.isna(result.frame.iloc[0, 0])
    assert bool(result.provenance.iloc[0]["is_deleted"])
    assert result.provenance.iloc[0]["period_label"] == "2023-02-01"


def test_feature_panel_requires_explicit_compatible_policies() -> None:
    source = synthetic.vintage_series(periods=1)
    empty = build_feature_panel([], decision_dates=pd.DatetimeIndex(["2023-01-01"]))
    assert empty.frame.empty
    assert empty.provenance.empty
    with pytest.raises(ValueError, match="unique"):
        build_feature_panel(
            [
                FeatureSpec("same", source, pd.Timedelta(days=1)),
                FeatureSpec("same", source, pd.Timedelta(days=2)),
            ],
            decision_dates=pd.DatetimeIndex(["2023-01-01"]),
        )
    with pytest.raises(ValueError, match="whole calendar days"):
        FeatureSpec("x", source, pd.Timedelta(hours=12))
    with pytest.raises(ValueError, match="period_start or period_end"):
        FeatureSpec(
            "x",
            source,
            pd.Timedelta(days=1),
            observation_date_column="period_label",
        )
    with pytest.raises(ValueError, match="timezone-naive"):
        build_feature_panel(
            [FeatureSpec("x", source, pd.Timedelta(days=1))],
            decision_dates=pd.DatetimeIndex(["2023-01-01T00:00:00Z"]),
        )
    with pytest.raises(ValueError, match="calendar date"):
        select_vintage(source, known_on="2023-01-01T12:00:00")


def test_feature_panel_rejects_stale_and_ambiguous_observation_dates() -> None:
    source = synthetic.vintage_series(periods=2)
    stale = build_feature_panel(
        [FeatureSpec("value", source, pd.Timedelta(0))],
        decision_dates=pd.DatetimeIndex(["2023-02-16"]),
    )
    assert pd.isna(stale.frame.iloc[0, 0])
    assert pd.isna(stale.provenance.iloc[0]["observation_date"])

    frame = source.frame.copy()
    second_period = frame["period_start"].eq(pd.Timestamp("2023-02-01"))
    frame.loc[second_period, "period_start"] = pd.Timestamp("2023-01-01")
    ambiguous = VintageSeriesSet(source.definition, frame, source.metadata)
    with pytest.raises(AnalysisError, match="ambiguous observations"):
        build_feature_panel(
            [FeatureSpec("value", ambiguous, pd.Timedelta(days=90))],
            decision_dates=pd.DatetimeIndex(["2023-04-01"]),
        )


@given(
    earlier=st.dates(min_value=date(2023, 2, 15), max_value=date(2023, 10, 1)),
    later=st.dates(min_value=date(2023, 2, 15), max_value=date(2023, 10, 1)),
)
def test_moving_decision_backward_never_selects_a_later_vintage(
    earlier: date,
    later: date,
) -> None:
    source = synthetic.vintage_series(periods=1)
    first, second = sorted((earlier, later))
    first_selection = select_vintage(source, known_on=first).frame
    second_selection = select_vintage(source, known_on=second).frame

    if not first_selection.empty and not second_selection.empty:
        assert first_selection.iloc[0]["available_from"] <= second_selection.iloc[0][
            "available_from"
        ]


@given(st.floats(min_value=-1_000, max_value=1_000, allow_nan=False, allow_infinity=False))
def test_future_observations_cannot_change_an_earlier_feature_panel(future_value: float) -> None:
    source = synthetic.vintage_series(periods=4)
    decision_dates = pd.DatetimeIndex(["2023-02-15", "2023-03-20"])
    spec = FeatureSpec("value", source, pd.Timedelta(days=90))
    expected = build_feature_panel([spec], decision_dates=decision_dates)

    changed_frame = source.frame.copy()
    future = changed_frame["period_start"].gt(decision_dates[-1])
    changed_frame.loc[future, "value"] = future_value
    changed = VintageSeriesSet(source.definition, changed_frame, source.metadata)
    actual = build_feature_panel(
        [FeatureSpec("value", changed, pd.Timedelta(days=90))],
        decision_dates=decision_dates,
    )

    pd.testing.assert_frame_equal(actual.frame, expected.frame)
    pd.testing.assert_frame_equal(actual.provenance, expected.provenance)
