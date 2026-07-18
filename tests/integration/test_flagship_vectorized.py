from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import duckdb
import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]
import pandas as pd
import pytest

from persistra import Project, ProjectMode
from persistra.accounting import AccountingOpening, DividendFacts, FillFacts, SplitFacts
from persistra.catalog import CompositeSnapshotRef, SnapshotRef
from persistra.dashboard import (
    BackupDashboardSource,
    DashboardLimits,
    PortableExportSource,
    ProjectDashboardSource,
)
from persistra.dashboard.data import DashboardData
from persistra.db import (
    DatabaseName,
    DatabaseRole,
    MaintenanceIntent,
    ResearchDatabase,
)
from persistra.db.connection import create_database_file
from persistra.domain import ContentId, Duration, FixedClock, QualifiedName
from persistra.errors import (
    DashboardSecurityError,
    DecisionInputSafetyError,
    EventSimulationRequestError,
    ExportSecurityError,
    ExportVerificationError,
)
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
from persistra.portfolio import (
    ConstructionRequest,
    ConstructorRef,
    ExternalDecisionInputDeclaration,
    SignalRef,
    UnsafeDecisionInputOverride,
)
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
from persistra.reports import ReportRequest, verify_bundle
from persistra.research import (
    DailyBarInput,
    FeatureRef,
    InformationClass,
    LineageCompleteness,
    MissingInputAction,
    ResearchCutoffSpec,
    ResearchDatasetDefinition,
    ResearchDatasetRef,
    SafetyStatus,
    TemporalContractKind,
)
from persistra.results import open_export
from persistra.simulation import (
    EventExecutionPolicy,
    EventSimulationRequest,
    OrderSide,
    OrderSpec,
    OrderType,
    TimeInForce,
    VectorizedSimulationRequest,
)
from persistra.viz import attribution as attribution_viz
from persistra.viz import diagnostics as diagnostics_viz
from persistra.viz import execution as execution_viz
from persistra.viz import performance
from persistra.viz import portfolio as portfolio_viz
from persistra.viz import provenance as provenance_viz

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
                    construction.decision_inputs(),
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
        event_inputs = project.services.portfolio.decision_inputs.register_external(
            ExternalDecisionInputDeclaration(
                ContentId.from_bytes(b"flagship-event-strategy"),
                InformationClass.CAUSAL,
                TemporalContractKind.POINT_IN_TIME,
                LineageCompleteness.COMPLETE,
                SafetyStatus.SAFE,
                True,
                ("synthetic-test-data",),
                "passed",
            )
        )
        forbidden_inputs = project.services.portfolio.decision_inputs.register_external(
            ExternalDecisionInputDeclaration(
                ContentId.from_bytes(b"label-derived-strategy"),
                InformationClass.LABEL,
                TemporalContractKind.OPAQUE,
                LineageCompleteness.COMPLETE,
                SafetyStatus.UNSAFE,
                False,
                ("synthetic-test-data",),
                "failed",
            )
        )
        with pytest.raises(DecisionInputSafetyError):
            project.services.portfolio.decision_inputs.validate(
                forbidden_inputs,
                UnsafeDecisionInputOverride("adversarial laundering test"),
            )
        with pytest.raises(EventSimulationRequestError):
            EventSimulationRequest(
                market_context,
                "primary",
                BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
                event_inputs,
                event_opening,
                (
                    OrderSpec(
                        "after-horizon",
                        instruments[0],
                        OrderSide.BUY,
                        Decimal("1"),
                        OrderType.MARKET,
                        TimeInForce.GTC,
                        start_at + timedelta(days=2),
                        start_at + timedelta(days=2),
                    ),
                ),
                start_at + timedelta(days=1),
            )
        event_run = project.services.simulation.event.run(
            project.services.simulation.event.plan(
                EventSimulationRequest(
                    market_context,
                    "primary",
                    BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
                    event_inputs,
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
        assert (
            pd.to_datetime(event_run.fills()["effective_at"], utc=True)
            > pd.Timestamp(start_at)
        ).all()
        assert {"filled", "expired", "replaced", "cancelled"} <= set(
            event_run.transitions()["status"]
        )
        event_balances = event_run.journal().groupby(
            ["book_sequence", "posting_book", "commodity"], dropna=False
        )["amount"].sum()
        assert (event_balances == 0).all()
        event_result = event_run.result()
        assert event_result.summary().simulation_kind == "event"
        assert len(event_result.equity()) == 2
        assert len(event_result.orders()) == 4
        assert len(event_result.order_transitions()) == len(
            event_run.transitions()
        )
        assert len(event_result.events()) == len(event_run.events())
        assert len(event_result.fills()) == event_run.reference.fill_count
        assert len(event_result.settlements()) == event_run.reference.fill_count
        assert event_result.logs()["event_name"].tolist() == [
            "simulation.event.started",
            "simulation.event.completed",
        ]
        assert all(
            value.startswith("sha256:")
            for value in event_result.logs()["context_content_id"]
        )
        assert (
            event_result.settlements()["due_at"].min()
            > event_result.fills()["execution_at"].min()
        )
        event_journal = event_result.journal()
        assert (
            event_journal.query("transaction_kind == 'settlement'")[
                "effective_at"
            ].min()
            > event_journal.query("transaction_kind in ['buy', 'sell']")[
                "effective_at"
            ].min()
        )
        event_export = project.services.results.exports.create(
            event_result, tmp_path / "event-portable.duckdb"
        )
        assert open_export(tmp_path / "event-portable.duckdb").fills().shape == (
            event_run.reference.fill_count,
            14,
        )
        assert event_export.byte_count > 0
        assert result.summary().decision_count >= 2
        assert len(result.logs()) == 2
        assert result.summary().fill_count >= 1
        assert len(result.equity()) == result.summary().decision_count + 1
        displayed_balances = result.journal().groupby(
            ["book_sequence", "posting_book", "commodity"], dropna=False
        )["amount"].sum()
        assert displayed_balances.abs().lt(1e-8).all()
        metrics = project.services.analysis.metrics.compute(result)
        assert metrics.scalar("persistra.metric.total_return").estimate is not None
        assert metrics.scalar("persistra.metric.cost_total").estimate is not None
        metric_results = {item.metric_name: item for item in metrics.results()}
        assert tuple(metric_results) == tuple(sorted(metric_results))
        assert len(metric_results) == 26
        assert metric_results["persistra.metric.hit_rate"].unit == "ratio"
        assert metric_results["persistra.metric.beta"].state.value == "missing_input"
        execution_analysis = project.services.analysis.execution(result)
        assert "shortfall_rate" in set(execution_analysis.results()["name"])
        attribution = project.services.analysis.attribution(result)
        assert attribution.results().query(
            "name == 'reconciliation_residual'"
        ).iloc[0]["estimate"] == 0
        comparison = project.services.analysis.compare(result, result)
        assert comparison.reference.compatibility_state == "compatible"
        scenario_analysis = project.services.analysis.scenarios((metrics, metrics))
        assert len(scenario_analysis.results()) >= 3
        annotation_id = project.services.results.annotate(
            result.id, "reviewed flagship", tags=("accepted", "flagship")
        )
        assert str(annotation_id.value) in set(
            project.services.results.annotations(result.id)["annotation_id"].astype(str)
        )
        project.services.results.archive(result.id)
        assert str(result.id.value) in set(
            project.services.results.list()["run_record_id"].astype(str)
        )
        exported = project.services.results.exports.create(
            result, tmp_path / "portable.duckdb"
        )
        assert project.services.results.exports.verify(tmp_path / "portable.duckdb") == (
            exported.manifest_content_id
        )
        tampered_duckdb = tmp_path / "portable-tampered.duckdb"
        shutil.copyfile(tmp_path / "portable.duckdb", tampered_duckdb)
        tamper_connection = duckdb.connect(str(tampered_duckdb))
        try:
            raw_manifest = tamper_connection.execute(
                "SELECT manifest_json FROM _persistra_export_manifest"
            ).fetchone()
            assert raw_manifest is not None
            changed_manifest = json.loads(raw_manifest[0])
            changed_manifest["fidelity_findings"] = ["tampered.provenance"]
            tamper_connection.execute(
                "UPDATE _persistra_export_manifest SET manifest_json = ?",
                [json.dumps(changed_manifest, sort_keys=True)],
            )
        finally:
            tamper_connection.close()
        with pytest.raises(ExportVerificationError):
            project.services.results.exports.verify(tampered_duckdb)
        with pytest.raises(ExportVerificationError):
            open_export(tampered_duckdb)
        parquet_export = project.services.results.exports.create(
            result, tmp_path / "portable-parquet", export_format="parquet"
        )
        assert project.services.results.exports.verify(tmp_path / "portable-parquet") == (
            parquet_export.manifest_content_id
        )
        csv_export = project.services.results.exports.create(
            result, tmp_path / "portable-csv", export_format="csv"
        )
        assert csv_export.byte_count > 0
        unsafe_bundle = tmp_path / "portable-parquet-unsafe"
        shutil.copytree(tmp_path / "portable-parquet", unsafe_bundle)
        unsafe_manifest_path = unsafe_bundle / "manifest.json"
        unsafe_manifest = json.loads(unsafe_manifest_path.read_text(encoding="utf-8"))
        unsafe_manifest["files"][0]["name"] = "../outside.parquet"
        unsafe_manifest_path.write_text(
            json.dumps(unsafe_manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        with pytest.raises(ExportSecurityError):
            project.services.results.exports.verify(unsafe_bundle)
        extra_file_bundle = tmp_path / "portable-csv-extra"
        shutil.copytree(tmp_path / "portable-csv", extra_file_bundle)
        (extra_file_bundle / "unlisted.txt").write_text("untrusted", encoding="utf-8")
        with pytest.raises(ExportSecurityError):
            project.services.results.exports.verify(extra_file_bundle)
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
        bundle = report.copy_bundle_to(tmp_path / "report-bundle")
        assert verify_bundle(tmp_path / "report-bundle") == bundle.manifest_content_id
        assert (tmp_path / "report-bundle" / "index.html").read_bytes() == rendered
        assert performance.returns(result).layout.meta["counts"]["returns"] >= 1
        assert performance.metric_summary(metrics).layout.meta["counts"]["metrics"] >= 1
        assert portfolio_viz.exposure(result).layout.meta["counts"]["equity"] >= 1
        assert portfolio_viz.positions(result).layout.meta["counts"]["positions"] >= 1
        assert execution_viz.fills(result).layout.meta["counts"]["fills"] >= 1
        assert execution_viz.costs(result).layout.meta["counts"]["cost_components"] >= 1
        assert attribution_viz.contributions(attribution).layout.meta["counts"][
            "contributions"
        ] >= 1
        assert diagnostics_viz.fidelity(result).layout.meta["counts"]["findings"] >= 1
        assert provenance_viz.roots(result).layout.meta["counts"]["roots"] == 3
        portable = open_export(tmp_path / "portable.duckdb")
        assert portable.id == result.id
        assert portable.summary().simulation_kind == "vectorized"
        assert len(portable.logs()) == 2
        assert len(portable.equity()) == len(result.equity())
        assert open_export(tmp_path / "portable-parquet").id == result.id
        assert open_export(tmp_path / "portable-csv").id == result.id
        portable_dashboard = DashboardData(
            PortableExportSource(
                tmp_path / "portable.duckdb",
                exported.manifest_content_id,
                exported.output_sha256,
            ),
            limits=DashboardLimits(max_query_rows=10_000),
        )
        for page in (
            "overview",
            "performance",
            "portfolio",
            "execution",
            "attribution",
            "diagnostics",
            "studies",
            "inspection",
        ):
            assert portable_dashboard.query(str(result.id), page).page == page
        result_id = str(result.id)

    project_dashboard = DashboardData(
        ProjectDashboardSource(root),
        limits=DashboardLimits(max_query_rows=10_000),
    )
    assert result_id in set(project_dashboard.runs()["run_record_id"].astype(str))
    for page in (
        "overview",
        "performance",
        "portfolio",
        "execution",
        "attribution",
        "diagnostics",
        "studies",
        "inspection",
    ):
        assert project_dashboard.query(result_id, page).page == page
    backup_path = tmp_path / "dashboard-backup.duckdb"
    with Project.open(
        root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=ResearchDatabase(),
        maintenance_intent=MaintenanceIntent.BACKUP,
    ) as maintenance:
        maintenance.services.databases.backup(destination=backup_path)
    backup_dashboard = DashboardData(
        BackupDashboardSource(backup_path),
        limits=DashboardLimits(max_query_rows=10_000),
    )
    assert backup_dashboard.query(result_id, "overview").page == "overview"
    with pytest.raises(DashboardSecurityError):
        DashboardData(
            BackupDashboardSource(root / ".persistra" / "research.duckdb"),
            limits=DashboardLimits(max_query_rows=10_000),
        ).runs()
