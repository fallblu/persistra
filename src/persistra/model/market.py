"""Normalized market data results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from persistra._portable import freeze_portable_mapping
from persistra.errors import DataValidationError
from persistra.model._frames import (
    BAR_CONTRACT,
    QUOTE_CONTRACT,
    TOP_OF_BOOK_CONTRACT,
    require_finite,
    require_metadata_values,
    require_nonnegative,
    require_scope_values,
    validate_frame,
)
from persistra.model._quotes import QuoteState, require_sizes_have_prices, with_quote_diagnostics

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
    """Required provenance with deeply immutable portable request parameters.

    Request parameters may contain strings, integers, finite floats, booleans, ``None``,
    string-keyed mappings, lists, and tuples. Persistra copies the complete structure,
    removes ``api_key`` and ``apikey`` fields recursively, freezes mappings, and converts
    sequences to tuples.
    """

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
        if not isinstance(cast("object", self.provider), str) or not self.provider.strip():
            raise ValueError("provider must not be empty")
        if not isinstance(cast("object", self.operation), str) or not self.operation.strip():
            raise ValueError("operation must not be empty")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.provider_as_of is not None and self.provider_as_of.tzinfo is None:
            raise ValueError("provider_as_of must be timezone-aware")
        parameters = freeze_portable_mapping(
            self.request_parameters,
            name="request parameters",
            redact_api_keys=True,
        )
        object.__setattr__(self, "request_parameters", parameters)


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
            BAR_CONTRACT,
            validate_rows=rows,
        )
        scope: dict[str, object | None] = {"instrument_id": self.instrument.instrument_id}
        if self.instrument.quote_currency is not None:
            scope["currency"] = self.instrument.quote_currency
        require_scope_values(frame, scope)
        require_metadata_values(
            frame,
            provider=self.metadata.provider,
            retrieved_at=self.metadata.retrieved_at,
        )
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
            QUOTE_CONTRACT,
            validate_rows=rows,
        )
        require_metadata_values(
            result,
            provider=self.metadata.provider,
            retrieved_at=self.metadata.retrieved_at,
            entitlement=self.metadata.entitlement.value,
        )
        object.__setattr__(self, "frame", result)


@dataclass(frozen=True, slots=True)
class TopOfBookSet:
    """Validated top-of-book snapshots and provenance.

    Missing and one-sided quotes are valid. Locked and crossed quotes are retained with
    ``bid_ask`` diagnostics. A size without its corresponding price is invalid.
    """

    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        def rows(frame: pd.DataFrame) -> None:
            require_nonnegative(frame, ["bid_price", "bid_size", "ask_price", "ask_size"])
            require_sizes_have_prices(
                frame,
                bid_price="bid_price",
                bid_size="bid_size",
                ask_price="ask_price",
                ask_size="ask_size",
            )

        result = validate_frame(
            self.frame,
            TOP_OF_BOOK_CONTRACT,
            validate_rows=rows,
        )
        require_metadata_values(
            result,
            provider=self.metadata.provider,
            retrieved_at=self.metadata.retrieved_at,
        )
        metadata = with_quote_diagnostics(
            self.metadata,
            (
                QuoteState(
                    str(row.provider_symbol),
                    row.bid_price,
                    row.ask_price,
                    "top-of-book snapshot",
                )
                for row in result.itertuples(index=False)
            ),
        )
        object.__setattr__(self, "frame", result)
        object.__setattr__(self, "metadata", metadata)
