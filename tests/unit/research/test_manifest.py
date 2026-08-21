"""Tests for portable research artifact manifests."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from persistra.research import (
    DatasetScope,
    create_research_manifest,
    environment_versions,
    identify_artifact,
    manifest_from_json,
    manifest_to_json,
    read_research_manifest,
    write_research_manifest,
)


def dataset() -> DatasetScope:
    """Return one explicit fixed-universe dataset identity."""
    return DatasetScope(
        name="daily_equities",
        scope={"symbols": ["A", "B", "C"], "start": "2024-01-01", "end": "2024-12-31"},
        schema_version="bars-v1",
        snapshot_identity="duckdb:snapshot-42",
    )


def test_environment_versions_record_the_library_and_direct_dependencies() -> None:
    versions = environment_versions()

    assert set(versions) == {
        "persistra",
        "duckdb",
        "matplotlib",
        "numpy",
        "pandas",
        "platformdirs",
        "requests",
        "scipy",
    }
    assert all(versions.values())


def test_manifest_round_trip_records_scope_parameters_environment_and_execution(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "summary.csv"
    artifact_path.write_bytes(b"signal,mean\nmomentum,0.01\n")
    artifact = identify_artifact(artifact_path)
    manifest = create_research_manifest(
        [dataset()],
        feature_parameters={"momentum": {"lookback": 20, "lag": 1}},
        label_parameters={"horizon": 5},
        split_parameters={"initial_train_size": 252, "embargo": 2},
        benchmark_parameters={"name": "equal_weight"},
        random_seeds={"bootstrap": 7},
        execution_status="succeeded",
        artifacts=[artifact],
        environment={"persistra": "4.0.0", "pandas": "3.0.0"},
    )

    document = manifest_to_json(manifest)
    restored = manifest_from_json(document)
    path = tmp_path / "manifest.json"
    write_research_manifest(manifest, path)

    assert json.loads(document)["datasets"][0]["scope"]["symbols"] == ["A", "B", "C"]
    assert restored == manifest
    assert restored.artifacts[0].sha256 == (
        "4418992e32a613ddec0ed6c5a057a7c9ab40e55dbfb729f651bcc65f0511c641"
    )
    assert restored.artifacts[0].size_bytes == len(artifact_path.read_bytes())
    assert read_research_manifest(path) == manifest


def test_manifest_deeply_freezes_scopes_and_every_parameter_family() -> None:
    scope_values: dict[str, Any] = {
        "symbols": ["A"],
        "filters": {"regions": ["US"]},
    }
    feature_values: dict[str, Any] = {"momentum": {"windows": [20, 60]}}
    label_values: dict[str, Any] = {"returns": {"horizons": [1, 5]}}
    split_values: dict[str, Any] = {"walk_forward": {"folds": [{"months": 12}]}}
    benchmark_values: dict[str, Any] = {"universe": {"symbols": ["A", "B"]}}
    scope = DatasetScope("data", scope_values, "v1", snapshot_identity="snap")
    manifest = create_research_manifest(
        [scope],
        feature_parameters=feature_values,
        label_parameters=label_values,
        split_parameters=split_values,
        benchmark_parameters=benchmark_values,
        environment={"persistra": "4"},
    )
    before = manifest_to_json(manifest)

    scope_values["symbols"].append("B")
    scope_values["filters"]["regions"].append("EU")
    feature_values["momentum"]["windows"].append(120)
    label_values["returns"]["horizons"].append(20)
    split_values["walk_forward"]["folds"][0]["months"] = 24
    benchmark_values["universe"]["symbols"].append("C")

    assert manifest_to_json(manifest) == before
    assert manifest_from_json(before) == manifest
    with pytest.raises(AttributeError):
        scope.scope["symbols"].append("C")
    with pytest.raises(TypeError):
        manifest.feature_parameters["momentum"]["windows"] = (1,)
    with pytest.raises(TypeError):
        manifest.split_parameters["walk_forward"]["folds"][0]["months"] = 36


def test_manifest_requires_identities_portable_values_and_consistent_status() -> None:
    with pytest.raises(ValueError, match="content or snapshot"):
        DatasetScope("data", {}, "v1")
    with pytest.raises(ValueError, match="not-run"):
        create_research_manifest(
            [dataset()],
            feature_parameters={},
            label_parameters={},
            split_parameters={},
            benchmark_parameters={},
            artifacts=[identify_artifact(__file__)],
            environment={"persistra": "4.0.0"},
        )
    with pytest.raises(ValueError, match="portable JSON"):
        create_research_manifest(
            [dataset()],
            feature_parameters={"date": pd.Timestamp("2025-01-01")},
            label_parameters={},
            split_parameters={},
            benchmark_parameters={},
            environment={"persistra": "4.0.0"},
        )
    with pytest.raises(ValueError, match="fields differ"):
        manifest_from_json('{"manifest_version": 1}')
