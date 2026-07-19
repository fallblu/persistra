from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]

from persistra import Project, ProjectMode
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock, QualifiedName
from persistra.market import (
    AdjustmentPriceMode,
    AdjustmentViewRequest,
    BarQuery,
    BarSpecDefinition,
    BarSpecRef,
    TradingStatus,
)
from persistra.reference import (
    AsOfContext,
    CalendarDefinition,
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
from persistra.sources.alphavantage.equity import (
    parse_daily_equity_bars,
    parse_dividends,
    parse_market_status,
    parse_splits,
)
from persistra.sources.alphavantage.ingest import (
    AlphaVantageIngestor,
    ParsedFamilyBatch,
)
from persistra.sources.alphavantage.registration import register_alphavantage

if TYPE_CHECKING:
    from persistra.market import DailyBar

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
AVAILABLE = datetime(2025, 12, 1, tzinfo=UTC)
FETCHED_AT = datetime(2026, 1, 10, tzinfo=UTC)


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


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def _sessions() -> dict[date, tuple[datetime, datetime]]:
    exchange = xcals.get_calendar("XNYS", start="2026-01-01", end="2026-01-12")
    sessions: dict[date, tuple[datetime, datetime]] = {}
    for label in exchange.schedule.index:
        row = cast("Any", exchange.schedule.loc[label])
        sessions[label.date()] = (
            row["open"].to_pydatetime(),
            row["close"].to_pydatetime(),
        )
    return sessions


def test_alphavantage_core_stock_end_to_end(tmp_path: Path) -> None:
    root = _project(tmp_path)
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
    sessions = _sessions()
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        register_alphavantage(project)
        project.services.reference.register_instrument(instrument)
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
        spec = project.services.market.bar_specs.register(
            BarSpecDefinition(QualifiedName("persistra.bar.session.regular"))
        )
        bars: tuple[DailyBar, ...] = parse_daily_equity_bars(
            _fixture("time_series_daily.json"),
            instrument_id=instrument.instrument_id,
            spec=spec,
            calendar=calendar,
            sessions=sessions,
            available_at=FETCHED_AT,
        )
        assert len(bars) == 6
        splits = parse_splits(
            _fixture("splits.json"),
            security_id=instrument.security_id,
            instrument_id=instrument.instrument_id,
            sessions=sessions,
            available_at=FETCHED_AT,
        )
        dividends = parse_dividends(
            _fixture("dividends.json"),
            security_id=instrument.security_id,
            instrument_id=instrument.instrument_id,
            sessions=sessions,
            available_at=FETCHED_AT,
        )
        actions = tuple(
            action
            for action in splits + dividends
            if (action.effective_date or action.ex_date or date.min).year == 2026
        )
        assert len(actions) == 2
        status = parse_market_status(
            _fixture("market_status.json"),
            region="United States",
            market_type="Equity",
            instruments=(instrument.instrument_id,),
            effective_at=bars[0].interval_start,
            available_at=FETCHED_AT,
        )
        report = AlphaVantageIngestor(project).ingest(
            ParsedFamilyBatch(
                bars=bars,
                corporate_actions=actions,
                trading_status=status,
            )
        )
        assert report.bars == 6
        assert report.corporate_actions == 2
        assert report.trading_status == 1
        snapshot = project.services.snapshots.create()

    context = AsOfContext(
        snapshot,
        datetime(2026, 1, 12, tzinfo=UTC),
        datetime(2026, 1, 12, tzinfo=UTC),
    )
    with Project.open(root, mode=ProjectMode.READ_ONLY, clock=FixedClock(NOW)) as project:
        query = BarQuery(
            (instrument.instrument_id,),
            BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 10, tzinfo=UTC),
            context,
        )
        raw = project.services.market.bars.query(query)
        assert len(raw) == 6
        assert set(raw["currency"]) == {"USD"}
        assert raw["availability_quality"].unique().tolist() == ["ingestion_bounded"]
        adjusted = project.services.market.adjustments.view(
            AdjustmentViewRequest(
                query,
                AdjustmentPriceMode.TOTAL_RETURN,
                datetime(2026, 1, 9, 21, tzinfo=UTC),
            )
        )
        adjusted_rows = adjusted.bars()
        assert adjusted_rows.iloc[0]["adjusted_close"] < 51
        assert adjusted_rows.iloc[-1]["adjusted_close"] == 54.0
        assert len(adjusted.factors()) == 2
        assert (
            project.services.market.status.at(
                instrument.instrument_id,
                bars[0].interval_start + timedelta(hours=1),
                context=context,
            )
            is TradingStatus.TRADING
        )
