from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from persistra.domain import ContentId, QualifiedName
from persistra.domain.numbers import (
    NumericKind,
    SourceNumeric,
    SourceNumericKind,
    Unit,
    UnitSpec,
)
from persistra.errors import (
    BenchmarkResolutionError,
    EstimateQueryError,
    FilingResolutionError,
    FundamentalMappingError,
    FundamentalQueryError,
    MacroQueryError,
    RateConventionError,
)
from persistra.market.economic_models import (
    ActualObservation,
    BenchmarkConstituent,
    BenchmarkDefinition,
    BenchmarkId,
    BenchmarkKind,
    BenchmarkQuery,
    BenchmarkSeriesKind,
    BenchmarkSeriesObservation,
    BenchmarkVersionRef,
    CompoundingKind,
    ConsensusEstimate,
    DayCountKind,
    EstimateMeasureDefinition,
    EstimateMeasureId,
    EstimateQuery,
    EstimateTarget,
    EstimateTargetKind,
    FactNumericKind,
    FactPeriodKind,
    FilingId,
    FilingMode,
    FilingObservation,
    FilingStatus,
    FiscalPeriodKind,
    FundamentalMappingDefinition,
    FundamentalQuery,
    IndividualEstimate,
    MacroObservation,
    MacroQuery,
    MacroRelease,
    MacroReleaseId,
    MacroSeriesDefinition,
    MacroSeriesId,
    MacroSeriesRef,
    MacroVintageMode,
    MacroVintageStatus,
    NormalizedConceptDefinition,
    NormalizedConceptId,
    RateQuoteKind,
    ReportId,
    ResolvedBenchmarkVersionRef,
    ResolvedMacroSeriesRef,
    ResolvedRiskFreeCurveRef,
    RiskFreeCurveDefinition,
    RiskFreeCurveId,
    RiskFreeCurveRef,
    RiskFreePoint,
    RiskFreeQuery,
    Tenor,
    VintageCompleteness,
)
from persistra.reference import InstrumentId, IssuerId
from persistra.reference.models import CalendarRef

_AT = datetime(2025, 1, 6, tzinfo=UTC)
_CONTEXT = cast("Any", None)
_UNIT = UnitSpec(Unit("usd"), NumericKind.DECIMAL)
_RATE_UNIT = UnitSpec(Unit("rate"), NumericKind.DECIMAL)
_CONTENT = ContentId.from_bytes(b"content")


def _numeric(value: str, kind: SourceNumericKind = SourceNumericKind.AMOUNT) -> SourceNumeric:
    return SourceNumeric(Decimal(value), kind, _UNIT)


def test_tenor_filing_and_fundamental_validation() -> None:
    assert Tenor.days(30).count == 30
    assert Tenor.months(3).kind.value == "months"
    with pytest.raises(RateConventionError):
        Tenor.days(0)

    def filing(**overrides: object) -> FilingObservation:
        values: dict[str, Any] = {
            "filing_id": FilingId.new(),
            "report_id": ReportId.new(),
            "issuer_id": IssuerId.new(),
            "accession_namespace": "sec",
            "normalized_accession": "0000000000-25-000001",
            "source_filing_key": "filing-1",
            "form_type": "10-K",
            "status": FilingStatus.FILED,
            "filing_date": date(2025, 1, 6),
            "report_period_end": date(2024, 12, 31),
            "available_at": _AT,
        }
        values.update(overrides)
        return FilingObservation(**values)

    assert filing().status is FilingStatus.FILED
    with pytest.raises(FilingResolutionError):
        filing(status=FilingStatus.ACCEPTED)
    with pytest.raises(FilingResolutionError):
        filing(is_amendment=True)
    with pytest.raises(FilingResolutionError):
        filing(source_filing_key="")

    with pytest.raises(FundamentalMappingError):
        NormalizedConceptDefinition(
            QualifiedName("persistra.concept.revenue"),
            0,
            FactPeriodKind.DURATION,
            FactNumericKind.AMOUNT,
            _UNIT,
        )
    with pytest.raises(FundamentalMappingError):
        FundamentalMappingDefinition(
            QualifiedName("persistra.mapping.revenue"),
            1,
            "sec",
            "*",
            "Revenues",
            NormalizedConceptId.new(),
            0,
            _numeric("1", SourceNumericKind.PURE),
            _numeric("1", SourceNumericKind.PURE),
            _CONTENT,
        )


