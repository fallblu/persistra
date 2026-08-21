"""Tests for the standardized Persistra project layout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import persistra.project as project_module
from persistra.data import DuckDBStore
from persistra.errors import ProjectError
from persistra.project import PersistraProject, create_project

EXPECTED_PATHS = {
    ".gitignore",
    ".python-version",
    "README.md",
    "artifacts",
    "artifacts/research",
    "artifacts/research/.gitkeep",
    "artifacts/trading-engine",
    "artifacts/trading-engine/.gitkeep",
    "cache",
    "cache/responses",
    "cache/responses/.gitkeep",
    "data.duckdb",
    "main.py",
    "notebooks",
    "notebooks/.gitkeep",
    "persistra.toml",
    "pyproject.toml",
    "tests",
    "tests/test_project.py",
}


def _relative_paths(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*")}


def _set_installed_distribution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    installed_version: str = "4.1.2",
    direct_url: str | None = None,
) -> None:
    class InstalledDistribution:
        version = installed_version

        def read_text(self, filename: str) -> str | None:
            assert filename == "direct_url.json"
            return direct_url

    def installed_distribution(_distribution: str) -> InstalledDistribution:
        return InstalledDistribution()

    monkeypatch.setattr(project_module, "distribution", installed_distribution)


def test_create_project_uses_default_normalized_name_and_exact_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_installed_distribution(monkeypatch)
    target = tmp_path / "Example_Project"
    project = create_project(target)
    assert project == PersistraProject(target.resolve(), "example-project")
    assert _relative_paths(target) == EXPECTED_PATHS
    assert (target / "persistra.toml").read_text(encoding="utf-8") == (
        'format_version = 1\n\n[project]\nname = "example-project"\n'
    )
    assert (target / ".python-version").read_text(encoding="utf-8") == "3.12\n"
    generated_pyproject = (target / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "example-project"' in generated_pyproject
    assert '"persistra[inspect]>=4.1.2,<5"' in generated_pyproject
    assert "[build-system]" not in generated_pyproject
    assert "package = false" in generated_pyproject
    assert "[tool.uv.sources]" not in generated_pyproject
    assert not (target / "uv.lock").exists()
    assert not (target / ".venv").exists()
    with DuckDBStore.open(project.store_path, read_only=True) as store:
        assert store.list_datasets() == ()


def test_create_project_accepts_an_existing_empty_target_and_explicit_name(
    tmp_path: Path,
) -> None:
    target = tmp_path / "directory-name"
    target.mkdir()
    project = create_project(target, name="  Research.Tools_2026  ")
    assert project.root == target.resolve()
    assert project.name == "research-tools-2026"
    assert target.is_dir()


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "must not be empty"),
        ("   ", "must not be empty"),
        ("has spaces", "must start and end"),
        ("-leading", "must start and end"),
        ("trailing_", "must start and end"),
        ("naïve", "must start and end"),
    ],
)
def test_create_project_rejects_invalid_names(
    tmp_path: Path, name: str, message: str
) -> None:
    target = tmp_path / "target"
    with pytest.raises(ProjectError, match=message):
        create_project(target, name=name)
    assert not target.exists()


def test_project_open_returns_absolute_fixed_paths_even_when_runtime_paths_are_absent(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    project = create_project(target)
    project.store_path.unlink()
    (project.raw_cache_directory / ".gitkeep").unlink()
    project.raw_cache_directory.rmdir()
    opened = PersistraProject.open(target / ".." / "project")
    assert opened.root == target.resolve()
    assert opened.store_path == opened.root / "data.duckdb"
    assert opened.raw_cache_directory == opened.root / "cache/responses"
    assert opened.research_artifact_directory == opened.root / "artifacts/research"
    assert opened.trading_engine_artifact_directory == (
        opened.root / "artifacts/trading-engine"
    )
    assert opened.notebook_directory == opened.root / "notebooks"
    assert all(
        path.is_relative_to(opened.root)
        for path in (
            opened.store_path,
            opened.raw_cache_directory,
            opened.research_artifact_directory,
            opened.trading_engine_artifact_directory,
            opened.notebook_directory,
        )
    )


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ("", "exactly format_version"),
        ('format_version = 1\n[project]\nname = "x"\nextra = 2\n', "exactly name"),
        ('format_version = 1\nextra = 2\n[project]\nname = "x"\n', "exactly"),
        ('format_version = true\n[project]\nname = "x"\n', "integer 1"),
        ('format_version = "1"\n[project]\nname = "x"\n', "integer 1"),
        ('format_version = 2\n[project]\nname = "x"\n', "not supported"),
        ('format_version = 1\n[project]\nname = ""\n', "nonempty string"),
        ('format_version = 1\n[project]\nname = 3\n', "nonempty string"),
        ('format_version = 1\nproject = "x"\n', "must be a table"),
        ('format_version = [\n', "malformed"),
    ],
)
def test_project_manifest_parsing_is_strict(
    tmp_path: Path, manifest: str, message: str
) -> None:
    (tmp_path / "persistra.toml").write_text(manifest, encoding="utf-8")
    with pytest.raises(ProjectError, match=message):
        PersistraProject.open(tmp_path)


def test_project_open_requires_manifest_directly_in_explicit_root(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    (parent / "persistra.toml").write_text(
        'format_version = 1\n[project]\nname = "parent"\n', encoding="utf-8"
    )
    with pytest.raises(ProjectError, match="does not exist"):
        PersistraProject.open(child)


def test_create_project_rejects_target_and_parent_edge_cases(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="parent does not exist"):
        create_project(tmp_path / "missing" / "project")

    parent_file = tmp_path / "parent-file"
    parent_file.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectError, match="parent is not a directory"):
        create_project(parent_file / "project")

    target_file = tmp_path / "target-file"
    target_file.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectError, match="target is not a directory"):
        create_project(target_file)

    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "nested").mkdir()
    with pytest.raises(ProjectError, match="target is not empty"):
        create_project(nonempty)

    link = tmp_path / "link"
    link.symlink_to(nonempty, target_is_directory=True)
    with pytest.raises(ProjectError, match="symbolic link"):
        create_project(link)

    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "absent", target_is_directory=True)
    with pytest.raises(ProjectError, match="symbolic link"):
        create_project(dangling)


def test_preflight_rejects_every_generated_path_collision(tmp_path: Path) -> None:
    target = tmp_path / "target"
    relatives = (
        *project_module._DIRECTORIES,  # pyright: ignore[reportPrivateUsage]
        *project_module._project_files(  # pyright: ignore[reportPrivateUsage]
            "project", project_module._installed_dependency()  # pyright: ignore[reportPrivateUsage]
        ),
        *project_module._MARKERS,  # pyright: ignore[reportPrivateUsage]
        Path("data.duckdb"),
    )
    for relative in relatives:
        target.mkdir()
        collision = target / relative
        collision.parent.mkdir(parents=True, exist_ok=True)
        if relative in project_module._DIRECTORIES:  # pyright: ignore[reportPrivateUsage]
            collision.mkdir(exist_ok=True)
        else:
            collision.touch()
        with pytest.raises(ProjectError, match="already exists"):
            project_module._preflight_generated_paths(  # pyright: ignore[reportPrivateUsage]
                target, relatives
            )
        for path in sorted(target.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        target.rmdir()


@pytest.mark.parametrize("installed", ["unknown", "4.1.0+local", "4", "v4.1.0"])
def test_invalid_installed_versions_fail_before_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, installed: str
) -> None:
    _set_installed_distribution(monkeypatch, installed_version=installed)
    target = tmp_path / "project"
    with pytest.raises(ProjectError, match="cannot produce"):
        create_project(target)
    assert not target.exists()


@pytest.mark.parametrize(
    ("installed", "expected"),
    [
        ("4.1", "persistra[inspect]>=4.1,<5"),
        ("4.1.0rc1", "persistra[inspect]>=4.1.0rc1,<5"),
        ("1!4.1.0", "persistra[inspect]>=1!4.1.0,<1!5"),
    ],
)
def test_dependency_range_uses_complete_version_and_next_major(
    installed: str,
    expected: str,
) -> None:
    assert (
        project_module._dependency_range(installed)  # pyright: ignore[reportPrivateUsage]
        == expected
    )


@pytest.mark.parametrize("editable", [False, True])
def test_create_project_maps_a_local_installed_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    editable: bool,
) -> None:
    source = tmp_path / "Persistra source"
    source.mkdir()
    direct_url = json.dumps(
        {
            "url": source.as_uri(),
            "dir_info": {"editable": True} if editable else {},
        }
    )
    _set_installed_distribution(monkeypatch, direct_url=direct_url)

    create_project(tmp_path / "project")

    generated = (tmp_path / "project/pyproject.toml").read_text(encoding="utf-8")
    editable_setting = ", editable = true" if editable else ""
    assert "[tool.uv.sources]" in generated
    assert (
        f'persistra = {{ path = "{source.resolve()}"{editable_setting} }}' in generated
    )


@pytest.mark.parametrize(
    "direct_url",
    [
        None,
        "not JSON",
        "[]",
        '{"url": "file:///tmp/persistra"}',
        '{"url": "https://example.com/persistra.git", "dir_info": {}}',
        '{"url": "file:relative/persistra", "dir_info": {}}',
    ],
)
def test_create_project_omits_sources_without_a_local_directory_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    direct_url: str | None,
) -> None:
    _set_installed_distribution(monkeypatch, direct_url=direct_url)

    create_project(tmp_path / "project")

    generated = (tmp_path / "project/pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.uv.sources]" not in generated


@pytest.mark.parametrize("existing_target", [False, True])
@pytest.mark.parametrize("failure_call", range(1, 12))
def test_write_failure_rolls_back_only_current_invocation_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    existing_target: bool,
    failure_call: int,
) -> None:
    target = tmp_path / "project"
    if existing_target:
        target.mkdir()
    original = project_module._write_exclusive  # pyright: ignore[reportPrivateUsage]
    calls = 0

    def fail_on_third(path: Path, content: str, created: list[Path]) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("injected write failure")
        original(path, content, created)

    monkeypatch.setattr(project_module, "_write_exclusive", fail_on_third)
    with pytest.raises(ProjectError, match="injected write failure"):
        create_project(target)
    assert target.exists() is existing_target
    if existing_target:
        assert list(target.iterdir()) == []


@pytest.mark.parametrize(
    "relative",
    project_module._DIRECTORIES,  # pyright: ignore[reportPrivateUsage]
)
def test_directory_failure_rolls_back_created_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative: Path,
) -> None:
    target = tmp_path / "project"
    target.mkdir()
    original = Path.mkdir

    def mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path == target / relative:
            raise OSError("injected directory failure")
        original(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(ProjectError, match="injected directory failure"):
        create_project(target)
    assert list(target.iterdir()) == []


def test_exclusive_write_preserves_a_racing_collision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "project"
    target.mkdir()
    original = project_module._preflight_generated_paths  # pyright: ignore[reportPrivateUsage]

    def collide(root: Path, relatives: tuple[Path, ...]) -> None:
        original(root, relatives)
        (root / ".gitignore").write_text("external", encoding="utf-8")

    monkeypatch.setattr(project_module, "_preflight_generated_paths", collide)
    with pytest.raises(ProjectError, match="already exists"):
        create_project(target)
    assert (target / ".gitignore").read_text(encoding="utf-8") == "external"
    assert set(target.iterdir()) == {target / ".gitignore"}


def test_partial_store_failure_is_rolled_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "project"

    def fail_store(path: Path) -> None:
        path.touch()
        raise OSError("injected store failure")

    monkeypatch.setattr(project_module.DuckDBStore, "create", fail_store)
    with pytest.raises(ProjectError, match="injected store failure"):
        create_project(target)
    assert not target.exists()


def test_generated_text_is_deterministic_and_ignore_policy_is_explicit(tmp_path: Path) -> None:
    first = create_project(tmp_path / "first", name="same_name")
    second = create_project(tmp_path / "second", name="same-name")
    text_paths = sorted(path for path in EXPECTED_PATHS if "." in Path(path).name)
    for relative in text_paths:
        if relative == "data.duckdb":
            continue
        assert (first.root / relative).read_bytes() == (second.root / relative).read_bytes()
    ignored = (first.root / ".gitignore").read_text(encoding="utf-8")
    assert "uv.lock" not in ignored
    assert "*.duckdb" in ignored
    assert "!cache/responses/.gitkeep" in ignored
    assert "!artifacts/research/.gitkeep" in ignored


def test_generated_application_and_test_run_from_another_directory(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    environment = os.environ.copy()
    result = subprocess.run(
        [sys.executable, str(project.root / "main.py")],
        cwd=elsewhere,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Project: project" in result.stdout
    assert str(project.store_path) in result.stdout
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(project.root / "tests/test_project.py")],
        cwd=elsewhere,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert test_result.returncode == 0, test_result.stdout + test_result.stderr
    assert "1 passed" in test_result.stdout
