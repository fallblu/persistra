# pyright: reportPrivateUsage=false
"""Non-destructive migrations for versioned Persistra stores."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import duckdb
import pandas as pd

from persistra._json import strict_json_loads
from persistra.data.store import (
    STORE_SCHEMA_VERSION,
    DuckDBStore,
    MigratedSnapshot,
    StoreMigration,
    _decode_result,
    _restore_retrieved_at,
)
from persistra.data.verification import _SCHEMA_COLUMNS, verify_store
from persistra.errors import StoreError

__all__ = ["migrate_store"]

_LEGACY_STORE_SCHEMA_VERSION = 1


def migrate_store(source: str | Path, destination: str | Path) -> StoreMigration:
    """Migrate one v1 store into a new v2 store without changing the source."""
    source_path = Path(source).expanduser().absolute()
    destination_path = Path(destination).expanduser().absolute()
    if source_path == destination_path:
        raise StoreError("source and destination stores must differ")
    if not source_path.is_file():
        raise StoreError(f"source store does not exist: {source_path}")
    if destination_path.exists() or destination_path.is_symlink():
        raise StoreError(f"destination store already exists: {destination_path}")
    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StoreError(f"could not create store directory: {destination_path.parent}") from error

    source_digest = _file_sha256(source_path)
    try:
        with TemporaryDirectory(
            dir=destination_path.parent,
            prefix=f".{destination_path.name}.migration.",
        ) as staging_directory:
            staged_path = Path(staging_directory) / "store.duckdb"
            report = _migrate_to_staged_store(source_path, staged_path, source_digest)
            if _file_sha256(source_path) != source_digest:
                raise StoreError("source store changed during migration")
            try:
                os.link(staged_path, destination_path)
            except FileExistsError as error:
                raise StoreError(f"destination store already exists: {destination_path}") from error
            except OSError as error:
                raise StoreError(f"could not publish migrated store: {destination_path}") from error
    except StoreError:
        raise
    except Exception as error:
        raise StoreError("store migration failed") from error
    return report


def _migrate_to_staged_store(
    source_path: Path,
    staged_path: Path,
    source_digest: str,
) -> StoreMigration:
    try:
        source_connection = duckdb.connect(str(source_path), read_only=True)
    except duckdb.Error as error:
        raise StoreError(f"source store is not a valid DuckDB database: {source_path}") from error
    try:
        _validate_v1_schema(source_connection)
        source_store = DuckDBStore(source_path, source_connection)
        with DuckDBStore.create(staged_path) as target_store:
            target_store.save_catalog(source_store.load_catalog())
            report = _migrate_occurrences(
                source_connection,
                target_store,
                source_digest,
            )
            target_store._connection.execute(
                """
                INSERT INTO store_migration VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    report.source_store_sha256,
                    report.source_schema_version,
                    report.target_schema_version,
                    report.source_snapshot_count,
                    report.target_snapshot_count,
                    report.occurrence_count,
                    json.dumps(
                        [asdict(snapshot) for snapshot in report.snapshots],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ],
            )
    finally:
        source_connection.close()

    verification = verify_store(staged_path)
    if not verification.is_valid:
        codes = ", ".join(finding.code for finding in verification.findings)
        raise StoreError(f"migrated store failed verification: {codes}")
    return report


def _validate_v1_schema(connection: duckdb.DuckDBPyConnection) -> None:
    try:
        version_rows = connection.execute("SELECT version FROM schema_version").fetchall()
    except duckdb.Error as error:
        raise StoreError("source store schema is missing or invalid") from error
    if version_rows != [(_LEGACY_STORE_SCHEMA_VERSION,)]:
        raise StoreError("source store schema version is not supported for migration")

    rows = connection.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'main'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    actual: dict[str, tuple[tuple[str, str, str], ...]] = {}
    grouped: dict[str, list[tuple[str, str, str]]] = {}
    for table_name, column_name, data_type, is_nullable in rows:
        grouped.setdefault(str(table_name), []).append(
            (str(column_name), str(data_type), str(is_nullable))
        )
    actual = {name: tuple(columns) for name, columns in grouped.items()}

    expected = {
        name: columns for name, columns in _SCHEMA_COLUMNS.items() if name != "store_migration"
    }
    current_bar_columns = expected["bar_rows"]
    legacy_bar_columns = tuple(
        column for column in current_bar_columns if column[0] != "provider_timestamp_label"
    )
    for table_name, columns in expected.items():
        actual_columns = actual.get(table_name)
        if table_name == "bar_rows":
            if actual_columns not in {columns, legacy_bar_columns}:
                raise StoreError("source store has an unsupported v1 bar_rows schema")
        elif actual_columns != columns:
            raise StoreError(f"source store has an unsupported v1 table schema: {table_name}")


