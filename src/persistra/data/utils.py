"""Explicit reshaping, alignment, and resampling utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.errors import DataValidationError
from persistra.model import BarSet, CacheStatus, ResultMetadata, SchemaDiagnostic, SeriesSet
from persistra.model._frames import BAR_DTYPES, typed_frame

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def pivot_bars(results: Iterable[BarSet], *, field: str) -> pd.DataFrame:
    """Pivot one explicit normalized bar field into a wide frame."""
    if field not in {"open", "high", "low", "close", "adjusted_close", "volume"}:
        raise ValueError("field is not a supported bar value")
    columns: list[pd.Series] = []
    temporal_kind: str | None = None
    for result in results:
        frame = result.frame
        kind = "timestamp" if frame["timestamp"].notna().any() else "date"
        if temporal_kind is not None and temporal_kind != kind:
            raise DataValidationError("bar results must use compatible temporal labels")
        temporal_kind = kind
        series = frame.set_index(kind)[field].copy()
        series.name = (result.metadata.provider, result.instrument.instrument_id)
        columns.append(series)
    if not columns:
        return pd.DataFrame()
    return pd.concat(columns, axis=1).sort_index()


def pivot_series(results: Iterable[SeriesSet]) -> pd.DataFrame:
    """Pivot compatible normalized scalar series into a wide frame."""
    collected = list(results)
    frequencies = {result.definition.frequency for result in collected}
    if len(frequencies) > 1:
        raise DataValidationError("series frequencies differ; resample before pivoting")
    columns: list[pd.Series] = []
    for result in collected:
        series = result.frame.set_index("period_label")["value"].copy()
        series.name = (result.metadata.provider, result.definition.series_id)
        columns.append(series)
    if not columns:
        return pd.DataFrame()
    return pd.concat(columns, axis=1).sort_index()


def align(
    values: Mapping[str, pd.Series | pd.DataFrame], *, how: str = "intersection"
) -> dict[str, pd.Series | pd.DataFrame]:
    """Align labeled objects by intersection or union without filling gaps."""
    if how not in {"intersection", "union"}:
        raise ValueError("how must be intersection or union")
    copied = {name: value.copy(deep=True) for name, value in values.items()}
    if not copied:
        return {}
    indexes = [value.index for value in copied.values()]
    labels = indexes[0]
    for index in indexes[1:]:
        labels = labels.intersection(index) if how == "intersection" else labels.union(index)
    labels = labels.sort_values()
    return {name: value.reindex(labels) for name, value in copied.items()}


def resample_bars(
    bars: BarSet,
    *,
    frequency: str,
    timezone: str,
    sessions: set[str],
) -> BarSet:
    """Derive OHLCV bars under explicit timezone and session rules."""
    if not frequency or not timezone or not sessions:
        raise ValueError("frequency, timezone, and sessions are required")
    selected = bars.frame[bars.frame["session"].isin(sessions)].copy()
    if selected.empty or selected["timestamp"].isna().all():
        raise DataValidationError("resampling requires selected intraday bars")
    indexed = selected.set_index(selected["timestamp"].dt.tz_convert(timezone))
    resampler = indexed.resample(frequency)
    aggregate = pd.DataFrame(
        {
            "open": resampler["open"].first(),
            "high": resampler["high"].max(),
            "low": resampler["low"].min(),
            "close": resampler["close"].last(),
            "adjusted_close": resampler["adjusted_close"].last(),
            "volume": resampler["volume"].sum(min_count=1),
            "dividend_amount": resampler["dividend_amount"].sum(min_count=1),
            "split_coefficient": resampler["split_coefficient"].last(),
        }
    )
    aggregate = aggregate.dropna(subset=["open", "high", "low", "close"])
    count = len(aggregate)
    template = selected.iloc[0]
    timestamp_index = cast("pd.DatetimeIndex", aggregate.index)
    data: dict[str, Any] = {
        "instrument_id": [template["instrument_id"]] * count,
        "provider": ["persistra"] * count,
        "provider_symbol": [template["provider_symbol"]] * count,
        "interval": [frequency] * count,
        "date": [pd.NaT] * count,
        "timestamp": timestamp_index.tz_convert("UTC"),
        "timestamp_position": ["start"] * count,
        "source_timezone": [timezone] * count,
        "session": [next(iter(sessions)) if len(sessions) == 1 else "all"] * count,
        "price_adjustment": [template["price_adjustment"]] * count,
        "currency": [template["currency"]] * count,
        "open": aggregate["open"],
        "high": aggregate["high"],
        "low": aggregate["low"],
        "close": aggregate["close"],
        "adjusted_close": aggregate["adjusted_close"],
        "volume": aggregate["volume"],
        "dividend_amount": aggregate["dividend_amount"],
        "split_coefficient": aggregate["split_coefficient"],
        "provider_as_of": [pd.NaT] * count,
        "retrieved_at": [bars.metadata.retrieved_at] * count,
    }
    frame = typed_frame(data, BAR_DTYPES).sort_values("timestamp").reset_index(drop=True)
    metadata = ResultMetadata(
        provider="persistra",
        operation="resample_bars",
        request_parameters={
            "frequency": frequency,
            "timezone": timezone,
            "sessions": sorted(sessions),
        },
        retrieved_at=bars.metadata.retrieved_at,
        cache_status=CacheStatus.NOT_USED,
        diagnostics=(SchemaDiagnostic("derived", "bars are locally resampled"),),
    )
    return BarSet(bars.instrument, frame, metadata)


def asof_align(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    maximum_staleness: pd.Timedelta,
) -> pd.DataFrame:
    """Backward-align observations and report each matched source age."""
    if maximum_staleness <= pd.Timedelta(0):
        raise ValueError("maximum_staleness must be positive")
    if not isinstance(left.index, pd.DatetimeIndex) or not isinstance(
        right.index, pd.DatetimeIndex
    ):
        raise TypeError("as-of inputs must use DatetimeIndex")
    left_copy = left.copy(deep=True).sort_index().reset_index(names="left_label")
    right_copy = right.copy(deep=True).sort_index().reset_index(names="matched_label")
    result = pd.merge_asof(
        left_copy,
        right_copy,
        left_on="left_label",
        right_on="matched_label",
        direction="backward",
        tolerance=maximum_staleness,
        suffixes=("_left", "_right"),
    )
    result["matched_age"] = result["left_label"] - result["matched_label"]
    return result.set_index("left_label")
