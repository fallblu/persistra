"""Shared standard-library command line interface."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from typing import TYPE_CHECKING

from persistra._inspection import (
    DirectoryInspection,
    InspectionError,
    discover_stores,
    inventory_document,
    serve_inspector,
)
from persistra.errors import ProjectError
from persistra.project import ProjectValidation, create_project, validate_project

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the shared Persistra command parser."""
    parser = argparse.ArgumentParser(prog="persistra")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect", help="inspect local Persistra stores")
    inspect_parser.add_argument("directory")
    inspect_parser.add_argument(
        "--recursive", action="store_true", help="include descendant directories"
    )
    inspect_parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    inspect_parser.add_argument("--port", type=int, help="local server port")
    inspect_parser.add_argument(
        "--list", dest="list_mode", action="store_true", help="print a headless store inventory"
    )
    inspect_parser.add_argument(
        "--json", action="store_true", help="write the headless inventory as versioned JSON"
    )
    init_parser = commands.add_parser("init", help="create a standard Persistra project")
    init_parser.add_argument("directory")
    init_parser.add_argument("--name", help="explicit normalized project name")
    project_parser = commands.add_parser("project", help="work with a Persistra project")
    project_commands = project_parser.add_subparsers(dest="project_command", required=True)
    validate_parser = project_commands.add_parser(
        "validate", help="diagnose a project without changing it"
    )
    validate_parser.add_argument("directory")
    validate_parser.add_argument(
        "--json", action="store_true", help="write versioned JSON diagnostics"
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run one parsed command and return its process status."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "inspect":
        if arguments.list_mode and (arguments.no_open or arguments.port is not None):
            parser.error("--list cannot be combined with server options --no-open or --port")
        if arguments.json and not arguments.list_mode:
            parser.error("--json requires --list")
        if arguments.list_mode:
            inspection = discover_stores(
                arguments.directory,
                recursive=arguments.recursive,
                allow_empty=True,
            )
            _render_inspection_inventory(inspection, as_json=arguments.json)
            if not inspection.stores:
                print(
                    f"persistra: error: no supported Persistra stores found in "
                    f"{inspection.directory}",
                    file=sys.stderr,
                )
                return 1
            return 0
        inspection = discover_stores(arguments.directory, recursive=arguments.recursive)
        _render_inspection_warnings(inspection)
        serve_inspector(
            inspection,
            port=arguments.port,
            open_browser=not arguments.no_open,
        )
        return 0
    if arguments.command == "init":
        project = create_project(arguments.directory, name=arguments.name)
        print(f"Created Persistra project {project.name} at {project.root}")
        print()
        print(f"cd {shlex.quote(str(project.root))}")
        print("uv sync")
        print("uv run python main.py")
        print("uv run persistra project validate .")
        print("uv run persistra inspect .")
        return 0
    if arguments.command == "project" and arguments.project_command == "validate":
        validation = validate_project(arguments.directory)
        _render_project_validation(validation, as_json=arguments.json)
        return 0 if validation.is_valid else 1
    raise AssertionError(f"unhandled command: {arguments.command}")


def _render_inspection_warnings(inspection: DirectoryInspection) -> None:
    for warning in inspection.warnings:
        print(f"persistra: warning: {warning}", file=sys.stderr)


def _render_inspection_inventory(inspection: DirectoryInspection, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(inventory_document(inspection), indent=2))
        return
    _render_inspection_warnings(inspection)
    print(f"Persistra store inventory: {inspection.directory}")
    if inspection.project_name is not None:
        print(
            f"Project: {inspection.project_name} "
            f"(format version {inspection.project_format_version})"
        )
    for store in inspection.stores:
        print(f"Store: {store.path}")
        print(f"  Schema version: {store.schema_version}")
        if not store.datasets:
            print("  Datasets: none")
        for dataset in store.datasets:
            print(f"  Dataset: {dataset.family} / {dataset.scope_key}")
            print(f"    Snapshots: {dataset.snapshot_count}")
            print(f"    First seen: {dataset.first_seen.isoformat()}")
            print(f"    Last seen: {dataset.last_seen.isoformat()}")
            print(f"    Latest snapshot: {dataset.latest_snapshot_id}")


def _render_project_validation(validation: ProjectValidation, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(validation.to_dict(), indent=2))
        return
    print(f"Persistra project validation: {validation.root}")
    if validation.project_name is not None:
        print(f"Project: {validation.project_name}")
    for finding in validation.findings:
        location = "" if finding.location is None else f" [{finding.location}]"
        print(f"{finding.severity.value}: {finding.code}{location}: {finding.message}")
    print(
        f"Validation completed: {validation.error_count} error(s), "
        f"{validation.warning_count} warning(s)."
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the CLI without exposing tracebacks for expected user errors."""
    try:
        status = run(argv)
    except KeyboardInterrupt:
        print("persistra: cancelled", file=sys.stderr)
        raise SystemExit(130) from None
    except (InspectionError, ProjectError, OSError) as error:
        print(f"persistra: error: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    raise SystemExit(status)
