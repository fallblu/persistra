"""Filesystem verification for research-manifest artifacts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from persistra.errors import DataValidationError

if TYPE_CHECKING:
    from persistra.research.model import ResearchManifest


@dataclass(frozen=True, slots=True)
class ArtifactVerificationFinding:
    """One structured artifact-integrity finding."""

    code: str
    artifact_name: str
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    """Inspection-friendly result of verifying every declared artifact."""

    root: Path
    verified_artifacts: tuple[str, ...]
    findings: tuple[ArtifactVerificationFinding, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether all declared artifacts match and no extras exist."""
        return not self.findings

    def raise_for_errors(self) -> None:
        """Raise one normalized error when verification found any problem."""
        if self.findings:
            codes = ", ".join(finding.code for finding in self.findings)
            raise DataValidationError(f"research artifact verification failed: {codes}")


def verify_manifest_artifacts(
    manifest: ResearchManifest,
    root: str | Path,
    *,
    report_unexpected: bool = True,
) -> ArtifactVerification:
    """Verify declared files under an explicit trusted directory without following symlinks."""
    supplied_root = Path(root)
    if supplied_root.is_symlink():
        raise DataValidationError(f"artifact root must not be a symlink: {supplied_root}")
    try:
        trusted_root = supplied_root.resolve(strict=True)
    except OSError as error:
        raise DataValidationError(f"artifact root is unavailable: {supplied_root}") from error
    if not trusted_root.is_dir():
        raise DataValidationError(f"artifact root is not a directory: {trusted_root}")

    findings: list[ArtifactVerificationFinding] = []
    verified: list[str] = []
    declared_paths: set[Path] = set()
    for artifact in manifest.artifacts:
        relative = Path(artifact.name)
        target = trusted_root / relative
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            findings.append(_finding("artifact.unsafe", artifact.name, target, "unsafe path"))
            continue
        declared_paths.add(target)
        if _contains_symlink(trusted_root, relative):
            findings.append(_finding("artifact.unsafe", artifact.name, target, "symlink path"))
            continue
        if not target.exists():
            findings.append(_finding("artifact.missing", artifact.name, target, "file is missing"))
            continue
        if not target.is_file():
            findings.append(
                _finding("artifact.unsafe", artifact.name, target, "not a regular file")
            )
            continue
        digest, size = _file_identity(target)
        if size != artifact.size_bytes:
            findings.append(
                _finding(
                    "artifact.size_mismatch",
                    artifact.name,
                    target,
                    f"expected {artifact.size_bytes} bytes, found {size}",
                )
            )
            continue
        if digest != artifact.sha256:
            findings.append(
                _finding(
                    "artifact.hash_mismatch",
                    artifact.name,
                    target,
                    f"expected SHA-256 {artifact.sha256}, found {digest}",
                )
            )
            continue
        verified.append(artifact.name)

    if report_unexpected:
        findings.extend(_unexpected_findings(trusted_root, declared_paths))
    return ArtifactVerification(trusted_root, tuple(verified), tuple(findings))


def _contains_symlink(root: Path, relative: Path) -> bool:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
        if not current.exists():
            return False
    return False


def _file_identity(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _unexpected_findings(
    root: Path, declared_paths: set[Path]
) -> list[ArtifactVerificationFinding]:
    findings: list[ArtifactVerificationFinding] = []
    for directory, names, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in sorted(names):
            candidate = parent / name
            if candidate.is_symlink():
                relative = candidate.relative_to(root).as_posix()
                findings.append(_finding("artifact.unsafe", relative, candidate, "symlink path"))
        for name in sorted(files):
            candidate = parent / name
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                if candidate not in declared_paths:
                    findings.append(
                        _finding("artifact.unsafe", relative, candidate, "symlink path")
                    )
            elif candidate not in declared_paths:
                findings.append(
                    _finding("artifact.unexpected", relative, candidate, "file is not declared")
                )
    return findings


def _finding(code: str, name: str, path: Path, message: str) -> ArtifactVerificationFinding:
    return ArtifactVerificationFinding(code, name, path, message)
