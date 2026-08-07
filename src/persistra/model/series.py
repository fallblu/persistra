"""Normalized scalar quote and series results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

import pandas as pd

from persistra.model._frames import SERIES_DTYPES, require_finite, validate_frame

if TYPE_CHECKING:
    from datetime import datetime

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
