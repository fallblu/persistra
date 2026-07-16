from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from persistra.db.leases import LeaseMode, acquire_lease
from persistra.errors import (
    DatabaseLeaseConflictError,
    LeaseUpgradeError,
    UnsupportedFilesystemError,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_shared_reentrancy_and_mode_conversion(tmp_path: Path) -> None:
    database = tmp_path / "database.duckdb"
    first = acquire_lease(database, LeaseMode.SHARED)
    second = acquire_lease(database, LeaseMode.SHARED)
    try:
        with pytest.raises(LeaseUpgradeError):
            acquire_lease(database, LeaseMode.EXCLUSIVE)
    finally:
        second.close()
        first.close()


def test_exclusive_is_not_reentrant(tmp_path: Path) -> None:
    database = tmp_path / "database.duckdb"
    with acquire_lease(database, LeaseMode.EXCLUSIVE):
        with pytest.raises(DatabaseLeaseConflictError):
            acquire_lease(database, LeaseMode.EXCLUSIVE)


def test_owner_evidence_is_durable_and_exclusive_cleans_stale_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "database.duckdb"
    lease = acquire_lease(database, LeaseMode.SHARED)
    owners = database.with_name(database.name + ".persistra-lock") / "owners"
    owner = next(owners.glob("*.json"))
    evidence = json.loads(owner.read_text(encoding="utf-8"))
    assert evidence["process_start_token"]
    lease.record_database_id("database:00000000-0000-4000-8000-000000000001")
    assert "database_id" in json.loads(owner.read_text(encoding="utf-8"))
    lease.close()
    stale = owners / "lease:stale.json"
    stale.write_text("{}", encoding="utf-8")
    with acquire_lease(database, LeaseMode.EXCLUSIVE):
        assert not stale.exists()


def test_lease_rejects_symlinked_guard(tmp_path: Path) -> None:
    database = tmp_path / "database.duckdb"
    sidecar = database.with_name(database.name + ".persistra-lock")
    (sidecar / "owners").mkdir(parents=True)
    (sidecar / "guard").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(UnsupportedFilesystemError):
        acquire_lease(database, LeaseMode.SHARED)


@pytest.mark.multiprocess
def test_exclusive_lease_conflicts_across_processes(tmp_path: Path) -> None:
    database = tmp_path / "database.duckdb"
    script = """
import sys
from pathlib import Path
from persistra.db.leases import LeaseMode, acquire_lease
from persistra.errors import DatabaseLeaseConflictError
try:
    acquire_lease(Path(sys.argv[1]), LeaseMode.SHARED)
except DatabaseLeaseConflictError:
    raise SystemExit(0)
raise SystemExit(1)
"""
    with acquire_lease(database, LeaseMode.EXCLUSIVE):
        completed = subprocess.run(
            [sys.executable, "-c", script, str(database)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert completed.returncode == 0, completed.stderr
