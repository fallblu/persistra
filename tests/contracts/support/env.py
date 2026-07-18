"""Deterministic project environment for family contract tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from persistra import Project, ProjectMode
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

NOW = datetime(2026, 1, 10, 12, tzinfo=UTC)


def make_project_root(tmp_path: Path) -> Path:
    """Initialize a project with one primary market database and return its root."""
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


@contextmanager
def open_market_project(root: Path) -> Generator[Project]:
    """Open a market-write project session at the deterministic fixed clock."""
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        yield project
