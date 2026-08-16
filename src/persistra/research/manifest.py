"""Portable research manifests without a managed experiment database."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from persistra.research.model import ArtifactIdentity, DatasetScope, ResearchManifest

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

DIRECT_DISTRIBUTIONS = (
    "persistra",
    "duckdb",
    "matplotlib",
    "numpy",
    "pandas",
    "platformdirs",
    "requests",
    "scipy",
)


def environment_versions(
    distributions: Sequence[str] = DIRECT_DISTRIBUTIONS,
) -> dict[str, str]:
    """Return installed versions for the library and named direct dependencies."""
    versions: dict[str, str] = {}
    for distribution in distributions:
        if not distribution:
            raise ValueError("distribution names must not be empty")
        try:
            versions[distribution] = version(distribution)
        except PackageNotFoundError as error:
            raise ValueError(f"distribution is not installed: {distribution}") from error
    return versions


def identify_artifact(path: str | Path, *, name: str | None = None) -> ArtifactIdentity:
    """Calculate the SHA-256 identity and byte size of one output artifact."""
    artifact_path = Path(path)
    digest = hashlib.sha256()
    size = 0
    with artifact_path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return ArtifactIdentity(artifact_path.name if name is None else name, digest.hexdigest(), size)


def create_research_manifest(
    datasets: Sequence[DatasetScope],
    *,
    feature_parameters: Mapping[str, Any],
    label_parameters: Mapping[str, Any],
    split_parameters: Mapping[str, Any],
    benchmark_parameters: Mapping[str, Any],
    random_seeds: Mapping[str, int] | None = None,
    execution_status: Literal["not-run", "succeeded", "failed"] = "not-run",
    artifacts: Sequence[ArtifactIdentity] = (),
    environment: Mapping[str, str] | None = None,
) -> ResearchManifest:
    """Build a versioned manifest after validating that its values are portable JSON."""
    manifest = ResearchManifest(
        manifest_version=1,
        datasets=tuple(datasets),
        feature_parameters=feature_parameters,
        label_parameters=label_parameters,
        split_parameters=split_parameters,
        benchmark_parameters=benchmark_parameters,
        environment=environment_versions() if environment is None else environment,
        random_seeds={} if random_seeds is None else random_seeds,
        execution_status=execution_status,
        artifacts=tuple(artifacts),
    )
    manifest_to_json(manifest)
    return manifest


def manifest_to_json(manifest: ResearchManifest, *, indent: int | None = 2) -> str:
    """Serialize a manifest as stable portable JSON with a trailing newline."""
    if indent is not None and indent < 0:
        raise ValueError("indent must be nonnegative or None")
    document = json.dumps(
        _manifest_dictionary(manifest),
        allow_nan=False,
        indent=indent,
        sort_keys=True,
    )
    return f"{document}\n"


def manifest_from_json(document: str) -> ResearchManifest:
    """Parse and validate a versioned research manifest JSON document."""
    raw = json.loads(document)
    if not isinstance(raw, dict):
        raise ValueError("research manifest must be a JSON object")
    payload = cast("dict[str, object]", raw)
    expected = {
        "manifest_version",
        "datasets",
        "parameters",
        "environment",
        "random_seeds",
        "execution",
    }
    if set(payload) != expected:
        raise ValueError("research manifest fields differ from the version 1 schema")
    parameters = _mapping(payload["parameters"], name="parameters")
    execution = _mapping(payload["execution"], name="execution")
    datasets_raw = payload["datasets"]
    artifacts_raw = execution.get("artifacts")
    if not isinstance(datasets_raw, list) or not isinstance(artifacts_raw, list):
        raise ValueError("datasets and artifacts must be JSON arrays")
    dataset_items = cast("list[object]", datasets_raw)
    artifact_items = cast("list[object]", artifacts_raw)
    datasets = tuple(_dataset_from_mapping(item) for item in dataset_items)
    artifacts = tuple(_artifact_from_mapping(item) for item in artifact_items)
    status = execution.get("status")
    if status not in {"not-run", "succeeded", "failed"}:
        raise ValueError("unsupported execution status")
    manifest_version = payload["manifest_version"]
    if not isinstance(manifest_version, int):
        raise ValueError("manifest_version must be an integer")
    environment = _string_mapping(payload["environment"], name="environment")
    seeds_raw = _mapping(payload["random_seeds"], name="random_seeds")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in seeds_raw.values()):
        raise ValueError("random seeds must be integers")
    seeds = cast("dict[str, int]", seeds_raw)
    return ResearchManifest(
        manifest_version=manifest_version,
        datasets=datasets,
        feature_parameters=_mapping(parameters.get("features"), name="feature parameters"),
        label_parameters=_mapping(parameters.get("labels"), name="label parameters"),
        split_parameters=_mapping(parameters.get("splits"), name="split parameters"),
        benchmark_parameters=_mapping(
            parameters.get("benchmarks"), name="benchmark parameters"
        ),
        environment=environment,
        random_seeds=seeds,
        execution_status=cast("Literal['not-run', 'succeeded', 'failed']", status),
        artifacts=artifacts,
    )


def write_research_manifest(
    manifest: ResearchManifest,
    path: str | Path,
    *,
    indent: int | None = 2,
) -> None:
    """Write a research manifest as UTF-8 JSON."""
    Path(path).write_text(manifest_to_json(manifest, indent=indent), encoding="utf-8")


def read_research_manifest(path: str | Path) -> ResearchManifest:
    """Read a UTF-8 research manifest and validate its complete schema."""
    return manifest_from_json(Path(path).read_text(encoding="utf-8"))


def _manifest_dictionary(manifest: ResearchManifest) -> dict[str, object]:
    return {
        "manifest_version": manifest.manifest_version,
        "datasets": [
            {
                "name": dataset.name,
                "scope": dict(dataset.scope),
                "schema_version": dataset.schema_version,
                "content_identity": dataset.content_identity,
                "snapshot_identity": dataset.snapshot_identity,
            }
            for dataset in manifest.datasets
        ],
        "parameters": {
            "features": dict(manifest.feature_parameters),
            "labels": dict(manifest.label_parameters),
            "splits": dict(manifest.split_parameters),
            "benchmarks": dict(manifest.benchmark_parameters),
        },
        "environment": dict(manifest.environment),
        "random_seeds": dict(manifest.random_seeds),
        "execution": {
            "status": manifest.execution_status,
            "artifacts": [
                {
                    "name": artifact.name,
                    "sha256": artifact.sha256,
                    "size_bytes": artifact.size_bytes,
                }
                for artifact in manifest.artifacts
            ],
        },
    }


def _mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object with string keys")
    dictionary = cast("dict[object, object]", value)
    if any(not isinstance(key, str) for key in dictionary):
        raise ValueError(f"{name} must be a JSON object with string keys")
    return cast("dict[str, Any]", dictionary)


def _string_mapping(value: object, *, name: str) -> dict[str, str]:
    result = _mapping(value, name=name)
    if any(not isinstance(item, str) for item in result.values()):
        raise ValueError(f"{name} values must be strings")
    return cast("dict[str, str]", result)


def _dataset_from_mapping(value: object) -> DatasetScope:
    item = _mapping(value, name="dataset")
    expected = {
        "name",
        "scope",
        "schema_version",
        "content_identity",
        "snapshot_identity",
    }
    if set(item) != expected:
        raise ValueError("dataset fields differ from the version 1 schema")
    name = item["name"]
    schema_version = item["schema_version"]
    content_identity = item["content_identity"]
    snapshot_identity = item["snapshot_identity"]
    if not isinstance(name, str) or not isinstance(schema_version, str):
        raise ValueError("dataset name and schema_version must be strings")
    if content_identity is not None and not isinstance(content_identity, str):
        raise ValueError("content_identity must be a string or null")
    if snapshot_identity is not None and not isinstance(snapshot_identity, str):
        raise ValueError("snapshot_identity must be a string or null")
    return DatasetScope(
        name=name,
        scope=_mapping(item["scope"], name="dataset scope"),
        schema_version=schema_version,
        content_identity=content_identity,
        snapshot_identity=snapshot_identity,
    )


def _artifact_from_mapping(value: object) -> ArtifactIdentity:
    item = _mapping(value, name="artifact")
    if set(item) != {"name", "sha256", "size_bytes"}:
        raise ValueError("artifact fields differ from the version 1 schema")
    name = item["name"]
    sha256 = item["sha256"]
    size_bytes = item["size_bytes"]
    if not isinstance(name, str) or not isinstance(sha256, str):
        raise ValueError("artifact name and sha256 must be strings")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
        raise ValueError("artifact size_bytes must be an integer")
    return ArtifactIdentity(name, sha256, size_bytes)
