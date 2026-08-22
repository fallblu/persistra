"""Packaging and direct dependency invariants."""

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import cast

from scripts.check_package import (
    CORE_TOP_LEVEL_NAMESPACES,
    EXPECTED_PROJECT_URLS,
    PUBLIC_TOP_LEVEL_NAMESPACES,
    SDIST_DIRECTORY_PREFIXES,
    SDIST_ROOT_FILES,
    source_top_level_namespaces,
    validate_sdist_policy,
)
from scripts.check_release import validate_release_tag

IMPORT_TO_DISTRIBUTION = {
    "duckdb": "duckdb",
    "numpy": "numpy",
    "pandas": "pandas",
    "platformdirs": "platformdirs",
    "requests": "requests",
    "scipy": "scipy",
}
BASE_SUPPORT_DISTRIBUTIONS = {"tzdata"}
VISUALIZATION_DISTRIBUTIONS = {"matplotlib", "pillow"}
INSPECTOR_DISTRIBUTIONS = VISUALIZATION_DISTRIBUTIONS | {"panel"}

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
        "persistra.validation",
        "persistra.viz",
    )
    assert CORE_TOP_LEVEL_NAMESPACES == PUBLIC_TOP_LEVEL_NAMESPACES[:-1]
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
    assert declared == set(IMPORT_TO_DISTRIBUTION.values()) | BASE_SUPPORT_DISTRIBUTIONS

    imported: set[str] = set()
    for path in Path("src/persistra").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
    third_party = imported - sys.stdlib_module_names - {"persistra"}
    assert third_party == set(IMPORT_TO_DISTRIBUTION) | {"matplotlib"}


def test_visualization_and_inspector_dependencies_are_focused_extras() -> None:
    document = cast("dict[str, object]", tomllib.loads(Path("pyproject.toml").read_text()))
    project = cast("dict[str, object]", document["project"])
    extras = cast("dict[str, list[str]]", project["optional-dependencies"])
    names = {
        extra: {re.split(r"[<>=!~\[]", dependency, maxsplit=1)[0] for dependency in requirements}
        for extra, requirements in extras.items()
    }
    assert names["viz"] == VISUALIZATION_DISTRIBUTIONS
    assert names["inspect"] == INSPECTOR_DISTRIBUTIONS
    dependencies = cast("list[str]", project["dependencies"])
    assert not any(
        dependency.startswith(("matplotlib", "panel", "pillow")) for dependency in dependencies
    )


def test_published_metadata_uses_canonical_urls_and_pep_639() -> None:
    document = cast(
        "dict[str, object]", tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    )
    project = cast("dict[str, object]", document["project"])
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    classifiers = cast("list[str]", project["classifiers"])
    assert not any(classifier.startswith("License ::") for classifier in classifiers)
    assert project["urls"] == EXPECTED_PROJECT_URLS

    extras = cast("dict[str, list[str]]", project["optional-dependencies"])
    assert extras["docs"] == [
        "mkdocs>=1.6.1,<2",
        "mkdocs-material>=9.7.6,<10",
        "mkdocstrings[python]>=0.30,<1",
        "pymdown-extensions>=11.0.1,<12",
    ]
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "](docs/" not in readme
    assert "https://fallblu.github.io/persistra/" in readme


def test_documentation_configuration_and_deployment_are_canonical_and_pinned() -> None:
    configuration = Path("mkdocs.yml").read_text(encoding="utf-8")
    assert "site_url: https://fallblu.github.io/persistra/" in configuration
    assert "repo_url: https://github.com/fallblu/persistra" in configuration
    assert "repo_name: fallblu/persistra" in configuration
    assert "edit_uri: edit/develop/docs/" in configuration
    assert "concepts/documentation-platform.md" in configuration

    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "NO_MKDOCS_2_WARNING=true uv run --group docs mkdocs build --strict" in makefile
    decision = Path("docs/concepts/documentation-platform.md").read_text(encoding="utf-8")
    assert "mkdocstrings integration as unfinished" in decision
    assert "MkDocs 1.x, Material 9.7, mkdocstrings 0.x" in decision

    workflow = Path(".github/workflows/docs.yml").read_text(encoding="utf-8")
    assert "branches: [develop]" in workflow
    assert "if: github.ref == 'refs/heads/develop'" in workflow
    build, deploy = workflow.split("  deploy:\n", 1)
    assert "pages: write" not in build
    assert "id-token: write" not in build
    assert "pages: write" in deploy
    assert "id-token: write" in deploy
    assert "make docs-check docs-build" in workflow

    actions = re.findall(r"uses: [^@\s]+@([^\s]+)", workflow)
    assert len(actions) == 5
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for revision in actions)


def test_source_distribution_policy_accepts_only_documented_content() -> None:
    files = tuple(
        sorted((*SDIST_ROOT_FILES, *(f"{prefix}file" for prefix in SDIST_DIRECTORY_PREFIXES)))
    )

    validate_sdist_policy(files)


def test_source_distribution_policy_rejects_contributor_only_files() -> None:
    files = tuple(
        sorted(
            (
                *SDIST_ROOT_FILES,
                *(f"{prefix}file" for prefix in SDIST_DIRECTORY_PREFIXES),
                "AGENTS.md",
            )
        )
    )

    try:
        validate_sdist_policy(files)
    except ValueError as error:
        assert "outside policy" in str(error)
    else:
        raise AssertionError("contributor-only file was accepted")
