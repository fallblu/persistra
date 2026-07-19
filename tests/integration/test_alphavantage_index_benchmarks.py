from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]

from persistra import Project, ProjectMode
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock, QualifiedName
from persistra.market import BenchmarkQuery, BenchmarkSeriesKind
from persistra.market.economic_models import BenchmarkVersionRef
from persistra.reference import CalendarDefinition, CalendarRef, VenueId
from persistra.reference.models import AsOfContext
from persistra.sources.alphavantage.indices import (
    index_benchmark_definition,
    parse_index_series,
)
from persistra.sources.alphavantage.ingest import (
    AlphaVantageIngestor,
    ParsedFamilyBatch,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
AVAILABLE = datetime(2025, 12, 1, tzinfo=UTC)
FETCHED_AT = datetime(2026, 1, 10, tzinfo=UTC)
CALENDAR_NAME = QualifiedName("persistra.calendar.xnys")


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


def test_alphavantage_index_levels_query_as_benchmark_series(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        calendar = project.services.reference.calendars.register(
            CalendarDefinition(
                CALENDAR_NAME,
                1,
                VenueId.new(),
                "XNYS",
                "America/New_York",
                date(2025, 12, 20),
                date(2026, 2, 1),
                AVAILABLE,
            )
        )
        benchmark = project.services.market.benchmarks.register(
            index_benchmark_definition(
                "spx_proxy", calendar=CalendarRef(CALENDAR_NAME, 1)
            )
        )
        observations = parse_index_series(
            _fixture("index_daily.json"),
            benchmark=benchmark,
            sessions=_sessions(),
            calendar_schedule_content_id=calendar.schedule_root_content_id,
            available_at=FETCHED_AT,
        )
        report = AlphaVantageIngestor(project).ingest(
            ParsedFamilyBatch(benchmark_observations=observations)
        )
        assert report.benchmark_observations == 3
        snapshot = project.services.snapshots.create()

    context = AsOfContext(
        snapshot,
        datetime(2026, 1, 12, tzinfo=UTC),
        datetime(2026, 1, 12, tzinfo=UTC),
    )
    with Project.open(root, mode=ProjectMode.READ_ONLY, clock=FixedClock(NOW)) as project:
        rows = project.services.market.benchmarks.series(
            BenchmarkQuery(
                BenchmarkVersionRef(
                    QualifiedName("alphavantage.index.spx_proxy"), 1
                ),
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 12, tzinfo=UTC),
                context,
                series_kind=BenchmarkSeriesKind.PRICE_INDEX,
            )
        )
        assert len(rows) == 3
        assert rows.iloc[-1]["value"] == 6132.5
