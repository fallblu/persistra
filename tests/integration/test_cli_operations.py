from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from persistra.cli import main
from persistra.db import DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock

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

    market = root / ".persistra" / "market.duckdb"
    create_database_file(
        market,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    with (root / "persistra.toml").open("a", encoding="utf-8") as config:
        config.write(
            '\n[databases.markets.primary]\npath = ".persistra/market.duckdb"\n'
            "verify_copy_on_open = false\n"
        )
    assert main(["data", "snapshot", "create", str(root), "--market", "primary"]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    second_market = root / ".persistra" / "second-market.duckdb"
    create_database_file(
        second_market,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    with (root / "persistra.toml").open("a", encoding="utf-8") as config:
        config.write(
            '\n[databases.markets.secondary]\npath = ".persistra/second-market.duckdb"\n'
            "verify_copy_on_open = false\n"
        )
    assert main(["data", "snapshot", "list", str(root), "--market", "primary"]) == 0
    snapshots = json.loads(capsys.readouterr().out)
    assert snapshots[0]["snapshot_id"] == snapshot["snapshot_id"]
    snapshot_id = snapshot["snapshot_id"]
    assert (
        main(
            [
                "data",
                "snapshot",
                "inspect",
                str(root),
                    snapshot_id,
                    "--market",
                    "primary",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["manifest_content_id"]
    assert main(["data", "quarantine", str(root), "--market", "primary"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_database_maintenance_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "project"
    assert main(["project", "init", str(root), "--name", "cli-maintenance"]) == 0
    capsys.readouterr()

    backup = tmp_path / "research-backup.duckdb"
    assert (
        main(
            [
                "db",
                "backup",
                str(root),
                "--database",
                "research",
                "--destination",
                str(backup),
            ]
        )
        == 0
    )
    backup_result = json.loads(capsys.readouterr().out)
    assert backup_result["destination"].endswith("research-backup.duckdb")

    assert main(["db", "verify-copy", str(root), str(backup)]) == 0
    verification = json.loads(capsys.readouterr().out)
    assert verification["kind"] == "backup"

    assert main(["db", "migrate", str(root), "--database", "research"]) == 0
    migration = json.loads(capsys.readouterr().out)
    assert migration["applied_migrations"] == []

    created = tmp_path / "extra-market.duckdb"
    assert (
        main(
            [
                "db",
                "create",
                str(root),
                str(created),
                "--role",
                "market",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["role"] == "market"

    restored = tmp_path / "restored.duckdb"
    assert (
        main(
            [
                "db",
                "restore",
                str(root),
                str(restored),
                "--backup",
                str(backup),
            ]
        )
        == 0
    )
    assert restored.is_file()
    capsys.readouterr()
