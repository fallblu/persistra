from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]
import pandas as pd

from persistra import Project, ProjectMode
from persistra.accounting import AccountingOpening, DividendFacts, FillFacts, SplitFacts
from persistra.catalog import CompositeSnapshotRef, SnapshotRef
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import ContentId, Duration, FixedClock, QualifiedName
from persistra.flagship import FLAGSHIP_MOMENTUM_V1
from persistra.market import (
    AdjustmentPriceMode,
    BarSpecDefinition,
    BarSpecRef,
    BarState,
    CorporateActionId,
    CorporateActionKind,
    CorporateActionObservation,
    CorporateActionStatus,
    DailyBar,
)
from persistra.portfolio import ConstructionRequest, ConstructorRef, SignalRef
from persistra.reference import (
    ActiveListings,
    AsOfContext,
    CalendarDefinition,
    CalendarRef,
    CutoffMode,
    InstrumentDefinition,
    InstrumentId,
    IssuerId,
    ListingId,
    ListingStatus,
    PublicCutoffPolicy,
    SecurityId,
    SecurityKind,
    SecurityStatus,
    SessionDecisionAnchor,
    SessionDecisionSchedule,
    SessionSelection,
    UniverseDefinition,
    UniverseRef,
    VenueId,
)
from persistra.reports import ReportRequest
from persistra.research import (
    DailyBarInput,
    FeatureRef,
    MissingInputAction,
    ResearchCutoffSpec,
    ResearchDatasetDefinition,
    ResearchDatasetRef,
)
from persistra.simulation import (
    EventExecutionPolicy,
    EventSimulationRequest,
    OrderSide,
    OrderSpec,
    OrderType,
    TimeInForce,
    VectorizedSimulationRequest,
)
from persistra.viz import performance

if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2025, 5, 1, 12, tzinfo=UTC)
AVAILABLE = datetime(2023, 12, 1, tzinfo=UTC)