def test_estimate_target_and_observation_validation() -> None:
    fiscal = EstimateTarget(
        EstimateTargetKind.FISCAL_PERIOD,
        _CONTENT,
        fiscal_year=2025,
        fiscal_period_kind=FiscalPeriodKind.FY,
        period_end=date(2025, 12, 31),
    )
    assert fiscal.fiscal_year == 2025
    horizon = EstimateTarget(
        EstimateTargetKind.FIXED_HORIZON,
        _CONTENT,
        horizon_days=30,
        target_at=_AT,
    )
    assert horizon.horizon_days == 30
    with pytest.raises(EstimateQueryError):
        EstimateTarget(EstimateTargetKind.FISCAL_PERIOD, _CONTENT)
    with pytest.raises(EstimateQueryError):
        EstimateTarget(EstimateTargetKind.FIXED_HORIZON, _CONTENT, horizon_days=0)

    with pytest.raises(EstimateQueryError):
        EstimateMeasureDefinition(
            QualifiedName("persistra.measure.eps"),
            1,
            "portfolio",
            FactNumericKind.AMOUNT,
            _UNIT,
        )

    def estimate(**overrides: object) -> IndividualEstimate:
        values: dict[str, Any] = {
            "source_estimate_key": "estimate-1",
            "measure_id": EstimateMeasureId.new(),
            "measure_version": 1,
            "subject_entity_kind": "issuer",
            "subject_entity_id": IssuerId.new(),
            "target": fiscal,
            "value": _numeric("1.25"),
            "available_at": _AT,
            "event_at": _AT,
        }
        values.update(overrides)
        return IndividualEstimate(**values)

    assert estimate().measure_version == 1
    with pytest.raises(EstimateQueryError):
        estimate(available_at=_AT - timedelta(seconds=1))

    def consensus(**overrides: object) -> ConsensusEstimate:
        values: dict[str, Any] = {
            "source_consensus_key": "consensus-1",
            "measure_id": EstimateMeasureId.new(),
            "measure_version": 1,
            "subject_entity_kind": "issuer",
            "subject_entity_id": IssuerId.new(),
            "target": fiscal,
            "contributor_count": 3,
            "unit": _UNIT,
            "methodology_content_id": _CONTENT,
            "available_at": _AT,
            "event_at": _AT,
            "mean": _numeric("1.5"),
            "high": _numeric("2"),
            "low": _numeric("1"),
        }
        values.update(overrides)
        return ConsensusEstimate(**values)

    assert consensus().contributor_count == 3
    with pytest.raises(EstimateQueryError):
        consensus(contributor_count=0)
    with pytest.raises(EstimateQueryError):
        consensus(low=None)
    with pytest.raises(EstimateQueryError):
        consensus(high=_numeric("0.5"), low=_numeric("1"), mean=_numeric("0.75"))
    with pytest.raises(EstimateQueryError):
        consensus(mean=_numeric("5"))
    with pytest.raises(EstimateQueryError):
        consensus(
            standard_deviation=SourceNumeric(
                Decimal("-1"), SourceNumericKind.AMOUNT, _UNIT
            )
        )

    with pytest.raises(EstimateQueryError):
        ActualObservation(
            "actual-1",
            EstimateMeasureId.new(),
            1,
            "issuer",
            IssuerId.new(),
            date(2024, 12, 31),
            _numeric("1"),
            _CONTENT,
            _AT,
            _AT,
            fiscal_year=2024,
        )


