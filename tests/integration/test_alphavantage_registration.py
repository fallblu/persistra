from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from persistra import Project, ProjectMode
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock
from persistra.sources.alphavantage.registration import register_alphavantage

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)


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


def test_alphavantage_registration_is_idempotent(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        first = register_alphavantage(project)
        second = register_alphavantage(project)
        assert first == second
        assert first.version == 1
