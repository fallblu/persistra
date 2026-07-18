from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from persistra import Project, ProjectMode
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import (
    ContentId,
    Currency,
    FixedClock,
    NumericKind,
    QualifiedName,
    SourceNumeric,
    SourceNumericKind,
    Unit,
    UnitSpec,
)
from persistra.market import (
    ActualObservation,
    BenchmarkConstituent,
    BenchmarkDefinition,
    BenchmarkKind,
    BenchmarkQuery,
    BenchmarkSeriesKind,
    BenchmarkSeriesObservation,
    BenchmarkVersionRef,
    CompoundingKind,
    ConsensusEstimate,
    DayCountKind,
    EstimateMeasureDefinition,
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
    MacroSeriesRef,
    MacroVintageMode,
    MacroVintageStatus,
    NormalizedConceptDefinition,
    RateQuoteKind,
    RawFundamentalFact,
    ReportId,
    RiskFreeCurveDefinition,
    RiskFreeCurveRef,
    RiskFreePoint,
    RiskFreeQuery,
    Tenor,
    VintageCompleteness,
)
from persistra.reference import (
    AsOfContext,
    CalendarDefinition,
    CalendarRef,
    InstrumentDefinition,
    InstrumentId,
    IssuerId,
    ListingId,
    ListingStatus,
    SecurityId,
    SecurityKind,
    SecurityStatus,
    VenueId,
)

if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
EVENT = datetime(2026, 1, 9, 12, tzinfo=UTC)
AVAILABLE = datetime(2026, 1, 10, 12, tzinfo=UTC)
AMOUNT_UNIT = UnitSpec(Unit("usd"), NumericKind.DECIMAL)
RATE_UNIT = UnitSpec(Unit("ratio"), NumericKind.DECIMAL)
AMOUNT = SourceNumeric("125", SourceNumericKind.AMOUNT, AMOUNT_UNIT)
RATE = SourceNumeric("0.04", SourceNumericKind.RATE, RATE_UNIT)
ONE = SourceNumeric("1", SourceNumericKind.PURE, RATE_UNIT)


def _project(tmp_path: Path) -> Path:
    layout = Project.init(tmp_path / "project")
    market = layout.state_path / "market.duckdb"
    create_database_file(
        market,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=FixedClock(NOW),
    )
    with layout.config_path.open("a", encoding="utf-8") as config:
        config.write(
            '\n[databases.markets.primary]\npath = ".persistra/market.duckdb"\n'
            "verify_copy_on_open = false\n"
        )
    return layout.root