def test_macro_and_benchmark_validation() -> None:
    with pytest.raises(MacroQueryError):
        MacroSeriesDefinition(
            QualifiedName("persistra.macro.cpi"),
            0,
            QualifiedName("persistra.frequency.monthly"),
            QualifiedName("persistra.sa.adjusted"),
            QualifiedName("persistra.geo.us"),
            _UNIT,
            FactNumericKind.PURE,
            VintageCompleteness.COMPLETE,
            _CONTENT,
        )
    observation = MacroObservation(
        "vintage-1",
        date(2024, 12, 1),
        date(2024, 12, 31),
        MacroVintageStatus.FINAL,
        _UNIT,
        value=_numeric("100"),
    )
    with pytest.raises(MacroQueryError):
        MacroObservation(
            "vintage-1",
            date(2024, 12, 31),
            date(2024, 12, 1),
            MacroVintageStatus.FINAL,
            _UNIT,
            value=_numeric("100"),
        )
    with pytest.raises(MacroQueryError):
        MacroObservation(
            "vintage-1",
            date(2024, 12, 1),
            date(2024, 12, 31),
            MacroVintageStatus.FINAL,
            _UNIT,
            value=_numeric("100"),
            is_missing=True,
        )

    series = ResolvedMacroSeriesRef(MacroSeriesId.new(), 1, _CONTENT)

    def release(**overrides: object) -> MacroRelease:
        values: dict[str, Any] = {
            "release_id": MacroReleaseId.new(),
            "series": series,
            "source_release_key": "release-1",
            "release_at": _AT,
            "available_at": _AT,
            "release_manifest_content_id": _CONTENT,
            "observations": (observation,),
        }
        values.update(overrides)
        return MacroRelease(**values)

    assert release().observations == (observation,)
    with pytest.raises(MacroQueryError):
        release(available_at=_AT - timedelta(seconds=1))
    with pytest.raises(MacroQueryError):
        release(source_release_sequence=0)
    with pytest.raises(MacroQueryError):
        release(observations=())

    calendar = CalendarRef(QualifiedName("persistra.calendar.xnys"), 1)
    with pytest.raises(BenchmarkResolutionError):
        BenchmarkDefinition(
            QualifiedName("persistra.benchmark.total_market"),
            1,
            BenchmarkKind.INSTRUMENT,
            None,
            cast("Any", None),
            calendar,
            _CONTENT,
            "open",
        )
    resolved = ResolvedBenchmarkVersionRef(BenchmarkId.new(), 1, _CONTENT)

    def series_observation(**overrides: object) -> BenchmarkSeriesObservation:
        values: dict[str, Any] = {
            "benchmark": resolved,
            "series_kind": BenchmarkSeriesKind.PERIOD_RETURN,
            "interval_end": _AT,
            "value": _numeric("0.01", SourceNumericKind.RATE),
            "currency": cast("Any", None),
            "calendar_schedule_content_id": _CONTENT,
            "source_methodology_content_id": _CONTENT,
            "available_at": _AT,
            "interval_start": _AT - timedelta(days=1),
        }
        values.update(overrides)
        return BenchmarkSeriesObservation(**values)

    assert series_observation().series_kind is BenchmarkSeriesKind.PERIOD_RETURN
    with pytest.raises(BenchmarkResolutionError):
        series_observation(interval_start=None)
    with pytest.raises(BenchmarkResolutionError):
        series_observation(value=_numeric("-2", SourceNumericKind.RATE))
    with pytest.raises(BenchmarkResolutionError):
        series_observation(
            series_kind=BenchmarkSeriesKind.PRICE_INDEX,
            value=_numeric("0", SourceNumericKind.RATE),
            interval_start=None,
        )

    def constituent(**overrides: object) -> BenchmarkConstituent:
        values: dict[str, Any] = {
            "benchmark": resolved,
            "instrument_id": InstrumentId.new(),
            "membership_role": "member",
            "valid_from": _AT,
            "methodology_content_id": _CONTENT,
            "available_at": _AT,
        }
        values.update(overrides)
        return BenchmarkConstituent(**values)

    assert constituent().membership_role == "member"
    with pytest.raises(BenchmarkResolutionError):
        constituent(valid_to=_AT)
    with pytest.raises(BenchmarkResolutionError):
        constituent(weight=_numeric("1.5", SourceNumericKind.RATE))


