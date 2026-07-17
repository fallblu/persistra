from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]

from persistra import Project, ProjectMode
from persistra.catalog import CompositeSnapshotRef, SnapshotRef
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock, QualifiedName
from persistra.market import (
    AdjustmentPriceMode,
    AdjustmentViewRequest,
    BarQuery,
    BarSpecDefinition,
    BarSpecRef,
    BarState,
    CorporateActionId,
    CorporateActionKind,
    CorporateActionObservation,
    CorporateActionStatus,
    DailyBar,
    TradingStatus,
    TradingStatusObservation,
)
from persistra.reference import (
    ActiveListings,
    AsOfContext,
    CalendarDefinition,
    CalendarRef,
    ClassificationAssignment,
    ClassificationAssignmentId,
    ClassificationNode,
    ClassificationNodeId,
    ClassificationSchemeDefinition,
    CutoffMode,
    EntityKind,
    ExplicitMembership,
    IdentifierAssignment,
    IdentifierKind,
    IdentifierNamespaceDefinition,
    InstrumentDefinition,
    InstrumentId,
    IssuerId,
    ListingId,
    ListingStatus,
    MembershipRole,
    NonSession,
    PublicCutoffPolicy,
    ResolvedIdentifierNamespace,
    SecurityId,
    SecurityKind,
    SecurityStatus,
    SessionDecisionAnchor,
    SessionDecisionSchedule,
    SessionSelection,
    UniverseDefinition,
    UniverseMembership,
    UniverseRef,
    VenueId,
)
from persistra.research import (
    DailyBarInput,
    MissingInputAction,
    ResearchCutoffSpec,
    ResearchDatasetDefinition,
    ResearchDatasetRef,
)

if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
AVAILABLE = datetime(2025, 12, 1, tzinfo=UTC)


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


def _seed(
    root: Path,
) -> tuple[SnapshotRef, InstrumentDefinition, ResolvedIdentifierNamespace]:
    instrument = InstrumentDefinition(
        IssuerId.new(),
        SecurityId.new(),
        VenueId.new(),
        ListingId.new(),
        InstrumentId.new(),
        "XNYS",
        "America/New_York",
        SecurityKind.COMMON_STOCK,
        SecurityStatus.ACTIVE,
        ListingStatus.ACTIVE,
        "USD",
        AVAILABLE,
        available_at=AVAILABLE,
    )
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        assert (
            project.services.reference.register_instrument(instrument)
            == instrument.instrument_id
        )
        namespace = project.services.reference.identifiers.register(
            IdentifierNamespaceDefinition(
                QualifiedName("persistra.identifier.ticker"),
                1,
                IdentifierKind.TICKER,
                EntityKind.INSTRUMENT,
            )
        )
        assignment_id = project.services.reference.identifiers.assign(
            IdentifierAssignment(
                namespace,
                "abc",
                EntityKind.INSTRUMENT,
                instrument.instrument_id,
                AVAILABLE,
                is_primary=True,
                available_at=AVAILABLE,
            )
        )
        assert project.services.reference.identifiers.assign(
            IdentifierAssignment(
                namespace,
                "abc",
                EntityKind.INSTRUMENT,
                instrument.instrument_id,
                AVAILABLE,
                is_primary=True,
                available_at=AVAILABLE,
            )
        ) == assignment_id
        scheme = project.services.reference.classifications.register(
            ClassificationSchemeDefinition(
                QualifiedName("project.classification.sector"), 1
            )
        )
        node = ClassificationNode(
            ClassificationNodeId.new(),
            scheme,
            "TECH",
            "Technology",
            AVAILABLE,
            available_at=AVAILABLE,
        )
        project.services.reference.classifications.add_node(node)
        project.services.reference.classifications.assign(
            ClassificationAssignment(
                ClassificationAssignmentId.new(),
                scheme,
                EntityKind.INSTRUMENT,
                instrument.instrument_id,
                node.classification_node_id,
                AVAILABLE,
                available_at=AVAILABLE,
            )
        )
        project.services.reference.memberships.ingest(
            (
                UniverseMembership(
                    "synthetic.large_cap",
                    instrument.instrument_id,
                    MembershipRole.CONSTITUENT,
                    AVAILABLE,
                    weight="1",
                    available_at=AVAILABLE,
                ),
            )
        )
        calendar = project.services.reference.calendars.register(
            CalendarDefinition(
                QualifiedName("persistra.calendar.xnys"),
                1,
                instrument.venue_id,
                "XNYS",
                "America/New_York",
                date(2025, 12, 20),
                date(2026, 2, 1),
                AVAILABLE,
            )
        )
        assert project.services.reference.calendars.register(
            CalendarDefinition(
                QualifiedName("persistra.calendar.xnys"),
                1,
                instrument.venue_id,
                "XNYS",
                "America/New_York",
                date(2025, 12, 20),
                date(2026, 2, 1),
                AVAILABLE,
            )
        ) == calendar
        spec = project.services.market.bar_specs.register(
            BarSpecDefinition(QualifiedName("persistra.bar.session.regular"))
        )
        exchange = xcals.get_calendar("XNYS", start="2026-01-01", end="2026-01-12")
        closes = {
            date(2026, 1, 2): Decimal("100"),
            date(2026, 1, 5): Decimal("102"),
            date(2026, 1, 6): Decimal("52"),
            date(2026, 1, 7): Decimal("53"),
            date(2026, 1, 8): Decimal("52.5"),
            date(2026, 1, 9): Decimal("54"),
        }
        bars: list[DailyBar] = []
        for session_date, close in closes.items():
            row = exchange.schedule.loc[str(session_date)]
            open_at = row["open"].to_pydatetime()
            close_at = row["close"].to_pydatetime()
            bars.append(
                DailyBar(
                    instrument.instrument_id,
                    spec,
                    calendar,
                    open_at,
                    close_at,
                    session_date,
                    BarState.COMPLETE,
                    "USD",
                    close - Decimal("1"),
                    close + Decimal("1"),
                    close - Decimal("2"),
                    close,
                    Decimal("1000"),
                    100,
                    close_at,
                )
            )
        bar_ids = project.services.market.bars.ingest(tuple(bars))
        assert project.services.market.bars.ingest(tuple(bars)) == bar_ids
        project.services.market.status.ingest(
            (
                TradingStatusObservation(
                    instrument.instrument_id,
                    TradingStatus.TRADING,
                    bars[0].interval_start,
                    AVAILABLE,
                ),
            )
        )
        project.services.market.actions.ingest(
            (
                CorporateActionObservation(
                    CorporateActionId.new(),
                    CorporateActionKind.SPLIT,
                    instrument.security_id,
                    instrument.instrument_id,
                    CorporateActionStatus.COMPLETED,
                    datetime(2026, 1, 3, tzinfo=UTC),
                    effective_at=bars[2].interval_start,
                    share_ratio=Decimal("2"),
                ),
                CorporateActionObservation(
                    CorporateActionId.new(),
                    CorporateActionKind.ORDINARY_CASH_DIVIDEND,
                    instrument.security_id,
                    instrument.instrument_id,
                    CorporateActionStatus.COMPLETED,
                    datetime(2026, 1, 7, 12, tzinfo=UTC),
                    ex_at=bars[4].interval_start,
                    cash_per_subject_unit=Decimal("1"),
                    currency="USD",
                ),
            )
        )
        snapshot = project.services.snapshots.create()
    return snapshot, instrument, namespace


