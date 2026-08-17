"""Standard Persistra project layout and safe initialization."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path
from typing import Self, cast
from urllib.parse import urlsplit
from urllib.request import url2pathname

from persistra.data import DuckDBStore
from persistra.errors import ProjectError

__all__ = ["PersistraProject", "create_project"]

PROJECT_FORMAT_VERSION = 1

_PROJECT_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_VERSION = re.compile(
    r"(?:(?P<epoch>[0-9]+)!)?"
    r"(?P<major>0|[1-9][0-9]*)"
    r"(?:\.(?:0|[1-9][0-9]*))+"
    r"(?:(?:a|b|rc)[0-9]+)?"
    r"(?:\.post[0-9]+)?"
    r"(?:\.dev[0-9]+)?"
)

_DIRECTORIES = (
    Path("cache"),
    Path("cache/responses"),
    Path("artifacts"),
    Path("artifacts/research"),
    Path("artifacts/trading-engine"),
    Path("notebooks"),
    Path("tests"),
)

_MARKERS = (
    Path("cache/responses/.gitkeep"),
    Path("artifacts/research/.gitkeep"),
    Path("artifacts/trading-engine/.gitkeep"),
    Path("notebooks/.gitkeep"),
)


@dataclass(frozen=True, slots=True)
class _ProjectDependency:
    requirement: str
    source: Path | None
    editable: bool


@dataclass(frozen=True, slots=True)
class PersistraProject:
    """A validated version-1 project rooted at an explicit directory."""

    root: Path
    name: str

    @classmethod
    def open(cls, root: str | Path) -> Self:
        """Open and strictly validate a project manifest without creating paths."""
        normalized_root = Path(root).expanduser().resolve()
        manifest_path = normalized_root / "persistra.toml"
        try:
            text = manifest_path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise ProjectError(f"project manifest does not exist: {manifest_path}") from error
        except (OSError, UnicodeError) as error:
            raise ProjectError(
                f"could not read project manifest {manifest_path}: {error}"
            ) from error
        name = _parse_manifest(text, source=manifest_path)
        return cls(normalized_root, name)

    @property
    def store_path(self) -> Path:
        """Return the fixed primary normalized-store path."""
        return self.root / "data.duckdb"

    @property
    def raw_cache_directory(self) -> Path:
        """Return the fixed raw provider-response cache directory."""
        return self.root / "cache" / "responses"

    @property
    def research_artifact_directory(self) -> Path:
        """Return the fixed research artifact directory."""
        return self.root / "artifacts" / "research"

    @property
    def trading_engine_artifact_directory(self) -> Path:
        """Return the fixed Trading Engine replay artifact directory."""
        return self.root / "artifacts" / "trading-engine"

    @property
    def notebook_directory(self) -> Path:
        """Return the fixed caller-owned notebook directory."""
        return self.root / "notebooks"


def create_project(
    root: str | Path,
    *,
    name: str | None = None,
) -> PersistraProject:
    """Create one complete standard project or restore the preexisting target state."""
    target = Path(root).expanduser().absolute()
    project_name = _normalize_name(target.name if name is None else name)
    dependency = _installed_dependency()
    target_existed = _preflight_target(target)
    text_files = _project_files(project_name, dependency)
    generated_paths = (*_DIRECTORIES, *text_files, *_MARKERS, Path("data.duckdb"))
    _preflight_generated_paths(target, generated_paths)

    created: list[Path] = []
    try:
        if not target_existed:
            target.mkdir()
            created.append(target)
        for relative in _DIRECTORIES:
            path = target / relative
            path.mkdir()
            created.append(path)
        for relative, content in text_files.items():
            _write_exclusive(target / relative, content, created)
        for relative in _MARKERS:
            _write_exclusive(target / relative, "", created)
        store_path = target / "data.duckdb"
        try:
            store = DuckDBStore.create(store_path)
        except Exception:
            if store_path.exists() or store_path.is_symlink():
                created.append(store_path)
            raise
        with store:
            created.append(store_path)
    except Exception as error:
        rollback_errors = _rollback(created)
        detail = f"; rollback also failed: {'; '.join(rollback_errors)}" if rollback_errors else ""
        if isinstance(error, ProjectError):
            raise ProjectError(f"{error}{detail}") from error
        raise ProjectError(f"could not create project at {target}: {error}{detail}") from error
    return PersistraProject.open(target)


def _preflight_target(target: Path) -> bool:
    parent = target.parent
    if not parent.exists():
        raise ProjectError(f"project parent does not exist: {parent}")
    if not parent.is_dir():
        raise ProjectError(f"project parent is not a directory: {parent}")
    if target.is_symlink():
        raise ProjectError(f"project target must not be a symbolic link: {target}")
    if not target.exists():
        return False
    if not target.is_dir():
        raise ProjectError(f"project target is not a directory: {target}")
    try:
        first_entry = next(target.iterdir(), None)
    except OSError as error:
        raise ProjectError(f"could not inspect project target {target}: {error}") from error
    if first_entry is not None:
        raise ProjectError(f"project target is not empty: {target}")
    return True


def _preflight_generated_paths(target: Path, relatives: tuple[Path, ...]) -> None:
    if len(set(relatives)) != len(relatives):
        raise ProjectError("generated project layout contains duplicate paths")
    normalized_root = target.resolve(strict=False)
    for relative in relatives:
        if relative.is_absolute() or ".." in relative.parts:
            raise ProjectError(f"generated path is not relative to the project: {relative}")
        path = target / relative
        if not path.resolve(strict=False).is_relative_to(normalized_root):
            raise ProjectError(f"generated path leaves the project root: {relative}")
        if path.exists() or path.is_symlink():
            raise ProjectError(f"generated path already exists: {path}")


def _write_exclusive(path: Path, content: str, created: list[Path]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            created.append(path)
            stream.write(content)
    except FileExistsError as error:
        raise ProjectError(f"generated path already exists: {path}") from error


def _rollback(created: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in reversed(created):
        try:
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink(missing_ok=True)
        except OSError as error:
            failures.append(f"{path}: {error}")
    return failures


def _normalize_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ProjectError("project name must not be empty")
    if _PROJECT_NAME.fullmatch(stripped) is None:
        raise ProjectError(
            "project name must start and end with a letter or digit and contain only "
            "letters, digits, periods, underscores, or hyphens"
        )
    normalized = re.sub(r"[-_.]+", "-", stripped).lower()
    if not normalized or not normalized[0].isalnum() or not normalized[-1].isalnum():
        raise ProjectError("project name cannot produce a usable normalized distribution name")
    return normalized


def _installed_dependency() -> _ProjectDependency:
    try:
        installed = distribution("persistra")
    except PackageNotFoundError as error:
        raise ProjectError("installed Persistra version is not available") from error
    source, editable = _installed_local_source(installed)
    return _ProjectDependency(_dependency_range(installed.version), source, editable)


def _dependency_range(installed_version: str) -> str:
    match = _VERSION.fullmatch(installed_version)
    if match is None:
        raise ProjectError(
            f"installed Persistra version cannot produce a dependency range: {installed_version}"
        )
    next_major = int(match.group("major")) + 1
    epoch = f"{match.group('epoch')}!" if match.group("epoch") is not None else ""
    return f"persistra[inspect]>={installed_version},<{epoch}{next_major}"


def _installed_local_source(installed: Distribution) -> tuple[Path | None, bool]:
    direct_url = installed.read_text("direct_url.json")
    if direct_url is None:
        return None, False
    try:
        raw_document: object = json.loads(direct_url)
    except json.JSONDecodeError:
        return None, False
    if not isinstance(raw_document, dict):
        return None, False
    document = cast("dict[str, object]", raw_document)
    url = document.get("url")
    raw_directory = document.get("dir_info")
    if not isinstance(url, str) or not isinstance(raw_directory, dict):
        return None, False
    parsed = urlsplit(url)
    if (
        parsed.scheme != "file"
        or parsed.netloc not in {"", "localhost"}
        or parsed.query
        or parsed.fragment
    ):
        return None, False
    source = Path(url2pathname(parsed.path))
    if not source.is_absolute():
        return None, False
    directory = cast("dict[str, object]", raw_directory)
    return source.resolve(), directory.get("editable") is True


def _parse_manifest(text: str, *, source: Path) -> str:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ProjectError(f"project manifest is malformed at {source}: {error}") from error
    if set(raw) != {"format_version", "project"}:
        raise ProjectError(
            "project manifest must contain exactly format_version and the [project] table"
        )
    format_version = raw["format_version"]
    if isinstance(format_version, bool) or not isinstance(format_version, int):
        raise ProjectError("project format_version must be the integer 1")
    if format_version != PROJECT_FORMAT_VERSION:
        raise ProjectError(f"project format_version is not supported: {format_version}")
    project = raw["project"]
    if not isinstance(project, dict):
        raise ProjectError("project manifest [project] must be a table")
    project_table = cast("dict[str, object]", project)
    if set(project_table) != {"name"}:
        raise ProjectError("project manifest [project] must contain exactly name")
    name = project_table["name"]
    if not isinstance(name, str) or not name.strip():
        raise ProjectError("project manifest name must be a nonempty string")
    return name


def _project_files(name: str, dependency: _ProjectDependency) -> dict[Path, str]:
    return {
        Path(".gitignore"): _gitignore(),
        Path(".python-version"): "3.12\n",
        Path("README.md"): _readme(name),
        Path("persistra.toml"): _manifest(name),
        Path("pyproject.toml"): _pyproject(name, dependency),
        Path("main.py"): _main_script(),
        Path("tests/test_project.py"): _test_script(name),
    }


def _manifest(name: str) -> str:
    return f'format_version = 1\n\n[project]\nname = "{name}"\n'


def _pyproject(name: str, dependency: _ProjectDependency) -> str:
    source_table = _source_table(dependency)
    return f'''[project]
name = "{name}"
version = "0.1.0"
description = "Persistra research project"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "{dependency.requirement}",
]

[dependency-groups]
dev = [
    "pytest>=9,<10",
]

[tool.uv]
package = false
{source_table}
[tool.pytest.ini_options]
testpaths = ["tests"]
'''


def _source_table(dependency: _ProjectDependency) -> str:
    if dependency.source is None:
        return ""
    path = json.dumps(str(dependency.source))
    editable = ", editable = true" if dependency.editable else ""
    return f'''\

[tool.uv.sources]
persistra = {{ path = {path}{editable} }}
'''


def _main_script() -> str:
    return '''from pathlib import Path

from persistra.data import DuckDBStore
from persistra.project import PersistraProject


def main() -> None:
    root = Path(__file__).resolve().parent
    project = PersistraProject.open(root)
    with DuckDBStore.open(project.store_path, read_only=True):
        print(f"Project: {project.name}")
        print(f"Store: {project.store_path}")
        print("Next: add explicit acquisition and research steps to this script.")


if __name__ == "__main__":
    main()
'''


def _test_script(name: str) -> str:
    return f'''from pathlib import Path

from persistra.data import DuckDBStore
from persistra.project import PersistraProject


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_generated_project_opens() -> None:
    project = PersistraProject.open(PROJECT_ROOT)
    assert project.name == "{name}"
    with DuckDBStore.open(project.store_path, read_only=True) as store:
        assert store.path == project.store_path
'''


def _readme(name: str) -> str:
    return f'''# {name}

This non-packaged uv application is a Persistra research project.

## Start

```console
uv sync
uv run python main.py
uv run persistra inspect .
uv run pytest
```

`data.duckdb` stores normalized Persistra results. Pass `cache/responses` explicitly to provider
clients for raw response caching. Put research outputs in `artifacts/research` and Trading Engine
replay bundles in `artifacts/trading-engine`. Keep notebooks in `notebooks` and tests in `tests`.

`persistra.toml` identifies this project and its fixed layout. It does not replace research
manifests or Trading Engine manifests, which continue to record their own inputs and outputs.

Generated data, raw responses, and artifacts are ignored by default. You own their retention,
backup, access-control, and deletion policies. Commit selected reproducibility manifests
deliberately when they do not contain secrets or sensitive data. Never commit `.env` files,
credentials, or local secret keys.
'''


def _gitignore() -> str:
    return '''.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.pyright/
.mypy_cache/

.env
.env.*
*.key
*.pem

cache/responses/*
!cache/responses/.gitkeep

*.duckdb
*.duckdb.wal
*.duckdb.tmp
*.duckdb-journal

artifacts/research/*
!artifacts/research/.gitkeep
artifacts/trading-engine/*
!artifacts/trading-engine/.gitkeep

.ipynb_checkpoints/
'''
