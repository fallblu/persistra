"""Read-only validation of explicit Persistra project directories."""

from __future__ import annotations

import re
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from persistra.data import verify_store
from persistra.validation import ValidationFinding, ValidationSeverity

PROJECT_FORMAT_VERSION = 1
PROJECT_VALIDATION_VERSION = 1

_STANDARD_DIRECTORIES = (
    Path("cache"),
    Path("cache/responses"),
    Path("artifacts"),
    Path("artifacts/research"),
    Path("artifacts/trading-engine"),
    Path("notebooks"),
    Path("tests"),
)
_STANDARD_FILES = (
    Path(".gitignore"),
    Path(".python-version"),
    Path("README.md"),
    Path("main.py"),
    Path("pyproject.toml"),
)
_PERSISTRA_REQUIREMENT = re.compile(
    r"^persistra(?:\s*\[[^]]+\])?(?:\s*(?:[<>=!~@;].*)?)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ProjectValidation:
    """Structured result of one explicit-directory project validation."""

    root: Path
    project_name: str | None
    findings: tuple[ValidationFinding, ...]

    @property
    def error_count(self) -> int:
        """Return the number of error findings."""
        return sum(item.severity is ValidationSeverity.ERROR for item in self.findings)

    @property
    def warning_count(self) -> int:
        """Return the number of warning findings."""
        return sum(item.severity is ValidationSeverity.WARNING for item in self.findings)

    @property
    def is_valid(self) -> bool:
        """Return whether project validation found no errors."""
        return self.error_count == 0

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic versioned JSON representation."""
        return {
            "validation_version": PROJECT_VALIDATION_VERSION,
            "root": str(self.root),
            "project_name": self.project_name,
            "valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "findings": [item.to_dict() for item in self.findings],
        }


def _finding(
    code: str,
    severity: ValidationSeverity,
    message: str,
    location: str | None = None,
) -> ValidationFinding:
    return ValidationFinding(code, severity, message, location)


def _error(code: str, message: str, location: str | None = None) -> ValidationFinding:
    return _finding(code, ValidationSeverity.ERROR, message, location)


def _warning(code: str, message: str, location: str | None = None) -> ValidationFinding:
    return _finding(code, ValidationSeverity.WARNING, message, location)


def validate_project(root: str | Path) -> ProjectValidation:
    """Validate exactly one project directory without searching or changing it."""
    target = Path(root).expanduser().absolute()
    findings: list[ValidationFinding] = []
    try:
        root_status = target.lstat()
    except FileNotFoundError:
        return ProjectValidation(
            target,
            None,
            (_error("project.root.missing", "project directory does not exist"),),
        )
    except OSError as error:
        return ProjectValidation(
            target,
            None,
            (_error("project.root.unreadable", f"project directory cannot be inspected: {error}"),),
        )
    if stat.S_ISLNK(root_status.st_mode):
        return ProjectValidation(
            target,
            None,
            (_error("project.root.symlink", "project directory must not be a symbolic link"),),
        )
    if not stat.S_ISDIR(root_status.st_mode):
        return ProjectValidation(
            target,
            None,
            (_error("project.root.type", "project root is not a directory"),),
        )

    resolved_root = target.resolve()
    manifest = target / "persistra.toml"
    project_name = _validate_manifest(manifest, resolved_root, findings)
    for relative in _STANDARD_DIRECTORIES:
        _validate_resource(
            target / relative,
            relative,
            resolved_root,
            directory=True,
            missing_is_error=False,
            findings=findings,
        )
    regular_files: set[Path] = set()
    for relative in _STANDARD_FILES:
        if _validate_resource(
            target / relative,
            relative,
            resolved_root,
            directory=False,
            missing_is_error=False,
            findings=findings,
        ):
            regular_files.add(relative)

    store_relative = Path("data.duckdb")
    store_path = target / store_relative
    if _validate_resource(
        store_path,
        store_relative,
        resolved_root,
        directory=False,
        missing_is_error=True,
        findings=findings,
    ):
        verification = verify_store(store_path)
        findings.extend(
            ValidationFinding(
                item.code,
                item.severity,
                item.message,
                (
                    str(store_relative)
                    if item.location is None
                    else f"{store_relative}:{item.location}"
                ),
            )
            for item in verification.findings
        )
    if Path("pyproject.toml") in regular_files:
        _validate_pyproject(target / "pyproject.toml", findings)
    return ProjectValidation(
        target,
        project_name,
        tuple(sorted(findings, key=lambda item: (item.code, item.location or "", item.message))),
    )


def _inside_root(path: Path, root: Path) -> bool:
    try:
        return path.resolve(strict=False).is_relative_to(root)
    except OSError:
        return False


def _validate_resource(
    path: Path,
    relative: Path,
    root: Path,
    *,
    directory: bool,
    missing_is_error: bool,
    findings: list[ValidationFinding],
) -> bool:
    location = str(relative)
    if not _inside_root(path, root):
        findings.append(
            _error(
                "project.path.outside_root",
                "standard path resolves outside the project root",
                location,
            )
        )
    try:
        status = path.lstat()
    except FileNotFoundError:
        missing = _error if missing_is_error else _warning
        findings.append(
            missing(
                "project.path.missing",
                "required project resource is missing"
                if missing_is_error
                else "standard project resource is absent",
                location,
            )
        )
        return False
    except OSError as error:
        findings.append(
            _error(
                "project.path.unreadable",
                f"standard path cannot be inspected: {error}",
                location,
            )
        )
        return False
    if stat.S_ISLNK(status.st_mode):
        findings.append(
            _error(
                "project.path.symlink",
                "standard project paths must not be symbolic links",
                location,
            )
        )
        return False
    expected = stat.S_ISDIR(status.st_mode) if directory else stat.S_ISREG(status.st_mode)
    if not expected:
        kind = "directory" if directory else "regular file"
        findings.append(
            _error(
                "project.path.type",
                f"standard project path must be a {kind}",
                location,
            )
        )
        return False
    return _inside_root(path, root)


def _validate_manifest(
    path: Path,
    root: Path,
    findings: list[ValidationFinding],
) -> str | None:
    location = "persistra.toml"
    if not _validate_resource(
        path,
        Path(location),
        root,
        directory=False,
        missing_is_error=True,
        findings=findings,
    ):
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        findings.append(
            _error(
                "project.manifest.unreadable",
                f"project manifest cannot be read: {error}",
                location,
            )
        )
        return None
    try:
        raw = cast("dict[str, object]", tomllib.loads(text))
    except tomllib.TOMLDecodeError as error:
        findings.append(
            _error(
                "project.manifest.malformed",
                f"project manifest is malformed: {error}",
                location,
            )
        )
        return None
    if set(raw) != {"format_version", "project"}:
        findings.append(
            _error(
                "project.manifest.schema",
                "manifest must contain exactly format_version and the project table",
                location,
            )
        )
        return None
    format_version = raw["format_version"]
    if isinstance(format_version, bool) or not isinstance(format_version, int):
        findings.append(
            _error(
                "project.manifest.schema",
                "manifest format_version must be an integer",
                location,
            )
        )
        return None
    if format_version != PROJECT_FORMAT_VERSION:
        findings.append(
            _error(
                "project.manifest.version_unsupported",
                f"project format version is not supported: {format_version}",
                location,
            )
        )
        return None
    project = raw["project"]
    if not isinstance(project, dict):
        findings.append(
            _error(
                "project.manifest.schema",
                "manifest project table must contain exactly name",
                location,
            )
        )
        return None
    project_table = cast("dict[str, object]", project)
    if set(project_table) != {"name"}:
        findings.append(
            _error(
                "project.manifest.schema",
                "manifest project table must contain exactly name",
                location,
            )
        )
        return None
    name = project_table["name"]
    if not isinstance(name, str) or not name.strip():
        findings.append(
            _error(
                "project.manifest.schema",
                "manifest project name must be a nonempty string",
                location,
            )
        )
        return None
    return name


def _validate_pyproject(path: Path, findings: list[ValidationFinding]) -> None:
    location = "pyproject.toml"
    try:
        document = cast("dict[str, object]", tomllib.loads(path.read_text(encoding="utf-8")))
    except tomllib.TOMLDecodeError as error:
        findings.append(
            _error(
                "project.pyproject.malformed",
                f"pyproject.toml is malformed: {error}",
                location,
            )
        )
        return
    except (OSError, UnicodeError) as error:
        findings.append(
            _error(
                "project.pyproject.unreadable",
                f"pyproject.toml cannot be read: {error}",
                location,
            )
        )
        return
    raw_project = document.get("project")
    dependencies: object = None
    if isinstance(raw_project, dict):
        dependencies = cast("dict[str, object]", raw_project).get("dependencies")
    if not isinstance(dependencies, list):
        findings.append(
            _warning(
                "project.pyproject.dependency",
                "pyproject.toml does not declare a valid project dependency list",
                location,
            )
        )
        return
    dependency_items = cast("list[object]", dependencies)
    if not all(isinstance(item, str) for item in dependency_items):
        findings.append(
            _warning(
                "project.pyproject.dependency",
                "pyproject.toml does not declare a valid project dependency list",
                location,
            )
        )
        return
    requirements = cast("list[str]", dependency_items)
    if not any(_PERSISTRA_REQUIREMENT.fullmatch(item.strip()) for item in requirements):
        findings.append(
            _warning(
                "project.pyproject.dependency",
                "pyproject.toml does not declare Persistra as a project dependency",
                location,
            )
        )
