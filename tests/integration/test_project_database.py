from __future__ import annotations

from datetime import UTC, datetime
from threading import Thread
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
    ResearchDatabase,
)
from persistra.db.connection import ManagedConnection, create_database_file, inspect_database
from persistra.domain import FixedClock
from persistra.errors import (
    CapabilityUnavailableError,
    CopyVerificationError,
    DatabaseCompatibilityError,
    DatabaseRecoveryRequiredError,
    DatabaseRoleError,
    MigrationRequiredError,
    ProjectAlreadyExistsError,
    ProjectClosedError,
    ProjectCloseError,
    ProjectConfigError,
    ProjectThreadError,
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
        with pytest.raises(ProjectCloseError, match="active transaction"):
            project.services.transactions.run("test.close", lambda _: project.close())
        assert project.services.diagnostics.doctor()[0].code == "db.schema.current"
    with pytest.raises(ProjectClosedError):
        project.inspect()
    project.close()
    with pytest.raises(ProjectAlreadyExistsError):
        Project.init(layout.root)


def test_read_only_open_and_mode_validation(tmp_path: Path) -> None:
    layout = Project.init(tmp_path / "project")
    with layout.config_path.open("a", encoding="utf-8") as config:
        config.write(
            '\n[resources]\nthreads = 1\nmemory_limit = "128MiB"\n'
            'temporary_limit = "64MiB"\n'
        )
    with Project.open(layout.root, mode=ProjectMode.READ_ONLY) as project:
        assert project.inspect().mode is ProjectMode.READ_ONLY
        primary = project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        assert int(primary.execute("SELECT current_setting('threads')").fetchone()[0]) == 1
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
    with Project.open(layout.root, mode=ProjectMode.RESEARCH_WRITE) as project:
        assert {item.logical_name for item in project.inspect().databases} == {
            "research",
            str(DatabaseName("primary")),
        }
        primary = project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        assert primary.execute("SELECT current_database()").fetchone() == ("research",)
        with pytest.raises(duckdb.PermissionException):
            primary.execute(f"ATTACH '{tmp_path / 'blocked.duckdb'}' AS blocked")


def test_close_rejects_cross_thread_resource_access(tmp_path: Path) -> None:
    layout = Project.init(tmp_path / "project")
    project = Project.open(layout.root)
    errors: list[BaseException] = []
    thread = Thread(target=lambda: _capture_close_error(project, errors))
    thread.start()
    thread.join()
    assert len(errors) == 1
    assert isinstance(errors[0], ProjectThreadError)
    project.close()


def _capture_close_error(project: Project, errors: list[BaseException]) -> None:
    try:
        project.close()
    except BaseException as error:
        errors.append(error)


def test_backup_publication_and_verification_detect_tampering(tmp_path: Path) -> None:
    layout = Project.init(tmp_path / "project")
    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=ResearchDatabase(),
        maintenance_intent=MaintenanceIntent.MIGRATE,
    ) as project:
        migration = project.services.databases.migrate()
        assert migration.schema_version == 5
        assert migration.applied_migrations == ()
    backup = tmp_path / "backups" / "research.duckdb"
    backup.parent.mkdir()
    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=ResearchDatabase(),
        maintenance_intent=MaintenanceIntent.BACKUP,
        clock=NOW,
    ) as project:
        result = project.services.databases.backup(destination=backup)
        assert result.destination == backup
        assert result.database_id
        assert result.manifest_path.is_file()
        assert result.checksum_path.is_file()
    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=PathDatabase(backup),
        maintenance_intent=MaintenanceIntent.VERIFY_COPY,
    ) as project:
        verification = project.services.databases.verify_copy()
        assert verification.copy_id == result.copy_id
        assert verification.database_content_id == result.database_content_id
    restored = tmp_path / "restored.duckdb"
    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=PathDatabase(restored),
        maintenance_intent=MaintenanceIntent.RESTORE,
        clock=NOW,
    ) as project:
        restored_result = project.services.databases.restore(backup_path=backup)
        assert restored_result.database_id != result.database_id
        assert project.inspect().databases[0].database_id == restored_result.database_id
    restored_connection = ManagedConnection(restored, read_only=True)
    try:
        lineage = restored_connection.execute(
            "SELECT parent_database_id, source_copy_id, relation "
            "FROM _persistra.database_lineage"
        ).fetchone()
        assert lineage == (
            result.database_id.value,
            result.copy_id.value,
            "restore",
        )
    finally:
        restored_connection.close()

    forked = tmp_path / "forked.duckdb"
    destination_project_id = ProjectId.new()
    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=PathDatabase(forked),
        maintenance_intent=MaintenanceIntent.FORK,
        clock=NOW,
    ) as project:
        fork_result = project.services.databases.fork(
            backup_path=backup,
            destination_project_id=destination_project_id,
        )
        assert fork_result.owner_project_id == destination_project_id
    result.manifest_path.write_bytes(result.manifest_path.read_bytes() + b" ")
    with pytest.raises(CopyVerificationError):
        Project.open(
            layout.root,
            mode=ProjectMode.MAINTENANCE,
            maintenance_database=PathDatabase(backup),
            maintenance_intent=MaintenanceIntent.VERIFY_COPY,
        )