def test_rate_curve_and_query_bounds_validation() -> None:
    calendar = CalendarRef(QualifiedName("persistra.calendar.xnys"), 1)

    def curve(**overrides: object) -> RiskFreeCurveDefinition:
        values: dict[str, Any] = {
            "name": QualifiedName("persistra.curve.ust"),
            "version": 1,
            "currency": cast("Any", None),
            "quote_kind": RateQuoteKind.PERIODIC_ZERO,
            "compounding": CompoundingKind.PERIODIC,
            "compounding_periods_per_year": 2,
            "day_count": DayCountKind.ACT_365F,
            "calendar": calendar,
            "business_day_policy_content_id": _CONTENT,
        }
        values.update(overrides)
        return RiskFreeCurveDefinition(**values)

    assert curve().compounding is CompoundingKind.PERIODIC
    with pytest.raises(RateConventionError):
        curve(compounding_periods_per_year=None)
    with pytest.raises(RateConventionError):
        curve(compounding_periods_per_year=0)
    with pytest.raises(RateConventionError):
        curve(quote_kind=RateQuoteKind.DISCOUNT_FACTOR)

    point_curve = ResolvedRiskFreeCurveRef(RiskFreeCurveId.new(), 1, _CONTENT)

    def point(**overrides: object) -> RiskFreePoint:
        values: dict[str, Any] = {
            "curve": point_curve,
            "source_release_key": "release-1",
            "effective_date": date(2025, 1, 6),
            "release_at": _AT,
            "available_at": _AT,
            "tenor": Tenor.months(3),
            "value": SourceNumeric(
                Decimal("0.05"), SourceNumericKind.RATE, _RATE_UNIT
            ),
            "quote_kind": RateQuoteKind.PERIODIC_ZERO,
            "compounding": CompoundingKind.PERIODIC,
            "compounding_periods_per_year": 2,
            "day_count": DayCountKind.ACT_365F,
            "source_curve_manifest_content_id": _CONTENT,
        }
        values.update(overrides)
        return RiskFreePoint(**values)

    assert point().tenor == Tenor.months(3)
    with pytest.raises(RateConventionError):
        point(available_at=_AT - timedelta(seconds=1))
    with pytest.raises(RateConventionError):
        point(
            quote_kind=RateQuoteKind.DISCOUNT_FACTOR,
            value=SourceNumeric(Decimal("0"), SourceNumericKind.RATE, _RATE_UNIT),
        )

    with pytest.raises(FundamentalQueryError):
        FundamentalQuery(
            (),
            (QualifiedName("persistra.concept.revenue"),),
            FilingMode.AS_REPORTED,
            date(2024, 1, 1),
            date(2024, 12, 31),
            _CONTEXT,
        )
    with pytest.raises(EstimateQueryError):
        EstimateQuery(
            (IssuerId.new(),),
            (QualifiedName("persistra.measure.eps"),),
            EstimateTargetKind.FISCAL_PERIOD,
            _AT,
            _AT,
            _CONTEXT,
        )
    with pytest.raises(MacroQueryError):
        MacroQuery(
            MacroSeriesRef(QualifiedName("persistra.macro.cpi"), 1),
            date(2024, 1, 1),
            date(2024, 12, 31),
            MacroVintageMode.EXACT_RELEASE,
            _CONTEXT,
        )
    with pytest.raises(BenchmarkResolutionError):
        BenchmarkQuery(
            BenchmarkVersionRef(QualifiedName("persistra.benchmark.total_market"), 1),
            _AT,
            _AT,
            _CONTEXT,
        )
    with pytest.raises(RateConventionError):
        RiskFreeQuery(
            RiskFreeCurveRef(QualifiedName("persistra.curve.ust"), 1),
            date(2024, 1, 1),
            date(2024, 12, 31),
            (Tenor.months(3), Tenor.months(3)),
            _CONTEXT,
        )