def _migrate_occurrences(
    source: duckdb.DuckDBPyConnection,
    target: DuckDBStore,
    source_digest: str,
) -> StoreMigration:
    source_snapshot_count = _count(source, "SELECT count(*) FROM acquisition_snapshots")
    rows = cast(
        "list[tuple[object, object, object, object, object, object]]",
        source.execute(
            """
        SELECT
            occurrences.saved_order,
            snapshots.snapshot_id,
            snapshots.family,
            snapshots.payload,
            occurrences.metadata,
            cast(occurrences.retrieved_at AS VARCHAR)
        FROM acquisition_occurrences AS occurrences
        JOIN acquisition_snapshots AS snapshots
          ON snapshots.snapshot_id = occurrences.snapshot_id
        ORDER BY occurrences.saved_order
        """
        ).fetchall(),
    )
    if [int(cast("Any", row[0])) for row in rows] != list(range(1, len(rows) + 1)):
        raise StoreError("source occurrence order is not contiguous")

    mappings: dict[str, tuple[str, int]] = {}
    mapping_order: list[str] = []
    for _, source_snapshot_id, family, payload_text, metadata_text, retrieved_at in rows:
        source_id = str(source_snapshot_id)
        payload = _json_object(str(payload_text), "snapshot payload")
        metadata = _json_object(str(metadata_text), "occurrence metadata")
        if str(family) == "bars":
            _migrate_bar_payload(payload)
        payload["metadata"] = metadata
        restored = cast(
            "dict[str, Any]",
            _restore_retrieved_at(payload, str(retrieved_at)),
        )
        result = _decode_result(str(family), restored)
        target_id = target.save(result)
        if source_id not in mappings:
            mappings[source_id] = (target_id, 1)
            mapping_order.append(source_id)
        else:
            mapped = mappings[source_id]
            if mapped[0] != target_id:
                raise StoreError("one source snapshot mapped to multiple target snapshots")
            mappings[source_id] = (mapped[0], mapped[1] + 1)

    if len(mappings) != source_snapshot_count:
        raise StoreError("source store contains a snapshot without an occurrence")
    snapshots = tuple(
        MigratedSnapshot(source_id, mappings[source_id][0], mappings[source_id][1])
        for source_id in mapping_order
    )
    target_snapshot_count = _count(
        target._connection, "SELECT count(*) FROM acquisition_snapshots"
    )
    return StoreMigration(
        source_store_sha256=source_digest,
        source_schema_version=_LEGACY_STORE_SCHEMA_VERSION,
        target_schema_version=STORE_SCHEMA_VERSION,
        source_snapshot_count=source_snapshot_count,
        target_snapshot_count=target_snapshot_count,
        occurrence_count=len(rows),
        snapshots=snapshots,
    )


def _migrate_bar_payload(payload: dict[str, Any]) -> None:
    frame = payload.get("frame")
    if not isinstance(frame, list):
        raise StoreError("source bar snapshot payload is invalid")
    for item in cast("list[object]", frame):
        if not isinstance(item, dict):
            raise StoreError("source bar snapshot row is invalid")
        row = cast("dict[str, Any]", item)
        position = row.get("timestamp_position")
        if "provider_timestamp_label" not in row:
            row["provider_timestamp_label"] = _legacy_provider_timestamp_label(row)
        if position == "provider_label":
            row["timestamp_position"] = "unspecified"


def _legacy_provider_timestamp_label(row: dict[str, Any]) -> str | None:
    position = row.get("timestamp_position")
    provider = row.get("provider")
    if position == "provider_label":
        if provider != "alpha_vantage":
            raise StoreError("only Alpha Vantage provider_label bars can be migrated")
        timestamp = row.get("timestamp")
        timezone_name = row.get("source_timezone")
        if not isinstance(timestamp, str) or not isinstance(timezone_name, str):
            raise StoreError("legacy provider-label bar lacks timestamp provenance")
        try:
            localized = pd.Timestamp(timestamp).tz_convert(ZoneInfo(timezone_name))
        except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
            raise StoreError(
                "legacy provider-label bar has invalid timestamp provenance"
            ) from error
        return localized.strftime("%Y-%m-%d %H:%M:%S")
    if provider == "alpha_vantage" and row.get("date") is not None:
        return str(row["date"])[:10]
    return None


def _json_object(value: str, name: str) -> dict[str, Any]:
    try:
        parsed = strict_json_loads(value)
    except ValueError as error:
        raise StoreError(f"source {name} is invalid") from error
    if not isinstance(parsed, dict):
        raise StoreError(f"source {name} is invalid")
    return cast("dict[str, Any]", parsed)


def _count(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise StoreError("store count query returned no row")
    return int(row[0])


def _file_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise StoreError(f"could not read store: {path}") from error
    return digest.hexdigest()
