"""Tests for non-destructive versioned store migration."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import pytest

from persistra.data import DuckDBStore, migrate_store, synthetic, verify_store
from persistra.errors import StoreError
from persistra.model import BarSet, Catalog

if TYPE_CHECKING:
    from pathlib import Path


def _legacy_source(path: Path, *, legacy_bar_shape: bool = True) -> tuple[list[str], int]:
    bars = synthetic.bars(periods=2, interval="5min")
    frame = bars.frame.copy()
    frame["provider"] = pd.Series(["alpha_vantage"] * len(frame), dtype="string")
    frame["source_timezone"] = pd.Series(
        ["America/New_York"] * len(frame), dtype="string"
    )
    labels = [
        timestamp.tz_convert(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
        for timestamp in frame["timestamp"]
    ]
    frame["provider_timestamp_label"] = pd.Series(labels, dtype="string")
    first_metadata = replace(bars.metadata, provider="alpha_vantage")
    first = BarSet(bars.instrument, frame, first_metadata)
    second_retrieved_at = first_metadata.retrieved_at + pd.Timedelta(hours=1)
    second_frame = frame.copy()
    second_frame["retrieved_at"] = pd.Series(
        [second_retrieved_at] * len(second_frame), dtype="datetime64[ns, UTC]"
    )
    second = BarSet(
        bars.instrument,
        second_frame,
        replace(first_metadata, retrieved_at=second_retrieved_at),
    )

    catalog = Catalog()
    catalog.add_instrument(bars.instrument)
    with DuckDBStore.create(path) as store:
        store.save_catalog(catalog)
        store.save(first)
        store.save(second)
        store.save(synthetic.series(periods=2))

    connection = duckdb.connect(str(path))
    if legacy_bar_shape:
        snapshots = connection.execute(
            "SELECT snapshot_id, payload FROM acquisition_snapshots WHERE family = 'bars'"
        ).fetchall()
        for snapshot_id, payload_text in snapshots:
            payload = cast("dict[str, Any]", json.loads(str(payload_text)))
            for row in payload["frame"]:
                row.pop("provider_timestamp_label")
                row["timestamp_position"] = "provider_label"
            connection.execute(
                "UPDATE acquisition_snapshots SET payload = ? WHERE snapshot_id = ?",
                [json.dumps(payload, sort_keys=True, separators=(",", ":")), snapshot_id],
            )
        connection.execute(
            "UPDATE bar_rows SET timestamp_position = 'provider_label'"
        )
        connection.execute("ALTER TABLE bar_rows DROP COLUMN provider_timestamp_label")
    connection.execute("DROP TABLE store_migration")
    connection.execute("UPDATE schema_version SET version = 1")
    count_row = connection.execute("SELECT count(*) FROM acquisition_occurrences").fetchone()
    assert count_row is not None
    occurrence_count = int(count_row[0])
    connection.close()
    return labels, occurrence_count


def test_migrate_store_preserves_occurrences_catalog_and_durable_lineage(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source-v1.duckdb"
    destination = tmp_path / "destination-v2.duckdb"
    labels, occurrence_count = _legacy_source(source)
    source_before = sha256(source.read_bytes()).hexdigest()

    report = migrate_store(source, destination)

    assert sha256(source.read_bytes()).hexdigest() == source_before
    assert report.source_store_sha256 == source_before
    assert report.source_schema_version == 1
    assert report.target_schema_version == 2
    assert report.source_snapshot_count == 2
    assert report.target_snapshot_count == 2
    assert report.occurrence_count == occurrence_count == 3
    assert [snapshot.occurrence_count for snapshot in report.snapshots] == [2, 1]
    assert report.to_dict()["source_store_sha256"] == source_before
    assert verify_store(destination).is_valid

    with DuckDBStore.open(destination, read_only=True) as store:
        assert store.schema_version == 2
        assert store.migration_lineage() == report
        assert store.load_catalog().instruments
        assert isinstance(store.load_snapshot(report.snapshots[0].target_snapshot_id), BarSet)
        dataset = next(item for item in store.list_datasets() if item.family == "bars")
        migrated_bars = store.query_bars(dataset.scope_key)
        assert migrated_bars["timestamp_position"].tolist() == ["unspecified"] * 2
        assert migrated_bars["provider_timestamp_label"].tolist() == labels

    with pytest.raises(StoreError, match="not supported"):
        DuckDBStore.open(source, read_only=True)


def test_migrate_store_accepts_current_shaped_v1_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    source = tmp_path / "current-shape-v1.duckdb"
    destination = tmp_path / "migrated.duckdb"
    _legacy_source(source, legacy_bar_shape=False)
    destination.write_bytes(b"preserve me")

    with pytest.raises(StoreError, match="already exists"):
        migrate_store(source, destination)
    assert destination.read_bytes() == b"preserve me"

    destination.unlink()
    report = migrate_store(source, destination)
    assert report.occurrence_count == 3
    assert verify_store(destination).is_valid


def test_store_open_rejects_a_current_version_with_an_incompatible_shape(
    tmp_path: Path,
) -> None:
    path = tmp_path / "incompatible-v2.duckdb"
    DuckDBStore.create(path).close()
    connection = duckdb.connect(str(path))
    connection.execute("ALTER TABLE bar_rows DROP COLUMN provider_timestamp_label")
    connection.close()

    with pytest.raises(StoreError, match="unexpected column contract"):
        DuckDBStore.open(path, read_only=True)


def test_migrate_store_requires_distinct_paths_and_removes_failed_staging(
    tmp_path: Path,
) -> None:
    source = tmp_path / "invalid-v1.duckdb"
    DuckDBStore.create(source).close()
    connection = duckdb.connect(str(source))
    connection.execute("DROP TABLE store_migration")
    connection.execute("UPDATE schema_version SET version = 1")
    connection.execute("DROP TABLE bar_rows")
    connection.close()

    with pytest.raises(StoreError, match="must differ"):
        migrate_store(source, source)
    destination = tmp_path / "failed.duckdb"
    with pytest.raises(StoreError, match="unsupported v1 bar_rows schema"):
        migrate_store(source, destination)
    assert not destination.exists()
