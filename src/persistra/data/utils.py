"""Explicit reshaping, alignment, and resampling utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

import pandas as pd

from persistra.errors import DataValidationError
from persistra.model import BarSet, CacheStatus, ResultMetadata, SchemaDiagnostic, SeriesSet
from persistra.model._frames import BAR_DTYPES, typed_frame

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

type _TimeUnit = Literal["s", "ms", "us", "ns"]

_TIME_UNITS_FINEST_FIRST: tuple[_TimeUnit, ...] = ("ns", "us", "ms", "s")


def _finest_time_unit(left: _TimeUnit, right: _TimeUnit) -> _TimeUnit:
    for unit in _TIME_UNITS_FINEST_FIRST:
        if unit == left or unit == right:
            return unit
    raise AssertionError("unsupported datetime unit")


def pivot_bars(results: Iterable[BarSet], *, field: str) -> pd.DataFrame:
    """Pivot one explicit normalized bar field into a wide frame."""
    if field not in {"open", "high", "low", "close", "adjusted_close", "volume"}:
        raise ValueError("field is not a supported bar value")
    columns: list[pd.Series] = []
    temporal_kind: str | None = None
    identities: set[tuple[str, str]] = set()
    for result in results:
        frame = result.frame
        identity = (result.metadata.provider, result.instrument.instrument_id)
        if identity in identities:
            raise DataValidationError(f"duplicate bar pivot identity: {identity!r}")
        identities.add(identity)
        kind = _bar_temporal_kind(frame)
        if kind is not None and temporal_kind is not None and temporal_kind != kind:
            raise DataValidationError("bar results must use compatible temporal labels")
        if kind is not None:
            temporal_kind = kind
        index_name = kind or temporal_kind or "date"
        series = frame.set_index(index_name)[field].copy()
        series.name = identity
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
    identities: set[tuple[str, str]] = set()
    for result in collected:
        identity = (result.metadata.provider, result.definition.series_id)
        if identity in identities:
            raise DataValidationError(f"duplicate series pivot identity: {identity!r}")
        identities.add(identity)
        series = result.frame.set_index("period_label")["value"].copy()
        series.name = identity
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
    for name, value in values.items():
        if not value.index.is_unique:
            duplicate = value.index[value.index.duplicated()][0]
            raise DataValidationError(
                f"alignment input {name!r} index must be unique; duplicate label: {duplicate!r}"
            )
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
    positions = selected["timestamp_position"]
    if positions.isna().any() or positions.nunique() != 1:
        raise DataValidationError("resampling requires one supported source timestamp position")
    timestamp_position = str(positions.iloc[0])
    if timestamp_position not in {"start", "end"}:
        raise DataValidationError(
            f"resampling does not support source timestamp position {timestamp_position!r}"
        )
    indexed = selected.set_index(selected["timestamp"].dt.tz_convert(timezone))
    closed = "left" if timestamp_position == "start" else "right"
    resampler = indexed.resample(frequency, closed=closed, label="left")
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
            "source_timestamp_position": timestamp_position,
            "output_timestamp_position": "start",
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
    _validate_asof_columns(left, right)
    if not right.index.is_unique:
        duplicate = right.index[right.index.duplicated()][0]
        raise DataValidationError(
            f"as-of source index must be unique; duplicate label: {duplicate!r}"
        )
    left_unit = left.index.unit
    right_unit = right.index.unit
    common_unit = _finest_time_unit(left_unit, right_unit)
    left_copy = left.copy(deep=True)
    left_copy.index = left.index.as_unit(common_unit)
    right_copy = right.copy(deep=True)
    right_copy.index = right.index.as_unit(common_unit)
    left_copy = left_copy.sort_index().reset_index(names="left_label")
    right_copy = right_copy.sort_index().reset_index(names="matched_label")
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
    result["left_label"] = result["left_label"].dt.as_unit(left_unit)
    result["matched_label"] = result["matched_label"].dt.as_unit(right_unit)
    return result.set_index("left_label")


def _bar_temporal_kind(frame: pd.DataFrame) -> str | None:
    has_dates = bool(frame["date"].notna().any())
    has_timestamps = bool(frame["timestamp"].notna().any())
    if has_dates and has_timestamps:
        raise DataValidationError("one bar pivot input contains mixed temporal labels")
    if has_timestamps:
        return "timestamp"
    if has_dates:
        return "date"
    return None


def _validate_asof_columns(left: pd.DataFrame, right: pd.DataFrame) -> None:
    for side, frame in (("left", left), ("right", right)):
        if not frame.columns.is_unique:
            raise DataValidationError(f"as-of {side} columns must be unique")
    reserved = {"left_label", "matched_label", "matched_age"}
    existing = set(left.columns) | set(right.columns)
    collisions = reserved & existing
    if collisions:
        names = ", ".join(sorted(repr(name) for name in collisions))
        raise DataValidationError(f"as-of input columns use reserved output names: {names}")
    shared = set(left.columns) & set(right.columns)
    generated = {
        suffixed
        for name in shared
        for suffixed in (f"{name}_left", f"{name}_right")
    }
    suffix_collisions = generated & existing
    if suffix_collisions:
        names = ", ".join(sorted(repr(name) for name in suffix_collisions))
        raise DataValidationError(f"as-of input columns collide after suffixing: {names}")
