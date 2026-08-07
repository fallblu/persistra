"""Shared Alpha Vantage scalar-series normalization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.data.alphavantage._common import (
    AdapterContext,
    optional_text,
    required_float,
    unknown_fields,
)
from persistra.errors import ResponseError
from persistra.model import (
    SchemaDiagnostic,
    SeriesDefinition,
    SeriesKind,
    SeriesSet,
    provider_series_id,
)
from persistra.model._frames import SERIES_DTYPES, typed_frame

if TYPE_CHECKING:
    from persistra.data.alphavantage.transport import RawResponse


def parse_scalar_series(
    context: AdapterContext,
    payload: dict[str, Any],
    raw: RawResponse,
    *,
    operation: str,
    parameters: dict[str, object],
    provider_series: str,
    frequency: str,
    kind: SeriesKind,
    maturity: str | None = None,
) -> SeriesSet:
    """Normalize a commodity or economic provider series."""
    value = payload.get("data")
    if not isinstance(value, list):
        raise ResponseError(f"{operation} response has no data list")
    items = cast("list[Any]", value)
    if not all(isinstance(item, dict) for item in items):
        raise ResponseError(f"{operation} response has malformed data rows")
    rows = cast("list[dict[str, Any]]", items)
    source_frequency = str(payload.get("interval") or frequency)
    unit = str(payload.get("unit") or "unknown")
    display_name = str(payload.get("name") or provider_series)
    geography = optional_text(payload, "geography")
    seasonal = optional_text(payload, "seasonal_adjustment")
    series_id = provider_series_id("alpha_vantage", provider_series, source_frequency)
    diagnostics: list[SchemaDiagnostic] = []
    output: list[dict[str, Any]] = []
    for row in rows:
        diagnostics.extend(unknown_fields(row, {"date", "value"}, context="series"))
        label = optional_text(row, "date")
        if label is None:
            raise ResponseError("provider series row has no date label")
        output.append(
            {
                "series_id": series_id,
                "provider": "alpha_vantage",
                "provider_series": provider_series,
                "series_kind": kind.value,
                "frequency": source_frequency,
                "period_label": label,
                "period_start": pd.NaT,
                "period_end": pd.NaT,
                "value": required_float(row, "value"),
                "unit": unit,
                "geography": geography,
                "seasonal_adjustment": seasonal,
                "maturity": maturity,
                "provider_as_of": pd.NaT,
                "retrieved_at": raw.retrieved_at,
            }
        )
    values = {name: [row[name] for row in output] for name in SERIES_DTYPES}
    frame = (
        typed_frame(values, SERIES_DTYPES)
        .sort_values(["series_id", "frequency", "maturity", "period_label"], kind="stable")
        .reset_index(drop=True)
    )
    metadata = context.metadata(operation, parameters, raw, diagnostics=tuple(diagnostics))
    definition = SeriesDefinition(
        series_id,
        kind,
        display_name,
        "alpha_vantage",
        provider_series,
        source_frequency,
        unit,
        geography,
        seasonal,
        maturity,
    )
    return SeriesSet(definition, frame, metadata)
