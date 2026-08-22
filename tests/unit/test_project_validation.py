"""Tests for deterministic read-only project validation."""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

from persistra import _cli
from persistra.project import create_project, validate_project
from persistra.validation import ValidationSeverity

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _codes(root: Path) -> set[str]:
    return {item.code for item in validate_project(root).findings}


def test_valid_project_has_a_versioned_empty_report(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project")

    validation = validate_project(project.root)

    assert validation.is_valid
    assert validation.error_count == 0
    assert validation.warning_count == 0
    assert validation.project_name == "project"
    assert validation.to_dict() == {
        "validation_version": 1,
        "root": str(project.root),
        "project_name": "project",
        "valid": True,
        "error_count": 0,
        "warning_count": 0,
        "findings": [],
    }


def test_optional_layout_and_dependency_findings_are_warnings(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project")
    shutil.rmtree(project.notebook_directory)
    (project.root / ".python-version").unlink()
    (project.root / "pyproject.toml").write_text(
        '[project]\nname = "research"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )

    validation = validate_project(project.root)

    assert validation.is_valid
    assert validation.warning_count == 3
    assert all(item.severity is ValidationSeverity.WARNING for item in validation.findings)
    assert "project.path.missing" in {item.code for item in validation.findings}
    assert "project.pyproject.dependency" in {item.code for item in validation.findings}


def test_manifest_validation_is_strict_and_never_searches_parents(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    (parent / "persistra.toml").write_text(
        'format_version = 1\n[project]\nname = "parent"\n', encoding="utf-8"
    )
    assert "project.path.missing" in _codes(child)

    (child / "persistra.toml").write_text("format_version = [", encoding="utf-8")
    assert "project.manifest.malformed" in _codes(child)

    (child / "persistra.toml").write_text(
        'format_version = 2\n[project]\nname = "child"\n', encoding="utf-8"
    )
    assert "project.manifest.version_unsupported" in _codes(child)

    (child / "persistra.toml").write_text(
        'format_version = 1\nextra = true\n[project]\nname = "child"\n',
        encoding="utf-8",
    )
    assert "project.manifest.schema" in _codes(child)


def test_project_validator_rejects_roots_symlinks_and_wrong_types(tmp_path: Path) -> None:
    assert "project.root.missing" in _codes(tmp_path / "missing")
    root_file = tmp_path / "file"
    root_file.write_text("x", encoding="utf-8")
    assert "project.root.type" in _codes(root_file)

    project = create_project(tmp_path / "project")
    external = tmp_path / "external"
    external.mkdir()
    shutil.rmtree(project.notebook_directory)
    project.notebook_directory.symlink_to(external, target_is_directory=True)
    validation = validate_project(project.root)
    assert "project.path.symlink" in {item.code for item in validation.findings}
    assert "project.path.outside_root" in {item.code for item in validation.findings}

    marker = project.raw_cache_directory / ".gitkeep"
    marker.unlink()
    project.raw_cache_directory.rmdir()
    project.raw_cache_directory.write_text("wrong type", encoding="utf-8")
    assert "project.path.type" in _codes(project.root)


def test_project_validator_reports_missing_damaged_store_and_malformed_pyproject(
    tmp_path: Path,
) -> None:
    missing_store = create_project(tmp_path / "missing-store")
    missing_store.store_path.unlink()
    missing = validate_project(missing_store.root)
    assert not missing.is_valid
    assert "project.path.missing" in {item.code for item in missing.findings}

    damaged_store = create_project(tmp_path / "damaged-store")
    damaged_store.store_path.unlink()
    damaged_store.store_path.write_bytes(b"damaged")
    damaged = validate_project(damaged_store.root)
    assert not damaged.is_valid
    assert "store.open.invalid" in {item.code for item in damaged.findings}

    malformed = create_project(tmp_path / "malformed")
    (malformed.root / "pyproject.toml").write_text("[project", encoding="utf-8")
    assert "project.pyproject.malformed" in _codes(malformed.root)


def test_project_validate_cli_has_human_json_and_exit_status_contracts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = create_project(tmp_path / "project")

    assert _cli.run(["project", "validate", str(project.root)]) == 0
    human = capsys.readouterr().out
    assert f"Persistra project validation: {project.root}" in human
    assert "0 error(s), 0 warning(s)" in human

    assert _cli.run(["project", "validate", str(project.root), "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["validation_version"] == 1
    assert document["valid"] is True

    (project.root / ".python-version").unlink()
    assert _cli.run(["project", "validate", str(project.root), "--json"]) == 0
    first_warning_output = capsys.readouterr().out
    assert json.loads(first_warning_output)["warning_count"] == 1
    assert _cli.run(["project", "validate", str(project.root), "--json"]) == 0
    assert capsys.readouterr().out == first_warning_output

    project.store_path.unlink()
    assert _cli.run(["project", "validate", str(project.root)]) == 1
    assert "error: project.path.missing" in capsys.readouterr().out
