"""Immutable reference, calendar, and universe contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.catalog import CompositeSnapshotRef, SnapshotRef
from persistra.domain import (
    AssetClass,
    ContentId,
    Duration,
    EffectiveInterval,
    EntityId,
    QualifiedName,
    SchemaVersion,
)
from persistra.domain.time import validate_instant
from persistra.errors import ReferenceDefinitionError

if TYPE_CHECKING:
    from datetime import date, datetime


class IssuerId(EntityId):
    KIND: ClassVar[str] = "issuer"


class SecurityId(EntityId):
    KIND: ClassVar[str] = "security"


class VenueId(EntityId):
    KIND: ClassVar[str] = "venue"


class ListingId(EntityId):
    KIND: ClassVar[str] = "listing"


class InstrumentId(EntityId):
    KIND: ClassVar[str] = "instrument"


class IdentifierNamespaceId(EntityId):
    KIND: ClassVar[str] = "identifier_namespace"


class IdentifierAssignmentId(EntityId):
    KIND: ClassVar[str] = "identifier_assignment"


class CalendarId(EntityId):
    KIND: ClassVar[str] = "calendar"


class ClassificationSchemeId(EntityId):
    KIND: ClassVar[str] = "classification_scheme"


class ClassificationNodeId(EntityId):
    KIND: ClassVar[str] = "classification_node"


class ClassificationAssignmentId(EntityId):
    KIND: ClassVar[str] = "classification_assignment"


class UniverseDefinitionId(EntityId):
    KIND: ClassVar[str] = "universe_definition"


class UniverseEvaluationId(EntityId):
    KIND: ClassVar[str] = "universe_evaluation"


@dataclass(frozen=True, slots=True)
class ClassificationSchemeDefinition:
    name: QualifiedName
    version: int
    allows_multiple: bool = False

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ReferenceDefinitionError("classification version must be positive")


@dataclass(frozen=True, slots=True)
class ResolvedClassificationScheme:
    classification_scheme_id: ClassificationSchemeId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class ClassificationNode:
    classification_node_id: ClassificationNodeId
    scheme: ResolvedClassificationScheme
    code: str
    display_name: str
    valid_from: datetime
    valid_to: datetime | None = None
    parent_node_id: ClassificationNodeId | None = None
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.code or not self.display_name:
            raise ReferenceDefinitionError("classification node text is required")
        validate_instant(self.valid_from)
        if self.valid_to is not None:
            EffectiveInterval(self.valid_from, self.valid_to)


@dataclass(frozen=True, slots=True)
class ClassificationAssignment:
    classification_assignment_id: ClassificationAssignmentId
    scheme: ResolvedClassificationScheme
    entity_kind: EntityKind
    entity_id: EntityId
    classification_node_id: ClassificationNodeId
    valid_from: datetime
    valid_to: datetime | None = None
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.entity_kind not in {
            EntityKind.ISSUER,
            EntityKind.SECURITY,
            EntityKind.INSTRUMENT,
        }:
            raise ReferenceDefinitionError("classification entity kind is unsupported")
        validate_instant(self.valid_from)
        if self.valid_to is not None:
            EffectiveInterval(self.valid_from, self.valid_to)


@dataclass(frozen=True, slots=True)
class UniverseMembership:
    source_universe_key: str
    instrument_id: InstrumentId
    role: MembershipRole
    valid_from: datetime
    valid_to: datetime | None = None
    weight: str | None = None
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.source_universe_key:
            raise ReferenceDefinitionError("source universe key is required")
        validate_instant(self.valid_from)
        if self.valid_to is not None:
            EffectiveInterval(self.valid_from, self.valid_to)
        if self.weight is not None:
            from decimal import Decimal

            if Decimal(self.weight) < 0:
                raise ReferenceDefinitionError("membership weight must be nonnegative")


class EntityKind(StrEnum):
    ISSUER = "issuer"
    SECURITY = "security"
    VENUE = "venue"
    LISTING = "listing"
    INSTRUMENT = "instrument"


class SecurityKind(StrEnum):
    COMMON_STOCK = "common_stock"
    ETF = "etf"
    REIT = "reit"
    ADR = "adr"
    SPAC_COMMON = "spac_common"
    PREFERRED_STOCK = "preferred_stock"
    CLOSED_END_FUND = "closed_end_fund"
    FX_PAIR = "fx_pair"
    CRYPTO_PAIR = "crypto_pair"
    COMMODITY = "commodity"
    INDEX = "index"

    @property
    def asset_class(self) -> AssetClass:
        """Return the asset class this security kind belongs to."""
        return _SECURITY_KIND_ASSET_CLASS[self]


_SECURITY_KIND_ASSET_CLASS: dict[SecurityKind, AssetClass] = {
    SecurityKind.COMMON_STOCK: AssetClass.EQUITY,
    SecurityKind.ETF: AssetClass.EQUITY,
    SecurityKind.REIT: AssetClass.EQUITY,
    SecurityKind.ADR: AssetClass.EQUITY,
    SecurityKind.SPAC_COMMON: AssetClass.EQUITY,
    SecurityKind.PREFERRED_STOCK: AssetClass.EQUITY,
    SecurityKind.CLOSED_END_FUND: AssetClass.EQUITY,
    SecurityKind.FX_PAIR: AssetClass.FX,
    SecurityKind.CRYPTO_PAIR: AssetClass.CRYPTO,
    SecurityKind.COMMODITY: AssetClass.COMMODITY,
    SecurityKind.INDEX: AssetClass.INDEX,
}


class SecurityStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MERGED = "merged"
    LIQUIDATED = "liquidated"
    UNKNOWN = "unknown"


class ListingStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"
    DELISTED = "delisted"


class IdentifierKind(StrEnum):
    TICKER = "ticker"
    EXCHANGE_TICKER = "exchange_ticker"
    FIGI = "figi"
    COMPOSITE_FIGI = "composite_figi"
    CUSIP = "cusip"
    ISIN = "isin"
    CIK = "cik"
    LEI = "lei"
    VENDOR = "vendor"


class CutoffMode(StrEnum):
    PUBLIC = "public"
    PUBLIC_AND_PROJECT = "public_and_project"


class SessionDecisionAnchor(StrEnum):
    OPEN = "open"
    CLOSE = "close"


class SessionSelection(StrEnum):
    EVERY_SESSION = "every_session"
    WEEK_END = "week_end"
    MONTH_END = "month_end"
    QUARTER_END = "quarter_end"


class MembershipRole(StrEnum):
    CONSTITUENT = "constituent"
    ELIGIBLE = "eligible"
    WATCHLIST = "watchlist"


@dataclass(frozen=True, slots=True)
class PublicCutoffPolicy:
    lag: Duration = field(default_factory=lambda: Duration(0))
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    @classmethod
    def at_decision(cls) -> PublicCutoffPolicy:
        return cls()

    @classmethod
    def lagged(cls, lag: Duration) -> PublicCutoffPolicy:
        return cls(lag)

    def resolve(self, decision_at: datetime) -> datetime:
        instant = validate_instant(decision_at)
        try:
            return instant - self.lag.to_timedelta()
        except OverflowError as error:
            raise ReferenceDefinitionError("public cutoff underflows datetime") from error


@dataclass(frozen=True, slots=True)
class AsOfContext:
    snapshot: SnapshotRef | CompositeSnapshotRef
    effective_at: datetime
    public_cutoff_at: datetime
    cutoff_mode: CutoffMode = CutoffMode.PUBLIC
    project_cutoff_at: datetime | None = None
    source_precedence: QualifiedName = field(
        default_factory=lambda: QualifiedName("persistra.source_precedence.explicit_order")
    )
    source_precedence_version: int = 1
    market_database: str | None = None

    def __post_init__(self) -> None:
        validate_instant(self.effective_at)
        validate_instant(self.public_cutoff_at)
        if self.cutoff_mode is CutoffMode.PUBLIC:
            if self.project_cutoff_at is not None:
                raise ReferenceDefinitionError(
                    "public cutoff mode forbids a project cutoff"
                )
        elif self.project_cutoff_at is None:
            raise ReferenceDefinitionError(
                "public-and-project cutoff mode requires a project cutoff"
            )
        else:
            validate_instant(self.project_cutoff_at)
        if isinstance(self.snapshot, CompositeSnapshotRef) and not self.market_database:
            raise ReferenceDefinitionError(
                "composite as-of context requires a market database name"
            )


@dataclass(frozen=True, slots=True)
class InstrumentDefinition:
    issuer_id: IssuerId
    security_id: SecurityId
    venue_id: VenueId
    listing_id: ListingId
    instrument_id: InstrumentId
    mic: str
    timezone_name: str
    security_kind: SecurityKind
    security_status: SecurityStatus
    listing_status: ListingStatus
    currency: str
    valid_from: datetime
    valid_to: datetime | None = None
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_instant(self.valid_from)
        if self.valid_to is not None:
            EffectiveInterval(self.valid_from, self.valid_to)
        if self.available_at is not None:
            validate_instant(self.available_at)
        if len(self.mic) != 4 or not self.mic.isascii() or not self.mic.isupper():
            raise ReferenceDefinitionError("venue MIC must be four uppercase ASCII letters")
        if self.currency != "USD":
            raise ReferenceDefinitionError("phase 3 supports only USD instruments")


@dataclass(frozen=True, slots=True)
class IdentifierNamespaceDefinition:
    name: QualifiedName
    version: int
    kind: IdentifierKind
    entity_kind: EntityKind
    case_sensitive: bool = False
    venue_scoped: bool = False

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ReferenceDefinitionError("identifier namespace version must be positive")


@dataclass(frozen=True, slots=True)
class ResolvedIdentifierNamespace:
    namespace_id: IdentifierNamespaceId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class IdentifierAssignment:
    namespace: ResolvedIdentifierNamespace
    raw_value: str
    entity_kind: EntityKind
    entity_id: EntityId
    valid_from: datetime
    valid_to: datetime | None = None
    venue_id: VenueId | None = None
    is_primary: bool = False
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_instant(self.valid_from)
        if self.valid_to is not None:
            EffectiveInterval(self.valid_from, self.valid_to)
        if not self.raw_value or len(self.raw_value) > 255:
            raise ReferenceDefinitionError("identifier value is empty or too long")


@dataclass(frozen=True, slots=True)
class IdentifierResolution:
    state: str
    entity_kind: EntityKind | None
    entity_id: EntityId | None
    assignment_ids: tuple[IdentifierAssignmentId, ...] = ()


@dataclass(frozen=True, slots=True)
class CalendarRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ResolvedCalendarRef:
    calendar_id: CalendarId
    version: int
    definition_content_id: ContentId
    schedule_root_content_id: ContentId


@dataclass(frozen=True, slots=True)
class CalendarDefinition:
    name: QualifiedName
    version: int
    venue_id: VenueId
    exchange_calendar_name: str
    timezone_name: str
    coverage_start: date
    coverage_end: date
    available_at: datetime

    def __post_init__(self) -> None:
        if self.version < 1 or self.coverage_start >= self.coverage_end:
            raise ReferenceDefinitionError("calendar version or coverage is invalid")
        validate_instant(self.available_at)


@dataclass(frozen=True, slots=True)
class Session:
    calendar_date: date
    open_at: datetime
    close_at: datetime
    break_start_at: datetime | None = None
    break_end_at: datetime | None = None
    is_early_close: bool = False


@dataclass(frozen=True, slots=True)
class NonSession:
    calendar_date: date
    closure_reason: str


CalendarDay = Session | NonSession


@dataclass(frozen=True, slots=True)
class SessionDecisionSchedule:
    calendar: CalendarRef
    anchor: SessionDecisionAnchor
    selection: SessionSelection
    delay: Duration = field(default_factory=lambda: Duration(0))


@dataclass(frozen=True, slots=True)
class DecisionInstant:
    decision_at: datetime
    session_date: date


@dataclass(frozen=True, slots=True)
class ExplicitMembership:
    source_universe_key: str
    roles: tuple[MembershipRole, ...] = (MembershipRole.CONSTITUENT,)


@dataclass(frozen=True, slots=True)
class ActiveListings:
    venues: tuple[VenueId, ...]
    security_kinds: tuple[SecurityKind, ...]


@dataclass(frozen=True, slots=True)
class ExplicitInstrument:
    instrument_id: InstrumentId
    valid_from: datetime
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class ExplicitInstruments:
    instruments: tuple[ExplicitInstrument, ...]


CandidateExpression = ExplicitMembership | ActiveListings | ExplicitInstruments


@dataclass(frozen=True, slots=True)
class UniverseRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class UniverseDefinition:
    name: QualifiedName
    version: int
    candidate_expression: CandidateExpression
    require_active_listing: bool = True
    allowed_security_kinds: tuple[SecurityKind, ...] = (
        SecurityKind.COMMON_STOCK,
        SecurityKind.ETF,
        SecurityKind.REIT,
        SecurityKind.ADR,
        SecurityKind.SPAC_COMMON,
    )
    required_identifier_namespace: QualifiedName | None = None

    def __post_init__(self) -> None:
        if self.version < 1 or not self.allowed_security_kinds:
            raise ReferenceDefinitionError("universe definition is invalid")


@dataclass(frozen=True, slots=True)
class ResolvedUniverseRef:
    universe_definition_id: UniverseDefinitionId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class UniverseEvaluationRef:
    universe_evaluation_id: UniverseEvaluationId
    universe_definition_id: UniverseDefinitionId
    definition_version: int
    composite_snapshot_id: EntityId
    execution_content_id: ContentId
    calendar_schedule_content_id: ContentId
