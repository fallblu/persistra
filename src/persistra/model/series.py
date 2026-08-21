"""Normalized scalar quote and series results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, cast

import pandas as pd

from persistra.errors import DataValidationError
from persistra.model._frames import (
    SERIES_DTYPES,
    VINTAGE_SERIES_DTYPES,
    require_finite,
    require_metadata_values,
    require_scope_values,
    validate_frame,
)
from persistra.model._quotes import QuoteState, with_quote_diagnostics

if TYPE_CHECKING:
    from datetime import date, datetime

    from persistra.model.identity import SeriesDefinition
    from persistra.model.market import ResultMetadata


@dataclass(frozen=True, slots=True)
class ExchangeRateQuote:
    """One provider exchange-rate observation.

    Missing and one-sided bid-ask quotes are valid. Locked and crossed quotes are retained
    with a ``bid_ask`` diagnostic.
    """

    instrument_id: str
    provider: str
    base_currency: str
    quote_currency: str
    exchange_rate: float
    bid: float | None
    ask: float | None
    provider_timestamp: datetime | None
    provider_timezone: str | None
    retrieved_at: datetime
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        _require_result_text(self.instrument_id, "instrument_id")
        _require_result_text(self.provider, "provider")
        _require_result_text(self.base_currency, "base_currency")
        _require_result_text(self.quote_currency, "quote_currency")
        if self.base_currency.casefold() == self.quote_currency.casefold():
            raise DataValidationError("base_currency and quote_currency must differ")
        if self.provider_timezone is not None:
            _require_result_text(self.provider_timezone, "provider_timezone")
        values = (self.exchange_rate, self.bid, self.ask)
        if any(value is not None and (not isfinite(value) or value <= 0) for value in values):
            raise DataValidationError("exchange rates must be positive and finite")
        if self.provider != self.metadata.provider:
            raise DataValidationError("provider differs from result metadata")
        if self.retrieved_at != self.metadata.retrieved_at:
            raise DataValidationError("retrieved_at differs from result metadata")
        metadata = with_quote_diagnostics(
            self.metadata,
            (
                QuoteState(
                    self.instrument_id,
                    self.bid,
                    self.ask,
                    "exchange-rate quote",
                ),
            ),
        )
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class CommoditySpotQuote:
    """One provider commodity spot observation."""

    series_id: str
    provider: str
    metal: str
    value: float
    unit: str
    provider_timestamp: datetime | None
    retrieved_at: datetime
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        _require_result_text(self.series_id, "series_id")
        _require_result_text(self.provider, "provider")
        _require_result_text(self.metal, "metal")
        _require_result_text(self.unit, "unit")
        if not pd.notna(self.value) or not float("-inf") < self.value < float("inf"):
            raise DataValidationError("commodity spot value must be finite")
        if self.provider != self.metadata.provider:
            raise DataValidationError("provider differs from result metadata")
        if self.retrieved_at != self.metadata.retrieved_at:
            raise DataValidationError("retrieved_at differs from result metadata")


@dataclass(frozen=True, slots=True)
class SeriesSet:
    """One validated scalar series and its provenance."""

    definition: SeriesDefinition
    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        def rows(frame: pd.DataFrame) -> None:
            require_finite(frame, ["value"])

        result = validate_frame(
            self.frame,
            SERIES_DTYPES,
            validate_rows=rows,
            sort_by=["series_id", "frequency", "maturity", "period_label"],
            unique_by=["series_id", "frequency", "maturity", "period_label"],
        )
        _validate_series_scope(result, self.definition, self.metadata)
        object.__setattr__(self, "frame", result)


@dataclass(frozen=True, slots=True)
class VintageSeriesSet:
    """One validated scalar-series revision history and its provenance."""

    definition: SeriesDefinition
    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        def rows(frame: pd.DataFrame) -> None:
            require_finite(frame, ["value"])
            _validate_vintage_dates(frame)
            _validate_vintage_intervals(frame)
            if (frame.loc[frame["is_deleted"], "value"].notna()).any():
                raise DataValidationError("deleted versions must not contain values")

        result = validate_frame(
            self.frame,
            VINTAGE_SERIES_DTYPES,
            validate_rows=rows,
            sort_by=[
                "series_id",
                "frequency",
                "maturity",
                "period_label",
                "available_from",
            ],
            unique_by=[
                "series_id",
                "frequency",
                "maturity",
                "period_label",
                "available_from",
            ],
        )
        _validate_vintage_scope(result, self.definition, self.metadata)
        object.__setattr__(self, "frame", result)


@dataclass(frozen=True, slots=True)
class VintageDatesResult:
    """Release dates when one provider series changed and their provenance."""

    provider_series: str
    dates: tuple[date, ...]
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        _require_result_text(self.provider_series, "provider_series")
        if tuple(sorted(set(self.dates))) != self.dates:
            raise DataValidationError("vintage dates must be sorted and unique")


def _require_result_text(value: str, name: str) -> None:
    if not isinstance(cast("object", value), str) or not value.strip():
        raise DataValidationError(f"{name} must not be empty")


def _validate_vintage_dates(frame: pd.DataFrame) -> None:
    if frame["available_from"].isna().any():
        raise DataValidationError("available_from must not be missing")
    for column in ("period_start", "period_end", "available_from", "available_through"):
        observed = frame[column].dropna()
        if not observed.equals(observed.dt.normalize()):
            raise DataValidationError(f"{column} must contain calendar dates")
    closed = frame["available_through"].notna()
    if (frame.loc[closed, "available_through"] < frame.loc[closed, "available_from"]).any():
        raise DataValidationError("available_through must not precede available_from")


def _validate_vintage_intervals(frame: pd.DataFrame) -> None:
    observation_key = ["series_id", "frequency", "maturity", "period_label"]
    for _, versions in frame.groupby(observation_key, dropna=False, sort=False):
        ordered = versions.sort_values("available_from", kind="stable")
        starts = ordered["available_from"].reset_index(drop=True)
        ends = ordered["available_through"].reset_index(drop=True)
        for index in range(1, len(ordered)):
            if starts.iloc[index - 1] == starts.iloc[index]:
                continue
            previous_end = ends.iloc[index - 1]
            if pd.isna(previous_end) or previous_end >= starts.iloc[index]:
                raise DataValidationError("vintage availability intervals must not overlap")


def _validate_vintage_scope(
    frame: pd.DataFrame,
    definition: SeriesDefinition,
    metadata: ResultMetadata,
) -> None:
    _validate_series_scope(frame, definition, metadata)


def _validate_series_scope(
    frame: pd.DataFrame,
    definition: SeriesDefinition,
    metadata: ResultMetadata,
) -> None:
    expected: dict[str, object | None] = {
        "series_id": definition.series_id,
        "provider": definition.provider,
        "provider_series": definition.provider_series,
        "series_kind": definition.kind.value,
        "frequency": definition.frequency,
        "unit": definition.unit,
        "geography": definition.geography,
        "seasonal_adjustment": definition.seasonal_adjustment,
        "maturity": definition.maturity,
    }
    require_scope_values(frame, expected)
    if metadata.provider != definition.provider:
        raise DataValidationError("metadata provider differs from its result scope")
    require_metadata_values(frame, retrieved_at=metadata.retrieved_at)
