"""Tests for safe research-manifest inspection."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import pytest

from persistra import _cli
from persistra._artifact_inspection import (
    DiscoveredResearchArtifact,
    artifact_inventory,
    artifact_overview,
    artifact_tables,
)
from persistra._inspection import (
    InspectorViewModel,
    build_panel_app,
    discover_stores,
    inventory_document,
)
from persistra.research import (
    DatasetScope,
    create_research_manifest,
    identify_artifact,
    write_research_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path


def write_research_artifact(root: Path, *, name: str = "research-manifest.json") -> Path:
    """Write one valid manifest and checksummed result table."""
    root.mkdir(parents=True, exist_ok=True)
    result = root / "results.csv"
    result.write_text("metric,value\nsharpe,1.25\n", encoding="utf-8")
    manifest = create_research_manifest(
        (
            DatasetScope(
                "prices",
                {"instrument": "AAA"},
                "1",
                content_identity="prices-sha256",
            ),
        ),
        feature_parameters={"window": 20, "nested": {"lag": 1}},
        label_parameters={"horizon": 5},
        split_parameters={"method": "rolling"},
        benchmark_parameters={"symbol": "SPY"},
        random_seeds={"model": 7},
        execution_status="succeeded",
        artifacts=(identify_artifact(result),),
        environment={"persistra": "test"},
        include_runtime=False,
    )
    path = root / name
    write_research_manifest(manifest, path)
    return path


def test_project_discovery_verifies_manifests_and_isolates_warnings(tmp_path: Path) -> None:
    research_path = write_research_artifact(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    nested_research = write_research_artifact(nested, name="nested.research-manifest.json")
    malformed_research = tmp_path / "bad.research-manifest.json"
    malformed_research.write_text("{}", encoding="utf-8")
    (tmp_path / "unrelated.json").write_text("{}", encoding="utf-8")
    linked = tmp_path / "linked.research-manifest.json"
    linked.symlink_to(research_path)
    immediate = discover_stores(tmp_path)
    assert [artifact.path for artifact in immediate.artifacts] == [research_path.resolve()]
    assert all("linked" not in warning for warning in immediate.warnings)
    assert any("bad.research-manifest.json" in warning for warning in immediate.warnings)

    recursive = discover_stores(tmp_path, recursive=True)
    assert [artifact.path for artifact in recursive.artifacts] == [
        research_path.resolve(),
        nested_research.resolve(),
    ]
    assert all("unrelated.json" not in warning for warning in recursive.warnings)

    model = InspectorViewModel(recursive)
    assert model.artifact(research_path).path == research_path.resolve()
    with pytest.raises(ValueError, match="not part"):
        model.artifact(tmp_path / "unrelated.json")


def test_changed_research_output_is_never_rendered(tmp_path: Path) -> None:
    manifest_path = write_research_artifact(tmp_path)
    (tmp_path / "results.csv").write_text("changed", encoding="utf-8")

    inspection = discover_stores(tmp_path, allow_empty=True)

    assert inspection.artifacts == ()
    assert len(inspection.warnings) == 1
    assert str(manifest_path) in inspection.warnings[0]
    assert "verification failed" in inspection.warnings[0]


def test_research_artifact_tables_show_parameters_provenance_checksums_and_status(
    tmp_path: Path,
) -> None:
    manifest_path = write_research_artifact(tmp_path)
    artifact = discover_stores(tmp_path).artifacts[0]
    assert isinstance(artifact, DiscoveredResearchArtifact)

    overview = dict(
        zip(
            artifact_overview(artifact)["field"],
            artifact_overview(artifact)["value"],
            strict=True,
        )
    )
    tables = {table.name: table.frame for table in artifact_tables(artifact)}
    document = inventory_document(discover_stores(tmp_path))
    artifact_document = artifact_inventory(artifact)

    assert overview["execution_status"] == "succeeded"
    assert set(tables) == {"Parameters", "Datasets", "Checksums", "Provenance"}
    assert "window" in set(tables["Parameters"]["name"])
    assert tables["Checksums"].iloc[0]["verified"]
    assert tables["Provenance"].iloc[0].to_dict() == {
        "name": "persistra",
        "value": "test",
    }
    assert document["artifact_count"] == 1
    assert artifact_document["manifest_version"] == 1
    artifacts = cast("list[dict[str, object]]", document["artifacts"])
    assert artifacts[0]["path"] == str(manifest_path.resolve())


def test_artifact_only_inventory_and_panel_are_supported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pn = pytest.importorskip("panel")
    manifest_path = write_research_artifact(tmp_path)

    assert _cli.run(["inspect", str(tmp_path), "--list"]) == 0
    assert f"Artifact: Research manifest / {manifest_path.resolve()}" in capsys.readouterr().out
    assert _cli.run(["inspect", str(tmp_path), "--list", "--json"]) == 0
    document = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    assert document["artifact_count"] == 1

    model = InspectorViewModel(discover_stores(tmp_path))
    app: Any = build_panel_app(model, panel=pn)
    widgets = {widget.label: widget for widget in app.sidebar[0]}
    assert widgets["Store"].value is None
    assert widgets["Verified artifact"].value == manifest_path.resolve()
    assert app.main[-1][0].object.startswith("No supported Persistra stores")
    assert app.main[-1][1].title == "Verified project artifact"