def test_economic_families_round_trip_through_snapshot_queries(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    issuer_id = IssuerId.new()
    instrument_id = InstrumentId.new()
    calendar_name = QualifiedName("persistra.calendar.xnys")
    filing_id = FilingId.new()
    report_id = ReportId.new()

    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        instrument = InstrumentDefinition(
            issuer_id,
            SecurityId.new(),
            VenueId.new(),
            ListingId.new(),
            instrument_id,
            "XNYS",
            "America/New_York",
            SecurityKind.COMMON_STOCK,
            SecurityStatus.ACTIVE,
            ListingStatus.ACTIVE,
            "USD",
            EVENT,
            available_at=AVAILABLE,
        )
        project.services.reference.register_instrument(instrument)
        project.services.reference.calendars.register(
            CalendarDefinition(
                calendar_name,
                1,
                instrument.venue_id,
                "XNYS",
                "America/New_York",
                date(2025, 1, 1),
                date(2027, 1, 1),
                AVAILABLE,
            )
        )
        filing = FilingObservation(
            filing_id,
            report_id,
            issuer_id,
            "sec",
            "0001",
            "sec-0001",
            "10-k",
            FilingStatus.ACCEPTED,
            date(2026, 1, 9),
            date(2025, 12, 31),
            AVAILABLE,
            accepted_at=EVENT,
            report_period_start=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period_kind=FiscalPeriodKind.FY,
        )
        assert project.services.market.fundamentals.ingest_filing(filing) == filing_id
        fact = RawFundamentalFact(
            filing_id,
            report_id,
            issuer_id,
            "us-gaap",
            "2025",
            "persistra.revenue",
            FactPeriodKind.DURATION,
            date(2025, 12, 31),
            ContentId.from_bytes(b"annual-period"),
            FactNumericKind.AMOUNT,
            AMOUNT_UNIT,
            AVAILABLE,
            value=AMOUNT,
            period_start=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period_kind=FiscalPeriodKind.FY,
            currency=Currency("USD"),
        )
        fact_ids = project.services.market.fundamentals.ingest_facts((fact,))
        assert project.services.market.fundamentals.ingest_facts((fact,)) == fact_ids
        concept_id = project.services.market.fundamentals.register_concept(
            NormalizedConceptDefinition(
                QualifiedName("persistra.fundamental.revenue"),
                1,
                FactPeriodKind.DURATION,
                FactNumericKind.AMOUNT,
                AMOUNT_UNIT,
            )
        )
        project.services.market.fundamentals.register_mapping(
            FundamentalMappingDefinition(
                QualifiedName("persistra.mapping.us_gaap"),
                1,
                "us-gaap",
                "%",
                "persistra.revenue",
                concept_id,
                1,
                ONE,
                ONE,
                ContentId.from_bytes(b"dimensions"),
            )
        )
        project.services.market.fundamentals.normalize(
            mapping_policy=QualifiedName("persistra.mapping.us_gaap")
        )

        measure_name = QualifiedName("persistra.estimate.revenue")
        measure_id = project.services.market.estimates.register_measure(
            EstimateMeasureDefinition(
                measure_name,
                1,
                "issuer",
                FactNumericKind.AMOUNT,
                AMOUNT_UNIT,
            )
        )
        target = EstimateTarget(
            EstimateTargetKind.FISCAL_PERIOD,
            ContentId.from_bytes(b"estimate-target"),
            fiscal_year=2025,
            fiscal_period_kind=FiscalPeriodKind.FY,
            period_end=date(2025, 12, 31),
            report_id=report_id,
        )
        individual = IndividualEstimate(
            "estimate-1",
            measure_id,
            1,
            "issuer",
            issuer_id,
            target,
            AMOUNT,
            AVAILABLE,
            EVENT,
            currency=Currency("USD"),
        )
        consensus = ConsensusEstimate(
            "consensus-1",
            measure_id,
            1,
            "issuer",
            issuer_id,
            target,
            2,
            AMOUNT_UNIT,
            ContentId.from_bytes(b"consensus-method"),
            AVAILABLE,
            EVENT,
            mean=AMOUNT,
            median=AMOUNT,
            high=SourceNumeric("130", SourceNumericKind.AMOUNT, AMOUNT_UNIT),
            low=SourceNumeric("120", SourceNumericKind.AMOUNT, AMOUNT_UNIT),
            currency=Currency("USD"),
        )
        actual = ActualObservation(
            "actual-1",
            measure_id,
            1,
            "issuer",
            issuer_id,
            date(2025, 12, 31),
            AMOUNT,
            ContentId.from_bytes(b"actual-policy"),
            AVAILABLE,
            EVENT,
            fiscal_year=2025,
            fiscal_period_kind=FiscalPeriodKind.FY,
            currency=Currency("USD"),
            filing_id=filing_id,
        )
        project.services.market.estimates.ingest_individual((individual,))
        project.services.market.estimates.ingest_consensus((consensus,))
        project.services.market.estimates.ingest_actuals((actual,))

        macro_name = QualifiedName("persistra.macro.gdp")
        macro = project.services.market.macro.register(
            MacroSeriesDefinition(
                macro_name,
                1,
                QualifiedName("persistra.frequency.quarterly"),
                QualifiedName("persistra.seasonal.adjusted"),
                QualifiedName("persistra.geography.us"),
                AMOUNT_UNIT,
                FactNumericKind.AMOUNT,
                VintageCompleteness.COMPLETE,
                ContentId.from_bytes(b"macro-period"),
            )
        )
        release = MacroRelease(
            MacroReleaseId.new(),
            macro,
            "gdp-2025q4",
            EVENT,
            AVAILABLE,
            ContentId.from_bytes(b"macro-release"),
            (
                MacroObservation(
                    "gdp-2025q4-first",
                    date(2025, 10, 1),
                    date(2025, 12, 31),
                    MacroVintageStatus.ADVANCE,
                    AMOUNT_UNIT,
                    value=AMOUNT,
                ),
            ),
        )
        assert project.services.market.macro.ingest(release) == (
            project.services.market.macro.ingest(release)
        )

        calendar = CalendarRef(calendar_name, 1)
        benchmark_name = QualifiedName("persistra.benchmark.synthetic")
        benchmark = project.services.market.benchmarks.register(
            BenchmarkDefinition(
                benchmark_name,
                1,
                BenchmarkKind.SOURCE_SERIES,
                None,
                Currency("USD"),
                calendar,
                ContentId.from_bytes(b"benchmark-method"),
                "redistributable",
            )
        )
        project.services.market.benchmarks.ingest_series(
            (
                BenchmarkSeriesObservation(
                    benchmark,
                    BenchmarkSeriesKind.PRICE_INDEX,
                    EVENT,
                    ONE,
                    Currency("USD"),
                    ContentId.from_bytes(b"calendar-schedule"),
                    ContentId.from_bytes(b"benchmark-source-method"),
                    AVAILABLE,
                ),
            )
        )
        project.services.market.benchmarks.ingest_constituents(
            (
                BenchmarkConstituent(
                    benchmark,
                    instrument_id,
                    "constituent",
                    EVENT,
                    ContentId.from_bytes(b"benchmark-method"),
                    AVAILABLE,
                    weight=ONE,
                ),
            )
        )

        curve_name = QualifiedName("persistra.rate.usd")
        curve = project.services.market.risk_free_curves.register(
            RiskFreeCurveDefinition(
                curve_name,
                1,
                Currency("USD"),
                RateQuoteKind.SIMPLE_YIELD,
                CompoundingKind.SIMPLE,
                None,
                DayCountKind.ACT_360,
                calendar,
                ContentId.from_bytes(b"business-day-policy"),
            )
        )
        point = RiskFreePoint(
            curve,
            "usd-2026-01-09",
            date(2026, 1, 9),
            EVENT,
            AVAILABLE,
            Tenor.days(1),
            RATE,
            RateQuoteKind.SIMPLE_YIELD,
            CompoundingKind.SIMPLE,
            None,
            DayCountKind.ACT_360,
            ContentId.from_bytes(b"curve-manifest"),
        )
        point_ids = project.services.market.rates.ingest((point,))
        assert project.services.market.rates.ingest((point,)) == point_ids
        snapshot = project.services.snapshots.create()

    context = AsOfContext(snapshot, NOW, NOW)
    with Project.open(root, mode=ProjectMode.READ_ONLY, clock=FixedClock(NOW)) as project:
        filings = project.services.market.fundamentals.filings(
            (issuer_id,), date(2025, 1, 1), date(2026, 1, 1), context=context
        )
        facts = project.services.market.fundamentals.raw_facts(
            FundamentalQuery(
                (issuer_id,),
                (QualifiedName("persistra.revenue"),),
                FilingMode.LATEST_KNOWN_FACT,
                date(2025, 1, 1),
                date(2026, 1, 1),
                context,
            )
        )
        estimate_query = EstimateQuery(
            (issuer_id,),
            (measure_name,),
            EstimateTargetKind.FISCAL_PERIOD,
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 2, 1, tzinfo=UTC),
            context,
        )
        macro_rows = project.services.market.macro.query(
            MacroQuery(
                MacroSeriesRef(macro_name, 1),
                date(2025, 1, 1),
                date(2026, 1, 1),
                MacroVintageMode.LATEST_KNOWN,
                context,
            )
        )
        benchmark_query = BenchmarkQuery(
            BenchmarkVersionRef(benchmark_name, 1),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 2, 1, tzinfo=UTC),
            context,
        )
        rate_query = RiskFreeQuery(
            RiskFreeCurveRef(curve_name, 1),
            date(2026, 1, 9),
            date(2026, 1, 9),
            (Tenor.days(1),),
            context,
        )

        assert len(filings) == len(facts) == 1
        assert len(project.services.market.estimates.individual(estimate_query)) == 1
        assert len(project.services.market.estimates.consensus(estimate_query)) == 1
        assert len(project.services.market.estimates.actuals(estimate_query)) == 1
        assert len(macro_rows) == 1
        assert len(project.services.market.benchmarks.series(benchmark_query)) == 1
        assert (
            len(project.services.market.benchmarks.constituents(benchmark_query)) == 1
        )
        assert len(project.services.market.rates.points(rate_query)) == 1
        assert project.services.market.rates.require(
            curve=RiskFreeCurveRef(curve_name, 1),
            effective_date=date(2026, 1, 9),
            tenor=Tenor.days(1),
            context=context,
        ) == 0.04
