"""Safe discovery and read-only tabulation of supported project artifacts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import pandas as pd

from persistra._portable import thaw_portable_mapping
from persistra.errors import DataValidationError
from persistra.integrations.trading_engine import (
    ReplayBundleError,
    verify_replay_bundle,
)
from persistra.research import read_research_manifest, verify_manifest_artifacts

if TYPE_CHECKING:
    from persistra.integrations.trading_engine import ReplayBundleVerification
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


@dataclass(frozen=True, slots=True)
class DiscoveredReplayArtifact:
    """One fully verified Trading Engine replay bundle."""

    path: Path
    verification: ReplayBundleVerification
    kind: Literal["replay_bundle"] = "replay_bundle"


type DiscoveredArtifact = DiscoveredResearchArtifact | DiscoveredReplayArtifact


def discover_artifacts(
    root: Path, *, recursive: bool
) -> tuple[tuple[DiscoveredArtifact, ...], tuple[str, ...]]:
    """Discover and verify only supported artifact manifests below ``root``."""
    artifacts: list[DiscoveredArtifact] = []
    warnings: list[str] = []
    for path in _artifact_candidates(root, recursive=recursive):
        try:
            if _is_research_manifest(path.name):
                manifest = read_research_manifest(path)
                verification = verify_manifest_artifacts(
                    manifest,
                    path.parent,
                    report_unexpected=False,
                )
                verification.raise_for_errors()
                artifacts.append(DiscoveredResearchArtifact(path, manifest, verification))
            else:
                artifacts.append(DiscoveredReplayArtifact(path, verify_replay_bundle(path)))
        except (DataValidationError, ReplayBundleError, OSError, ValueError) as error:
            warnings.append(f"{path}: {error}")
    return tuple(artifacts), tuple(warnings)


def artifact_overview(artifact: DiscoveredArtifact) -> pd.DataFrame:
    """Return provenance, verification, and execution status for one artifact."""
    if isinstance(artifact, DiscoveredResearchArtifact):
        manifest = artifact.manifest
        values: dict[str, object] = {
            "kind": "Research manifest",
            "path": artifact.path,
            "verification": "verified",
            "manifest_version": manifest.manifest_version,
            "execution_status": manifest.execution_status,
            "dataset_count": len(manifest.datasets),
            "artifact_count": len(manifest.artifacts),
        }
    else:
        verification = artifact.verification
        values = {
            "kind": "Trading Engine replay bundle",
            "path": artifact.path,
            "verification": "verified",
            "run_id": verification.run_id,
            "contract_version": verification.contract_version,
            "execution_model": verification.execution_model,
            "engine_version": verification.engine_version,
            "manifest_sha256": verification.manifest_sha256,
            "execution_status": "succeeded",
        }
    return _field_table(values)


def artifact_tables(artifact: DiscoveredArtifact) -> tuple[ArtifactTable, ...]:
    """Return bounded-by-renderer structured tables for one verified artifact."""
    if isinstance(artifact, DiscoveredResearchArtifact):
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

    verification = artifact.verification
    replay = verification.replay
    completion = pd.DataFrame(
        [{key: _portable_display(value) for key, value in asdict(replay.completion).items()}]
    )
    checksums = pd.DataFrame(
        [
            {"name": "manifest", "sha256": verification.manifest_sha256},
            *(
                {"name": name, "sha256": digest}
                for name, digest in sorted(verification.artifact_sha256.items())
            ),
        ]
    )
    capabilities = pd.DataFrame(
        [
            {"name": name, "value": _portable_display(value)}
            for name, value in sorted(verification.capabilities.items())
        ]
    )
    tables = [
        ArtifactTable("Completion", completion),
        ArtifactTable("Checksums", checksums),
        ArtifactTable("Engine capabilities", capabilities),
    ]
    for name in ("orders", "fills", "valuations", "metrics"):
        frame = getattr(replay, name)
        if isinstance(frame, pd.DataFrame):
            tables.append(ArtifactTable(name.replace("_", " ").title(), frame.copy(deep=True)))
    return tuple(tables)


def artifact_inventory(artifact: DiscoveredArtifact) -> dict[str, object]:
    """Return a stable JSON-ready summary without arbitrary artifact contents."""
    if isinstance(artifact, DiscoveredResearchArtifact):
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
    verification = artifact.verification
    return {
        "kind": artifact.kind,
        "path": str(artifact.path),
        "verification": "verified",
        "run_id": verification.run_id,
        "contract_version": verification.contract_version,
        "execution_model": verification.execution_model,
        "engine_version": verification.engine_version,
        "execution_status": "succeeded",
        "provenance": {
            "strategy": (
                None
                if verification.strategy_identity is None
                else {
                    "name": verification.strategy_identity.name,
                    "version": verification.strategy_identity.version,
                }
            ),
            "capabilities": thaw_portable_mapping(verification.capabilities),
        },
        "checksums": {
            "manifest": verification.manifest_sha256,
            **dict(verification.artifact_sha256),
        },
    }


def _artifact_candidates(root: Path, *, recursive: bool) -> tuple[Path, ...]:
    if not recursive:
        return tuple(
            sorted(
                path.resolve()
                for path in root.iterdir()
                if _is_candidate_name(path.name) and path.is_file() and not path.is_symlink()
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
            if _is_candidate_name(name) and path.is_file() and not path.is_symlink():
                found.append(path.resolve())
    return tuple(found)


def _is_candidate_name(name: str) -> bool:
    return _is_research_manifest(name) or name.endswith(".manifest.json")


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
