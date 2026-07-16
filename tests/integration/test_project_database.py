from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import duckdb
import pytest

from persistra import Project, ProjectMode
from persistra.db import (
    DatabaseName,
    DatabaseRole,
    MaintenanceIntent,
    PathDatabase,
    ProjectId,
)
from persistra.db.connection import ManagedConnection, create_database_file, inspect_database
from persistra.domain import FixedClock
from persistra.errors import (
    CapabilityUnavailableError,
    DatabaseRoleError,
    ProjectAlreadyExistsError,
    ProjectClosedError,
    ProjectConfigError,
    UnmanagedDatabaseError,
)

if TYPE_CHECKING:
    from pathlib import Path

NOW = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))


def test_project_init_open_transaction_inspect_and_close(tmp_path: Path) -> None:
    layout = Project.init(tmp_path / "project", name="research-project")
    assert layout.complete
    assert layout.config_path.is_file()
    assert layout.research_database_path is not None
    with Project.open(layout.root) as project:
        assert project.config.project_id == layout.project_id
        inspection = project.inspect()
        assert inspection.mode is ProjectMode.RESEARCH_WRITE
        assert inspection.databases[0].role is DatabaseRole.RESEARCH
        contexts: list[str] = []
        result = project.services.transactions.run(
            "test.operation", lambda context: contexts.append(context.operation_name) or 7
        )
        assert result == 7
        assert contexts == ["test.operation"]
        assert project.services.diagnostics.doctor()[0].code == "db.schema.current"
    with pytest.raises(ProjectClosedError):
        project.inspect()
    project.close()
    with pytest.raises(ProjectAlreadyExistsError):
        Project.init(layout.root)


def test_read_only_open_and_mode_validation(tmp_path: Path) -> None:
    layout = Project.init(tmp_path / "project")
    with Project.open(layout.root, mode=ProjectMode.READ_ONLY) as project:
        assert project.inspect().mode is ProjectMode.READ_ONLY
        with pytest.raises(CapabilityUnavailableError):
            project.services.transactions.run("forbidden", lambda _: None)
    with pytest.raises(ProjectConfigError):
        Project.open(layout.root, mode=ProjectMode.MARKET_WRITE)


def test_managed_bootstrap_role_and_unmanaged_rejection(tmp_path: Path) -> None:
    path = tmp_path / "market.duckdb"
    metadata = create_database_file(
        path,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=NOW,
    )
    connection = ManagedConnection(path, read_only=True)
    try:
        assert inspect_database(connection).database_id == metadata.database_id
        with pytest.raises(DatabaseRoleError):
            inspect_database(connection, expected_role=DatabaseRole.RESEARCH)
    finally:
        connection.close()
    unmanaged = tmp_path / "unmanaged.duckdb"
    raw = duckdb.connect(str(unmanaged))
    raw.close()
    connection = ManagedConnection(unmanaged, read_only=True)
    try:
        with pytest.raises(UnmanagedDatabaseError):
            inspect_database(connection)
    finally:
        connection.close()


def test_research_owner_is_validated(tmp_path: Path) -> None:
    path = tmp_path / "research.duckdb"
    owner = ProjectId.new()
    create_database_file(
        path,
        role=DatabaseRole.RESEARCH,
        project_id=owner,
        disposable=True,
        clock=NOW,
    )
    connection = ManagedConnection(path, read_only=True)
    try:
        with pytest.raises(DatabaseRoleError):
            inspect_database(connection, expected_project_id=ProjectId.new())
    finally:
        connection.close()


def test_maintenance_create_holds_target_and_records_creation_event(tmp_path: Path) -> None:
    layout = Project.init(tmp_path / "project")
    destination = tmp_path / "new-market.duckdb"
    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=PathDatabase(destination),
        maintenance_intent=MaintenanceIntent.CREATE,
        clock=NOW,
    ) as project:
        inspection = project.services.databases.create(
            role=DatabaseRole.MARKET,
            path=destination,
        )
        assert inspection.role is DatabaseRole.MARKET
        assert project.inspect().databases == (inspection,)
    connection = ManagedConnection(destination, read_only=True)
    try:
        event = connection.execute(
            "SELECT event_name, event_at, aggregate_sequence "
            "FROM _persistra.domain_events"
        ).fetchone()
        assert event == ("persistra.database.created", NOW.now(), 1)
    finally:
        connection.close()


def test_research_open_attaches_configured_market_read_only(tmp_path: Path) -> None:
    layout = Project.init(tmp_path / "project")
    market_path = layout.state_path / "market.duckdb"
    create_database_file(
        market_path,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=NOW,
    )
    with layout.config_path.open("a", encoding="utf-8") as config:
        config.write(
            '\n[databases.markets.primary]\npath = ".persistra/market.duckdb"\n'
            "verify_copy_on_open = false\n"
        )
    with Project.open(layout.root, mode=ProjectMode.READ_ONLY) as project:
        assert {item.logical_name for item in project.inspect().databases} == {
            "research",
            str(DatabaseName("primary")),
        }
