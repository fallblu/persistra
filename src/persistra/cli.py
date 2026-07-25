"""This module contains the command-line entry point for managed Persistra operations."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from persistra import Project, __version__
from persistra.catalog import BatchId, MarketSnapshotId
from persistra.db import (
    DatabaseName,
    DatabaseRole,
    MaintenanceIntent,
    MarketDatabase,
    PathDatabase,
    ProjectId,
    ProjectMode,
    ResearchDatabase,
)
from persistra.logging import configure_logging, safe_error

if TYPE_CHECKING:
    from collections.abc import Sequence


def _selector(value: str) -> ResearchDatabase | MarketDatabase | PathDatabase:
    if value == "research":
        return ResearchDatabase()
    if value.startswith("market:"):
        return MarketDatabase(DatabaseName(value.removeprefix("market:")))
    if value.startswith("path:"):
        return PathDatabase(Path(value.removeprefix("path:")))
    raise argparse.ArgumentTypeError("database must be research, market:NAME, or path:PATH")


def parser() -> argparse.ArgumentParser:
    """Build the bounded standard-library command parser."""
    root = argparse.ArgumentParser(prog="persistra", description="Persistra research workbench")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command")

    project = commands.add_parser("project", help="manage a project layout")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    initialize = project_commands.add_parser("init", help="initialize a project")
    initialize.add_argument("path", type=Path)
    initialize.add_argument("--name")
    initialize.add_argument("--no-research", action="store_true")
    inspect = project_commands.add_parser("inspect", help="inspect managed databases")
    inspect.add_argument("path", type=Path, nargs="?", default=Path("."))

    doctor = commands.add_parser("doctor", help="run read-only diagnostics")
    doctor.add_argument("path", type=Path, nargs="?", default=Path("."))

    database = commands.add_parser("db", help="perform isolated database maintenance")
    database_commands = database.add_subparsers(dest="db_command", required=True)
    create = database_commands.add_parser("create", help="create a managed database")
    create.add_argument("project", type=Path)
    create.add_argument("destination", type=Path)
    create.add_argument("--role", choices=[item.value for item in DatabaseRole], required=True)
    backup = database_commands.add_parser("backup", help="publish a verified backup")
    backup.add_argument("project", type=Path)
    backup.add_argument("--database", type=_selector, required=True)
    backup.add_argument("--destination", type=Path, required=True)
    verify = database_commands.add_parser("verify-copy", help="verify a published copy")
    verify.add_argument("project", type=Path)
    verify.add_argument("copy", type=Path)
    migrate = database_commands.add_parser("migrate", help="verify or migrate a database")
    migrate.add_argument("project", type=Path)
    migrate.add_argument("--database", type=_selector, required=True)
    snapshot_copy = database_commands.add_parser(
        "snapshot-copy", help="publish a snapshot-pinned market copy"
    )
    snapshot_copy.add_argument("project", type=Path)
    snapshot_copy.add_argument("--database", type=_selector, required=True)
    snapshot_copy.add_argument("--snapshot-id", type=MarketSnapshotId.parse, required=True)
    snapshot_copy.add_argument("--destination", type=Path, required=True)
    restore = database_commands.add_parser("restore", help="restore into a new destination")
    restore.add_argument("project", type=Path)
    restore.add_argument("destination", type=Path)
    restore.add_argument("--backup", type=Path, required=True)
    fork = database_commands.add_parser("fork", help="fork into a new destination")
    fork.add_argument("project", type=Path)
    fork.add_argument("destination", type=Path)
    fork.add_argument("--backup", type=Path, required=True)
    fork.add_argument("--destination-project", type=ProjectId.parse, required=True)
    data = commands.add_parser("data", help="validate and inspect managed market data")
    data_commands = data.add_subparsers(dest="data_command", required=True)
    validate = data_commands.add_parser("validate", help="validate one staged batch")
    validate.add_argument("project", type=Path)
    validate.add_argument("--market", type=DatabaseName, required=True)
    validate.add_argument("--batch-id", type=BatchId.parse, required=True)
    quarantine = data_commands.add_parser("quarantine", help="list quarantined records")
    quarantine.add_argument("project", type=Path)
    quarantine.add_argument("--market", type=DatabaseName, required=True)
    quarantine.add_argument("--batch-id", type=BatchId.parse)
    snapshots = data_commands.add_parser("snapshot", help="manage market snapshots")
    snapshot_commands = snapshots.add_subparsers(dest="snapshot_command", required=True)
    snapshot_list = snapshot_commands.add_parser("list", help="list committed snapshots")
    snapshot_list.add_argument("project", type=Path)
    snapshot_list.add_argument("--market", type=DatabaseName, required=True)
    snapshot_list.add_argument("--limit", type=int, default=100)
    snapshot_inspect = snapshot_commands.add_parser(
        "inspect", help="inspect one committed snapshot"
    )
    snapshot_inspect.add_argument("project", type=Path)
    snapshot_inspect.add_argument("snapshot_id", type=MarketSnapshotId.parse)
    snapshot_inspect.add_argument("--market", type=DatabaseName, required=True)
    snapshot_create = snapshot_commands.add_parser("create", help="create a market snapshot")
    snapshot_create.add_argument("project", type=Path)
    snapshot_create.add_argument("--market", type=DatabaseName, required=True)

    dashboard = commands.add_parser("dashboard", help="launch the read-only local dashboard")
    sources = dashboard.add_mutually_exclusive_group(required=True)
    sources.add_argument("--project", type=Path)
    sources.add_argument("--backup", type=Path)
    sources.add_argument("--export", type=Path)
    dashboard.add_argument("--bind", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8501)
    dashboard.add_argument("--open-browser", action="store_true")
    dashboard.add_argument("--unsupported-network-override", action="store_true")
    return root


def _print(value: Any) -> None:
    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            mapping = cast("dict[Any, Any]", item)
            if set(mapping) == {"_value"}:
                return str(mapping["_value"])
            if set(mapping) == {"algorithm", "digest"} and isinstance(
                mapping["digest"], bytes
            ):
                return f"{mapping['algorithm']}:{mapping['digest'].hex()}"
            return {str(key): normalize(child) for key, child in mapping.items()}
        if isinstance(item, list | tuple):
            return [normalize(child) for child in cast("list[Any] | tuple[Any, ...]", item)]
        return item

    print(
        json.dumps(
            normalize(value), sort_keys=True, default=str, separators=(",", ":")
        )
    )


def _run_command(argv: Sequence[str] | None = None) -> int:
    """Run one bounded command and emit machine-readable JSON evidence."""
    arguments = parser().parse_args(argv)
    if arguments.command is None:
        parser().print_help()
        return 0
    if arguments.command == "project" and arguments.project_command == "init":
        layout = Project.init(
            arguments.path,
            name=arguments.name,
            create_research_database=not arguments.no_research,
        )
        _print(asdict(layout))
        return 0
    if arguments.command == "project" and arguments.project_command == "inspect":
        with Project.open(arguments.path, mode=ProjectMode.READ_ONLY) as project:
            _print(asdict(project.inspect()))
        return 0
    if arguments.command == "doctor":
        with Project.open(arguments.path, mode=ProjectMode.READ_ONLY) as project:
            _print([asdict(item) for item in project.services.diagnostics.doctor()])
        return 0
    if arguments.command == "dashboard":
        from persistra.dashboard import (
            BackupDashboardSource,
            DashboardRequest,
            PortableExportSource,
            ProjectDashboardSource,
            launch,
        )

        source = (
            ProjectDashboardSource(arguments.project)
            if arguments.project is not None
            else BackupDashboardSource(arguments.backup)
            if arguments.backup is not None
            else PortableExportSource(arguments.export)
        )
        return launch(
            DashboardRequest(
                source,
                bind_address=arguments.bind,
                port=arguments.port,
                open_browser=arguments.open_browser,
                unsupported_network_override=arguments.unsupported_network_override,
            )
        )
    if arguments.command == "db" and arguments.db_command == "create":
        selector = PathDatabase(arguments.destination)
        with Project.open(
            arguments.project,
            mode=ProjectMode.MAINTENANCE,
            maintenance_database=selector,
            maintenance_intent=MaintenanceIntent.CREATE,
        ) as project:
            result = project.services.databases.create(
                role=DatabaseRole(arguments.role), path=arguments.destination
            )
            _print(asdict(result))
        return 0
    if arguments.command == "db" and arguments.db_command == "backup":
        with Project.open(
            arguments.project,
            mode=ProjectMode.MAINTENANCE,
            maintenance_database=arguments.database,
            maintenance_intent=MaintenanceIntent.BACKUP,
        ) as project:
            result = project.services.databases.backup(destination=arguments.destination)
            _print(asdict(result))
        return 0
    if arguments.command == "db" and arguments.db_command == "verify-copy":
        with Project.open(
            arguments.project,
            mode=ProjectMode.MAINTENANCE,
            maintenance_database=PathDatabase(arguments.copy),
            maintenance_intent=MaintenanceIntent.VERIFY_COPY,
        ) as project:
            _print(asdict(project.services.databases.verify_copy()))
        return 0
    if arguments.command == "db" and arguments.db_command == "migrate":
        with Project.open(
            arguments.project,
            mode=ProjectMode.MAINTENANCE,
            maintenance_database=arguments.database,
            maintenance_intent=MaintenanceIntent.MIGRATE,
        ) as project:
            _print(asdict(project.services.databases.migrate()))
        return 0
    if arguments.command == "db" and arguments.db_command == "snapshot-copy":
        with Project.open(
            arguments.project,
            mode=ProjectMode.MAINTENANCE,
            maintenance_database=arguments.database,
            maintenance_intent=MaintenanceIntent.SNAPSHOT_COPY,
        ) as project:
            result = project.services.databases.snapshot_copy(
                snapshot_id=arguments.snapshot_id,
                destination=arguments.destination,
            )
            _print(asdict(result))
        return 0
    if arguments.command == "db" and arguments.db_command in {"restore", "fork"}:
        intent = (
            MaintenanceIntent.RESTORE
            if arguments.db_command == "restore"
            else MaintenanceIntent.FORK
        )
        with Project.open(
            arguments.project,
            mode=ProjectMode.MAINTENANCE,
            maintenance_database=PathDatabase(arguments.destination),
            maintenance_intent=intent,
        ) as project:
            result = (
                project.services.databases.restore(backup_path=arguments.backup)
                if arguments.db_command == "restore"
                else project.services.databases.fork(
                    backup_path=arguments.backup,
                    destination_project_id=arguments.destination_project,
                )
            )
            _print(asdict(result))
        return 0
    if arguments.command == "data" and arguments.data_command == "validate":
        with Project.open(
            arguments.project,
            mode=ProjectMode.MARKET_WRITE,
            writable_market=arguments.market,
        ) as project:
            _print(asdict(project.services.ingestion.validate(arguments.batch_id)))
        return 0
    if arguments.command == "data" and arguments.data_command == "quarantine":
        with Project.open(arguments.project, mode=ProjectMode.READ_ONLY) as project:
            rows = project.services.ingestion.quarantine.list(
                market=arguments.market, batch_id=arguments.batch_id
            )
            _print([asdict(item) for item in rows])
        return 0
    if arguments.command == "data" and arguments.data_command == "snapshot":
        if arguments.snapshot_command == "create":
            with Project.open(
                arguments.project,
                mode=ProjectMode.MARKET_WRITE,
                writable_market=arguments.market,
            ) as project:
                _print(asdict(project.services.snapshots.create()))
            return 0
        with Project.open(arguments.project, mode=ProjectMode.READ_ONLY) as project:
            result = (
                project.services.snapshots.list(
                    market=arguments.market, limit=arguments.limit
                )
                if arguments.snapshot_command == "list"
                else project.services.snapshots.get(
                    arguments.snapshot_id, market=arguments.market
                )
            )
            _print(
                [asdict(item) for item in result]
                if isinstance(result, tuple)
                else asdict(result)
            )
        return 0
    parser().error("unsupported command")


def main(argv: Sequence[str] | None = None) -> int:
    """Run a CLI command behind a safe structured exception boundary."""
    configure_logging(json_output=True, level=logging.INFO)
    try:
        return _run_command(argv)
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # CLI boundary intentionally contains unknown failures.
        evidence = safe_error(error)
        print(
            json.dumps(
                {"error": evidence},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2 if evidence["reason_code"] != "internal.unexpected" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
