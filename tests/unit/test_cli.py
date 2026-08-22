"""Tests for the shared Persistra command line interface."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from persistra import _cli
from persistra._inspection import DirectoryInspection, InspectionError
from persistra.data import DuckDBStore, synthetic
from persistra.project import create_project


def test_inspect_command_routes_all_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inspection = DirectoryInspection(tmp_path, (), ("candidate warning",))
    calls: dict[str, object] = {}

    def discover(directory: str, *, recursive: bool) -> DirectoryInspection:
        calls.update(directory=directory, recursive=recursive)
        return inspection

    def serve(value: DirectoryInspection, *, port: int | None, open_browser: bool) -> None:
        calls.update(inspection=value, port=port, open_browser=open_browser)

    monkeypatch.setattr(_cli, "discover_stores", discover)
    monkeypatch.setattr(_cli, "serve_inspector", serve)
    assert _cli.run(["inspect", str(tmp_path), "--recursive", "--no-open", "--port", "8123"]) == 0
    assert calls == {
        "directory": str(tmp_path),
        "recursive": True,
        "inspection": inspection,
        "port": 8123,
        "open_browser": False,
    }


def test_expected_cli_errors_have_no_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_directory: str, *, recursive: bool) -> DirectoryInspection:
        del recursive
        raise InspectionError("choose another path")

    monkeypatch.setattr(
        _cli,
        "discover_stores",
        fail,
    )
    with pytest.raises(SystemExit) as raised:
        _cli.main(["inspect", "."])
    assert raised.value.code == 2
    assert capsys.readouterr().err == "persistra: error: choose another path\n"


def test_inspect_list_renders_human_and_json_inventory_without_panel(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path / "project", name="Research_Project")
    with DuckDBStore.open(project.store_path) as store:
        snapshot_id = store.save(synthetic.bars(periods=2))
        store.save(synthetic.series(periods=2))
    (project.root / "invalid.duckdb").write_text("invalid", encoding="utf-8")

    def deny_server(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("list mode attempted to start the inspector server")

    monkeypatch.setattr(_cli, "serve_inspector", deny_server)

    assert _cli.run(["inspect", str(project.root), "--list"]) == 0
    human = capsys.readouterr()
    assert f"Persistra store inventory: {project.root}" in human.out
    assert "Project: research-project (format version 1)" in human.out
    assert f"Store: {project.store_path}" in human.out
    assert "Schema version: 3" in human.out
    assert "Dataset: bars /" in human.out
    assert "Snapshots: 1" in human.out
    assert f"Latest snapshot: {snapshot_id}" in human.out
    assert "invalid.duckdb" in human.err

    assert _cli.run(["inspect", str(project.root), "--list", "--json"]) == 0
    rendered = capsys.readouterr()
    document = json.loads(rendered.out)
    assert rendered.err == ""
    assert document["inventory_version"] == 1
    assert document["directory"] == str(project.root)
    assert document["project"] == {"name": "research-project", "format_version": 1}
    assert document["store_count"] == 1
    assert len(document["warnings"]) == 1
    assert "invalid.duckdb" in document["warnings"][0]
    stored = document["stores"][0]
    assert stored["path"] == str(project.store_path)
    assert stored["schema_version"] == 3
    assert stored["dataset_count"] == 2
    assert [item["family"] for item in stored["datasets"]] == ["bars", "series"]
    dataset = stored["datasets"][0]
    assert dataset["family"] == "bars"
    assert isinstance(dataset["scope_key"], str)
    assert dataset["snapshot_count"] == 1
    assert dataset["latest_snapshot_id"] == snapshot_id
    assert datetime.fromisoformat(dataset["first_seen"]).tzinfo is not None
    assert datetime.fromisoformat(dataset["last_seen"]).tzinfo is not None

    assert _cli.run(["inspect", str(project.root), "--list", "--json"]) == 0
    repeated = capsys.readouterr()
    assert repeated.err == ""
    assert repeated.out == rendered.out


def test_inspect_list_recursive_discovery_and_empty_status(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    DuckDBStore.create(nested / "data.duckdb").close()

    assert _cli.run(["inspect", str(tmp_path), "--list", "--json"]) == 1
    empty = capsys.readouterr()
    assert json.loads(empty.out)["stores"] == []
    assert "no supported Persistra stores" in empty.err

    assert _cli.run(["inspect", str(tmp_path), "--list", "--json", "--recursive"]) == 0
    recursive = capsys.readouterr()
    assert recursive.err == ""
    assert json.loads(recursive.out)["stores"][0]["path"] == str((nested / "data.duckdb").resolve())


@pytest.mark.parametrize(
    "arguments, message",
    [
        (["inspect", ".", "--list", "--port", "8000"], "cannot be combined"),
        (["inspect", ".", "--list", "--no-open"], "cannot be combined"),
        (["inspect", ".", "--json"], "requires --list"),
    ],
)
def test_inspect_list_rejects_incompatible_options(
    arguments: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        _cli.run(arguments)
    assert raised.value.code == 2
    assert message in capsys.readouterr().err


def test_init_command_prints_normalized_project_and_next_steps(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    root = tmp_path / "project with spaces"
    calls: dict[str, object] = {}

    def create(directory: str, *, name: str | None) -> SimpleNamespace:
        calls.update(directory=directory, name=name)
        return SimpleNamespace(root=root, name="research-project")

    monkeypatch.setattr(_cli, "create_project", create)
    assert _cli.run(["init", "target", "--name", "Research_Project"]) == 0
    assert calls == {"directory": "target", "name": "Research_Project"}
    output = capsys.readouterr().out
    assert f"Created Persistra project research-project at {root}" in output
    assert f"cd '{root}'" in output
    assert "uv sync" in output
    assert "uv run persistra project validate ." in output
    assert "uv run persistra inspect ." in output


def test_keyboard_interrupt_reports_cancellation_and_status_130(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def cancel(_directory: str, *, name: str | None) -> None:
        del name
        raise KeyboardInterrupt

    monkeypatch.setattr(_cli, "create_project", cancel)
    with pytest.raises(SystemExit) as raised:
        _cli.main(["init", "target"])

    assert raised.value.code == 130
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "persistra: cancelled\n"


def test_cli_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit) as raised:
        _cli.run([])
    assert raised.value.code == 2
