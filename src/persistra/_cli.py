"""Shared standard-library command line interface."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from persistra._inspection import InspectionError, discover_stores, serve_inspector

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
    inspect_parser.add_argument(
        "--no-open", action="store_true", help="do not open a browser"
    )
    inspect_parser.add_argument("--port", type=int, help="local server port")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run one parsed command and return its process status."""
    arguments = build_parser().parse_args(argv)
    if arguments.command == "inspect":
        inspection = discover_stores(arguments.directory, recursive=arguments.recursive)
        for warning in inspection.warnings:
            print(f"persistra: warning: {warning}", file=sys.stderr)
        serve_inspector(
            inspection,
            port=arguments.port,
            open_browser=not arguments.no_open,
        )
        return 0
    raise AssertionError(f"unhandled command: {arguments.command}")


def main(argv: Sequence[str] | None = None) -> None:
    """Run the CLI without exposing tracebacks for expected user errors."""
    try:
        status = run(argv)
    except (InspectionError, OSError) as error:
        print(f"persistra: error: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    raise SystemExit(status)