def _project(tmp_path: Path, *, market: bool = False) -> Path:
    layout = Project.init(tmp_path / "project")
    if market:
        market_path = layout.state_path / "market.duckdb"
        create_database_file(
            market_path,
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


def test_foundational_journal_fifo_split_dividend_and_reconciliation(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    instrument = InstrumentId.new()
    with Project.open(root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)) as project:
        opening = AccountingOpening(
            datetime(2025, 1, 2, 14, 30, tzinfo=UTC),
            Decimal("10000"),
            ContentId.from_bytes(b"opening"),
        )
        book = project.services.accounting.create_book(opening)
        buy = FillFacts(
            ContentId.from_bytes(b"buy"),
            instrument,
            datetime(2025, 1, 2, 14, 31, tzinfo=UTC),
            "buy",
            Decimal("10"),
            Decimal("100"),
            Decimal("1"),
            Decimal("2"),
        )
        first_id = project.services.accounting.apply_fill(
            book.reference.accounting_book_id, buy
        )
        assert project.services.accounting.apply_fill(
            book.reference.accounting_book_id, buy
        ) == first_id
        project.services.accounting.apply_split(
            book.reference.accounting_book_id,
            SplitFacts(
                ContentId.from_bytes(b"split"),
                instrument,
                datetime(2025, 1, 3, 14, 30, tzinfo=UTC),
                Decimal("2"),
            ),
        )
        project.services.accounting.apply_dividend(
            book.reference.accounting_book_id,
            DividendFacts(
                ContentId.from_bytes(b"dividend"),
                instrument,
                datetime(2025, 1, 4, 14, 30, tzinfo=UTC),
                Decimal("0.50"),
            ),
        )
        project.services.accounting.apply_fill(
            book.reference.accounting_book_id,
            FillFacts(
                ContentId.from_bytes(b"sell"),
                instrument,
                datetime(2025, 1, 5, 14, 30, tzinfo=UTC),
                "sell",
                Decimal("5"),
                Decimal("60"),
                Decimal("1"),
                Decimal("1"),
            ),
        )
        assert book.positions()["quantity"].tolist() == [Decimal("15")]
        lot = book.lots().iloc[0]
        assert lot["open_quantity"] == Decimal("15")
        assert lot["remaining_basis_usd"] == Decimal("750")
        assert book.cash() == Decimal("9308")
        reconciliation = book.reconcile()
        assert reconciliation.balanced
        assert reconciliation.position_count == 1
        journal = book.journal()
        balances = journal.groupby(
            ["book_sequence", "posting_book", "commodity"], dropna=False
        )["amount"].sum()
        assert (balances == 0).all()


def _seed_market(
    root: Path,
) -> tuple[SnapshotRef, tuple[InstrumentId, ...], datetime, datetime]:
    exchange = xcals.get_calendar("XNYS", start="2024-01-02", end="2025-04-15")
    schedule = exchange.schedule
    first_session = schedule.index[0].date()
    last_session = schedule.index[-1].date()
    start_at = schedule.iloc[0]["open"].to_pydatetime()
    end_at = schedule.iloc[-1]["close"].to_pydatetime() + timedelta(microseconds=1)
    venue = VenueId.new()
    instruments = (InstrumentId.new(), InstrumentId.new())
    definitions = tuple(
        InstrumentDefinition(
            IssuerId.new(),
            SecurityId.new(),
            venue,
            ListingId.new(),
            instrument,
            "XNYS",
            "America/New_York",
            SecurityKind.COMMON_STOCK,
            SecurityStatus.ACTIVE,
            ListingStatus.ACTIVE,
            "USD",
            AVAILABLE,
            available_at=AVAILABLE,
        )
        for instrument in instruments
    )
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        for definition in definitions:
            project.services.reference.register_instrument(definition)
        calendar = project.services.reference.calendars.register(
            CalendarDefinition(
                QualifiedName("persistra.calendar.xnys"),
                1,
                venue,
                "XNYS",
                "America/New_York",
                first_session,
                last_session + timedelta(days=1),
                AVAILABLE,
            )
        )
        spec = project.services.market.bar_specs.register(
            BarSpecDefinition(QualifiedName("persistra.bar.session.regular"))
        )
        bars: list[DailyBar] = []
        split_date = date(2025, 2, 14)
        for ordinal, (session, row) in enumerate(schedule.iterrows()):
            session_date = cast("pd.Timestamp", session).date()
            for asset, instrument in enumerate(instruments):
                raw = Decimal("80") + Decimal(ordinal) * Decimal(
                    "0.08" if asset == 0 else "0.16"
                )
                if asset == 1 and session_date >= split_date:
                    raw /= Decimal("2")
                bars.append(
                    DailyBar(
                        instrument,
                        spec,
                        calendar,
                        row["open"].to_pydatetime(),
                        row["close"].to_pydatetime(),
                        session_date,
                        BarState.COMPLETE,
                        "USD",
                        raw,
                        raw + Decimal("1"),
                        raw - Decimal("1"),
                        raw + Decimal("0.25"),
                        Decimal("1000000"),
                        1000,
                        row["close"].to_pydatetime(),
                    )
                )
        project.services.market.bars.ingest(tuple(bars))
        held = definitions[1]
        project.services.market.actions.ingest(
            (
                CorporateActionObservation(
                    CorporateActionId.new(),
                    CorporateActionKind.SPLIT,
                    held.security_id,
                    held.instrument_id,
                    CorporateActionStatus.COMPLETED,
                    AVAILABLE,
                    effective_at=datetime(2025, 2, 14, 14, 30, tzinfo=UTC),
                    share_ratio=Decimal("2"),
                ),
                CorporateActionObservation(
                    CorporateActionId.new(),
                    CorporateActionKind.ORDINARY_CASH_DIVIDEND,
                    held.security_id,
                    held.instrument_id,
                    CorporateActionStatus.COMPLETED,
                    AVAILABLE,
                    ex_at=datetime(2025, 3, 3, 14, 30, tzinfo=UTC),
                    cash_per_subject_unit=Decimal("0.25"),
                    currency="USD",
                ),
            )
        )
        snapshot = project.services.snapshots.create()
    return snapshot, instruments, start_at, end_at


def test_flagship_public_workflow_to_semantically_pinned_report(tmp_path: Path) -> None:
    root = _project(tmp_path, market=True)
    snapshot, instruments, start_at, end_at = _seed_market(root)
    with Project.open(root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)) as project:
        composite = project.services.snapshots.create_composite(
            {DatabaseName("primary"): snapshot}
        )
        assert isinstance(composite, CompositeSnapshotRef)
        venue_id = project.services.reference.instruments(
            context=AsOfContext(
                composite,
                end_at,
                end_at,
                market_database="primary",
            ),
            instrument_ids=(instruments[0],),
        ).iloc[0]["venue_id"]
        project.services.universes.register(
            UniverseDefinition(
                QualifiedName("project.universe.flagship"),
                1,
                ActiveListings(
                    (VenueId.parse(venue_id),),
                    (SecurityKind.COMMON_STOCK,),
                ),
            )
        )
        decision_schedule = SessionDecisionSchedule(
            CalendarRef(QualifiedName("persistra.calendar.xnys"), 1),
            SessionDecisionAnchor.CLOSE,
            SessionSelection.EVERY_SESSION,
        )
        project.services.research.datasets.register(
            ResearchDatasetDefinition(
                QualifiedName("project.dataset.flagship"),
                1,
                UniverseRef(QualifiedName("project.universe.flagship"), 1),
                decision_schedule,
                ResearchCutoffSpec.public(PublicCutoffPolicy.at_decision()),
                (
                    DailyBarInput(
                        "daily",
                        BarSpecRef(
                            QualifiedName("persistra.bar.session.regular"),
                            1,
                        ),
                        adjustment_mode=AdjustmentPriceMode.SPLIT,
                        max_age=Duration(604_800_000_000),
                        missing_action=MissingInputAction.MARK_UNUSABLE,
                    ),
                ),
            )
        )
        dataset = project.services.research.datasets.build(
            definition=ResearchDatasetRef(
                QualifiedName("project.dataset.flagship"), 1
            ),
            composite_snapshot=composite,
            start_at=start_at,
            end_at=end_at,
            market_database="primary",
        )
        project.services.research.features.register(FLAGSHIP_MOMENTUM_V1.momentum)
        feature = project.services.research.features.materialize(
            definition=FeatureRef(FLAGSHIP_MOMENTUM_V1.momentum.name, 1),
            primary_dataset=dataset.reference.research_dataset_build_id,
        )
        project.services.portfolio.signals.register(FLAGSHIP_MOMENTUM_V1.signal)
        signal = project.services.portfolio.signals.materialize(
            definition=SignalRef(FLAGSHIP_MOMENTUM_V1.signal.name, 1),
            feature=feature.reference.feature_materialization_id,
        )
        assert feature.reference.computed_count > 0
        assert signal.reference.computed_count > 0
        project.services.portfolio.constructors.register(
            FLAGSHIP_MOMENTUM_V1.constructor
        )
        target_start = pd.Timestamp(
            signal.rows().query("state == 'computed'")["decision_at"].min()
        ).to_pydatetime()
        assert (signal.rows()["decision_at"] >= target_start).any()
        construction = project.services.portfolio.construct(
            ConstructionRequest(
                ConstructorRef(FLAGSHIP_MOMENTUM_V1.constructor.name, 1),
                signal.reference.signal_materialization_id,
                start_at=target_start,
                end_at=datetime(2025, 4, 1, tzinfo=UTC),
            )
        )
        selected = construction.weights().query("selected")
        assert selected.groupby("decision_at").size().eq(1).all()
        market_context = AsOfContext(
            composite,
            end_at,
            end_at,
            cutoff_mode=CutoffMode.PUBLIC,
            market_database="primary",
        )
        opening = AccountingOpening(
            start_at,
            FLAGSHIP_MOMENTUM_V1.opening_cash_usd,
            ContentId.from_bytes(b"flagship-opening"),
        )
        run = project.services.simulation.vectorized.run(
            project.services.simulation.vectorized.plan(
                VectorizedSimulationRequest(
                    market_context,
                    "primary",
                    BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
                    construction.reference.portfolio_construction_result_id,
                    opening,
                    FLAGSHIP_MOMENTUM_V1.execution,
                )
            )
        )
        result = run.result()
        hardening = project._primary_connection().execute(  # pyright: ignore[reportPrivateUsage]
            "SELECT h.replay_status, count(c.checkpoint_sequence) FROM "
            "simulation.vectorized_run_hardening h JOIN "
            "simulation.simulation_checkpoints c USING (vectorized_simulation_id) "
            "WHERE h.vectorized_simulation_id = ? GROUP BY h.replay_status",
            [run.reference.vectorized_simulation_id.value],
        ).fetchone()
        assert hardening is not None
        assert hardening[1] >= 1
        event_opening = AccountingOpening(
            start_at,
            FLAGSHIP_MOMENTUM_V1.opening_cash_usd,
            ContentId.from_bytes(b"event-opening"),
        )
        event_run = project.services.simulation.event.run(
            project.services.simulation.event.plan(
                EventSimulationRequest(
                    market_context,
                    "primary",
                    BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
                    event_opening,
                    (
                        OrderSpec(
                            "partial-day",
                            instruments[0],
                            OrderSide.BUY,
                            Decimal("1500"),
                            OrderType.MARKET,
                            TimeInForce.DAY,
                            start_at,
                            start_at,
                        ),
                        OrderSpec(
                            "parent",
                            instruments[1],
                            OrderSide.BUY,
                            Decimal("10"),
                            OrderType.LIMIT,
                            TimeInForce.GTC,
                            start_at,
                            start_at,
                            limit_price=Decimal("1"),
                        ),
                        OrderSpec(
                            "replacement",
                            instruments[1],
                            OrderSide.BUY,
                            Decimal("10"),
                            OrderType.MARKET,
                            TimeInForce.GTC,
                            start_at + timedelta(days=1),
                            start_at + timedelta(days=1),
                            replaces_client_key="parent",
                        ),
                        OrderSpec(
                            "cancelled",
                            instruments[0],
                            OrderSide.BUY,
                            Decimal("5"),
                            OrderType.LIMIT,
                            TimeInForce.GTC,
                            start_at,
                            start_at,
                            limit_price=Decimal("1"),
                            cancel_at=start_at + timedelta(days=2),
                        ),
                    ),
                    start_at + timedelta(days=10),
                    EventExecutionPolicy(participation_limit=Decimal("0.001")),
                )
            )
        )
        assert event_run.reference.fill_count == 2
        assert event_run.fills()["quantity"].tolist() == [
            Decimal("1000"),
            Decimal("10"),
        ]
        assert {"filled", "expired", "replaced", "cancelled"} <= set(
            event_run.transitions()["status"]
        )
        event_balances = event_run.journal().groupby(
            ["book_sequence", "posting_book", "commodity"], dropna=False
        )["amount"].sum()
        assert (event_balances == 0).all()
        assert result.summary().decision_count >= 2
        assert result.summary().fill_count >= 1
        assert len(result.equity()) == result.summary().decision_count + 1
        displayed_balances = result.journal().groupby(
            ["book_sequence", "posting_book", "commodity"], dropna=False
        )["amount"].sum()
        assert displayed_balances.abs().lt(1e-8).all()
        metrics = project.services.analysis.metrics.compute(result)
        assert metrics.scalar("persistra.metric.total_return").estimate is not None
        figure = performance.equity(result)
        assert figure.layout.meta["result_manifest_content_id"] == str(
            result.summary().result_manifest_content_id
        )
        report = project.services.reports.render(
            project.services.reports.plan(ReportRequest(result.id, metrics.id))
        )
        rendered = report.open_bytes()
        assert b"persistra-report-manifest" in rendered
        assert b"simulation.vectorized.no_orders" in rendered
        assert b'<script src="http' not in rendered
        assert report.reference.output_content_id == ContentId.from_bytes(rendered)
