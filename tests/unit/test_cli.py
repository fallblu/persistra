"""Tests for the shared Persistra command line interface."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from persistra import _cli
from persistra._inspection import DirectoryInspection, InspectionError


def test_inspect_command_routes_all_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inspection = DirectoryInspection(tmp_path, (), ("candidate warning",))
    calls: dict[str, object] = {}

    def discover(directory: str, *, recursive: bool) -> DirectoryInspection:
        calls.update(directory=directory, recursive=recursive)
        return inspection

    def serve(
        value: DirectoryInspection, *, port: int | None, open_browser: bool
    ) -> None:
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
    assert "uv run persistra inspect ." in output


def test_cli_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit) as raised:
        _cli.run([])
    assert raised.value.code == 2
