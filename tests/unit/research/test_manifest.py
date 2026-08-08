"""Tests for portable research artifact manifests."""

import json
from pathlib import Path

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
