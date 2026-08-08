"""Normalized market data results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from persistra.errors import DataValidationError
from persistra.model._frames import (
    BAR_DTYPES,
    QUOTE_DTYPES,
    TOP_OF_BOOK_DTYPES,
    require_finite,
    require_nonnegative,
    validate_frame,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    import pandas as pd

    from persistra.model.identity import Instrument


class EntitlementMode(StrEnum):
    """Provider freshness and entitlement modes."""

    HISTORICAL = "historical"
    DELAYED = "delayed"
    REALTIME = "realtime"
    NOT_APPLICABLE = "not_applicable"


class CacheStatus(StrEnum):
    """Raw response cache outcomes."""

    HIT = "hit"
    MISS = "miss"
    REFRESHED = "refreshed"
    OFFLINE = "offline"
    NOT_USED = "not_used"


@dataclass(frozen=True, slots=True)
class SchemaDiagnostic:
    """A nonfatal provider schema difference."""

    field: str
    message: str


@dataclass(frozen=True, slots=True)
class ResultMetadata:
    """Required provenance for one acquisition result."""

    provider: str
    operation: str
    request_parameters: Mapping[str, Any]
    retrieved_at: datetime
    provider_as_of: datetime | None = None
    entitlement: EntitlementMode = EntitlementMode.NOT_APPLICABLE
    cache_status: CacheStatus = CacheStatus.NOT_USED
    schema_version: int = 1
    diagnostics: tuple[SchemaDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.provider_as_of is not None and self.provider_as_of.tzinfo is None:
            raise ValueError("provider_as_of must be timezone-aware")
        redacted = {
            key: value
            for key, value in self.request_parameters.items()
            if key.lower().replace("_", "") != "apikey"
        }
        object.__setattr__(self, "request_parameters", MappingProxyType(redacted))


@dataclass(frozen=True, slots=True)
class BarSet:
    """Validated bars and their acquisition provenance."""

    instrument: Instrument
    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        def rows(frame: pd.DataFrame) -> None:
            require_finite(frame, ["open", "high", "low", "close"], positive=True)
            require_nonnegative(frame, ["volume", "dividend_amount", "split_coefficient"])
            valid_temporal = frame["date"].notna() ^ frame["timestamp"].notna()
            if not valid_temporal.all():
                raise DataValidationError("exactly one bar temporal identity must apply")
            if (frame["low"] > frame[["open", "close"]].min(axis=1)).any():
                raise DataValidationError("low exceeds open or close")
            if (frame["high"] < frame[["open", "close"]].max(axis=1)).any():
                raise DataValidationError("high is below open or close")

        frame = validate_frame(
            self.frame,
            BAR_DTYPES,
            validate_rows=rows,
            sort_by=[
                "instrument_id",
                "interval",
                "price_adjustment",
                "session",
                "date",
                "timestamp",
            ],
            unique_by=[
                "instrument_id",
                "interval",
                "price_adjustment",
                "session",
                "date",
                "timestamp",
            ],
        )
        if not frame.empty and set(frame["instrument_id"]) != {self.instrument.instrument_id}:
            raise DataValidationError("bar instrument identity differs from its result scope")
        object.__setattr__(self, "frame", frame)


@dataclass(frozen=True, slots=True)
class QuoteSet:
    """Validated latest quotes and acquisition provenance."""

    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        def rows(frame: pd.DataFrame) -> None:
            require_finite(frame, ["price"], positive=True)
            require_finite(
                frame,
                ["open", "high", "low", "previous_close", "change", "change_percent"],
            )
            require_nonnegative(frame, ["volume"])

        result = validate_frame(
            self.frame,
            QUOTE_DTYPES,
            validate_rows=rows,
            sort_by=[],
            unique_by=["provider", "provider_symbol"],
        )
        object.__setattr__(self, "frame", result)


@dataclass(frozen=True, slots=True)
class TopOfBookSet:
    """Validated top-of-book snapshots and provenance."""

    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        def rows(frame: pd.DataFrame) -> None:
            require_nonnegative(frame, ["bid_price", "bid_size", "ask_price", "ask_size"])

        result = validate_frame(
            self.frame,
            TOP_OF_BOOK_DTYPES,
            validate_rows=rows,
            sort_by=[],
            unique_by=["provider", "provider_symbol"],
        )
        object.__setattr__(self, "frame", result)