def test_creation_cleans_partial_file_and_inspection_requires_schemas(tmp_path: Path) -> None:
    path = tmp_path / "failed.duckdb"

    class FailingClock:
        def now(self) -> datetime:
            raise RuntimeError("clock failure")

    with pytest.raises(RuntimeError, match="clock failure"):
        create_database_file(
            path,
            role=DatabaseRole.MARKET,
            project_id=None,
            disposable=False,
            clock=FailingClock(),
        )
    assert not path.exists()
    assert list(tmp_path.glob(".*.partial-*")) == []

    research = tmp_path / "research.duckdb"
    create_database_file(
        research,
        role=DatabaseRole.RESEARCH,
        project_id=ProjectId.new(),
        disposable=False,
        clock=NOW,
    )
    connection = ManagedConnection(research, read_only=False)
    connection.execute("DROP SCHEMA workspace")
    with pytest.raises(DatabaseCompatibilityError):
        inspect_database(connection)
    connection.close()
    market = tmp_path / "market.duckdb"
    create_database_file(
        market,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=NOW,
    )
    connection = ManagedConnection(market, read_only=False)
    connection.execute("DROP TABLE catalog.batch_records")
    with pytest.raises(DatabaseCompatibilityError, match="role tables"):
        inspect_database(connection)
    connection.close()
    market_columns = tmp_path / "market-columns.duckdb"
    create_database_file(
        market_columns,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=NOW,
    )
    connection = ManagedConnection(market_columns, read_only=False)
    connection.execute(
        "ALTER TABLE catalog.canonical_revisions "
        "RENAME COLUMN dataset_version TO missing_dataset_version"
    )
    with pytest.raises(DatabaseCompatibilityError, match="canonical_revisions"):
        inspect_database(connection)
    connection.close()
    research_columns = tmp_path / "research-columns.duckdb"
    create_database_file(
        research_columns,
        role=DatabaseRole.RESEARCH,
        project_id=ProjectId.new(),
        disposable=False,
        clock=NOW,
    )
    connection = ManagedConnection(research_columns, read_only=False)
    database_name = str(connection.execute("SELECT current_database()").fetchone()[0])
    connection.execute(
        f'ALTER TABLE "{database_name}".research.composite_snapshot_members '
        "DROP COLUMN verified_copy_id"
    )
    with pytest.raises(DatabaseCompatibilityError, match="composite_snapshot_members"):
        inspect_database(connection)
    connection.close()


