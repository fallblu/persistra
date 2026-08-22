"""Portable research manifests without a managed experiment database."""

from __future__ import annotations

import hashlib
import json
import platform
import re
from importlib.metadata import PackageNotFoundError, distribution, version
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from persistra._files import atomic_write_bytes
from persistra._portable import freeze_portable_mapping, thaw_portable_mapping
from persistra.research.model import ArtifactIdentity, DatasetScope, ResearchManifest

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

EnvironmentExtra = Literal["viz", "inspect"]

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")
_EXTRA_MARKER = re.compile(r"\bextra\s*==\s*['\"]([^'\"]+)['\"]")


def research_manifest_schema(version: int = 1) -> Mapping[str, Any]:
    """Load an immutable copy of the supported research-manifest JSON Schema."""
    if version != 1:
        raise ValueError(f"unsupported research manifest schema version: {version}")
    resource = files("persistra.research.schemas").joinpath("research-manifest-v1.schema.json")
    raw: object = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("packaged research manifest schema must be a JSON object")
    return freeze_portable_mapping(cast("dict[str, Any]", raw), name="research manifest schema")


def environment_distributions(*, extras: Sequence[EnvironmentExtra] = ()) -> tuple[str, ...]:
    """Return declared direct distributions for the base package and selected extras."""
    requested = set(extras)
    unsupported = requested - {"viz", "inspect"}
    if unsupported:
        rendered = ", ".join(sorted(unsupported))
        raise ValueError(f"unsupported environment extras: {rendered}")
    try:
        requirements = distribution("persistra").requires or []
    except PackageNotFoundError as error:
        raise ValueError("Persistra distribution metadata is not installed") from error

    names = {"persistra"}
    for requirement in requirements:
        match = _REQUIREMENT_NAME.match(requirement)
        if match is None:
            raise ValueError(f"invalid installed Persistra requirement: {requirement}")
        markers = set(_EXTRA_MARKER.findall(requirement))
        if markers and markers.isdisjoint(requested):
            continue
        if not markers or requested.intersection(markers):
            names.add(match.group(1).lower().replace("_", "-"))
    return tuple(sorted(names))


def environment_versions(
    distributions: Sequence[str] | None = None,
    *,
    extras: Sequence[EnvironmentExtra] = (),
) -> dict[str, str]:
    """Return installed versions for direct dependencies or an explicit custom set."""
    if distributions is not None and extras:
        raise ValueError("extras cannot be combined with explicit distributions")
    selected = environment_distributions(extras=extras) if distributions is None else distributions
    versions: dict[str, str] = {}
    for distribution_name in selected:
        if not distribution_name:
            raise ValueError("distribution names must not be empty")
        try:
            versions[distribution_name] = version(distribution_name)
        except PackageNotFoundError as error:
            raise ValueError(f"distribution is not installed: {distribution_name}") from error
    return versions


def runtime_environment(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return stable Python and platform facts with explicit caller overrides."""
    facts = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": f"{platform.system()}-{platform.machine()}",
    }
    if overrides is not None:
        if any(not key or not value for key, value in overrides.items()):
            raise ValueError("runtime override names and values must be nonempty strings")
        facts.update(overrides)
    return facts


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
    include_runtime: bool = True,
    runtime_overrides: Mapping[str, str] | None = None,
) -> ResearchManifest:
    """Build a versioned manifest after validating that its values are portable JSON."""
    if not isinstance(cast("object", include_runtime), bool):
        raise ValueError("include_runtime must be a boolean")
    if not include_runtime and runtime_overrides is not None:
        raise ValueError("runtime_overrides require include_runtime=True")
    recorded_environment = dict(environment_versions() if environment is None else environment)
    if include_runtime:
        recorded_environment.update(runtime_environment(runtime_overrides))
    manifest = ResearchManifest(
        manifest_version=1,
        datasets=tuple(datasets),
        feature_parameters=feature_parameters,
        label_parameters=label_parameters,
        split_parameters=split_parameters,
        benchmark_parameters=benchmark_parameters,
        environment=recorded_environment,
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
    if isinstance(manifest_version, bool) or not isinstance(manifest_version, int):
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
        benchmark_parameters=_mapping(parameters.get("benchmarks"), name="benchmark parameters"),
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
    overwrite: bool = False,
) -> None:
    """Atomically write a UTF-8 research manifest without replacing by default."""
    document = manifest_to_json(manifest, indent=indent).encode("utf-8")
    atomic_write_bytes(Path(path), document, overwrite=overwrite)


def read_research_manifest(path: str | Path) -> ResearchManifest:
    """Read a UTF-8 research manifest and validate its complete schema."""
    return manifest_from_json(Path(path).read_text(encoding="utf-8"))


def _manifest_dictionary(manifest: ResearchManifest) -> dict[str, object]:
    return {
        "manifest_version": manifest.manifest_version,
        "datasets": [
            {
                "name": dataset.name,
                "scope": thaw_portable_mapping(dataset.scope),
                "schema_version": dataset.schema_version,
                "content_identity": dataset.content_identity,
                "snapshot_identity": dataset.snapshot_identity,
            }
            for dataset in manifest.datasets
        ],
        "parameters": {
            "features": thaw_portable_mapping(manifest.feature_parameters),
            "labels": thaw_portable_mapping(manifest.label_parameters),
            "splits": thaw_portable_mapping(manifest.split_parameters),
            "benchmarks": thaw_portable_mapping(manifest.benchmark_parameters),
        },
        "environment": thaw_portable_mapping(manifest.environment),
        "random_seeds": thaw_portable_mapping(manifest.random_seeds),
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
