#!/usr/bin/env python
"""Fail if any *targeted* public symbol lacks a docstring.

Targeted = public classes / functions / methods under src/persistra, EXCLUDING
the optional features/tda subpackage (not re-exported, not rendered in the
Reference). Also checks that each listed subpackage __init__ has a module
docstring. Used as the Phase 0 gate.

Usage:
    python scripts/check_docstrings.py            # check everything
    python scripts/check_docstrings.py core viz   # check only these subpackages
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path("src/persistra")
EXCLUDE_DIRS = {"tda"}  # optional subpackage, not in the rendered Reference
INIT_PACKAGES = [
    "core",
    "data",
    "strategy",
    "pipeline",
    "features",
    "metrics",
    "viz",
    "experiments",
]


def _public(name: str) -> bool:
    return not name.startswith("_")


def _iter_targets(tree: ast.AST):
    """Yield public top-level defs/classes and public methods of public classes."""
    for node in tree.body:  # type: ignore[attr-defined]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not _public(node.name):
                continue
            yield node
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and _public(
                        sub.name
                    ):
                        yield sub


def main(argv: list[str]) -> int:
    only = set(argv)
    missing: list[str] = []

    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        pkg = rel.parts[0] if len(rel.parts) > 1 else rel.stem
        if only and pkg not in only:
            continue
        tree = ast.parse(path.read_text())
        for node in _iter_targets(tree):
            if ast.get_docstring(node) is None:
                missing.append(f"{rel}:{node.lineno}  {node.name}")

    for pkg in INIT_PACKAGES:
        if only and pkg not in only:
            continue
        init = SRC / pkg / "__init__.py"
        if init.exists() and ast.get_docstring(ast.parse(init.read_text())) is None:
            missing.append(f"{pkg}/__init__.py:1  <module docstring>")

    if missing:
        print(f"Missing docstrings ({len(missing)}):")
        for m in missing:
            print("  ", m)
        return 1
    print("All targeted public symbols documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