def test_forward_migration_is_backup_first_and_reopens_current_schema(
    tmp_path: Path,
) -> None:
    layout = Project.init(tmp_path / "project")
    assert layout.research_database_path is not None
    connection = ManagedConnection(layout.research_database_path, read_only=False)
    try:
        connection.execute(
            "DELETE FROM _persistra.schema_migrations WHERE migration_number >= 4"
        )
        connection.execute(
            "DELETE FROM _persistra.domain_events "
            "WHERE event_name = 'persistra.database.migrated' "
            "AND aggregate_sequence >= 4"
        )
        for table in (
            "feature_values",
        ):
            connection.execute(f"DROP TABLE research_data.{table}")
        for table in (
            "feature_materializations",
            "feature_versions",
            "feature_definitions",
        ):
            connection.execute(f"DROP TABLE research.{table}")
        connection.execute("DROP TABLE results.run_records")
        for table in ("report_outputs", "report_plans", "artifacts"):
            connection.execute(f"DROP TABLE analysis.{table}")
        for schema in (
            "portfolio",
            "accounting",
            "journal_data",
            "simulation",
            "simulation_data",
            "result_data",
            "analysis_data",
        ):
            connection.execute(f"DROP SCHEMA {schema} CASCADE")
        for table in (
            "research_dataset_input_outcomes",
            "research_dataset_row_audit",
            "research_dataset_builds",
            "research_dataset_versions",
            "research_datasets",
            "universe_rule_outcomes",
            "universe_eligibility",
            "universe_evaluations",
            "universe_definitions",
        ):
            connection.execute(f"DROP TABLE research.{table}")
        connection.execute("DROP SCHEMA research_data")
        connection.execute("UPDATE _persistra.database_info SET schema_version = 3")
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    with pytest.raises(MigrationRequiredError):
        Project.open(layout.root, mode=ProjectMode.READ_ONLY)

    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=ResearchDatabase(),
        maintenance_intent=MaintenanceIntent.MIGRATE,
        clock=NOW,
    ) as project:
        result = project.services.databases.migrate()
        assert result.schema_version == 5
        assert result.applied_migrations == (4, 5)
        assert result.backup_copy_id is not None
        assert project.inspect().databases[0].schema_version == 5
        assert project.services.databases.migrate().applied_migrations == ()

    backups = tuple((layout.state_path / "backups").glob("*.duckdb"))
    assert len(backups) == 1
    assert backups[0].with_name(f"{backups[0].name}.persistra-copy.json").is_file()
    connection = ManagedConnection(layout.research_database_path, read_only=True)
    try:
        assert inspect_database(connection).schema_version == 5
        assert connection.execute(
            "SELECT migration_name, backup_copy_id FROM _persistra.schema_migrations "
            "WHERE migration_number = 4"
        ).fetchone() == (
            "daily_market_research_foundation",
            result.backup_copy_id.value,
        )
    finally:
        connection.close()
    restored = tmp_path / "restored-from-schema-2.duckdb"
    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=PathDatabase(restored),
        maintenance_intent=MaintenanceIntent.RESTORE,
        clock=NOW,
    ) as project:
        restored_result = project.services.databases.restore(backup_path=backups[0])
        assert restored_result.destination == restored
    connection = ManagedConnection(restored, read_only=True)
    try:
        assert inspect_database(connection).schema_version == 5
    finally:
        connection.close()


def test_maintenance_operations_revalidate_leased_path_identity(tmp_path: Path) -> None:
    layout = Project.init(tmp_path / "project")
    assert layout.research_database_path is not None
    moved = layout.research_database_path.with_suffix(".moved")
    destination = tmp_path / "backup.duckdb"
    with Project.open(
        layout.root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=ResearchDatabase(),
        maintenance_intent=MaintenanceIntent.BACKUP,
    ) as project:
        layout.research_database_path.rename(moved)
        try:
            with pytest.raises(DatabaseRecoveryRequiredError, match="identity changed"):
                project.services.databases.backup(destination=destination)
        finally:
            moved.rename(layout.research_database_path)
