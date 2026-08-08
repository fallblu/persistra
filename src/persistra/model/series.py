"""Normalized scalar quote and series results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

import pandas as pd

from persistra.errors import DataValidationError
from persistra.model._frames import (
    SERIES_DTYPES,
    VINTAGE_SERIES_DTYPES,
    require_finite,
    validate_frame,
)

if TYPE_CHECKING:
    from datetime import date, datetime

    from persistra.model.identity import SeriesDefinition
    from persistra.model.market import ResultMetadata


@dataclass(frozen=True, slots=True)
class ExchangeRateQuote:
    """One provider exchange-rate observation."""

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
        values = (self.exchange_rate, self.bid, self.ask)
        if any(value is not None and (not isfinite(value) or value <= 0) for value in values):
            raise ValueError("exchange rates must be positive and finite")


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
        if not pd.notna(self.value) or not float("-inf") < self.value < float("inf"):
            raise ValueError("commodity spot value must be finite")


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
        if not result.empty and set(result["series_id"]) != {self.definition.series_id}:
            raise ValueError("series identity differs from its result scope")
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
        if not self.provider_series:
            raise ValueError("provider_series must not be empty")
        if not self.metadata.provider:
            raise DataValidationError("metadata provider must not be empty")
        if tuple(sorted(set(self.dates))) != self.dates:
            raise DataValidationError("vintage dates must be sorted and unique")


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
    expected: dict[str, str | None] = {
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
    for column, value in expected.items():
        matches = frame[column].isna() if value is None else frame[column].eq(value)
        if not matches.fillna(False).all():
            raise DataValidationError(f"{column} differs from its result scope")
    if metadata.provider != definition.provider:
        raise DataValidationError("metadata provider differs from its result scope")
    if not frame.empty and not frame["retrieved_at"].eq(metadata.retrieved_at).all():
        raise DataValidationError("retrieved_at differs from result metadata")
