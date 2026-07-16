"""Command-line entry point for managed Persistra operations."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from persistra import Project, __version__
from persistra.db import (
    DatabaseName,
    DatabaseRole,
    MaintenanceIntent,
    MarketDatabase,
    PathDatabase,
    ProjectMode,
    ResearchDatabase,
)

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
    return root


def _print(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")))


def main(argv: Sequence[str] | None = None) -> int:
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
    parser().error("unsupported command")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
