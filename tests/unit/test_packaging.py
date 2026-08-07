"""Packaging and direct dependency invariants."""

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import cast

IMPORT_TO_DISTRIBUTION = {
    "duckdb": "duckdb",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "pandas": "pandas",
    "platformdirs": "platformdirs",
    "requests": "requests",
}


def test_runtime_imports_are_declared_direct_dependencies() -> None:
    document = cast("dict[str, object]", tomllib.loads(Path("pyproject.toml").read_text()))
    project = cast("dict[str, object]", document["project"])
    dependencies = cast("list[str]", project["dependencies"])
    declared = {re.split(r"[<>=!~\[]", dependency, maxsplit=1)[0] for dependency in dependencies}
    assert declared == set(IMPORT_TO_DISTRIBUTION.values())

    imported: set[str] = set()
    for path in Path("src/persistra").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
    third_party = imported - sys.stdlib_module_names - {"persistra"}
    assert third_party == set(IMPORT_TO_DISTRIBUTION)
