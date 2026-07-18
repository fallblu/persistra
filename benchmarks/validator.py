"""Independent structural and sampled-value benchmark validation."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import duckdb

from persistra.domain.serialization import canonical_bytes

if TYPE_CHECKING:
    from pathlib import Path

_SEED = 20250300
_WORKLOAD = "persistra.benchmark.daily_equity_1000x10@1"


def independent_draw(label: str, *parts: int | str) -> float:
    payload = canonical_bytes((_SEED, _WORKLOAD, label, *parts, 0))
    integer = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return (integer + 0.5) / 2**64


def validate_fixture(path: Path, expected_rows: int) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("benchmark fixture is not a regular file")
    connection = duckdb.connect(str(path), read_only=True)
    try:
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        count_row = connection.execute("SELECT count(*) FROM bars").fetchone()
        first = connection.execute(
            "SELECT session_ordinal, instrument_ordinal, volume FROM bars "
            "ORDER BY session_ordinal, instrument_ordinal LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    if count_row is None:
        raise ValueError("benchmark fixture row count is unavailable")
    count = int(count_row[0])
    if tables != [("bars",)] or count != expected_rows or first is None:
        raise ValueError("benchmark fixture topology or row count is invalid")
    expected_volume = 100 * max(
        1,
        int(
            (
                (10_000 + 200 * (1 % 5_000))
                * (0.5 + independent_draw("volume", 1, 0))
            )
            // 100
        ),
    )
    if tuple(first) != (0, 1, expected_volume):
        raise ValueError("benchmark fixture sampled value is invalid")
