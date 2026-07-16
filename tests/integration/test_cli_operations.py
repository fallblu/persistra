from __future__ import annotations

import json
from typing import TYPE_CHECKING

from persistra.cli import main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_project_init_inspect_and_doctor_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "project"
    assert main(["project", "init", str(root), "--name", "cli-project"]) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["complete"] is True
    assert main(["project", "inspect", str(root)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["name"] == "cli-project"
    assert main(["doctor", str(root)]) == 0
    findings = json.loads(capsys.readouterr().out)
    assert findings[0]["code"] == "db.schema.current"
