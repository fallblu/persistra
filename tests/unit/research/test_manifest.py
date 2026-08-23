"""Tests for portable research artifact manifests."""

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from persistra.errors import DataValidationError
from persistra.research import (
    DatasetScope,
    create_research_manifest,
    environment_distributions,
    environment_versions,
    identify_artifact,
    manifest_from_json,
    manifest_to_json,
    read_research_manifest,
    research_manifest_schema,
    runtime_environment,
    verify_manifest_artifacts,
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


def manifest():
    """Return one portable succeeded research manifest."""
    return create_research_manifest(
        [dataset()],
        feature_parameters={"momentum": {"lookback": 20, "lag": 1}},
        label_parameters={"horizon": 5},
        split_parameters={"initial_train_size": 252, "embargo": 2},
        benchmark_parameters={"name": "equal_weight"},
        random_seeds={"bootstrap": 7},
        execution_status="succeeded",
        environment={"persistra": "4.0.0", "pandas": "3.0.0"},
    )


def test_environment_versions_record_the_library_and_direct_dependencies() -> None:
    versions = environment_versions()

    assert set(versions) == {
        "persistra",
        "duckdb",
        "jsonschema",
        "numpy",
        "pandas",
        "platformdirs",
        "pyarrow",
        "referencing",
        "requests",
        "scipy",
        "tzdata",
    }
    assert all(versions.values())


def test_environment_versions_include_only_explicit_optional_extras() -> None:
    assert set(environment_distributions(extras=("viz",))) == {
        "persistra",
        "duckdb",
        "jsonschema",
        "numpy",
        "pandas",
        "plotly",
        "platformdirs",
        "pyarrow",
        "referencing",
        "requests",
        "scipy",
        "tzdata",
    }
    assert set(environment_distributions(extras=("inspect",))) == {
        "persistra",
        "duckdb",
        "jsonschema",
        "numpy",
        "pandas",
        "panel",
        "plotly",
        "platformdirs",
        "pyarrow",
        "referencing",
        "requests",
        "scipy",
        "tzdata",
    }
    assert environment_versions(extras=("viz",))["plotly"]
    with pytest.raises(ValueError, match="cannot be combined"):
        environment_versions(("persistra",), extras=("viz",))


def test_runtime_environment_records_stable_facts_with_opt_out_and_overrides() -> None:
    facts = runtime_environment({"platform": "private"})
    assert set(facts) == {"python_implementation", "python_version", "platform"}
    assert facts["platform"] == "private"

    without_runtime = create_research_manifest(
        [dataset()],
        feature_parameters={},
        label_parameters={},
        split_parameters={},
        benchmark_parameters={},
        environment={"persistra": "4"},
        include_runtime=False,
    )
    assert without_runtime.environment == {"persistra": "4"}
    with pytest.raises(ValueError, match="require include_runtime"):
        create_research_manifest(
            [dataset()],
            feature_parameters={},
            label_parameters={},
            split_parameters={},
            benchmark_parameters={},
            include_runtime=False,
            runtime_overrides={"platform": "private"},
        )


def test_packaged_schema_matches_example_serializer_and_parser() -> None:
    schema = research_manifest_schema()
    validator: Any = Draft202012Validator(schema)
    example_path = Path("docs/examples/research-manifest-v1.json")
    example = json.loads(example_path.read_text(encoding="utf-8"))
    serialized = json.loads(manifest_to_json(manifest()))

    validator.validate(example)
    validator.validate(serialized)
    assert manifest_from_json(json.dumps(example)).manifest_version == 1
    assert manifest_from_json(json.dumps(serialized)) == manifest()
    version_two = create_research_manifest(
        [dataset()],
        feature_parameters={},
        label_parameters={},
        split_parameters={},
        benchmark_parameters={},
        model_parameters={"factor_risk": {"covariance_estimator": "ledoit_wolf"}},
        manifest_version=2,
        environment={"persistra": "4"},
        include_runtime=False,
    )
    version_two_document = manifest_to_json(version_two)
    version_two_validator: Any = Draft202012Validator(research_manifest_schema(2))
    version_two_validator.validate(json.loads(version_two_document))
    assert manifest_from_json(version_two_document) == version_two
    with pytest.raises(ValueError, match="manifest_version=2"):
        create_research_manifest(
            [],
            feature_parameters={},
            label_parameters={},
            split_parameters={},
            benchmark_parameters={},
            model_parameters={"factor_risk": {}},
            include_runtime=False,
        )
    missing_models = json.loads(version_two_document)
    del missing_models["parameters"]["models"]
    with pytest.raises(ValueError, match="version 2"):
        manifest_from_json(json.dumps(missing_models))
    with pytest.raises(ValueError, match="unsupported"):
        research_manifest_schema(3)


def test_artifact_verification_reports_success_and_content_changes(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    path = root / "tables" / "summary.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"alpha")
    artifact = identify_artifact(path, name="tables/summary.csv")
    result = create_research_manifest(
        [dataset()],
        feature_parameters={},
        label_parameters={},
        split_parameters={},
        benchmark_parameters={},
        environment={"persistra": "4"},
        include_runtime=False,
        execution_status="succeeded",
        artifacts=[artifact],
    )

    valid = verify_manifest_artifacts(result, root)
    assert valid.is_valid
    assert valid.verified_artifacts == ("tables/summary.csv",)
    valid.raise_for_errors()

    path.write_bytes(b"bravo")
    changed = verify_manifest_artifacts(result, root)
    assert [finding.code for finding in changed.findings] == ["artifact.hash_mismatch"]
    with pytest.raises(DataValidationError, match="hash_mismatch"):
        changed.raise_for_errors()

    path.write_bytes(b"longer")
    resized = verify_manifest_artifacts(result, root)
    assert [finding.code for finding in resized.findings] == ["artifact.size_mismatch"]


def test_artifact_verification_reports_missing_unexpected_and_unsafe_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    (root / "extra.bin").write_bytes(b"extra")
    (root / "linked.bin").symlink_to(outside)
    artifacts = [
        identify_artifact(outside, name="missing.bin"),
        identify_artifact(outside, name="../outside.bin"),
        identify_artifact(outside, name="linked.bin"),
    ]
    result = create_research_manifest(
        [dataset()],
        feature_parameters={},
        label_parameters={},
        split_parameters={},
        benchmark_parameters={},
        environment={"persistra": "4"},
        include_runtime=False,
        execution_status="failed",
        artifacts=artifacts,
    )

    verification = verify_manifest_artifacts(result, root)
    codes = [finding.code for finding in verification.findings]
    assert codes.count("artifact.unsafe") == 2
    assert "artifact.missing" in codes
    assert "artifact.unexpected" in codes


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


def test_manifest_write_is_exclusive_unless_overwrite_is_explicit(tmp_path: Path) -> None:
    result = manifest()
    path = tmp_path / "manifest.json"
    path.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_research_manifest(result, path)

    assert path.read_text(encoding="utf-8") == "preserve\n"
    write_research_manifest(result, path, overwrite=True)
    assert read_research_manifest(path) == result
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))


def test_manifest_write_cleans_private_staging_after_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = import_module("persistra._files")
    path = tmp_path / "manifest.json"
    path.write_text("preserve\n", encoding="utf-8")

    def interrupt(_descriptor: int) -> None:
        raise OSError("interrupted fsync")

    monkeypatch.setattr(files.os, "fsync", interrupt)
    with pytest.raises(OSError, match="interrupted fsync"):
        write_research_manifest(manifest(), path, overwrite=True)

    assert path.read_text(encoding="utf-8") == "preserve\n"
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))


def test_manifest_write_cleans_private_staging_after_publication_permission_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = import_module("persistra._files")
    path = tmp_path / "manifest.json"

    def deny_link(_source: Path, _target: Path) -> None:
        raise PermissionError("publication denied")

    monkeypatch.setattr(files.os, "link", deny_link)
    with pytest.raises(PermissionError, match="publication denied"):
        write_research_manifest(manifest(), path)

    assert not path.exists()
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))


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
