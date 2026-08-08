"""Focused FRED series definition, observation, and revision acquisition."""

from __future__ import annotations

from datetime import UTC, date, datetime
from math import isfinite
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.data.fred._common import AdapterContext, unknown_fields
from persistra.errors import DataValidationError, NoDataError, ResponseError
from persistra.model import (
    SchemaDiagnostic,
    SeriesDefinition,
    SeriesKind,
    SeriesSet,
    VintageDatesResult,
    VintageSeriesSet,
    provider_series_id,
)
from persistra.model._frames import SERIES_DTYPES, VINTAGE_SERIES_DTYPES, typed_frame

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persistra.data.fred.transport import RawResponse

_OBSERVATION_LIMIT = 100_000
_VINTAGE_DATE_LIMIT = 10_000
_OPEN_END = "9999-12-31"

_SERIES_FIELDS = {
    "id",
    "realtime_start",
    "realtime_end",
    "title",
    "observation_start",
    "observation_end",
    "frequency",
    "frequency_short",
    "units",
    "units_short",
    "seasonal_adjustment",
    "seasonal_adjustment_short",
    "last_updated",
    "popularity",
    "notes",
}
_OBSERVATION_FIELDS = {"realtime_start", "realtime_end", "date", "value"}


class SeriesNamespace:
    """Source-level FRED series and ALFRED revision operations."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def definition(
        self,
        series_id: str,
        *,
        realtime_start: date | str | None = None,
        realtime_end: date | str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> SeriesDefinition:
        """Retrieve the definition used to interpret one provider series."""
        parameters = {"series_id": _series_key(series_id)}
        start, end = _optional_bounds(realtime_start, realtime_end, "realtime")
        if start is not None:
            parameters["realtime_start"] = start
        if end is not None:
            parameters["realtime_end"] = end
        definition, _provider_as_of, diagnostics, raw = self._definition(
            parameters,
            refresh=refresh,
            offline=offline,
        )
        self._context.metadata("series", parameters, (raw,), diagnostics=diagnostics)
        return definition

    def latest(
        self,
        series_id: str,
        *,
        observation_start: date | str | None = None,
        observation_end: date | str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> SeriesSet:
        """Retrieve current source-level observations at the native frequency."""
        provider_series = _series_key(series_id)
        start, end = _optional_bounds(observation_start, observation_end, "observation")
        definition, provider_as_of, definition_diagnostics, _ = self._definition(
            {"series_id": provider_series},
            refresh=refresh,
            offline=offline,
        )
        parameters: dict[str, Any] = {
            "series_id": provider_series,
            "output_type": 1,
            "sort_order": "asc",
        }
        if start is not None:
            parameters["observation_start"] = start
        if end is not None:
            parameters["observation_end"] = end
        items, responses, envelope_diagnostics = self._context.pages(
            "series_observations",
            parameters,
            item_key="observations",
            limit=_OBSERVATION_LIMIT,
            refresh=refresh,
            offline=offline,
        )
        retrieved_at = max(response.retrieved_at for response in responses)
        rows, row_diagnostics = _latest_rows(definition, items, retrieved_at, provider_as_of)
        diagnostics = (*definition_diagnostics, *envelope_diagnostics, *row_diagnostics)
        metadata = self._context.metadata(
            "series_observations",
            parameters,
            responses,
            diagnostics=diagnostics,
            provider_as_of=provider_as_of,
        )
        return SeriesSet(definition, _series_frame(rows), metadata)

    def vintages(
        self,
        series_id: str,
        *,
        realtime_start: date | str | None = None,
        realtime_end: date | str | None = None,
        vintage_dates: Sequence[date | str] | None = None,
        observation_start: date | str | None = None,
        observation_end: date | str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> VintageSeriesSet:
        """Retrieve explicit vintages or one bounded ALFRED revision history."""
        provider_series = _series_key(series_id)
        explicit_dates = _explicit_dates(vintage_dates)
        if explicit_dates and (realtime_start is not None or realtime_end is not None):
            raise ValueError("vintage_dates and realtime bounds are mutually exclusive")
        if not explicit_dates and realtime_start is None:
            raise ValueError("realtime_start or vintage_dates is required")
        realtime_start_label: str | None = None
        realtime_end_label: str | None = None
        if not explicit_dates:
            realtime_start_label, realtime_end_label = _optional_bounds(
                realtime_start,
                realtime_end,
                "realtime",
            )
            if realtime_end_label is None:
                realtime_end_label = _OPEN_END

        observation_start_label, observation_end_label = _optional_bounds(
            observation_start,
            observation_end,
            "observation",
        )
        definition, _provider_as_of, definition_diagnostics, _ = self._definition(
            {"series_id": provider_series},
            refresh=refresh,
            offline=offline,
        )
        parameters: dict[str, Any] = {
            "series_id": provider_series,
            "output_type": 1,
            "sort_order": "asc",
        }
        if explicit_dates:
            parameters["vintage_dates"] = ",".join(explicit_dates)
        else:
            parameters["realtime_start"] = realtime_start_label
            parameters["realtime_end"] = realtime_end_label
        if observation_start_label is not None:
            parameters["observation_start"] = observation_start_label
        if observation_end_label is not None:
            parameters["observation_end"] = observation_end_label

        items, responses, envelope_diagnostics = self._context.pages(
            "series_observations",
            parameters,
            item_key="observations",
            limit=_OBSERVATION_LIMIT,
            refresh=refresh,
            offline=offline,
        )
        retrieved_at = max(response.retrieved_at for response in responses)
        rows, row_diagnostics = _vintage_rows(definition, items, retrieved_at)
        diagnostics = (*definition_diagnostics, *envelope_diagnostics, *row_diagnostics)
        metadata = self._context.metadata(
            "series_observations",
            parameters,
            responses,
            diagnostics=diagnostics,
        )
        return VintageSeriesSet(definition, _vintage_frame(rows), metadata)

    def vintage_dates(
        self,
        series_id: str,
        *,
        realtime_start: date | str | None = None,
        realtime_end: date | str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> VintageDatesResult:
        """List every change date for one series inside inclusive real-time bounds."""
        provider_series = _series_key(series_id)
        parameters: dict[str, Any] = {
            "series_id": provider_series,
            "sort_order": "asc",
        }
        start, end = _optional_bounds(realtime_start, realtime_end, "realtime")
        if start is not None:
            parameters["realtime_start"] = start
        if end is not None:
            parameters["realtime_end"] = end
        items, responses, diagnostics = self._context.pages(
            "series_vintagedates",
            parameters,
            item_key="vintage_dates",
            limit=_VINTAGE_DATE_LIMIT,
            refresh=refresh,
            offline=offline,
        )
        dates: list[date] = []
        for value in items:
            if not isinstance(value, str):
                raise ResponseError("series_vintagedates response has a non-text date")
            dates.append(_provider_date(value, "vintage date").date())
        ordered = tuple(sorted(set(dates)))
        if len(ordered) != len(dates):
            raise DataValidationError("provider returned duplicate vintage dates")
        metadata = self._context.metadata(
            "series_vintagedates",
            parameters,
            responses,
            diagnostics=diagnostics,
        )
        return VintageDatesResult(provider_series, ordered, metadata)

    def _definition(
        self,
        parameters: dict[str, Any],
        *,
        refresh: bool,
        offline: bool,
    ) -> tuple[SeriesDefinition, datetime | None, tuple[SchemaDiagnostic, ...], RawResponse]:
        payload, raw = self._context.json(
            "series",
            parameters,
            refresh=refresh,
            offline=offline,
        )
        diagnostics = list(
            unknown_fields(
                payload,
                {"realtime_start", "realtime_end", "seriess"},
                context="series envelope",
            )
        )
        values = payload.get("seriess")
        if not isinstance(values, list):
            raise ResponseError("series response has no seriess list")
        items = cast("list[Any]", values)
        if not items:
            raise NoDataError("no provider data for series")
        if len(items) != 1 or not isinstance(items[0], dict):
            raise ResponseError("series response does not contain one definition")
        item = cast("dict[str, Any]", items[0])
        diagnostics.extend(unknown_fields(item, _SERIES_FIELDS, context="series definition"))
        definition, provider_as_of = _parse_definition(item)
        return definition, provider_as_of, tuple(diagnostics), raw


def _parse_definition(item: dict[str, Any]) -> tuple[SeriesDefinition, datetime | None]:
    provider_series = _required_text(item, "id", "series definition")
    frequency = _required_text(item, "frequency", "series definition").lower()
    units = _required_text(item, "units", "series definition")
    seasonal = _optional_text(item, "seasonal_adjustment")
    last_updated = _optional_text(item, "last_updated")
    provider_as_of: datetime | None = None
    if last_updated is not None:
        try:
            parsed = datetime.fromisoformat(last_updated)
        except ValueError as error:
            raise ResponseError("series definition has invalid last_updated") from error
        if parsed.tzinfo is None:
            raise ResponseError("series definition last_updated has no UTC offset")
        provider_as_of = parsed.astimezone(UTC)
    return (
        SeriesDefinition(
            provider_series_id("fred", provider_series, frequency),
            SeriesKind.ECONOMIC,
            _required_text(item, "title", "series definition"),
            "fred",
            provider_series,
            frequency,
            units,
            seasonal_adjustment=seasonal,
        ),
        provider_as_of,
    )


def _latest_rows(
    definition: SeriesDefinition,
    items: list[Any],
    retrieved_at: datetime,
    provider_as_of: datetime | None,
) -> tuple[list[dict[str, Any]], tuple[SchemaDiagnostic, ...]]:
    rows: list[dict[str, Any]] = []
    diagnostics: list[SchemaDiagnostic] = []
    for value in items:
        item = _observation(value)
        diagnostics.extend(unknown_fields(item, _OBSERVATION_FIELDS, context="observation"))
        raw_value = _required_text(item, "value", "observation")
        if raw_value == ".":
            continue
        period = _provider_date(_required_text(item, "date", "observation"), "observation date")
        rows.append(
            {
                **_series_scope(definition, period),
                "value": _provider_float(raw_value),
                "provider_as_of": provider_as_of,
                "retrieved_at": retrieved_at,
            }
        )
    return rows, tuple(diagnostics)


def _vintage_rows(
    definition: SeriesDefinition,
    items: list[Any],
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], tuple[SchemaDiagnostic, ...]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    diagnostics: list[SchemaDiagnostic] = []
    for value in items:
        item = _observation(value)
        diagnostics.extend(unknown_fields(item, _OBSERVATION_FIELDS, context="observation"))
        period_text = _required_text(item, "date", "observation")
        available_from_text = _required_text(item, "realtime_start", "observation")
        available_through_text = _required_text(item, "realtime_end", "observation")
        period = _provider_date(period_text, "observation date")
        available_from = _provider_date(available_from_text, "realtime_start")
        available_through = (
            pd.NaT
            if available_through_text == _OPEN_END
            else _provider_date(available_through_text, "realtime_end")
        )
        raw_value = _required_text(item, "value", "observation")
        missing = raw_value == "."
        row = {
            **_series_scope(definition, period),
            "available_from": available_from,
            "available_through": available_through,
            "value": pd.NA if missing else _provider_float(raw_value),
            "is_deleted": missing,
            "retrieved_at": retrieved_at,
        }
        key = (period_text, available_from_text)
        previous = rows.get(key)
        if previous is not None and not _same_vintage(previous, row):
            raise DataValidationError(
                "provider returned conflicting revisions on one daily boundary"
            )
        rows[key] = row
    return list(rows.values()), tuple(diagnostics)


def _series_scope(definition: SeriesDefinition, period: pd.Timestamp) -> dict[str, Any]:
    return {
        "series_id": definition.series_id,
        "provider": definition.provider,
        "provider_series": definition.provider_series,
        "series_kind": definition.kind.value,
        "frequency": definition.frequency,
        "period_label": period.strftime("%Y-%m-%d"),
        "period_start": period,
        "period_end": pd.NaT,
        "unit": definition.unit,
        "geography": definition.geography,
        "seasonal_adjustment": definition.seasonal_adjustment,
        "maturity": definition.maturity,
    }


def _series_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    values = {name: [row[name] for row in rows] for name in SERIES_DTYPES}
    return typed_frame(values, SERIES_DTYPES).sort_values(
        ["series_id", "frequency", "maturity", "period_label"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)


def _vintage_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    values = {name: [row[name] for row in rows] for name in VINTAGE_SERIES_DTYPES}
    return typed_frame(values, VINTAGE_SERIES_DTYPES).sort_values(
        ["series_id", "frequency", "maturity", "period_label", "available_from"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)


def _observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResponseError("series_observations response has a malformed row")
    return cast("dict[str, Any]", value)


def _provider_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise ResponseError("observation has a nonnumeric value") from error
    if not isfinite(result):
        raise ResponseError("observation has a nonfinite value")
    return result


def _provider_date(value: str, field: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(date.fromisoformat(value))
    except ValueError as error:
        raise ResponseError(f"provider returned invalid {field}") from error
    return result


def _series_key(value: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError("series_id must not be empty")
    return result


def _optional_bounds(
    start: date | str | None,
    end: date | str | None,
    label: str,
) -> tuple[str | None, str | None]:
    start_label = None if start is None else _date_argument(start, f"{label}_start")
    end_label = None if end is None else _date_argument(end, f"{label}_end")
    if start_label is not None and end_label is not None and start_label > end_label:
        raise ValueError(f"{label}_start must not follow {label}_end")
    return start_label, end_label


def _explicit_dates(values: Sequence[date | str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    dates = tuple(_date_argument(value, "vintage_dates") for value in values)
    if not dates:
        raise ValueError("vintage_dates must not be empty")
    ordered = tuple(sorted(set(dates)))
    if len(ordered) != len(dates):
        raise ValueError("vintage_dates must be unique")
    if len(ordered) > 2_000:
        raise ValueError("FRED accepts at most 2000 explicit JSON vintage dates")
    return ordered


def _date_argument(value: date | str, field: str) -> str:
    if isinstance(value, datetime):
        raise TypeError(f"{field} must be a date or ISO date string")
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD") from error


def _required_text(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ResponseError(f"{context} has no {field}")
    return value


def _optional_text(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    return value if isinstance(value, str) and value else None


def _same_vintage(first: dict[str, Any], second: dict[str, Any]) -> bool:
    for key in VINTAGE_SERIES_DTYPES:
        if key == "retrieved_at":
            continue
        left = first[key]
        right = second[key]
        left_missing = cast("bool", pd.isna(left))
        right_missing = cast("bool", pd.isna(right))
        if left_missing and right_missing:
            continue
        if left_missing or right_missing:
            return False
        if left != right:
            return False
    return True