def test_daily_reference_market_universe_and_dataset_scenario(tmp_path: Path) -> None:
    root = _project(tmp_path)
    snapshot, instrument, namespace = _seed(root)
    assert hasattr(snapshot, "snapshot_id")
    direct_context = AsOfContext(
        snapshot,
        datetime(2026, 1, 9, 21, tzinfo=UTC),
        datetime(2026, 1, 9, 21, tzinfo=UTC),
    )
    with Project.open(
        root,
        mode=ProjectMode.READ_ONLY,
        clock=FixedClock(NOW),
    ) as project:
        instruments = project.services.reference.instruments(
            context=direct_context,
            instrument_ids=(instrument.instrument_id,),
        )
        assert instruments["mic"].tolist() == ["XNYS"]
        resolution = project.services.reference.identifiers.resolve(
            namespace,
            "ABC",
            entity_kind=EntityKind.INSTRUMENT,
            context=direct_context,
        )
        assert resolution.entity_id == instrument.instrument_id
        classifications = project.services.reference.classifications.query(
            context=direct_context, entity_id=instrument.instrument_id
        )
        assert classifications["code"].tolist() == ["TECH"]
        calendar = project.services.reference.calendars.get(
            CalendarRef(QualifiedName("persistra.calendar.xnys"), 1),
            context=direct_context,
        )
        saturday = calendar.session(date(2026, 1, 3))
        assert isinstance(saturday, NonSession)
        assert saturday.closure_reason == "weekend"
        assert calendar.next_session(date(2026, 1, 2)).calendar_date == date(2026, 1, 5)
        assert calendar.previous_session(date(2026, 1, 5)).calendar_date == date(
            2026, 1, 2
        )
        query = BarQuery(
            (instrument.instrument_id,),
            BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 10, tzinfo=UTC),
            direct_context,
        )
        raw = project.services.market.bars.query(query)
        assert len(raw) == 6
        adjusted = project.services.market.adjustments.view(
            AdjustmentViewRequest(
                query,
                AdjustmentPriceMode.TOTAL_RETURN,
                datetime(2026, 1, 9, 21, tzinfo=UTC),
            )
        )
        adjusted_rows = adjusted.bars()
        assert adjusted_rows.iloc[0]["adjusted_close"] < 50
        assert len(adjusted.factors()) == 2
        assert project.services.market.status.at(
            instrument.instrument_id,
            datetime(2026, 1, 6, tzinfo=UTC),
            context=direct_context,
        ) is TradingStatus.TRADING

    with Project.open(
        root,
        mode=ProjectMode.RESEARCH_WRITE,
        clock=FixedClock(NOW),
    ) as project:
        composite = project.services.snapshots.create_composite(
            {DatabaseName("primary"): snapshot}
        )
        assert isinstance(composite, CompositeSnapshotRef)
        universe = project.services.universes.register(
            UniverseDefinition(
                QualifiedName("project.universe.daily"),
                1,
                ActiveListings(
                    (instrument.venue_id,),
                    (SecurityKind.COMMON_STOCK,),
                ),
                required_identifier_namespace=QualifiedName(
                    "persistra.identifier.ticker"
                ),
            )
        )
        assert project.services.universes.register(
            UniverseDefinition(
                QualifiedName("project.universe.daily"),
                1,
                ActiveListings(
                    (instrument.venue_id,),
                    (SecurityKind.COMMON_STOCK,),
                ),
                required_identifier_namespace=QualifiedName(
                    "persistra.identifier.ticker"
                ),
            )
        ) == universe
        schedule = SessionDecisionSchedule(
            CalendarRef(QualifiedName("persistra.calendar.xnys"), 1),
            SessionDecisionAnchor.CLOSE,
            SessionSelection.EVERY_SESSION,
        )
        evaluation = project.services.universes.evaluate(
            definition=UniverseRef(QualifiedName("project.universe.daily"), 1),
            composite_snapshot=composite,
            decisions=schedule,
            start_at=datetime(2026, 1, 2, tzinfo=UTC),
            end_at=datetime(2026, 1, 10, tzinfo=UTC),
            cutoff_mode=CutoffMode.PUBLIC,
            public_cutoff_policy=PublicCutoffPolicy.at_decision(),
            market_database="primary",
        )
        eligibility = project.services.universes.eligibility(
            evaluation.universe_evaluation_id
        )
        assert eligibility["eligible"].all()
        membership_universe = project.services.universes.register(
            UniverseDefinition(
                QualifiedName("project.universe.membership"),
                1,
                ExplicitMembership("synthetic.large_cap"),
            )
        )
        membership_name = QualifiedName("project.universe.membership")
        membership_evaluation = project.services.universes.evaluate(
            definition=UniverseRef(membership_name, 1),
            composite_snapshot=composite,
            decisions=schedule,
            start_at=datetime(2026, 1, 2, tzinfo=UTC),
            end_at=datetime(2026, 1, 6, tzinfo=UTC),
            market_database="primary",
        )
        assert membership_universe.version == 1
        assert project.services.universes.eligibility(
            membership_evaluation.universe_evaluation_id
        )["eligible"].all()
        definition = ResearchDatasetDefinition(
            QualifiedName("project.dataset.daily"),
            1,
            UniverseRef(QualifiedName("project.universe.daily"), 1),
            schedule,
            ResearchCutoffSpec.public(),
            (
                DailyBarInput(
                    "raw_bar",
                    BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
                    missing_action=MissingInputAction.MARK_UNUSABLE,
                ),
                DailyBarInput(
                    "total_return_bar",
                    BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
                    adjustment_mode=AdjustmentPriceMode.TOTAL_RETURN,
                ),
            ),
        )
        project.services.research.datasets.register(definition)
        build = project.services.research.datasets.build(
            definition=ResearchDatasetRef(QualifiedName("project.dataset.daily"), 1),
            composite_snapshot=composite,
            start_at=datetime(2026, 1, 2, tzinfo=UTC),
            end_at=datetime(2026, 1, 10, tzinfo=UTC),
            market_database="primary",
            universe_evaluation=evaluation.universe_evaluation_id,
        )
        assert build.reference.row_count == 6
        assert len(build.decision_rows()) == 6
        assert len(build.eligibility_audit()) == 6
        assert len(build.input_outcomes()) == 12
        assert sum(len(chunk) for chunk in build.iter_rows(chunk_rows=2)) == 6
        retry = project.services.research.datasets.build(
            definition=ResearchDatasetRef(QualifiedName("project.dataset.daily"), 1),
            composite_snapshot=composite,
            start_at=datetime(2026, 1, 2, tzinfo=UTC),
            end_at=datetime(2026, 1, 10, tzinfo=UTC),
            market_database="primary",
            universe_evaluation=evaluation.universe_evaluation_id,
        )
        assert retry.reference == build.reference


def test_cutoffs_hide_later_market_observations(tmp_path: Path) -> None:
    root = _project(tmp_path)
    snapshot, instrument, _namespace = _seed(root)
    early = AsOfContext(
        snapshot,
        datetime(2026, 1, 5, 21, tzinfo=UTC),
        datetime(2026, 1, 2, 21, tzinfo=UTC),
    )
    with Project.open(root, mode=ProjectMode.READ_ONLY) as project:
        query = BarQuery(
            (instrument.instrument_id,),
            BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 6, tzinfo=UTC),
            early,
        )
        frame = project.services.market.bars.query(query)
        assert frame["session_date"].tolist() == [date(2026, 1, 2)]
        assert project.services.market.bars.classify_at(
            instrument.instrument_id,
            datetime(2026, 1, 2, 21, tzinfo=UTC) + timedelta(microseconds=1),
            spec=query.spec,
            context=early,
        )["state"] == "selected"
