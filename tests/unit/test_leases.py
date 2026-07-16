from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from persistra.db.leases import LeaseMode, acquire_lease
from persistra.errors import DatabaseLeaseConflictError, LeaseUpgradeError

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
