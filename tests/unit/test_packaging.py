"""Packaging and direct dependency invariants."""

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import cast

from scripts.check_package import PUBLIC_TOP_LEVEL_NAMESPACES, source_top_level_namespaces
from scripts.check_release import validate_release_tag

IMPORT_TO_DISTRIBUTION = {
    "duckdb": "duckdb",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "pandas": "pandas",
    "platformdirs": "platformdirs",
    "requests": "requests",
    "scipy": "scipy",
}
RUNTIME_SUPPORT_DISTRIBUTIONS = {"pillow", "tzdata"}

_CHANGELOG_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) —", re.MULTILINE)


def test_package_smoke_covers_public_top_level_namespaces() -> None:
    assert PUBLIC_TOP_LEVEL_NAMESPACES == (
        "persistra",
        "persistra.analysis",
        "persistra.data",
        "persistra.errors",
        "persistra.integrations",
        "persistra.model",
        "persistra.portfolio",
        "persistra.project",
        "persistra.research",
        "persistra.viz",
    )
    assert source_top_level_namespaces() == PUBLIC_TOP_LEVEL_NAMESPACES


def test_project_version_sources_agree() -> None:
    project_document = cast(
        "dict[str, object]", tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    )
    project = cast("dict[str, object]", project_document["project"])
    project_version = cast("str", project["version"])

    lock_document = cast(
        "dict[str, object]", tomllib.loads(Path("uv.lock").read_text(encoding="utf-8"))
    )
    packages = cast("list[dict[str, object]]", lock_document["package"])
    locked = [package for package in packages if package.get("name") == "persistra"]
    assert len(locked) == 1
    assert locked[0]["version"] == project_version

    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    changelog_release = _CHANGELOG_RELEASE.search(changelog)
    assert changelog_release is not None
    assert changelog_release.group(1) == project_version

def test_release_tag_must_match_project_version() -> None:
    validate_release_tag("v4.0.0", "4.0.0")
    try:
        validate_release_tag("v4.0.1", "4.0.0")
    except ValueError as error:
        assert str(error) == "release tag must be v4.0.0, not v4.0.1"
    else:
        raise AssertionError("mismatched release tag was accepted")


def test_runtime_requirements_are_declared_direct_dependencies() -> None:
    document = cast("dict[str, object]", tomllib.loads(Path("pyproject.toml").read_text()))
    project = cast("dict[str, object]", document["project"])
    dependencies = cast("list[str]", project["dependencies"])
    declared = {re.split(r"[<>=!~\[]", dependency, maxsplit=1)[0] for dependency in dependencies}
    assert declared == set(IMPORT_TO_DISTRIBUTION.values()) | RUNTIME_SUPPORT_DISTRIBUTIONS

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


def test_inspector_dependency_is_optional() -> None:
    document = cast("dict[str, object]", tomllib.loads(Path("pyproject.toml").read_text()))
    project = cast("dict[str, object]", document["project"])
    extras = cast("dict[str, list[str]]", project["optional-dependencies"])
    assert extras["inspect"] == ["panel>=1.9.3,<2"]
    dependencies = cast("list[str]", project["dependencies"])
    assert all(not dependency.startswith("panel") for dependency in dependencies)
