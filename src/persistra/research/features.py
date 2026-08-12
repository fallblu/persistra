"""Point-in-time selection and feature-panel construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.errors import AnalysisError
from persistra.model import VintageSeriesSet
from persistra.research._validation import (
    ZERO_DAYS,
    calendar_date,
    calendar_index,
    require_whole_days,
)
from persistra.research.model import (
    FEATURE_PROVENANCE_COLUMNS,
    FeaturePanel,
    FeaturePolicy,
    FeatureSpec,
    VintagePolicy,
    VintageSelection,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date, datetime


def select_vintage(
    source: VintageSeriesSet,
    *,
    known_on: date | datetime | str | pd.Timestamp,
    publication_lag: pd.Timedelta = ZERO_DAYS,
) -> VintageSelection:
    """Select each observation version known on a calendar date.

    ``publication_lag`` delays all source availability intervals. The selected source rows keep
    their original interval boundaries, while the returned result records the chosen lag.
    """
    date = calendar_date(known_on, name="known_on")
    require_whole_days(publication_lag, name="publication_lag")
    source_date = date - publication_lag
    frame = source.frame
    applicable = frame["available_from"].le(source_date) & (
        frame["available_through"].isna() | frame["available_through"].ge(source_date)
    )
    definition = source.definition
    return VintageSelection(
        frame=frame.loc[applicable],
        known_on=date,
        publication_lag=publication_lag,
        series_id=definition.series_id,
        provider=definition.provider,
        provider_series=definition.provider_series,
        source_retrieved_at=source.metadata.retrieved_at,
    )


def project_vintage_history(
    source: VintageSeriesSet,
    policy: VintagePolicy,
) -> VintageSeriesSet:
    """Project one retained revision history under an explicit content policy.

    Real-time history keeps every provider interval. First-release history keeps the earliest
    retained version of each observation and ignores later revisions. Final-vintage history
    keeps the last retained version but makes it visible from the first recorded release date,
    deliberately exposing future revision content for bias measurement.
    """
    if policy not in {"final_vintage", "first_release", "real_time"}:
        raise ValueError("unsupported vintage policy")
    frame = source.frame.copy(deep=True)
    if policy == "real_time" or frame.empty:
        return VintageSeriesSet(source.definition, frame, source.metadata)
    observation_key = ["series_id", "frequency", "maturity", "period_label"]
    grouped = frame.groupby(observation_key, dropna=False, sort=False)
    if policy == "first_release":
        selected = grouped.head(1).copy()
    else:
        first_availability = grouped["available_from"].transform("min")
        selected = grouped.tail(1).copy()
        selected["available_from"] = first_availability.loc[selected.index].to_numpy()
    selected["available_through"] = pd.NaT
    return VintageSeriesSet(source.definition, selected, source.metadata)


def build_feature_panel(
    specs: Iterable[FeatureSpec],
    *,
    decision_dates: pd.DatetimeIndex,
) -> FeaturePanel:
    """Build point-in-time features under explicit lag and staleness policies."""
    dates = calendar_index(decision_dates, name="decision_dates")
    collected = tuple(specs)
    names = [spec.name for spec in collected]
    if len(set(names)) != len(names):
        raise ValueError("feature names must be unique")
    policies = tuple(_policy(spec) for spec in collected)
    values: dict[str, pd.Series] = {}
    provenance: list[dict[str, Any]] = []
    for spec in collected:
        feature_values: list[object] = []
        for decision_date in dates:
            selected = select_vintage(
                spec.source,
                known_on=decision_date,
                publication_lag=spec.publication_lag,
            ).frame
            observation_dates = selected[spec.observation_date_column]
            eligible = selected[observation_dates.notna() & observation_dates.le(decision_date)]
            row = _latest_observation(eligible, spec)
            age = (
                None
                if row is None
                else decision_date - cast("pd.Timestamp", row[spec.observation_date_column])
            )
            if row is not None and age is not None and age > spec.maximum_staleness:
                row = None
                age = None
            value = pd.NA if row is None or bool(row["is_deleted"]) else row["value"]
            feature_values.append(value)
            provenance.append(_provenance_row(spec, decision_date, row, age, value))
        values[spec.name] = pd.Series(feature_values, index=dates, dtype="Float64")
    frame = pd.DataFrame(values, index=dates)
    provenance_frame = pd.DataFrame(provenance, columns=FEATURE_PROVENANCE_COLUMNS)
    return FeaturePanel(frame, provenance_frame, policies)


def _latest_observation(eligible: pd.DataFrame, spec: FeatureSpec) -> pd.Series | None:
    if eligible.empty:
        return None
    latest_date = eligible[spec.observation_date_column].max()
    latest = eligible[eligible[spec.observation_date_column].eq(latest_date)]
    if len(latest) > 1:
        raise AnalysisError(f"{spec.name} has ambiguous observations on {latest_date}")
    return latest.iloc[0]


def _policy(spec: FeatureSpec) -> FeaturePolicy:
    definition = spec.source.definition
    return FeaturePolicy(
        name=spec.name,
        series_id=definition.series_id,
        provider=definition.provider,
        provider_series=definition.provider_series,
        maximum_staleness=spec.maximum_staleness,
        publication_lag=spec.publication_lag,
        observation_date_column=spec.observation_date_column,
        source_retrieved_at=spec.source.metadata.retrieved_at,
    )


def _provenance_row(
    spec: FeatureSpec,
    decision_date: pd.Timestamp,
    row: pd.Series | None,
    age: pd.Timedelta | None,
    value: object,
) -> dict[str, Any]:
    definition = spec.source.definition
    return {
        "decision_date": decision_date,
        "feature": spec.name,
        "series_id": definition.series_id,
        "provider": definition.provider,
        "provider_series": definition.provider_series,
        "period_label": pd.NaT if row is None else row["period_label"],
        "observation_date": pd.NaT if row is None else row[spec.observation_date_column],
        "available_from": pd.NaT if row is None else row["available_from"],
        "available_through": pd.NaT if row is None else row["available_through"],
        "source_retrieved_at": spec.source.metadata.retrieved_at,
        "matched_age": pd.NaT if age is None else age,
        "publication_lag": spec.publication_lag,
        "maximum_staleness": spec.maximum_staleness,
        "is_deleted": pd.NA if row is None else row["is_deleted"],
        "selected_value": value,
    }
