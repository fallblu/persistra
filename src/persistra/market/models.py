"""Immutable daily market-data and point-in-time adjustment contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId, QualifiedName, SchemaVersion, TimeInterval
from persistra.domain.time import validate_instant
from persistra.errors import BarSpecError, CorporateActionTermsError, MarketDataQueryError

if TYPE_CHECKING:
    from datetime import date, datetime
    from decimal import Decimal

    from persistra.reference import (
        AsOfContext,
        InstrumentId,
        ResolvedCalendarRef,
        SecurityId,
    )


class BarSpecId(EntityId):
    KIND: ClassVar[str] = "bar_spec"


class CorporateActionId(EntityId):
    KIND: ClassVar[str] = "corporate_action"


class BarState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_TRADE = "no_trade"


class TradingStatus(StrEnum):
    TRADING = "trading"
    HALTED = "halted"
    PAUSED = "paused"
    AUCTION = "auction"
    CLOSED = "closed"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


class CorporateActionKind(StrEnum):
    ORDINARY_CASH_DIVIDEND = "ordinary_cash_dividend"
    SPECIAL_CASH_DIVIDEND = "special_cash_dividend"
    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    STOCK_DIVIDEND = "stock_dividend"
    SYMBOL_CHANGE = "symbol_change"
    LISTING_CHANGE = "listing_change"
    MERGER = "merger"
    ACQUISITION = "acquisition"
    SPINOFF = "spinoff"
    DELISTING = "delisting"
    LIQUIDATION = "liquidation"
    ETF_DISTRIBUTION = "etf_distribution"
    UNRESOLVED_ENTITLEMENT = "unresolved_entitlement"


class CorporateActionStatus(StrEnum):
    ANNOUNCED = "announced"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AdjustmentPriceMode(StrEnum):
    RAW = "raw"
    SPLIT = "split"
    TOTAL_RETURN = "total_return"


class AdjustmentRowStatus(StrEnum):
    RAW = "raw"
    ADJUSTED = "adjusted"
    UNAVAILABLE = "unavailable"
    SEGMENT_BREAK = "segment_break"


@dataclass(frozen=True, slots=True)
class BarSpecRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class BarSpecDefinition:
    name: QualifiedName
    version: int = 1
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    def __post_init__(self) -> None:
        if self.version < 1:
            raise BarSpecError("bar spec version must be positive")
        if str(self.name) != "persistra.bar.session.regular":
            raise BarSpecError("phase 3 supports only regular-session daily bars")


@dataclass(frozen=True, slots=True)
class ResolvedBarSpecRef:
    bar_spec_id: BarSpecId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class DailyBar:
    instrument_id: InstrumentId
    spec: ResolvedBarSpecRef
    calendar: ResolvedCalendarRef
    interval_start: datetime
    interval_end: datetime
    session_date: date
    state: BarState
    currency: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal
    trade_count: int | None
    available_at: datetime

    def __post_init__(self) -> None:
        TimeInterval(self.interval_start, self.interval_end)
        validate_instant(self.available_at)
        if self.currency != "USD":
            raise MarketDataQueryError("phase 3 bars require USD")
        if self.volume < 0 or (self.trade_count is not None and self.trade_count < 0):
            raise MarketDataQueryError("bar volume and trade count must be nonnegative")
        prices = (self.open, self.high, self.low, self.close)
        if self.state is BarState.NO_TRADE:
            if any(value is not None for value in prices) or self.volume != 0:
                raise MarketDataQueryError("no-trade bars require null prices and zero volume")
        else:
            if any(value is None or value <= 0 for value in prices):
                raise MarketDataQueryError("complete and partial bars require positive OHLC")
            assert all(value is not None for value in prices)
            assert self.open is not None
            assert self.high is not None
            assert self.low is not None
            assert self.close is not None
            if self.low > min(self.open, self.close) or self.high < max(
                self.open, self.close
            ) or self.low > self.high:
                raise MarketDataQueryError("bar OHLC ordering is inconsistent")
        if self.state is BarState.COMPLETE and self.available_at < self.interval_end:
            raise MarketDataQueryError("complete bar cannot be available before interval end")


@dataclass(frozen=True, slots=True)
class BarQuery:
    instruments: tuple[InstrumentId, ...]
    spec: BarSpecRef
    start: datetime
    end: datetime
    context: AsOfContext
    include_partial: bool = False
    include_no_trade: bool = True
    max_rows: int = 5_000_000

    def __post_init__(self) -> None:
        TimeInterval(self.start, self.end)
        if not self.instruments or len(set(self.instruments)) != len(self.instruments):
            raise MarketDataQueryError("bar query requires unique instruments")
        if self.max_rows < 1:
            raise MarketDataQueryError("bar query max_rows must be positive")


@dataclass(frozen=True, slots=True)
class TradingStatusObservation:
    instrument_id: InstrumentId
    status: TradingStatus
    effective_at: datetime
    available_at: datetime
    effective_to: datetime | None = None

    def __post_init__(self) -> None:
        validate_instant(self.effective_at)
        validate_instant(self.available_at)
        if self.effective_to is not None:
            TimeInterval(self.effective_at, self.effective_to)


@dataclass(frozen=True, slots=True)
class CorporateActionObservation:
    action_id: CorporateActionId
    kind: CorporateActionKind
    subject_security_id: SecurityId
    subject_instrument_id: InstrumentId | None
    status: CorporateActionStatus
    available_at: datetime
    ex_at: datetime | None = None
    effective_at: datetime | None = None
    share_ratio: Decimal | None = None
    cash_per_subject_unit: Decimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        validate_instant(self.available_at)
        if self.ex_at is not None:
            validate_instant(self.ex_at)
        if self.effective_at is not None:
            validate_instant(self.effective_at)
        split_kinds = {CorporateActionKind.SPLIT, CorporateActionKind.REVERSE_SPLIT}
        cash_kinds = {
            CorporateActionKind.ORDINARY_CASH_DIVIDEND,
            CorporateActionKind.SPECIAL_CASH_DIVIDEND,
        }
        if self.kind in split_kinds:
            if (
                self.share_ratio is None
                or self.share_ratio <= 0
                or (self.effective_at is None and self.ex_at is None)
                or self.cash_per_subject_unit is not None
            ):
                raise CorporateActionTermsError("split terms are incomplete or invalid")
        elif self.kind in cash_kinds:
            if (
                self.ex_at is None
                or self.cash_per_subject_unit is None
                or self.cash_per_subject_unit <= 0
                or self.currency != "USD"
                or self.share_ratio is not None
            ):
                raise CorporateActionTermsError(
                    "cash-dividend terms are incomplete or invalid"
                )
        else:
            raise CorporateActionTermsError(
                "corporate action kind is deferred beyond phase 3"
            )


@dataclass(frozen=True, slots=True)
class AdjustmentViewRequest:
    bars: BarQuery
    mode: AdjustmentPriceMode
    anchor_at: datetime

    def __post_init__(self) -> None:
        validate_instant(self.anchor_at)
        if self.anchor_at < self.bars.start:
            raise MarketDataQueryError("adjustment anchor precedes the bar range")
