"""Shared Alpha Vantage normalization helpers."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from persistra.errors import ResponseError
from persistra.model import (
    EntitlementMode,
    ResultMetadata,
    SchemaDiagnostic,
)
from persistra.model._frames import BAR_DTYPES, typed_frame

if TYPE_CHECKING:
    from collections.abc import Mapping

    from persistra.data.alphavantage.transport import AlphaVantageTransport, RawResponse

HISTORICAL_CACHE_AGE = timedelta(hours=24)
_DEFAULT_CACHE_AGE = object()


@dataclass(frozen=True, slots=True)
class AdapterContext:
    """Configuration shared by all Alpha Vantage namespaces."""

    transport: AlphaVantageTransport
    strict_schema: bool = False
    cache_ages: Mapping[str, timedelta | None] = field(
        default_factory=lambda: cast("Mapping[str, timedelta | None]", {})
    )

    def json(
        self,
        operation: str,
        parameters: dict[str, Any],
        *,
        cache_age: timedelta | None | object = _DEFAULT_CACHE_AGE,
        refresh: bool = False,
        offline: bool = False,
    ) -> tuple[dict[str, Any], RawResponse]:
        """Request and decode one JSON object."""
        selected_cache_age = (
            self.cache_ages.get(operation, HISTORICAL_CACHE_AGE)
            if cache_age is _DEFAULT_CACHE_AGE
            else cast("timedelta | None", cache_age)
        )
        raw = self.transport.request(
            operation,
            parameters,
            cache_age=selected_cache_age,
            refresh=refresh,
            offline=offline,
        )
        try:
            value = json.loads(raw.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResponseError(f"malformed JSON success body for {operation}") from error
        if not isinstance(value, dict):
            raise ResponseError(f"expected a JSON object for {operation}")
        return cast("dict[str, Any]", value), raw

    def csv(
        self,
        operation: str,
        parameters: dict[str, Any],
        *,
        refresh: bool = False,
        offline: bool = False,
    ) -> tuple[list[dict[str, str]], RawResponse]:
        """Request and decode one CSV table."""
        raw = self.transport.request(
            operation,
            parameters,
            cache_age=self.cache_ages.get(operation, HISTORICAL_CACHE_AGE),
            refresh=refresh,
            offline=offline,
        )
        try:
            text = raw.body.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ResponseError(f"malformed CSV success body for {operation}") from error
        return list(csv.DictReader(io.StringIO(text))), raw

    def metadata(
        self,
        operation: str,
        parameters: dict[str, Any],
        raw: RawResponse,
        *,
        entitlement: EntitlementMode = EntitlementMode.NOT_APPLICABLE,
        diagnostics: tuple[SchemaDiagnostic, ...] = (),
        provider_as_of: datetime | None = None,
    ) -> ResultMetadata:
        """Create normalized provenance from one raw response."""
        if self.strict_schema and diagnostics:
            fields = ", ".join(item.field for item in diagnostics)
            raise ResponseError(f"unknown provider fields for {operation}: {fields}")
        return ResultMetadata.create(
            provider="alpha_vantage",
            operation=operation,
            request_parameters=parameters,
            retrieved_at=raw.retrieved_at,
            provider_as_of=provider_as_of,
            entitlement=entitlement,
            cache_status=raw.cache_status,
            diagnostics=diagnostics,
        )


def parse_bar_frame(
    payload: dict[str, Any],
    *,
    operation: str,
    instrument_id: str,
    provider_symbol: str,
    interval: str,
    currency: str | None,
    adjustment: str,
    session: str,
    retrieved_at: datetime,
    strict_schema: bool,
) -> tuple[pd.DataFrame, tuple[SchemaDiagnostic, ...]]:
    """Normalize a provider time-series object into BarFrame."""
    metadata = _metadata_object(payload)
    timezone_name = str(metadata.get("5. Time Zone") or metadata.get("6. Time Zone") or "UTC")
    series_key = next(
        (
            key
            for key, value in payload.items()
            if key != "Meta Data" and isinstance(value, (dict, list))
        ),
        None,
    )
    if series_key is None:
        raise ResponseError("time-series response has no data object")
    source = payload[series_key]
    rows: list[tuple[str, dict[str, Any]]]
    if isinstance(source, dict):
        mapping = cast("dict[str, Any]", source)
        rows = [
            (str(label), cast("dict[str, Any]", values))
            for label, values in mapping.items()
            if isinstance(values, dict)
        ]
    elif isinstance(source, list):
        rows = []
        for item in cast("list[Any]", source):
            if not isinstance(item, dict):
                raise ResponseError("time-series data row is not an object")
            record = cast("dict[str, Any]", item)
            label = str(record.get("timestamp") or record.get("date") or "")
            rows.append((label, record))
    else:
        raise ResponseError("time-series data is malformed")
    diagnostics: list[SchemaDiagnostic] = []
    output: list[dict[str, Any]] = []
    intraday = interval.endswith("min")
    for label, source_row in rows:
        fields = {_field_name(key): value for key, value in source_row.items()}
        known = {
            "open",
            "high",
            "low",
            "close",
            "adjusted close",
            "volume",
            "dividend amount",
            "split coefficient",
            "timestamp",
            "date",
            "market cap",
        }
        for field_name in set(fields).difference(known):
            diagnostics.append(SchemaDiagnostic(field_name, "unknown provider bar field"))
        temporal = _provider_time(label, timezone_name, intraday)
        open_value = _required_float(fields, "open")
        high_value = _required_float(fields, "high")
        low_value = _required_float(fields, "low")
        close_value = _required_float(fields, "close")
        context = f"{operation} {provider_symbol} {interval} at {label}"
        if low_value > min(open_value, close_value):
            raise ResponseError(
                f"contradictory provider OHLC for {context}: low exceeds open or close"
            )
        if high_value < max(open_value, close_value):
            raise ResponseError(
                f"contradictory provider OHLC for {context}: high is below open or close"
            )
        output.append(
            {
                "instrument_id": instrument_id,
                "provider": "alpha_vantage",
                "provider_symbol": provider_symbol,
                "interval": interval,
                "date": pd.NaT if intraday else temporal,
                "timestamp": temporal if intraday else pd.NaT,
                "timestamp_position": "provider_label" if intraday else "not_applicable",
                "source_timezone": timezone_name,
                "session": session,
                "price_adjustment": adjustment,
                "currency": currency,
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
                "adjusted_close": _optional_float(fields, "adjusted close"),
                "volume": _optional_float(fields, "volume"),
                "dividend_amount": _optional_float(fields, "dividend amount"),
                "split_coefficient": _optional_float(fields, "split coefficient"),
                "provider_as_of": pd.NaT,
                "retrieved_at": retrieved_at,
            }
        )
    if strict_schema and diagnostics:
        fields = ", ".join(item.field for item in diagnostics)
        raise ResponseError(f"unknown provider bar fields: {fields}")
    data = {name: [row[name] for row in output] for name in BAR_DTYPES}
    frame = typed_frame(data, BAR_DTYPES)
    frame = frame.sort_values(
        ["instrument_id", "interval", "price_adjustment", "session", "date", "timestamp"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    return frame, tuple(diagnostics)


def unknown_fields(
    row: dict[str, Any], known: set[str], *, context: str
) -> tuple[SchemaDiagnostic, ...]:
    """Return deterministic diagnostics for unknown provider fields."""
    return tuple(
        SchemaDiagnostic(str(field), f"unknown provider {context} field")
        for field in sorted(set(row).difference(known))
    )


def required_text(row: dict[str, Any], *names: str) -> str:
    """Read one required provider text field by alias."""
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise ResponseError(f"required provider field is missing: {names[0]}")


def optional_text(row: dict[str, Any], *names: str) -> str | None:
    """Read one optional provider text field by alias."""
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def required_float(row: dict[str, Any], *names: str) -> float:
    """Read one finite required provider number."""
    value = optional_float(row, *names)
    if value is None:
        raise ResponseError(f"required provider number is missing: {names[0]}")
    return value


def optional_float(row: dict[str, Any], *names: str) -> float | None:
    """Read one finite optional provider number."""
    for name in names:
        if name not in row or row[name] in (None, "", "None", "null", "N/A", "."):
            continue
        try:
            value = float(str(row[name]).rstrip("%"))
        except (TypeError, ValueError) as error:
            raise ResponseError(f"provider number is malformed: {name}") from error
        if not pd.notna(value) or value in (float("inf"), float("-inf")):
            raise ResponseError(f"provider number is not finite: {name}")
        return value
    return None


def optional_int(row: dict[str, Any], *names: str) -> int | None:
    """Read one integral optional provider number."""
    value = optional_float(row, *names)
    if value is None:
        return None
    if not value.is_integer():
        raise ResponseError(f"provider count is not integral: {names[0]}")
    return int(value)


def parse_date(value: str | None) -> date | None:
    """Parse an optional provider calendar date."""
    if value is None or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as error:
        raise ResponseError("provider date is malformed") from error


def parse_timestamp(value: str | None, timezone_name: str | None = None) -> datetime | None:
    """Parse an optional provider timestamp as a UTC instant."""
    if value is None or not value:
        return None
    try:
        parsed = pd.Timestamp(value)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize(timezone_name or "UTC")
        return parsed.tz_convert("UTC").to_pydatetime()
    except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
        raise ResponseError("provider timestamp is malformed") from error


def _metadata_object(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("Meta Data", {})
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _field_name(value: str) -> str:
    name = value.strip().lower()
    if ". " in name and name[0].isdigit():
        name = name.split(". ", 1)[1]
    if " (" in name:
        name = name.split(" (", 1)[0]
    return name.replace("_", " ")


def _required_float(row: dict[str, Any], name: str) -> float:
    return required_float(row, name)


def _optional_float(row: dict[str, Any], name: str) -> float | None:
    return optional_float(row, name)


def _provider_time(label: str, timezone_name: str, intraday: bool) -> pd.Timestamp:
    try:
        parsed = pd.Timestamp(label)
        if intraday:
            zone = ZoneInfo(timezone_name)
            return parsed.tz_localize(zone).tz_convert("UTC")
        return parsed.normalize().tz_localize(None)
    except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
        raise ResponseError("provider bar time is malformed") from error
