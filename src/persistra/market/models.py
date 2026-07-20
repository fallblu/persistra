"""Immutable daily market-data and point-in-time adjustment contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import (
    AvailabilityQuality,
    ContentId,
    Currency,
    Duration,
    EntityId,
    QualifiedName,
    SchemaVersion,
    TimeInterval,
)
from persistra.domain.errors import InvalidCurrencyError
from persistra.domain.time import validate_instant
from persistra.errors import (
    AdjustmentPolicyError,
    BarSpecError,
    CorporateActionTermsError,
    MarketDataQueryError,
    QuoteConditionError,
    TradeConditionError,
    TradingStatusError,
)

if TYPE_CHECKING:
    from datetime import date, datetime
    from decimal import Decimal

    from persistra.catalog import CanonicalRevisionId, SourceId
    from persistra.reference import (
        AsOfContext,
        InstrumentId,
        ResolvedCalendarRef,
        SecurityId,
        VenueId,
    )


class BarSpecId(EntityId):
    KIND: ClassVar[str] = "bar_spec"


class CorporateActionId(EntityId):
    KIND: ClassVar[str] = "corporate_action"


class AdjustmentPolicyId(EntityId):
    KIND: ClassVar[str] = "adjustment_policy"


class AdjustmentMaterializationId(EntityId):
    KIND: ClassVar[str] = "adjustment_materialization"


class BarIntervalKind(StrEnum):
    SESSION = "session"
    FIXED = "fixed"


class BarAlignment(StrEnum):
    SESSION_OPEN = "session_open"
    UTC_EPOCH = "utc_epoch"


class BarPhase(StrEnum):
    REGULAR = "regular"
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"
    EXTENDED_COMBINED = "extended_combined"


class BarState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_TRADE = "no_trade"
    NO_VOLUME = "no_volume"


def _require_registered_currency(
    code: str, error: type[Exception], message: str
) -> None:
    try:
        Currency(code)
    except InvalidCurrencyError as cause:
        raise error(message) from cause


class MarketObservationScope(StrEnum):
    VENUE = "venue"
    CONSOLIDATED = "consolidated"


class QuoteScope(StrEnum):
    VENUE_TOP = "venue_top"
    CONSOLIDATED_NBBO = "consolidated_nbbo"


class QuoteState(StrEnum):
    ACTIVE = "active"
    EMPTY = "empty"


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


class ActionLegKind(StrEnum):
    CASH = "cash"
    SECURITY = "security"
    UNRESOLVED = "unresolved"


class AdjustmentPriceMode(StrEnum):
    RAW = "raw"
    SPLIT = "split"
    TOTAL_RETURN = "total_return"


class AdjustmentKnowledgeMode(StrEnum):
    POINT_IN_TIME = "point_in_time"
    RETROSPECTIVE = "retrospective"


class AdjustmentDirection(StrEnum):
    BACKWARD_TO_ANCHOR = "backward_to_anchor"


class AdjustmentRowStatus(StrEnum):
    RAW = "raw"
    ADJUSTED = "adjusted"
    UNAVAILABLE = "unavailable"
    SEGMENT_BREAK = "segment_break"


class PriceObservationState(StrEnum):
    SELECTED = "selected"
    MISSING = "missing"
    STALE = "stale"
    NO_TRADE = "no_trade"
    PARTIAL_EXCLUDED = "partial_excluded"
    UNAVAILABLE = "unavailable"
    INVALID_SUMMARY = "invalid_summary"


@dataclass(frozen=True, slots=True)
class BarSpecRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class BarSpecDefinition:
    name: QualifiedName
    version: int = 1
    interval_kind: BarIntervalKind = BarIntervalKind.SESSION
    nominal_interval: Duration | None = None
    alignment: BarAlignment = BarAlignment.SESSION_OPEN
    phase: BarPhase = BarPhase.REGULAR
    phase_boundary_policy_content_id: ContentId = field(
        default_factory=lambda: ContentId.from_bytes(
            b"persistra.market.phase_boundary.regular@1"
        )
    )
    allow_short_final_interval: bool = False
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    def __post_init__(self) -> None:
        if self.version < 1:
            raise BarSpecError("bar spec version must be positive")
        if self.interval_kind is BarIntervalKind.SESSION:
            if (
                self.nominal_interval is not None
                or self.alignment is not BarAlignment.SESSION_OPEN
                or self.allow_short_final_interval
            ):
                raise BarSpecError("session bar specification has invalid fixed-grid fields")
        elif self.nominal_interval is None or self.nominal_interval.microseconds <= 0:
            raise BarSpecError("fixed bar specification requires a positive interval")


@dataclass(frozen=True, slots=True)
class ResolvedBarSpecRef:
    bar_spec_id: BarSpecId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class AdjustmentPolicyRef:
    name: QualifiedName
    version: int

    def __post_init__(self) -> None:
        if self.version < 1:
            raise AdjustmentPolicyError("adjustment policy version must be positive")


@dataclass(frozen=True, slots=True)
class AdjustmentPolicyDefinition:
    name: QualifiedName
    version: int
    mode: AdjustmentPriceMode
    knowledge_mode: AdjustmentKnowledgeMode
    split_basis_policy: QualifiedName = field(
        default_factory=lambda: QualifiedName("persistra.adjustment.split_basis")
    )
    cash_distribution_policy: QualifiedName | None = None
    segment_break_policy: QualifiedName = field(
        default_factory=lambda: QualifiedName("persistra.adjustment.segment_break")
    )
    direction: AdjustmentDirection = AdjustmentDirection.BACKWARD_TO_ANCHOR
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    def __post_init__(self) -> None:
        if self.version < 1:
            raise AdjustmentPolicyError("adjustment policy version must be positive")
        if (
            self.mode is AdjustmentPriceMode.TOTAL_RETURN
            and self.cash_distribution_policy is None
        ):
            raise AdjustmentPolicyError(
                "total-return policy requires a cash-distribution policy"
            )
        if (
            self.mode is not AdjustmentPriceMode.TOTAL_RETURN
            and self.cash_distribution_policy is not None
        ):
            raise AdjustmentPolicyError(
                "non-total-return policy forbids a cash-distribution policy"
            )


@dataclass(frozen=True, slots=True)
class ResolvedAdjustmentPolicyRef:
    adjustment_policy_id: AdjustmentPolicyId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class Bar:
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
    observed_through_at: datetime | None = None
    scope: MarketObservationScope = MarketObservationScope.CONSOLIDATED
    venue_id: VenueId | None = None
    aggregation_name: QualifiedName | None = field(
        default_factory=lambda: QualifiedName("persistra.market.consolidated")
    )
    aggregation_version: int | None = 1
    aggregation_content_id: ContentId | None = field(
        default_factory=lambda: ContentId.from_bytes(
            b"persistra.market.consolidated@1"
        )
    )
    phase: BarPhase = BarPhase.REGULAR
    calendar_schedule_content_id: ContentId | None = None
    vwap: Decimal | None = None
    notional_amount: Decimal | None = None
    source_condition_codes: tuple[str, ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        TimeInterval(self.interval_start, self.interval_end)
        validate_instant(self.available_at)
        observed_through = self.observed_through_at or self.interval_end
        validate_instant(observed_through)
        if not self.interval_start < observed_through <= self.interval_end:
            raise MarketDataQueryError("bar observed-through instant is outside its interval")
        object.__setattr__(self, "observed_through_at", observed_through)
        schedule_content_id = (
            self.calendar_schedule_content_id or self.calendar.schedule_root_content_id
        )
        object.__setattr__(self, "calendar_schedule_content_id", schedule_content_id)
        _require_registered_currency(
            self.currency, MarketDataQueryError, "bar currency is not a registered code"
        )
        if self.volume < 0 or (self.trade_count is not None and self.trade_count < 0):
            raise MarketDataQueryError("bar volume and trade count must be nonnegative")
        if self.scope is MarketObservationScope.VENUE:
            if (
                self.venue_id is None
                or self.aggregation_name is not None
                or self.aggregation_version is not None
                or self.aggregation_content_id is not None
            ):
                raise MarketDataQueryError("venue bars require only a venue identity")
        elif (
            self.venue_id is not None
            or self.aggregation_name is None
            or self.aggregation_version is None
            or self.aggregation_version < 1
            or self.aggregation_content_id is None
        ):
            raise MarketDataQueryError(
                "consolidated bars require a versioned aggregation identity"
            )
        prices = (self.open, self.high, self.low, self.close)
        if self.state is BarState.NO_TRADE:
            if (
                any(value is not None for value in prices)
                or self.volume != 0
                or self.vwap is not None
                or self.notional_amount is not None
                or self.trade_count not in {None, 0}
                or observed_through != self.interval_end
            ):
                raise MarketDataQueryError("no-trade bars require null prices and zero volume")
        elif self.state is BarState.NO_VOLUME:
            if (
                self.volume != 0
                or self.vwap is not None
                or self.notional_amount is not None
                or self.trade_count not in {None, 0}
            ):
                raise MarketDataQueryError(
                    "no-volume bars require zero volume and no trade-derived fields"
                )
            self._require_positive_ohlc(prices)
        else:
            if any(value is None or value <= 0 for value in prices) or self.volume <= 0:
                raise MarketDataQueryError("complete and partial bars require positive OHLC")
            if self.trade_count is not None and self.trade_count <= 0:
                raise MarketDataQueryError("traded bars require a positive trade count")
            if self.vwap is not None and self.vwap <= 0:
                raise MarketDataQueryError("bar VWAP must be positive")
            if self.notional_amount is not None and self.notional_amount <= 0:
                raise MarketDataQueryError("bar notional amount must be positive")
            self._require_positive_ohlc(prices)
        if self.state in {BarState.COMPLETE, BarState.NO_TRADE, BarState.NO_VOLUME}:
            if observed_through != self.interval_end or self.available_at < self.interval_end:
                raise MarketDataQueryError(
                    "final bar cannot be available before its interval end"
                )
        elif observed_through >= self.interval_end or self.available_at < observed_through:
            raise MarketDataQueryError(
                "partial bar availability must follow its activity horizon"
            )

    @staticmethod
    def _require_positive_ohlc(
        prices: tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None],
    ) -> None:
        open_, high, low, close = prices
        if open_ is None or high is None or low is None or close is None or min(
            open_, high, low, close
        ) <= 0:
            raise MarketDataQueryError("priced bars require positive OHLC")
        if low > min(open_, close) or high < max(open_, close) or low > high:
            raise MarketDataQueryError("bar OHLC ordering is inconsistent")


@dataclass(frozen=True, slots=True)
class BarQuery:
    instruments: tuple[InstrumentId, ...]
    spec: BarSpecRef
    start: datetime
    end: datetime
    context: AsOfContext
    include_partial: bool = False
    include_no_trade: bool = True
    scope: MarketObservationScope = MarketObservationScope.CONSOLIDATED
    max_rows: int = 5_000_000

    def __post_init__(self) -> None:
        TimeInterval(self.start, self.end)
        if not self.instruments or len(set(self.instruments)) != len(self.instruments):
            raise MarketDataQueryError("bar query requires unique instruments")
        if self.max_rows < 1:
            raise MarketDataQueryError("bar query max_rows must be positive")


def _validate_tick_query(
    instruments: tuple[InstrumentId, ...],
    venues: tuple[VenueId, ...],
    max_rows: int,
    chunk_rows: int,
) -> None:
    if not instruments or len(set(instruments)) != len(instruments):
        raise MarketDataQueryError("tick query requires unique instruments")
    if len(set(venues)) != len(venues):
        raise MarketDataQueryError("tick query venues must be unique")
    if max_rows < 1 or not 1 <= chunk_rows <= 250_000:
        raise MarketDataQueryError("tick query limits are invalid")


@dataclass(frozen=True, slots=True)
class TradeObservation:
    source_trade_key: str
    instrument_id: InstrumentId
    venue_id: VenueId
    event_at: datetime
    available_at: datetime
    source_sequence: int
    price: Decimal
    quantity: Decimal
    currency: str = "USD"
    trade_condition_codes: tuple[str, ...] = ()
    raw_condition_codes: tuple[str, ...] = ()
    price_forming: bool = True
    volume_forming: bool = True
    extended_hours: bool = False
    correction_reference_key: str | None = None
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.event_at)
        validate_instant(self.available_at)
        if not self.source_trade_key or len(self.source_trade_key.encode()) > 512:
            raise TradeConditionError("trade source key is invalid")
        if self.source_sequence < 0:
            raise TradeConditionError("trade source sequence must be nonnegative")
        _require_registered_currency(
            self.currency, TradeConditionError, "trade currency is not a registered code"
        )
        if self.price <= 0 or self.quantity <= 0:
            raise TradeConditionError("trade price, quantity, or currency is invalid")
        if self.available_at < self.event_at:
            raise TradeConditionError("trade availability precedes its event")
        normalized = tuple(sorted(set(self.trade_condition_codes)))
        if normalized != self.trade_condition_codes:
            raise TradeConditionError(
                "normalized trade conditions must be sorted and unique"
            )


@dataclass(frozen=True, slots=True)
class TradeQuery:
    instruments: tuple[InstrumentId, ...]
    start: datetime
    end: datetime
    context: AsOfContext
    venue_ids: tuple[VenueId, ...] = ()
    price_forming: bool | None = None
    volume_forming: bool | None = None
    extended_hours: bool | None = None
    max_rows: int = 5_000_000
    chunk_rows: int = 250_000

    def __post_init__(self) -> None:
        TimeInterval(self.start, self.end)
        _validate_tick_query(self.instruments, self.venue_ids, self.max_rows, self.chunk_rows)


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    source_quote_key: str
    instrument_id: InstrumentId
    event_at: datetime
    available_at: datetime
    source_sequence: int
    state: QuoteState
    scope: QuoteScope
    venue_id: VenueId | None = None
    bid_venue_id: VenueId | None = None
    ask_venue_id: VenueId | None = None
    currency: str = "USD"
    bid_price: Decimal | None = None
    bid_size: Decimal | None = None
    ask_price: Decimal | None = None
    ask_size: Decimal | None = None
    quote_condition_codes: tuple[str, ...] = ()
    raw_condition_codes: tuple[str, ...] = ()
    indicative: bool = False
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.event_at)
        validate_instant(self.available_at)
        if not self.source_quote_key or len(self.source_quote_key.encode()) > 512:
            raise QuoteConditionError("quote source key is invalid")
        if self.source_sequence < 0 or self.available_at < self.event_at:
            raise QuoteConditionError("quote sequence or availability is invalid")
        _require_registered_currency(
            self.currency, QuoteConditionError, "quote currency is not a registered code"
        )
        if (self.bid_price is None) != (self.bid_size is None) or (
            self.ask_price is None
        ) != (self.ask_size is None):
            raise QuoteConditionError("quote price and size sides must be paired")
        for price in (self.bid_price, self.ask_price):
            if price is not None and price <= 0:
                raise QuoteConditionError("quote prices must be positive")
        for size in (self.bid_size, self.ask_size):
            if size is not None and size < 0:
                raise QuoteConditionError("quote sizes must be nonnegative")
        if self.state is QuoteState.EMPTY:
            if any(
                value is not None
                for value in (
                    self.bid_price,
                    self.bid_size,
                    self.ask_price,
                    self.ask_size,
                    self.bid_venue_id,
                    self.ask_venue_id,
                )
            ):
                raise QuoteConditionError("empty quotes must clear both sides")
        elif self.bid_price is None and self.ask_price is None:
            raise QuoteConditionError("active quote requires at least one side")
        if self.scope is QuoteScope.VENUE_TOP:
            if (
                self.venue_id is None
                or self.bid_venue_id is not None
                or self.ask_venue_id is not None
            ):
                raise QuoteConditionError("venue quote identities are invalid")
        elif self.venue_id is not None:
            raise QuoteConditionError("consolidated quote forbids a row venue")
        if (self.bid_price is None and self.bid_venue_id is not None) or (
            self.ask_price is None and self.ask_venue_id is not None
        ):
            raise QuoteConditionError("absent quote sides cannot name a venue")
        if tuple(sorted(set(self.quote_condition_codes))) != self.quote_condition_codes:
            raise QuoteConditionError(
                "normalized quote conditions must be sorted and unique"
            )


@dataclass(frozen=True, slots=True)
class QuoteQuery:
    instruments: tuple[InstrumentId, ...]
    start: datetime
    end: datetime
    context: AsOfContext
    scope: QuoteScope
    include_indicative: bool = False
    max_rows: int = 5_000_000
    chunk_rows: int = 250_000

    def __post_init__(self) -> None:
        TimeInterval(self.start, self.end)
        _validate_tick_query(self.instruments, (), self.max_rows, self.chunk_rows)


@dataclass(frozen=True, slots=True)
class TradingStatusObservation:
    instrument_id: InstrumentId
    status: TradingStatus
    effective_at: datetime
    available_at: datetime
    effective_to: datetime | None = None
    source_status_key: str = ""
    venue_id: VenueId | None = None
    source_sequence: int = 0
    status_reason_code: str | None = None
    expected_resume_at: datetime | None = None
    source_condition_codes: tuple[str, ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.effective_at)
        validate_instant(self.available_at)
        if self.effective_to is not None:
            TimeInterval(self.effective_at, self.effective_to)
        if self.source_sequence < 0:
            raise TradingStatusError("status source sequence must be nonnegative")
        if self.expected_resume_at is not None:
            validate_instant(self.expected_resume_at)
            if self.expected_resume_at <= self.effective_at:
                raise TradingStatusError("expected resume must follow the status event")


@dataclass(frozen=True, slots=True)
class TradingStatusQuery:
    instruments: tuple[InstrumentId, ...]
    start: datetime
    end: datetime
    context: AsOfContext
    venue_ids: tuple[VenueId, ...] = ()
    max_rows: int = 5_000_000

    def __post_init__(self) -> None:
        TimeInterval(self.start, self.end)
        _validate_tick_query(self.instruments, self.venue_ids, self.max_rows, 250_000)


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
    source_action_key: str = ""
    resolution_method: str = "created"
    resolution_evidence_content_id: ContentId = field(
        default_factory=lambda: ContentId.from_bytes(
            b"persistra.corporate_action.resolution.created@1"
        )
    )
    announced_date: date | None = None
    announced_at: datetime | None = None
    declaration_date: date | None = None
    ex_date: date | None = None
    record_date: date | None = None
    payable_date: date | None = None
    payment_at: datetime | None = None
    effective_date: date | None = None
    expiration_date: date | None = None
    terms_basis: str | None = None
    date_policy_content_id: ContentId = field(
        default_factory=lambda: ContentId.from_bytes(
            b"persistra.corporate_action.date_policy@1"
        )
    )
    calendar_schedule_content_id: ContentId | None = None
    action_fingerprint_content_id: ContentId | None = None
    reference_revision_ids: tuple[str, ...] = ()
    source_terms: tuple[tuple[str, str], ...] = ()
    legs: tuple[CorporateActionLeg, ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.available_at)
        for instant in (
            self.announced_at,
            self.ex_at,
            self.payment_at,
            self.effective_at,
        ):
            if instant is not None:
                validate_instant(instant)
        if self.resolution_method not in {
            "source_cross_reference",
            "issuer_or_exchange_evidence",
            "created",
            "manual",
        }:
            raise CorporateActionTermsError("action resolution method is invalid")
        if self.reference_revision_ids != tuple(sorted(set(self.reference_revision_ids))):
            raise CorporateActionTermsError(
                "action reference revisions must be sorted and unique"
            )
        if len({leg.ordinal for leg in self.legs}) != len(self.legs):
            raise CorporateActionTermsError("action leg ordinals must be unique")
        if self.action_fingerprint_content_id is None:
            object.__setattr__(
                self,
                "action_fingerprint_content_id",
                ContentId.from_bytes(
                    (
                        f"{self.kind}:{self.subject_security_id}:"
                        f"{self.subject_instrument_id}:{self.ex_at}:{self.effective_at}"
                    ).encode()
                ),
            )
        if self.status is CorporateActionStatus.CANCELLED:
            return
        split_kinds = {CorporateActionKind.SPLIT, CorporateActionKind.REVERSE_SPLIT}
        cash_kinds = {
            CorporateActionKind.ORDINARY_CASH_DIVIDEND,
            CorporateActionKind.SPECIAL_CASH_DIVIDEND,
            CorporateActionKind.ETF_DISTRIBUTION,
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
                or self.currency is None
                or self.share_ratio is not None
            ):
                raise CorporateActionTermsError(
                    "cash-dividend terms are incomplete or invalid"
                )
            _require_registered_currency(
                self.currency,
                CorporateActionTermsError,
                "cash-dividend currency is not a registered code",
            )
        elif self.kind is CorporateActionKind.STOCK_DIVIDEND:
            if (
                (self.share_ratio is None or self.share_ratio <= 1)
                and not any(leg.kind is ActionLegKind.SECURITY for leg in self.legs)
            ):
                raise CorporateActionTermsError("stock-dividend terms are incomplete")
        elif self.kind in {
            CorporateActionKind.SYMBOL_CHANGE,
            CorporateActionKind.LISTING_CHANGE,
            CorporateActionKind.DELISTING,
        }:
            if self.effective_at is None:
                raise CorporateActionTermsError("lifecycle action requires effective time")
        elif self.kind in {
            CorporateActionKind.MERGER,
            CorporateActionKind.ACQUISITION,
            CorporateActionKind.SPINOFF,
            CorporateActionKind.LIQUIDATION,
        }:
            if self.effective_at is None and self.ex_at is None:
                raise CorporateActionTermsError("action effect time is required")
            if not self.legs:
                raise CorporateActionTermsError("action consideration legs are required")
        elif self.kind is CorporateActionKind.UNRESOLVED_ENTITLEMENT:
            if (
                self.effective_at is None
                or not any(leg.kind is ActionLegKind.UNRESOLVED for leg in self.legs)
            ):
                raise CorporateActionTermsError("unresolved entitlement terms are incomplete")
        else:
            raise CorporateActionTermsError(
                "corporate action kind has no supported terms contract"
            )


@dataclass(frozen=True, slots=True)
class CorporateActionLeg:
    ordinal: int
    kind: ActionLegKind
    target_security_id: SecurityId | None = None
    target_instrument_id: InstrumentId | None = None
    cash_per_subject_unit: Decimal | None = None
    quantity_per_subject_unit: Decimal | None = None
    currency: str | None = None
    entitlement_code: str | None = None
    terms_basis: str = "not_applicable"
    details: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.ordinal < 1 or self.terms_basis not in {
            "pre_action",
            "post_action",
            "not_applicable",
        }:
            raise CorporateActionTermsError("action leg ordinal or terms basis is invalid")
        if self.kind is ActionLegKind.CASH:
            if (
                self.cash_per_subject_unit is None
                or self.cash_per_subject_unit <= 0
                or self.currency is None
                or self.target_security_id is not None
                or self.target_instrument_id is not None
                or self.quantity_per_subject_unit is not None
            ):
                raise CorporateActionTermsError("cash action leg is invalid")
            _require_registered_currency(
                self.currency,
                CorporateActionTermsError,
                "cash action leg currency is not a registered code",
            )
        elif self.kind is ActionLegKind.SECURITY:
            if (
                self.quantity_per_subject_unit is None
                or self.quantity_per_subject_unit <= 0
                or (
                    self.target_security_id is None
                    and self.target_instrument_id is None
                )
                or self.cash_per_subject_unit is not None
                or self.currency is not None
            ):
                raise CorporateActionTermsError("security action leg is invalid")
        elif (
            not self.entitlement_code
            or self.target_security_id is not None
            or self.target_instrument_id is not None
            or self.cash_per_subject_unit is not None
            or self.quantity_per_subject_unit is not None
            or self.currency is not None
        ):
            raise CorporateActionTermsError("unresolved action leg is invalid")


@dataclass(frozen=True, slots=True)
class CorporateActionQuery:
    instruments: tuple[InstrumentId, ...]
    start: datetime
    end: datetime
    context: AsOfContext
    statuses: tuple[CorporateActionStatus, ...] = ()
    max_rows: int = 5_000_000

    def __post_init__(self) -> None:
        TimeInterval(self.start, self.end)
        if not self.instruments or len(set(self.instruments)) != len(self.instruments):
            raise MarketDataQueryError("action query requires unique instruments")
        if len(set(self.statuses)) != len(self.statuses) or self.max_rows < 1:
            raise MarketDataQueryError("action query filters are invalid")


@dataclass(frozen=True, slots=True)
class AdjustmentViewRequest:
    bars: BarQuery
    mode: AdjustmentPriceMode
    anchor_at: datetime

    def __post_init__(self) -> None:
        validate_instant(self.anchor_at)
        if self.anchor_at < self.bars.start:
            raise MarketDataQueryError("adjustment anchor precedes the bar range")
