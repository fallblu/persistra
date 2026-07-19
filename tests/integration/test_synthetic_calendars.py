from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from persistra import Project, ProjectMode
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock
from persistra.reference import (
    ALWAYS_OPEN_CALENDAR_NAME,
    FX_24X5_CALENDAR_NAME,
    SYNTHETIC_OTC_VENUE_ID,
    AsOfContext,
    CalendarDefinition,
    CalendarRef,
    NonSession,
    Session,
    SessionDecisionAnchor,
    SessionDecisionSchedule,
    SessionSelection,
)

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
AVAILABLE = datetime(2025, 12, 1, tzinfo=UTC)
COVERAGE_START = date(2025, 12, 20)
COVERAGE_END = date(2026, 1, 15)


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


def test_synthetic_calendar_definitions_use_shared_conventions() -> None:
    always = CalendarDefinition.always_open(
        coverage_start=COVERAGE_START,
        coverage_end=COVERAGE_END,
        available_at=AVAILABLE,
    )
    fx = CalendarDefinition.fx_24x5(
        coverage_start=COVERAGE_START,
        coverage_end=COVERAGE_END,
        available_at=AVAILABLE,
    )
    assert always.name == ALWAYS_OPEN_CALENDAR_NAME
    assert always.exchange_calendar_name == "24/7"
    assert fx.name == FX_24X5_CALENDAR_NAME
    assert fx.exchange_calendar_name == "24/5"
    assert always.venue_id == SYNTHETIC_OTC_VENUE_ID
    assert fx.venue_id == SYNTHETIC_OTC_VENUE_ID
    assert always.timezone_name == fx.timezone_name == "UTC"


def test_synthetic_calendars_register_and_produce_sessions(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        always = project.services.reference.calendars.register(
            CalendarDefinition.always_open(
                coverage_start=COVERAGE_START,
                coverage_end=COVERAGE_END,
                available_at=AVAILABLE,
            )
        )
        assert (
            project.services.reference.calendars.register(
                CalendarDefinition.always_open(
                    coverage_start=COVERAGE_START,
                    coverage_end=COVERAGE_END,
                    available_at=AVAILABLE,
                )
            )
            == always
        )
        project.services.reference.calendars.register(
            CalendarDefinition.fx_24x5(
                coverage_start=COVERAGE_START,
                coverage_end=COVERAGE_END,
                available_at=AVAILABLE,
            )
        )
        snapshot = project.services.snapshots.create()

    context = AsOfContext(
        snapshot,
        datetime(2026, 1, 9, 21, tzinfo=UTC),
        datetime(2026, 1, 9, 21, tzinfo=UTC),
    )
    with Project.open(root, mode=ProjectMode.READ_ONLY, clock=FixedClock(NOW)) as project:
        always_handle = project.services.reference.calendars.get(
            CalendarRef(ALWAYS_OPEN_CALENDAR_NAME, 1), context=context
        )
        fx_handle = project.services.reference.calendars.get(
            CalendarRef(FX_24X5_CALENDAR_NAME, 1), context=context
        )

        christmas = always_handle.session(date(2025, 12, 25))
        assert isinstance(christmas, Session)
        saturday = always_handle.session(date(2026, 1, 3))
        assert isinstance(saturday, Session)
        assert saturday.open_at == datetime(2026, 1, 3, tzinfo=UTC)
        assert saturday.close_at == datetime(2026, 1, 4, tzinfo=UTC)
        days = always_handle.schedule(date(2025, 12, 22), date(2026, 1, 5))
        assert all(isinstance(day, Session) for day in days)
        assert len(days) == 14

        fx_christmas = fx_handle.session(date(2025, 12, 25))
        assert isinstance(fx_christmas, Session)
        fx_saturday = fx_handle.session(date(2026, 1, 3))
        assert isinstance(fx_saturday, NonSession)
        assert fx_saturday.closure_reason == "weekend"
        assert fx_handle.next_session(date(2026, 1, 2)).calendar_date == date(2026, 1, 5)
        assert fx_handle.previous_session(date(2026, 1, 5)).calendar_date == date(
            2026, 1, 2
        )
        fx_days = fx_handle.schedule(date(2026, 1, 5), date(2026, 1, 12))
        assert [isinstance(day, Session) for day in fx_days] == [
            True,
            True,
            True,
            True,
            True,
            False,
            False,
        ]

        every, _ = project.services.reference.calendars.decisions(
            SessionDecisionSchedule(
                CalendarRef(ALWAYS_OPEN_CALENDAR_NAME, 1),
                SessionDecisionAnchor.CLOSE,
                SessionSelection.EVERY_SESSION,
            ),
            start_at=datetime(2026, 1, 2, tzinfo=UTC),
            end_at=datetime(2026, 1, 6, tzinfo=UTC),
            context=context,
        )
        assert [decision.session_date for decision in every] == [
            date(2026, 1, 2),
            date(2026, 1, 3),
            date(2026, 1, 4),
        ]
        assert every[0].decision_at == datetime(2026, 1, 3, tzinfo=UTC)

        week_end, _ = project.services.reference.calendars.decisions(
            SessionDecisionSchedule(
                CalendarRef(FX_24X5_CALENDAR_NAME, 1),
                SessionDecisionAnchor.CLOSE,
                SessionSelection.WEEK_END,
            ),
            start_at=datetime(2025, 12, 29, tzinfo=UTC),
            end_at=datetime(2026, 1, 11, tzinfo=UTC),
            context=context,
        )
        assert [decision.session_date for decision in week_end] == [
            date(2026, 1, 2),
            date(2026, 1, 9),
        ]
        assert week_end[0].decision_at - week_end[0].decision_at.replace(
            hour=0
        ) == timedelta(0)
