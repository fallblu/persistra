"""Canonical fundamental, estimate, macro, benchmark, and rate contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import (
    AvailabilityQuality,
    ContentId,
    Currency,
    EntityId,
    QualifiedName,
    SchemaVersion,
    SourceNumeric,
    UnitSpec,
)
from persistra.domain.time import validate_instant
from persistra.errors import (
    BenchmarkResolutionError,
    EstimateQueryError,
    FilingResolutionError,
    FundamentalMappingError,
    FundamentalQueryError,
    MacroQueryError,
    RateConventionError,
)

if TYPE_CHECKING:
    from datetime import date, datetime

    from persistra.catalog import CanonicalRevisionId, SourceId
    from persistra.reference import (
        AsOfContext,
        CalendarRef,
        InstrumentId,
        IssuerId,
    )


class ReportId(EntityId):
    KIND: ClassVar[str] = "report"


class FilingId(EntityId):
    KIND: ClassVar[str] = "filing"


class NormalizedConceptId(EntityId):
    KIND: ClassVar[str] = "normalized_concept"


class FundamentalMappingId(EntityId):
    KIND: ClassVar[str] = "fundamental_mapping"


class FundamentalNormalizationId(EntityId):
    KIND: ClassVar[str] = "fundamental_normalization"


class FundamentalNormalizationRunId(EntityId):
    KIND: ClassVar[str] = "fundamental_normalization_run"


class EstimateMeasureId(EntityId):
    KIND: ClassVar[str] = "estimate_measure"


class EstimateContributorId(EntityId):
    KIND: ClassVar[str] = "estimate_contributor"


class MacroSeriesId(EntityId):
    KIND: ClassVar[str] = "macro_series"


class MacroReleaseId(EntityId):
    KIND: ClassVar[str] = "macro_release"


class BenchmarkId(EntityId):
    KIND: ClassVar[str] = "benchmark"


class RiskFreeCurveId(EntityId):
    KIND: ClassVar[str] = "risk_free_curve"


class FactPeriodKind(StrEnum):
    INSTANT = "instant"
    DURATION = "duration"


class FactNumericKind(StrEnum):
    AMOUNT = "amount"
    RATE = "rate"
    COUNT = "count"
    PURE = "pure"


class FiscalPeriodKind(StrEnum):
    FY = "fy"
    Q1 = "q1"
    Q2 = "q2"
    Q3 = "q3"
    Q4 = "q4"
    H1 = "h1"
    H2 = "h2"
    YTD = "ytd"
    LTM = "ltm"
    OTHER = "other"


class FilingStatus(StrEnum):
    FILED = "filed"
    ACCEPTED = "accepted"
    WITHDRAWN = "withdrawn"


class FilingMode(StrEnum):
    AS_REPORTED = "as_reported"
    ORIGINAL = "original"
    LATEST_FILING_IN_REPORT = "latest_filing_in_report"
    LATEST_KNOWN_FACT = "latest_known_fact"
    ALL_FILINGS = "all_filings"


class EstimateObservationKind(StrEnum):
    INDIVIDUAL = "individual"
    CONSENSUS = "consensus"
    ACTUAL = "actual"


class EstimateTargetKind(StrEnum):
    FISCAL_PERIOD = "fiscal_period"
    FIXED_HORIZON = "fixed_horizon"


class MacroVintageStatus(StrEnum):
    ADVANCE = "advance"
    PRELIMINARY = "preliminary"
    REVISED = "revised"
    FINAL = "final"
    BENCHMARK_REVISION = "benchmark_revision"


class MacroVintageMode(StrEnum):
    EXACT_RELEASE = "exact_release"
    FIRST_RELEASE = "first_release"
    LATEST_KNOWN = "latest_known"
    ALL_VINTAGES = "all_vintages"


class VintageCompleteness(StrEnum):
    COMPLETE = "complete"
    LATEST_ONLY = "latest_only"
    UNKNOWN = "unknown"


class BenchmarkKind(StrEnum):
    INSTRUMENT = "instrument"
    SOURCE_SERIES = "source_series"
    CONSTITUENTS = "constituents"


class BenchmarkSeriesKind(StrEnum):
    PRICE_INDEX = "price_index"
    TOTAL_RETURN_INDEX = "total_return_index"
    PERIOD_RETURN = "period_return"


class RateQuoteKind(StrEnum):
    SIMPLE_YIELD = "simple_yield"
    BOND_EQUIVALENT_YIELD = "bond_equivalent_yield"
    PERIODIC_ZERO = "periodic_zero"
    CONTINUOUS_ZERO = "continuous_zero"
    DISCOUNT_FACTOR = "discount_factor"
    OVERNIGHT_RATE = "overnight_rate"


class CompoundingKind(StrEnum):
    SIMPLE = "simple"
    PERIODIC = "periodic"
    CONTINUOUS = "continuous"
    DISCOUNT_FACTOR = "discount_factor"


class DayCountKind(StrEnum):
    ACT_360 = "act_360"
    ACT_365F = "act_365f"
    ACT_ACT_ISDA = "act_act_isda"
    THIRTY_360_US = "thirty_360_us"


class TenorKind(StrEnum):
    DAYS = "days"
    MONTHS = "months"


@dataclass(frozen=True, slots=True)
class Tenor:
    kind: TenorKind
    count: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise RateConventionError("tenor count must be positive")

    @classmethod
    def days(cls, count: int) -> Tenor:
        return cls(TenorKind.DAYS, count)

    @classmethod
    def months(cls, count: int) -> Tenor:
        return cls(TenorKind.MONTHS, count)


@dataclass(frozen=True, slots=True)
class FilingObservation:
    filing_id: FilingId
    report_id: ReportId
    issuer_id: IssuerId
    accession_namespace: str
    normalized_accession: str
    source_filing_key: str
    form_type: str
    status: FilingStatus
    filing_date: date
    report_period_end: date
    available_at: datetime
    accepted_at: datetime | None = None
    report_period_start: date | None = None
    fiscal_year: int | None = None
    fiscal_period_kind: FiscalPeriodKind | None = None
    is_amendment: bool = False
    amends_filing_id: FilingId | None = None
    taxonomy_namespace: str | None = None
    taxonomy_version: str | None = None
    document_content_id: ContentId = field(
        default_factory=lambda: ContentId.from_bytes(b"empty-filing-document")
    )
    document_location: str | None = None
    document_redistributable: bool = False
    source_metadata: tuple[tuple[str, str], ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.available_at)
        if self.status is FilingStatus.ACCEPTED and self.accepted_at is None:
            raise FilingResolutionError("accepted filing requires acceptance time")
        if self.accepted_at is not None:
            validate_instant(self.accepted_at)
        if self.is_amendment != (self.amends_filing_id is not None):
            raise FilingResolutionError("filing amendment linkage is inconsistent")
        if not all(
            (self.accession_namespace, self.normalized_accession, self.source_filing_key)
        ):
            raise FilingResolutionError("filing source identities are required")


@dataclass(frozen=True, slots=True)
class RawFundamentalFact:
    filing_id: FilingId
    report_id: ReportId
    issuer_id: IssuerId
    taxonomy_namespace: str
    taxonomy_version: str
    source_concept_name: str
    period_kind: FactPeriodKind
    period_end: date
    period_policy_content_id: ContentId
    numeric_kind: FactNumericKind
    unit: UnitSpec
    available_at: datetime
    value: SourceNumeric | None = None
    is_nil: bool = False
    nil_reason_code: str | None = None
    period_start: date | None = None
    fiscal_year: int | None = None
    fiscal_period_kind: FiscalPeriodKind | None = None
    currency: Currency | None = None
    source_decimals: int | None = None
    source_precision: int | None = None
    dimensions: tuple[tuple[str, str], ...] = ()
    source_fact_key: str | None = None
    source_metadata: tuple[tuple[str, str], ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.available_at)
        if self.period_kind is FactPeriodKind.INSTANT and self.period_start is not None:
            raise FundamentalQueryError("instant fact forbids a period start")
        if self.period_kind is FactPeriodKind.DURATION and (
            self.period_start is None or self.period_start > self.period_end
        ):
            raise FundamentalQueryError("duration fact period is invalid")
        if self.is_nil != (self.value is None) or self.is_nil != (
            self.nil_reason_code is not None
        ):
            raise FundamentalQueryError("fact nil/value state is inconsistent")
        if self.value is not None and self.value.kind.value != self.numeric_kind.value:
            raise FundamentalQueryError("fact numeric tag conflicts with its value")


@dataclass(frozen=True, slots=True)
class NormalizedConceptDefinition:
    name: QualifiedName
    version: int
    period_kind: FactPeriodKind
    numeric_kind: FactNumericKind
    canonical_unit: UnitSpec
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    def __post_init__(self) -> None:
        if self.version < 1:
            raise FundamentalMappingError("concept version must be positive")


@dataclass(frozen=True, slots=True)
class FundamentalMappingDefinition:
    name: QualifiedName
    version: int
    source_taxonomy_namespace: str
    source_taxonomy_version_pattern: str
    source_concept_name: str
    normalized_concept_id: NormalizedConceptId
    normalized_concept_version: int
    sign_multiplier: SourceNumeric
    scale_multiplier: SourceNumeric
    dimension_policy_content_id: ContentId
    applicability: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.version < 1 or self.normalized_concept_version < 1:
            raise FundamentalMappingError("mapping versions must be positive")


@dataclass(frozen=True, slots=True)
class EstimateMeasureDefinition:
    name: QualifiedName
    version: int
    entity_kind: str
    numeric_kind: FactNumericKind
    canonical_unit: UnitSpec
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    def __post_init__(self) -> None:
        if self.version < 1 or self.entity_kind not in {
            "issuer",
            "security",
            "instrument",
        }:
            raise EstimateQueryError("estimate measure definition is invalid")


@dataclass(frozen=True, slots=True)
class EstimateTarget:
    kind: EstimateTargetKind
    policy_content_id: ContentId
    fiscal_year: int | None = None
    fiscal_period_kind: FiscalPeriodKind | None = None
    period_end: date | None = None
    report_id: ReportId | None = None
    horizon_days: int | None = None
    target_at: datetime | None = None

    def __post_init__(self) -> None:
        fiscal = self.kind is EstimateTargetKind.FISCAL_PERIOD
        if fiscal:
            if (
                self.fiscal_year is None
                or self.fiscal_period_kind is None
                or self.period_end is None
                or self.horizon_days is not None
                or self.target_at is not None
            ):
                raise EstimateQueryError("fiscal estimate target is incomplete")
        elif (
            self.horizon_days is None
            or self.horizon_days < 1
            or self.target_at is None
            or self.fiscal_year is not None
            or self.fiscal_period_kind is not None
            or self.period_end is not None
            or self.report_id is not None
        ):
            raise EstimateQueryError("fixed-horizon estimate target is incomplete")
        if self.target_at is not None:
            validate_instant(self.target_at)


@dataclass(frozen=True, slots=True)
class IndividualEstimate:
    source_estimate_key: str
    measure_id: EstimateMeasureId
    measure_version: int
    subject_entity_kind: str
    subject_entity_id: EntityId
    target: EstimateTarget
    value: SourceNumeric
    available_at: datetime
    event_at: datetime
    contributor_id: EstimateContributorId | None = None
    currency: Currency | None = None
    split_basis_content_id: ContentId | None = None
    source_revision_label: str | None = None
    source_metadata: tuple[tuple[str, str], ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.event_at)
        validate_instant(self.available_at)
        if self.available_at < self.event_at or not self.source_estimate_key:
            raise EstimateQueryError("estimate timing or source key is invalid")


@dataclass(frozen=True, slots=True)
class ConsensusEstimate:
    source_consensus_key: str
    measure_id: EstimateMeasureId
    measure_version: int
    subject_entity_kind: str
    subject_entity_id: EntityId
    target: EstimateTarget
    contributor_count: int
    unit: UnitSpec
    methodology_content_id: ContentId
    available_at: datetime
    event_at: datetime
    mean: SourceNumeric | None = None
    median: SourceNumeric | None = None
    high: SourceNumeric | None = None
    low: SourceNumeric | None = None
    standard_deviation: SourceNumeric | None = None
    currency: Currency | None = None
    constituent_manifest_content_id: ContentId | None = None
    source_metadata: tuple[tuple[str, str], ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.event_at)
        validate_instant(self.available_at)
        values = (self.mean, self.median, self.high, self.low, self.standard_deviation)
        if self.contributor_count < 0 or (
            self.contributor_count == 0 and any(value is not None for value in values)
        ) or (
            self.contributor_count > 0
            and all(value is None for value in values[:4])
        ):
            raise EstimateQueryError("consensus count/statistics are inconsistent")
        if (self.high is None) != (self.low is None):
            raise EstimateQueryError("consensus high and low must be paired")
        if self.high is not None and self.low is not None:
            if self.low.value > self.high.value:
                raise EstimateQueryError("consensus range is inverted")
            for value in (self.mean, self.median):
                if value is not None and not self.low.value <= value.value <= self.high.value:
                    raise EstimateQueryError("consensus statistic is outside its range")
        if (
            self.standard_deviation is not None
            and self.standard_deviation.value < 0
        ):
            raise EstimateQueryError("consensus dispersion must be nonnegative")


@dataclass(frozen=True, slots=True)
class ActualObservation:
    source_actual_key: str
    measure_id: EstimateMeasureId
    measure_version: int
    subject_entity_kind: str
    subject_entity_id: EntityId
    target_period_end: date
    value: SourceNumeric
    actual_policy_content_id: ContentId
    available_at: datetime
    event_at: datetime
    fiscal_year: int | None = None
    fiscal_period_kind: FiscalPeriodKind | None = None
    currency: Currency | None = None
    filing_id: FilingId | None = None
    raw_fact_revision_id: CanonicalRevisionId | None = None
    normalization_id: FundamentalNormalizationId | None = None
    source_metadata: tuple[tuple[str, str], ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.event_at)
        validate_instant(self.available_at)
        if (self.fiscal_year is None) != (self.fiscal_period_kind is None):
            raise EstimateQueryError("actual fiscal labels are incomplete")


@dataclass(frozen=True, slots=True)
class MacroSeriesRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class MacroSeriesDefinition:
    name: QualifiedName
    version: int
    frequency: QualifiedName
    seasonal_adjustment_status: QualifiedName
    geography_code: QualifiedName
    unit: UnitSpec
    numeric_kind: FactNumericKind
    vintage_completeness: VintageCompleteness
    period_policy_content_id: ContentId
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    def __post_init__(self) -> None:
        if self.version < 1:
            raise MacroQueryError("macro series version must be positive")


@dataclass(frozen=True, slots=True)
class ResolvedMacroSeriesRef:
    macro_series_id: MacroSeriesId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class MacroRelease:
    release_id: MacroReleaseId
    series: ResolvedMacroSeriesRef
    source_release_key: str
    release_at: datetime
    available_at: datetime
    release_manifest_content_id: ContentId
    observations: tuple[MacroObservation, ...]
    source_release_sequence: int | None = None
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.release_at)
        validate_instant(self.available_at)
        if self.available_at < self.release_at or not self.source_release_key:
            raise MacroQueryError("macro release timing or key is invalid")
        if self.source_release_sequence is not None and self.source_release_sequence < 1:
            raise MacroQueryError("macro release sequence must be positive")
        if not self.observations:
            raise MacroQueryError("macro release requires observations")


@dataclass(frozen=True, slots=True)
class MacroObservation:
    source_vintage_key: str
    period_start: date
    period_end: date
    vintage_status: MacroVintageStatus
    unit: UnitSpec
    value: SourceNumeric | None = None
    is_missing: bool = False
    missing_reason_code: str | None = None
    source_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.period_start > self.period_end:
            raise MacroQueryError("macro observation period is invalid")
        if self.is_missing != (self.value is None) or self.is_missing != (
            self.missing_reason_code is not None
        ):
            raise MacroQueryError("macro missing/value state is inconsistent")


@dataclass(frozen=True, slots=True)
class BenchmarkVersionRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class BenchmarkDefinition:
    name: QualifiedName
    version: int
    kind: BenchmarkKind
    instrument_id: InstrumentId | None
    currency: Currency
    calendar: CalendarRef
    methodology_content_id: ContentId
    licensing_class: str
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    def __post_init__(self) -> None:
        if self.version < 1 or (
            (self.kind is BenchmarkKind.INSTRUMENT) != (self.instrument_id is not None)
        ):
            raise BenchmarkResolutionError("benchmark definition variant is invalid")


@dataclass(frozen=True, slots=True)
class ResolvedBenchmarkVersionRef:
    benchmark_id: BenchmarkId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class BenchmarkSeriesObservation:
    benchmark: ResolvedBenchmarkVersionRef
    series_kind: BenchmarkSeriesKind
    interval_end: datetime
    value: SourceNumeric
    currency: Currency
    calendar_schedule_content_id: ContentId
    source_methodology_content_id: ContentId
    available_at: datetime
    interval_start: datetime | None = None
    session_date: date | None = None
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.interval_end)
        validate_instant(self.available_at)
        if self.series_kind is BenchmarkSeriesKind.PERIOD_RETURN:
            if self.interval_start is None or self.interval_start >= self.interval_end:
                raise BenchmarkResolutionError("benchmark return interval is invalid")
            if self.value.value <= -1:
                raise BenchmarkResolutionError("benchmark period return is invalid")
        elif self.interval_start is not None or self.value.value <= 0:
            raise BenchmarkResolutionError("benchmark index level is invalid")


@dataclass(frozen=True, slots=True)
class BenchmarkConstituent:
    benchmark: ResolvedBenchmarkVersionRef
    instrument_id: InstrumentId
    membership_role: str
    valid_from: datetime
    methodology_content_id: ContentId
    available_at: datetime
    valid_to: datetime | None = None
    weight: SourceNumeric | None = None
    index_shares: SourceNumeric | None = None
    divisor_contribution: SourceNumeric | None = None
    source_metadata: tuple[tuple[str, str], ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.valid_from)
        validate_instant(self.available_at)
        if self.valid_to is not None:
            validate_instant(self.valid_to)
            if self.valid_to <= self.valid_from:
                raise BenchmarkResolutionError("constituent interval is invalid")
        if self.weight is not None and not 0 <= self.weight.value <= 1:
            raise BenchmarkResolutionError("constituent weight is invalid")


@dataclass(frozen=True, slots=True)
class RiskFreeCurveRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class RiskFreeCurveDefinition:
    name: QualifiedName
    version: int
    currency: Currency
    quote_kind: RateQuoteKind
    compounding: CompoundingKind
    compounding_periods_per_year: int | None
    day_count: DayCountKind
    calendar: CalendarRef
    business_day_policy_content_id: ContentId
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))

    def __post_init__(self) -> None:
        periodic = self.compounding is CompoundingKind.PERIODIC
        if self.version < 1 or periodic != (
            self.compounding_periods_per_year is not None
        ):
            raise RateConventionError("curve compounding variant is invalid")
        if periodic and cast_int(self.compounding_periods_per_year) < 1:
            raise RateConventionError("periodic compounding frequency is invalid")
        discount = self.quote_kind is RateQuoteKind.DISCOUNT_FACTOR
        if discount != (self.compounding is CompoundingKind.DISCOUNT_FACTOR):
            raise RateConventionError("discount-factor convention is inconsistent")


def cast_int(value: int | None) -> int:
    assert value is not None
    return value


@dataclass(frozen=True, slots=True)
class ResolvedRiskFreeCurveRef:
    risk_free_curve_id: RiskFreeCurveId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class RiskFreePoint:
    curve: ResolvedRiskFreeCurveRef
    source_release_key: str
    effective_date: date
    release_at: datetime
    available_at: datetime
    tenor: Tenor
    value: SourceNumeric
    quote_kind: RateQuoteKind
    compounding: CompoundingKind
    compounding_periods_per_year: int | None
    day_count: DayCountKind
    source_curve_manifest_content_id: ContentId
    maturity_date: date | None = None
    source_metadata: tuple[tuple[str, str], ...] = ()
    canonical_revision_id: CanonicalRevisionId | None = None
    source_id: SourceId | None = None
    availability_quality: AvailabilityQuality = AvailabilityQuality.OBSERVED

    def __post_init__(self) -> None:
        validate_instant(self.release_at)
        validate_instant(self.available_at)
        if self.available_at < self.release_at:
            raise RateConventionError("rate availability precedes release")
        if (
            self.quote_kind is RateQuoteKind.DISCOUNT_FACTOR
            and self.value.value <= 0
        ):
            raise RateConventionError("discount factor must be positive")


@dataclass(frozen=True, slots=True)
class FundamentalQuery:
    issuers: tuple[IssuerId, ...]
    concepts: tuple[QualifiedName, ...]
    filing_mode: FilingMode
    start_date: date
    end_date: date
    context: AsOfContext
    period_kind: FactPeriodKind | None = None
    max_rows: int = 2_000_000

    def __post_init__(self) -> None:
        if (
            not self.issuers
            or not self.concepts
            or self.start_date > self.end_date
            or self.max_rows < 1
        ):
            raise FundamentalQueryError("fundamental query bounds are invalid")


@dataclass(frozen=True, slots=True)
class EstimateQuery:
    subjects: tuple[EntityId, ...]
    measures: tuple[QualifiedName, ...]
    target_kind: EstimateTargetKind
    start: datetime
    end: datetime
    context: AsOfContext
    max_rows: int = 2_000_000

    def __post_init__(self) -> None:
        validate_instant(self.start)
        validate_instant(self.end)
        if not self.subjects or not self.measures or self.start >= self.end:
            raise EstimateQueryError("estimate query bounds are invalid")


@dataclass(frozen=True, slots=True)
class MacroQuery:
    series: MacroSeriesRef
    start_date: date
    end_date: date
    vintage_mode: MacroVintageMode
    context: AsOfContext
    exact_release_id: MacroReleaseId | None = None
    max_rows: int = 2_000_000

    def __post_init__(self) -> None:
        if self.start_date > self.end_date or (
            self.vintage_mode is MacroVintageMode.EXACT_RELEASE
        ) != (self.exact_release_id is not None):
            raise MacroQueryError("macro query bounds or exact release are invalid")


@dataclass(frozen=True, slots=True)
class BenchmarkQuery:
    benchmark: BenchmarkVersionRef
    start: datetime
    end: datetime
    context: AsOfContext
    series_kind: BenchmarkSeriesKind | None = None
    max_rows: int = 2_000_000

    def __post_init__(self) -> None:
        validate_instant(self.start)
        validate_instant(self.end)
        if self.start >= self.end or self.max_rows < 1:
            raise BenchmarkResolutionError("benchmark query bounds are invalid")


@dataclass(frozen=True, slots=True)
class RiskFreeQuery:
    curve: RiskFreeCurveRef
    start_date: date
    end_date: date
    tenors: tuple[Tenor, ...]
    context: AsOfContext
    max_rows: int = 2_000_000

    def __post_init__(self) -> None:
        if (
            self.start_date > self.end_date
            or not self.tenors
            or len(set(self.tenors)) != len(self.tenors)
        ):
            raise RateConventionError("rate query bounds are invalid")
