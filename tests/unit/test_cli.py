"""Tests for the shared Persistra command line interface."""

from pathlib import Path

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


def test_cli_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit) as raised:
        _cli.run([])
    assert raised.value.code == 2
