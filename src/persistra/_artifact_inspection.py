"""Safe discovery and read-only tabulation of research manifests."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import pandas as pd

from persistra._portable import thaw_portable_mapping
from persistra.errors import DataValidationError
from persistra.research import read_research_manifest, verify_manifest_artifacts

if TYPE_CHECKING:
    from persistra.research import ArtifactVerification, ResearchManifest


@dataclass(frozen=True, slots=True)
class ArtifactTable:
    """One labeled table derived from a verified artifact."""

    name: str
    frame: pd.DataFrame


@dataclass(frozen=True, slots=True)
class DiscoveredResearchArtifact:
    """One fully parsed research manifest with verified declared outputs."""

    path: Path
    manifest: ResearchManifest
    verification: ArtifactVerification
    kind: Literal["research_manifest"] = "research_manifest"


type DiscoveredArtifact = DiscoveredResearchArtifact


def discover_artifacts(
    root: Path, *, recursive: bool
) -> tuple[tuple[DiscoveredArtifact, ...], tuple[str, ...]]:
    """Discover and verify research manifests below ``root``."""
    artifacts: list[DiscoveredArtifact] = []
    warnings: list[str] = []
    for path in _artifact_candidates(root, recursive=recursive):
        try:
            manifest = read_research_manifest(path)
            verification = verify_manifest_artifacts(
                manifest,
                path.parent,
                report_unexpected=False,
            )
            verification.raise_for_errors()
            artifacts.append(DiscoveredResearchArtifact(path, manifest, verification))
        except (DataValidationError, OSError, ValueError) as error:
            warnings.append(f"{path}: {error}")
    return tuple(artifacts), tuple(warnings)


def artifact_overview(artifact: DiscoveredArtifact) -> pd.DataFrame:
    """Return provenance and verification status for one manifest."""
    manifest = artifact.manifest
    return _field_table(
        {
            "kind": "Research manifest",
            "path": artifact.path,
            "verification": "verified",
            "manifest_version": manifest.manifest_version,
            "execution_status": manifest.execution_status,
            "dataset_count": len(manifest.datasets),
            "artifact_count": len(manifest.artifacts),
        }
    )


def artifact_tables(artifact: DiscoveredArtifact) -> tuple[ArtifactTable, ...]:
    """Return bounded-by-renderer structured tables for one verified manifest."""
    manifest = artifact.manifest
    parameters: list[dict[str, object]] = []
    sections: tuple[tuple[str, Mapping[str, object]], ...] = (
        ("features", manifest.feature_parameters),
        ("labels", manifest.label_parameters),
        ("splits", manifest.split_parameters),
        ("benchmarks", manifest.benchmark_parameters),
        ("models", manifest.model_parameters),
        ("random_seeds", manifest.random_seeds),
    )
    for section, values in sections:
        parameters.extend(
            {"section": section, "name": name, "value": _portable_display(value)}
            for name, value in sorted(values.items())
        )
    datasets = [
        {
            "name": dataset.name,
            "schema_version": dataset.schema_version,
            "scope": _portable_display(dataset.scope),
            "content_identity": dataset.content_identity,
            "snapshot_identity": dataset.snapshot_identity,
        }
        for dataset in manifest.datasets
    ]
    checksums = [
        {
            "name": item.name,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
            "verified": item.name in artifact.verification.verified_artifacts,
        }
        for item in manifest.artifacts
    ]
    provenance = [
        {"name": name, "value": value} for name, value in sorted(manifest.environment.items())
    ]
    return (
        ArtifactTable("Parameters", pd.DataFrame(parameters)),
        ArtifactTable("Datasets", pd.DataFrame(datasets)),
        ArtifactTable("Checksums", pd.DataFrame(checksums)),
        ArtifactTable("Provenance", pd.DataFrame(provenance)),
    )


def artifact_inventory(artifact: DiscoveredArtifact) -> dict[str, object]:
    """Return a stable JSON-ready manifest summary."""
    manifest = artifact.manifest
    return {
        "kind": artifact.kind,
        "path": str(artifact.path),
        "verification": "verified",
        "manifest_version": manifest.manifest_version,
        "execution_status": manifest.execution_status,
        "datasets": [dataset.name for dataset in manifest.datasets],
        "parameters": {
            "features": thaw_portable_mapping(manifest.feature_parameters),
            "labels": thaw_portable_mapping(manifest.label_parameters),
            "splits": thaw_portable_mapping(manifest.split_parameters),
            "benchmarks": thaw_portable_mapping(manifest.benchmark_parameters),
            "models": thaw_portable_mapping(manifest.model_parameters),
            "random_seeds": thaw_portable_mapping(manifest.random_seeds),
        },
        "provenance": thaw_portable_mapping(manifest.environment),
        "checksums": {item.name: item.sha256 for item in manifest.artifacts},
    }


def _artifact_candidates(root: Path, *, recursive: bool) -> tuple[Path, ...]:
    if not recursive:
        return tuple(
            sorted(
                path.resolve()
                for path in root.iterdir()
                if _is_research_manifest(path.name) and path.is_file() and not path.is_symlink()
            )
        )
    found: list[Path] = []
    for current, directories, files in os.walk(
        root, followlinks=False, onerror=lambda _error: None
    ):
        parent = Path(current)
        directories[:] = sorted(name for name in directories if not (parent / name).is_symlink())
        for name in sorted(files):
            path = parent / name
            if _is_research_manifest(name) and path.is_file() and not path.is_symlink():
                found.append(path.resolve())
    return tuple(found)


def _is_research_manifest(name: str) -> bool:
    return name == "research-manifest.json" or name.endswith(".research-manifest.json")


def _field_table(values: Mapping[str, object]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "field": tuple(values),
            "value": tuple(_portable_display(value) for value in values.values()),
        }
    )


def _portable_display(value: object) -> object:
    if isinstance(value, os.PathLike):
        return os.fsdecode(cast("os.PathLike[str]", value))
    if isinstance(value, Mapping):
        return repr(dict(cast("Mapping[object, object]", value)))
    if isinstance(value, (tuple, list)):
        return repr(cast("tuple[object, ...] | list[object]", value))
    return value
