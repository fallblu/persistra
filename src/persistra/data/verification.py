"""Read-only integrity verification for Persistra DuckDB stores."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import duckdb
import pandas as pd

from persistra._json import strict_json_loads
from persistra.data.store import (  # pyright: ignore[reportPrivateUsage]
    _DATASET_TABLES,
    STORE_SCHEMA_VERSION,
    _database_value,
    _decode_result,
    _duckdb_type,
    _encode_result,
    _frame,
    _json,
    _occurrence_payload,
    _records,
    _snapshot_payload,
    _source_hash,
)
from persistra.validation import ValidationFinding, ValidationSeverity

__all__ = ["StoreVerification", "verify_store"]

STORE_VERIFICATION_VERSION = 1


@dataclass(frozen=True, slots=True)
class StoreVerification:
    """Structured result of one read-only store integrity audit."""

    path: Path
    findings: tuple[ValidationFinding, ...]
    snapshot_count: int | None
    occurrence_count: int | None

    @property
    def is_valid(self) -> bool:
        """Return whether the audit found no integrity errors."""
        return not any(item.severity is ValidationSeverity.ERROR for item in self.findings)

    def to_dict(self) -> dict[str, object]:
        """Return the versioned JSON representation of this audit."""
        return {
            "verification_version": STORE_VERIFICATION_VERSION,
            "path": str(self.path),
            "valid": self.is_valid,
            "snapshot_count": self.snapshot_count,
            "occurrence_count": self.occurrence_count,
            "findings": [item.to_dict() for item in self.findings],
        }


def _column_type(dtype: str) -> str:
    value = _duckdb_type(dtype)
    return "TIMESTAMP WITH TIME ZONE" if value == "TIMESTAMPTZ" else value


_SCHEMA_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "schema_version": (("version", "INTEGER", "NO"),),
    "acquisition_snapshots": (
        ("snapshot_id", "VARCHAR", "NO"),
        ("family", "VARCHAR", "NO"),
        ("scope_key", "VARCHAR", "NO"),
        ("content_hash", "VARCHAR", "NO"),
        ("payload", "VARCHAR", "NO"),
        ("saved_order", "BIGINT", "NO"),
    ),
    "acquisition_occurrences": (
        ("saved_order", "BIGINT", "NO"),
        ("snapshot_id", "VARCHAR", "NO"),
        ("retrieved_at", "TIMESTAMP WITH TIME ZONE", "NO"),
        ("metadata", "VARCHAR", "NO"),
    ),
    "catalog_instruments": (
        ("instrument_id", "VARCHAR", "NO"),
        ("kind", "VARCHAR", "NO"),
        ("display_name", "VARCHAR", "NO"),
        ("base_currency", "VARCHAR", "YES"),
        ("quote_currency", "VARCHAR", "YES"),
    ),
    "catalog_listings": (
        ("listing_id", "VARCHAR", "NO"),
        ("instrument_id", "VARCHAR", "NO"),
        ("symbol", "VARCHAR", "NO"),
        ("exchange", "VARCHAR", "YES"),
        ("mic", "VARCHAR", "YES"),
        ("currency", "VARCHAR", "YES"),
        ("source_timezone", "VARCHAR", "YES"),
    ),
    "catalog_provider_symbols": (
        ("provider", "VARCHAR", "NO"),
        ("kind", "VARCHAR", "NO"),
        ("symbol", "VARCHAR", "NO"),
        ("instrument_id", "VARCHAR", "NO"),
        ("listing_id", "VARCHAR", "YES"),
    ),
    **{
        table.name: (
            ("snapshot_id", "VARCHAR", "NO"),
            ("row_key", "VARCHAR", "NO"),
            *((name, _column_type(dtype), "YES") for name, dtype in table.dtypes.items()),
        )
        for table in _DATASET_TABLES.values()
    },
}

_REQUIRED_CONSTRAINTS = {
    ("acquisition_snapshots", "PRIMARY KEY", ("snapshot_id",), None, ()),
    ("acquisition_snapshots", "UNIQUE", ("saved_order",), None, ()),
    (
        "acquisition_snapshots",
        "UNIQUE",
        ("family", "scope_key", "content_hash"),
        None,
        (),
    ),
    ("acquisition_occurrences", "PRIMARY KEY", ("saved_order",), None, ()),
    (
        "acquisition_occurrences",
        "FOREIGN KEY",
        ("snapshot_id",),
        "acquisition_snapshots",
        ("snapshot_id",),
    ),
    ("catalog_instruments", "PRIMARY KEY", ("instrument_id",), None, ()),
    ("catalog_listings", "PRIMARY KEY", ("listing_id",), None, ()),
    (
        "catalog_listings",
        "FOREIGN KEY",
        ("instrument_id",),
        "catalog_instruments",
        ("instrument_id",),
    ),
    (
        "catalog_provider_symbols",
        "PRIMARY KEY",
        ("provider", "kind", "symbol"),
        None,
        (),
    ),
    (
        "catalog_provider_symbols",
        "FOREIGN KEY",
        ("instrument_id",),
        "catalog_instruments",
        ("instrument_id",),
    ),
    (
        "catalog_provider_symbols",
        "FOREIGN KEY",
        ("listing_id",),
        "catalog_listings",
        ("listing_id",),
    ),
    *(
        (
            table.name,
            "PRIMARY KEY",
            ("snapshot_id", "row_key"),
            None,
            (),
        )
        for table in _DATASET_TABLES.values()
    ),
    *(
        (
            table.name,
            "FOREIGN KEY",
            ("snapshot_id",),
            "acquisition_snapshots",
            ("snapshot_id",),
        )
        for table in _DATASET_TABLES.values()
    ),
}


def _error(code: str, message: str, location: str | None = None) -> ValidationFinding:
    return ValidationFinding(code, ValidationSeverity.ERROR, message, location)


def verify_store(path: str | Path) -> StoreVerification:
    """Audit one existing store without changing its schema, rows, or files."""
    target = Path(path).expanduser().absolute()
    if not target.is_file():
        return StoreVerification(
            target,
            (_error("store.path.missing", "store is not a regular file"),),
            None,
            None,
        )
    try:
        connection = duckdb.connect(str(target), read_only=True)
    except duckdb.Error as error:
        return StoreVerification(
            target,
            (
                _error(
                    "store.open.invalid",
                    f"store is not a readable DuckDB database: {error}",
                ),
            ),
            None,
            None,
        )

    findings: list[ValidationFinding] = []
    snapshot_count: int | None = None
    occurrence_count: int | None = None
    try:
        schema_valid = _verify_schema(connection, findings)
        if schema_valid:
            snapshot_count, occurrence_count = _verify_contents(connection, findings)
    except Exception as error:
        findings.append(_error("store.audit.failed", f"store audit could not complete: {error}"))
    finally:
        connection.close()
    return StoreVerification(
        target,
        tuple(sorted(findings, key=lambda item: (item.code, item.location or "", item.message))),
        snapshot_count,
        occurrence_count,
    )


def _verify_schema(
    connection: duckdb.DuckDBPyConnection,
    findings: list[ValidationFinding],
) -> bool:
    initial_count = len(findings)
    rows = connection.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'main'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    actual: dict[str, list[tuple[str, str, str]]] = {}
    for table_name, column_name, data_type, is_nullable in rows:
        actual.setdefault(str(table_name), []).append(
            (str(column_name), str(data_type), str(is_nullable))
        )
    for table_name, expected in _SCHEMA_COLUMNS.items():
        columns = actual.get(table_name)
        if columns is None:
            findings.append(
                _error(
                    "store.schema.missing",
                    f"required table is missing: {table_name}",
                    table_name,
                )
            )
        elif tuple(columns) != expected:
            findings.append(
                _error(
                    "store.schema.shape",
                    f"required table has an unexpected column contract: {table_name}",
                    table_name,
                )
            )

    constraint_rows = connection.execute(
        """
        SELECT
            table_name,
            constraint_type,
            constraint_column_names,
            referenced_table,
            referenced_column_names
        FROM duckdb_constraints()
        WHERE schema_name = 'main'
        """
    ).fetchall()
    actual_constraints = {
        (
            str(row[0]),
            str(row[1]),
            tuple(str(item) for item in row[2]),
            None if row[3] is None else str(row[3]),
            tuple(str(item) for item in row[4]),
        )
        for row in constraint_rows
    }
    missing_constraints = _REQUIRED_CONSTRAINTS - actual_constraints
    for table_name in sorted({item[0] for item in missing_constraints}):
        findings.append(
            _error(
                "store.schema.constraints",
                f"required keys or references are missing from table: {table_name}",
                table_name,
            )
        )

    if "schema_version" in actual:
        version_rows = connection.execute("SELECT version FROM schema_version").fetchall()
        if len(version_rows) != 1 or type(version_rows[0][0]) is not int:
            findings.append(
                _error(
                    "store.schema.version",
                    "schema_version must contain exactly one integer row",
                    "schema_version",
                )
            )
        elif version_rows[0][0] != STORE_SCHEMA_VERSION:
            findings.append(
                _error(
                    "store.schema.version_unsupported",
                    f"store schema version is not supported: {version_rows[0][0]}",
                    "schema_version",
                )
            )
    return len(findings) == initial_count


type _SnapshotRow = tuple[str, str, str, str, str, int]
type _OccurrenceRow = tuple[int, str, str, str]


def _verify_contents(
    connection: duckdb.DuckDBPyConnection,
    findings: list[ValidationFinding],
) -> tuple[int, int]:
    snapshots = cast(
        "list[_SnapshotRow]",
        connection.execute(
            """
            SELECT snapshot_id, family, scope_key, content_hash, payload, saved_order
            FROM acquisition_snapshots
            ORDER BY saved_order, snapshot_id
            """
        ).fetchall(),
    )
    occurrences = cast(
        "list[_OccurrenceRow]",
        connection.execute(
            """
            SELECT saved_order, snapshot_id, cast(retrieved_at AS VARCHAR), metadata
            FROM acquisition_occurrences
            ORDER BY saved_order, snapshot_id
            """
        ).fetchall(),
    )
    _verify_inventory(snapshots, occurrences, findings)
    creation_payloads = _verify_snapshots(snapshots, occurrences, findings)
    _verify_typed_rows(connection, snapshots, creation_payloads, findings)
    return len(snapshots), len(occurrences)


def _verify_inventory(
    snapshots: list[_SnapshotRow],
    occurrences: list[_OccurrenceRow],
    findings: list[ValidationFinding],
) -> None:
    orders = [row[0] for row in occurrences]
    if orders != list(range(1, len(orders) + 1)):
        findings.append(
            _error(
                "store.inventory.order",
                "occurrence saved_order values must be contiguous and start at one",
                "acquisition_occurrences",
            )
        )
    snapshot_ids = {row[0] for row in snapshots}
    grouped: dict[str, list[_OccurrenceRow]] = {}
    for occurrence in occurrences:
        grouped.setdefault(occurrence[1], []).append(occurrence)
        if occurrence[1] not in snapshot_ids:
            findings.append(
                _error(
                    "store.reference.orphan",
                    f"occurrence references an absent snapshot: {occurrence[1]}",
                    f"occurrence:{occurrence[0]}",
                )
            )
    for snapshot_id, _family, _scope, _hash, _payload, saved_order in snapshots:
        related = grouped.get(snapshot_id, [])
        if not related:
            findings.append(
                _error(
                    "store.snapshot.occurrence_missing",
                    "snapshot has no acquisition occurrence",
                    f"snapshot:{snapshot_id}",
                )
            )
            continue
        first_order = min(item[0] for item in related)
        if saved_order != first_order:
            findings.append(
                _error(
                    "store.occurrence.chronology",
                    "snapshot saved_order does not identify its first occurrence",
                    f"snapshot:{snapshot_id}",
                )
            )


def _verify_snapshots(
    snapshots: list[_SnapshotRow],
    occurrences: list[_OccurrenceRow],
    findings: list[ValidationFinding],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[_OccurrenceRow]] = {}
    for occurrence in occurrences:
        grouped.setdefault(occurrence[1], []).append(occurrence)
    creation_payloads: dict[str, dict[str, Any]] = {}
    for snapshot_id, family, scope_key, content_hash, payload_text, saved_order in snapshots:
        location = f"snapshot:{snapshot_id}"
        try:
            raw_payload = strict_json_loads(payload_text)
            if not isinstance(raw_payload, dict):
                raise TypeError("snapshot payload must be a JSON object")
            payload = cast("dict[str, Any]", raw_payload)
        except (TypeError, ValueError) as error:
            findings.append(
                _error("store.snapshot.payload", f"snapshot payload is invalid: {error}", location)
            )
            continue
        recomputed_hash = _source_hash(payload)
        if recomputed_hash != content_hash:
            findings.append(
                _error(
                    "store.snapshot.hash",
                    "snapshot content_hash does not match its payload",
                    location,
                )
            )
        recomputed_id = sha256(f"{family}\x1f{scope_key}\x1f{content_hash}".encode()).hexdigest()
        if recomputed_id != snapshot_id:
            findings.append(
                _error(
                    "store.snapshot.identity",
                    "snapshot_id does not match family, scope, and content_hash",
                    location,
                )
            )
        for occurrence in grouped.get(snapshot_id, []):
            decoded = _decode_occurrence(
                family,
                scope_key,
                payload_text,
                occurrence,
                payload,
                findings,
            )
            if decoded is not None and occurrence[0] == saved_order:
                creation_payloads[snapshot_id] = decoded
    return creation_payloads


def _decode_occurrence(
    family: str,
    scope_key: str,
    payload_text: str,
    occurrence: _OccurrenceRow,
    stored_payload: dict[str, Any],
    findings: list[ValidationFinding],
) -> dict[str, Any] | None:
    saved_order, _snapshot_id, retrieved_at, metadata_text = occurrence
    location = f"occurrence:{saved_order}"
    try:
        raw_metadata = strict_json_loads(metadata_text)
        if not isinstance(raw_metadata, dict):
            raise TypeError("occurrence metadata must be a JSON object")
        metadata = cast("dict[str, Any]", raw_metadata)
        metadata_retrieved_at = metadata.get("retrieved_at")
        if not isinstance(metadata_retrieved_at, str) or datetime.fromisoformat(
            metadata_retrieved_at
        ) != datetime.fromisoformat(retrieved_at):
            findings.append(
                _error(
                    "store.occurrence.chronology",
                    "metadata retrieved_at does not match the occurrence timestamp",
                    location,
                )
            )
        payload = _occurrence_payload(payload_text, metadata_text, retrieved_at)
        result = _decode_result(family, payload)
        decoded_family, decoded_scope, encoded, decoded_retrieved_at = _encode_result(result)
    except Exception as error:
        findings.append(
            _error(
                "store.occurrence.decode",
                f"stored occurrence cannot be decoded: {error}",
                location,
            )
        )
        return None
    if decoded_family != family:
        findings.append(
            _error(
                "store.snapshot.family",
                f"decoded family does not match inventory family: {decoded_family}",
                location,
            )
        )
    if decoded_scope != scope_key:
        findings.append(
            _error(
                "store.snapshot.scope",
                f"decoded scope does not match inventory scope: {decoded_scope}",
                location,
            )
        )
    if decoded_retrieved_at != datetime.fromisoformat(retrieved_at):
        findings.append(
            _error(
                "store.occurrence.chronology",
                "decoded result timestamp does not match the occurrence timestamp",
                location,
            )
        )
    if _canonical_json(_snapshot_payload(encoded)) != _canonical_json(stored_payload):
        findings.append(
            _error(
                "store.snapshot.payload",
                "decoded snapshot does not reproduce the stored payload",
                location,
            )
        )
    return encoded


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json)


def _verify_typed_rows(
    connection: duckdb.DuckDBPyConnection,
    snapshots: list[_SnapshotRow],
    creation_payloads: dict[str, dict[str, Any]],
    findings: list[ValidationFinding],
) -> None:
    snapshot_families = {row[0]: row[1] for row in snapshots}
    for family, table in _DATASET_TABLES.items():
        snapshot_table_family = table.snapshot_family or family
        columns = ", ".join(
            (f'cast("{name}" AS VARCHAR)' if dtype == "datetime64[ns, UTC]" else f'"{name}"')
            for name, dtype in table.dtypes.items()
        )
        rows = connection.execute(
            f"SELECT snapshot_id, row_key, {columns} FROM {table.name} "
            "ORDER BY snapshot_id, row_key"
        ).fetchall()
        grouped: dict[str, list[tuple[object, ...]]] = {}
        for row in rows:
            snapshot_id = str(row[0])
            grouped.setdefault(snapshot_id, []).append(tuple(row[1:]))
            snapshot_family = snapshot_families.get(snapshot_id)
            if snapshot_family is None:
                findings.append(
                    _error(
                        "store.rows.orphan",
                        f"typed row references an absent snapshot: {snapshot_id}",
                        table.name,
                    )
                )
            elif snapshot_family != snapshot_table_family:
                findings.append(
                    _error(
                        "store.rows.family",
                        f"typed row belongs to {snapshot_family}, not {snapshot_table_family}",
                        f"snapshot:{snapshot_id}",
                    )
                )
        for snapshot_id, snapshot_family in snapshot_families.items():
            if snapshot_family != snapshot_table_family:
                continue
            payload = creation_payloads.get(snapshot_id)
            if payload is None:
                continue
            expected = _expected_rows(payload, table.frame_key, table.dtypes, table.row_key)
            actual = [
                (
                    str(row[0]),
                    *(
                        _comparable(value, dtype)
                        for value, dtype in zip(row[1:], table.dtypes.values(), strict=True)
                    ),
                )
                for row in grouped.get(snapshot_id, [])
            ]
            if sorted(expected, key=lambda row: str(row[0])) != sorted(
                actual, key=lambda row: str(row[0])
            ):
                findings.append(
                    _error(
                        "store.rows.mismatch",
                        f"{table.name} does not match the normalized snapshot payload",
                        f"snapshot:{snapshot_id}",
                    )
                )


def _expected_rows(
    payload: dict[str, Any],
    frame_key: str,
    dtypes: dict[str, str],
    row_key_fields: tuple[str, ...],
) -> list[tuple[object, ...]]:
    raw_records = cast("list[dict[str, Any]]", payload[frame_key])
    records = _records(_frame(raw_records, dtypes))
    return [
        (
            json.dumps(
                [record[field] for field in row_key_fields],
                separators=(",", ":"),
                default=_json,
            ),
            *(
                _comparable(_database_value(record[field]), dtype)
                for field, dtype in dtypes.items()
            ),
        )
        for record in records
    ]


def _comparable(value: object, dtype: str) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return ("missing",)
    if isinstance(value, float) and math.isnan(value):
        return ("missing",)
    if dtype == "datetime64[ns]":
        if isinstance(value, str):
            return date.fromisoformat(value.split("T", maxsplit=1)[0]).isoformat()
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
    if dtype == "datetime64[ns, UTC]":
        moment = datetime.fromisoformat(value) if isinstance(value, str) else value
        if isinstance(moment, pd.Timestamp):
            moment = moment.to_pydatetime()
        if isinstance(moment, datetime):
            return moment.astimezone(UTC).isoformat()
    return value
