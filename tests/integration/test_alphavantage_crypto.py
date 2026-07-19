from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from persistra import Project, ProjectMode
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock, QualifiedName
from persistra.market import BarQuery, BarSpecDefinition, BarSpecRef, BarState
from persistra.reference import AsOfContext, CalendarDefinition
from persistra.sources.alphavantage.ingest import (
    AlphaVantageIngestor,
    ParsedFamilyBatch,
)
from persistra.sources.alphavantage.pairs import (
    crypto_pair_instrument,
    parse_crypto_daily_bars,
    utc_day_sessions,
)
from persistra.sources.alphavantage.registration import register_alphavantage

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


def test_alphavantage_crypto_end_to_end(tmp_path: Path) -> None:
    root = _project(tmp_path)
    instrument = crypto_pair_instrument(
        "BTC", "EUR", valid_from=AVAILABLE, available_at=AVAILABLE
    )
    sessions = utc_day_sessions(date(2026, 1, 1), date(2026, 1, 11))
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        register_alphavantage(project)
        project.services.reference.register_instrument(instrument)
        calendar = project.services.reference.calendars.register(
            CalendarDefinition.always_open(
                coverage_start=date(2025, 12, 20),
                coverage_end=date(2026, 2, 1),
                available_at=AVAILABLE,
            )
        )
        spec = project.services.market.bar_specs.register(
            BarSpecDefinition(QualifiedName("persistra.bar.session.regular"))
        )
        bars = parse_crypto_daily_bars(
            _fixture("digital_currency_daily.json"),
            instrument_id=instrument.instrument_id,
            spec=spec,
            calendar=calendar,
            sessions=sessions,
            available_at=FETCHED_AT,
            currency="EUR",
        )
        assert len(bars) == 4
        report = AlphaVantageIngestor(project).ingest(ParsedFamilyBatch(bars=bars))
        assert report.bars == 4
        snapshot = project.services.snapshots.create()

    context = AsOfContext(
        snapshot,
        datetime(2026, 1, 12, tzinfo=UTC),
        datetime(2026, 1, 12, tzinfo=UTC),
    )
    with Project.open(root, mode=ProjectMode.READ_ONLY, clock=FixedClock(NOW)) as project:
        frame = project.services.market.bars.query(
            BarQuery(
                (instrument.instrument_id,),
                BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1),
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 10, tzinfo=UTC),
                context,
            )
        )
        assert len(frame) == 4
        assert set(frame["currency"]) == {"EUR"}
        assert date(2026, 1, 4) in set(frame["session_date"])
        assert date(2026, 1, 4).weekday() == 6
        states = set(frame["bar_state"])
        assert BarState.COMPLETE.value in states
        assert BarState.NO_VOLUME.value in states
        assert frame["availability_quality"].unique().tolist() == [
            "ingestion_bounded"
        ]
