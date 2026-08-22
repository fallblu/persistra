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
    "pyarrow": "pyarrow",
    "requests": "requests",
    "scipy": "scipy",
}
BASE_SUPPORT_DISTRIBUTIONS = {"tzdata"}
VISUALIZATION_DISTRIBUTIONS = {"plotly"}
INSPECTOR_DISTRIBUTIONS = VISUALIZATION_DISTRIBUTIONS | {"panel"}
PORTFOLIO_SOLVER_DISTRIBUTIONS = {"cvxpy"}

_CHANGELOG_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) —", re.MULTILINE)


def test_package_smoke_covers_public_top_level_namespaces() -> None:
    assert PUBLIC_TOP_LEVEL_NAMESPACES == (
        "persistra",
        "persistra.analysis",
        "persistra.data",
        "persistra.errors",
        "persistra.integrations",
        "persistra.model",
        "persistra.monte_carlo",
        "persistra.portfolio",
        "persistra.project",
        "persistra.research",
        "persistra.validation",
        "persistra.viz",
    )
    assert CORE_TOP_LEVEL_NAMESPACES == tuple(
        namespace for namespace in PUBLIC_TOP_LEVEL_NAMESPACES if namespace != "persistra.viz"
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
    assert third_party == set(IMPORT_TO_DISTRIBUTION) | {"cvxpy", "plotly"}


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
    assert names["portfolio-solver"] == PORTFOLIO_SOLVER_DISTRIBUTIONS
    dependencies = cast("list[str]", project["dependencies"])
    assert not any(
        dependency.startswith(("cvxpy", "plotly", "panel", "pyscipopt"))
        for dependency in dependencies
    )
    lockfile = Path("uv.lock").read_text(encoding="utf-8")
    assert 'name = "matplotlib"' not in lockfile


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


def test_external_link_check_is_bounded_isolated_and_pinned() -> None:
    configuration = cast(
        "dict[str, object]", tomllib.loads(Path("lychee.toml").read_text(encoding="utf-8"))
    )
    assert configuration["threads"] == 2
    assert configuration["max_concurrency"] == 4
    assert configuration["host_concurrency"] == 2
    assert configuration["max_redirects"] == 5
    assert configuration["max_retries"] == 2
    assert configuration["timeout"] == 20
    assert configuration["retry_wait_time"] == 2
    assert configuration["scheme"] == ["https"]
    assert configuration["require_https"] is True
    assert configuration["insecure"] is False
    assert configuration["exclude_all_private"] is True
    assert configuration["include_mail"] is False
    assert configuration["exclude"] == []

    workflow = Path(".github/workflows/external-links.yml").read_text(encoding="utf-8")
    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "branches: [develop]" in workflow
    assert "pull_request:" not in workflow
    assert "timeout-minutes: 15" in workflow
    assert "format: detailed" in workflow
    assert "token: \"\"" in workflow
    assert "lycheeVersion: v0.24.2" in workflow
    assert "--config lychee.toml --verbose --no-progress" in workflow
    assert "'README.md' 'docs/**/*.md'" in workflow

    actions = re.findall(r"uses: [^@\s]+@([^\s]+)", workflow)
    assert len(actions) == 2
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for revision in actions)

    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "lychee" not in makefile.lower()


def test_ci_pins_and_reports_trading_engine_compatibility() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    revision = "b1f87b8252a159506fa2e31d593ab78883917fe9"

    assert f"TRADING_ENGINE_COMPAT_REVISION: {revision}" in workflow
    assert "ref: ${{ env.TRADING_ENGINE_COMPAT_REVISION }}" in workflow
    assert "TRADING_ENGINE_COMPAT_REF" not in workflow
    assert "vars." not in workflow
    assert 'actual_revision="$(git rev-parse HEAD)"' in workflow
    assert 'test "$actual_revision" = "$TRADING_ENGINE_COMPAT_REVISION"' in workflow
    assert "Trading Engine compatibility revision: $actual_revision" in workflow
    assert '>> "$GITHUB_STEP_SUMMARY"' in workflow

    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Advance the revision deliberately in a dedicated pull request" in contributing
    assert "Moving-head checks may be run as nonrequired canaries" in contributing


def test_ci_concurrency_preserves_tags_and_protected_branches() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "format('pr-{0}', github.event.pull_request.number)" in workflow
    assert "|| github.ref" in workflow
    assert "github.event_name == 'pull_request'" in workflow
    assert "!startsWith(github.ref, 'refs/tags/')" in workflow
    assert "!github.ref_protected" in workflow
    assert "tags and protected branches always finish" in workflow

    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "groups pull-request runs by PR number" in contributing
    assert "Tag and protected-branch runs are never canceled" in contributing


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
