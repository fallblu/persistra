"""Command-line entry point for managed Persistra operations."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from persistra import __version__


def parser() -> argparse.ArgumentParser:
    """Build the bounded standard-library command parser."""
    root = argparse.ArgumentParser(prog="persistra", description="Persistra research workbench")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    root.add_subparsers(dest="command")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line shell."""
    parsed = parser().parse_args(argv)
    if parsed.command is None:
        parser().print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
