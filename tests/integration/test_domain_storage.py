from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

import duckdb
import pandas as pd

from persistra.domain import EntityId


class StorageId(EntityId):
    KIND: ClassVar[str] = "storage"


def test_duckdb_and_pandas_domain_round_trip() -> None:
    identifier = StorageId.new()
    instant = datetime(2026, 7, 15, 14, 30, 0, 123456, tzinfo=UTC)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("SET TimeZone = 'UTC'")
        connection.execute(
            "CREATE TABLE values_ ("
            "id UUID, instant_at TIMESTAMPTZ, amount DECIMAL(38,12), rate DECIMAL(38,18))"
        )
        connection.execute(
            "INSERT INTO values_ VALUES (?, ?, ?, ?)",
            [
                identifier.value,
                instant,
                Decimal("123.450000000000"),
                Decimal("0.050000000000000000"),
            ],
        )
        row = connection.execute("SELECT * FROM values_").fetchone()
        assert row == (
            identifier.value,
            instant,
            Decimal("123.450000000000"),
            Decimal("0.050000000000000000"),
        )
        frame = connection.execute("SELECT * FROM values_").df()
    finally:
        connection.close()
    frame["id"] = pd.Series([identifier.to_wire()], dtype="string")
    assert frame["id"].dtype == pd.StringDtype()
    assert str(frame["instant_at"].dtype).endswith("UTC]")
