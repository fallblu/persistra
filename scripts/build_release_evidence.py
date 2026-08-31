"""Build a CycloneDX SBOM and digest manifest for release distributions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]


def project_version(path: Path = ROOT / "pyproject.toml") -> str:
    """Return the declared project version."""
    with path.open("rb") as stream:
        document = tomllib.load(stream)
    version = document["project"]["version"]
    if not isinstance(version, str):
        raise TypeError("project version must be a string")
    return version


def distribution_subjects(directory: Path, version: str) -> tuple[Path, Path]:
    """Return exactly one wheel and one source distribution for the version."""
    wheels = tuple(sorted(directory.glob(f"persistra-{version}-*.whl")))
    source_distributions = tuple(sorted(directory.glob(f"persistra-{version}.tar.gz")))
    if len(wheels) != 1 or len(source_distributions) != 1:
        raise ValueError(
            "release evidence requires exactly one current wheel and source distribution"
        )
    return wheels[0], source_distributions[0]


def sha256(path: Path) -> str:
    """Return the streaming SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_dependency_names(path: Path = ROOT / "pyproject.toml") -> frozenset[str]:
    """Return normalized names for direct runtime dependencies."""
    with path.open("rb") as stream:
        document = cast("dict[str, object]", tomllib.load(stream))
    project_value = document.get("project")
    if not isinstance(project_value, dict):
        raise TypeError("project metadata must be a table")
    project = cast("dict[str, object]", project_value)
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list):
        raise TypeError("project dependencies must be strings")
    dependency_values = cast("list[object]", dependencies)
    if not all(isinstance(item, str) for item in dependency_values):
        raise TypeError("project dependencies must be strings")
    names = {
        re.split(r"[<>=!~;\[]", cast("str", item), maxsplit=1)[0]
        .strip()
        .lower()
        .replace("_", "-")
        for item in dependency_values
    }
    return frozenset(names)


def validate_sbom(path: Path, *, version: str, dependencies: frozenset[str]) -> None:
    """Require the selected CycloneDX contract and all direct runtime dependencies."""
    document = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != "1.6":
        raise ValueError("release SBOM must be CycloneDX 1.6 JSON")
    serial_number = document.get("serialNumber")
    if not isinstance(serial_number, str) or not serial_number.startswith("urn:uuid:"):
        raise ValueError("release SBOM must have a build-specific serial number")
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("release SBOM must declare metadata")
    component_value = cast("dict[str, object]", metadata).get("component")
    expected = {"name": "persistra", "type": "library", "version": version}
    if not isinstance(component_value, dict):
        raise ValueError("release SBOM root component differs from the built project")
    component = cast("dict[str, object]", component_value)
    if any(component.get(key) != value for key, value in expected.items()):
        raise ValueError("release SBOM root component differs from the built project")
    raw_components = document.get("components")
    if not isinstance(raw_components, list):
        raise ValueError("release SBOM must list installed components")
    component_names: set[str] = set()
    for item in cast("list[object]", raw_components):
        if not isinstance(item, dict):
            continue
        name = cast("dict[str, object]", item).get("name")
        if isinstance(name, str):
            component_names.add(name.lower().replace("_", "-"))
    missing = sorted(dependencies - component_names)
    if missing:
        raise ValueError(f"release SBOM is missing direct dependencies: {missing}")


def checksum_lines(paths: tuple[Path, ...], *, names: tuple[str, ...]) -> str:
    """Return sorted sha256sum-compatible records."""
    if len(paths) != len(names):
        raise ValueError("checksum paths and names must have equal lengths")
    records = sorted((name, sha256(path)) for path, name in zip(paths, names, strict=True))
    return "".join(f"{digest}  {name}\n" for name, digest in records)


def _run(arguments: list[str]) -> None:
    subprocess.run(arguments, cwd=ROOT, check=True)


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def build_release_evidence(distributions: Path, output: Path) -> dict[str, Any]:
    """Build and validate unsigned evidence before GitHub signs attestations."""
    version = project_version()
    wheel, source_distribution = distribution_subjects(distributions, version)
    output.mkdir(parents=True, exist_ok=True)
    requirements = output / "runtime-requirements.txt"
    sbom = output / "persistra.cdx.json"
    metadata_path = output / "build-metadata.json"
    subjects_path = output / "subjects.sha256"
    checksums_path = output / "SHA256SUMS"

    _run(
        [
            "uv",
            "export",
            "--quiet",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--output-file",
            str(requirements),
        ]
    )
    with tempfile.TemporaryDirectory(prefix="persistra-release-evidence-") as temporary:
        environment = Path(temporary) / "environment"
        python = environment / "bin" / "python"
        _run(["uv", "venv", str(environment), "--python", platform.python_version()])
        _run(["uv", "pip", "install", "--python", str(python), "-r", str(requirements)])
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                str(wheel),
            ]
        )
        _run(
            [
                sys.executable,
                "-m",
                "cyclonedx_py",
                "environment",
                str(python),
                "--pyproject",
                "pyproject.toml",
                "--mc-type",
                "library",
                "--sv",
                "1.6",
                "--of",
                "JSON",
                "--validate",
                "-o",
                str(sbom),
            ]
        )
    validate_sbom(sbom, version=version, dependencies=runtime_dependency_names())

    commit = _git_commit()
    expected_commit = os.environ.get("GITHUB_SHA")
    if expected_commit is not None and expected_commit != commit:
        raise ValueError("checked-out release source differs from the workflow commit")
    subjects = tuple(
        {
            "name": path.name,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in (wheel, source_distribution)
    )
    metadata: dict[str, Any] = {
        "format_version": 1,
        "python_version": platform.python_version(),
        "source_commit": commit,
        "source_ref": os.environ.get("GITHUB_REF"),
        "subjects": subjects,
        "version": version,
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    subjects_path.write_text(
        checksum_lines(
            (wheel, source_distribution),
            names=(wheel.name, source_distribution.name),
        ),
        encoding="utf-8",
    )
    checksums_path.write_text(
        checksum_lines(
            (wheel, source_distribution, sbom, requirements, metadata_path),
            names=(
                f"dist/{wheel.name}",
                f"dist/{source_distribution.name}",
                f"release-evidence/{sbom.name}",
                "release-evidence/runtime-requirements.txt",
                "release-evidence/build-metadata.json",
            ),
        ),
        encoding="utf-8",
    )
    return metadata


def main() -> None:
    """Generate release evidence from already built wheel and source distributions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--output", type=Path, default=ROOT / "release-evidence")
    arguments = parser.parse_args()
    metadata = build_release_evidence(arguments.dist, arguments.output)
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
