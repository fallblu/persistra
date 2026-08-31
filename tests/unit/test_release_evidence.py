"""Tests for release SBOM and digest evidence."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest

from scripts.build_release_evidence import (
    checksum_lines,
    distribution_subjects,
    runtime_dependency_names,
    validate_sbom,
)

if TYPE_CHECKING:
    from pathlib import Path


def _sbom(version: str = "4.2.0") -> dict[str, object]:
    dependencies = sorted(runtime_dependency_names())
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000000",
        "metadata": {
            "component": {"name": "persistra", "type": "library", "version": version}
        },
        "components": [{"name": name, "type": "library"} for name in dependencies],
    }


def test_distribution_subjects_require_one_current_wheel_and_sdist(tmp_path: Path) -> None:
    wheel = tmp_path / "persistra-4.2.0-py3-none-any.whl"
    source = tmp_path / "persistra-4.2.0.tar.gz"
    wheel.write_bytes(b"wheel")
    source.write_bytes(b"source")

    assert distribution_subjects(tmp_path, "4.2.0") == (wheel, source)

    (tmp_path / "persistra-4.2.0-extra.whl").write_bytes(b"extra")
    with pytest.raises(ValueError, match="exactly one"):
        distribution_subjects(tmp_path, "4.2.0")


def test_release_sbom_requires_standard_identity_and_direct_dependencies(tmp_path: Path) -> None:
    path = tmp_path / "persistra.cdx.json"
    document = _sbom()
    path.write_text(json.dumps(document), encoding="utf-8")

    validate_sbom(path, version="4.2.0", dependencies=runtime_dependency_names())

    document["components"] = []
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="missing direct dependencies"):
        validate_sbom(path, version="4.2.0", dependencies=runtime_dependency_names())


def test_checksum_records_are_sorted_and_sha256sum_compatible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    observed = checksum_lines((first, second), names=("z", "a"))

    assert observed == (
        f"{hashlib.sha256(b'second').hexdigest()}  a\n"
        f"{hashlib.sha256(b'first').hexdigest()}  z\n"
    )
