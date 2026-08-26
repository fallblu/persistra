"""Tests for read-only DuckDB store integrity verification."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING

import duckdb

import persistra.data.store as store_module
from persistra.data import DuckDBStore, synthetic, verify_store

if TYPE_CHECKING:
    from pathlib import Path


def _codes(path: Path) -> set[str]:
    return {item.code for item in verify_store(path).findings}


def test_verify_store_decodes_every_family_without_mutating_the_file(tmp_path: Path) -> None:
    path = tmp_path / "complete.duckdb"
    results = (
        synthetic.bars(periods=2),
        synthetic.quotes(),
        synthetic.top_of_book(),
        synthetic.option_chain(),
        synthetic.series(periods=2),
        synthetic.vintage_series(periods=2),
        synthetic.vintage_dates(),
        synthetic.exchange_rate(),
        synthetic.commodity_spot(),
        synthetic.search(),
        synthetic.market_status(),
        synthetic.index_catalog(),
    )
    with DuckDBStore.create(path) as store:
        for result in results:
            store.save(result)
        store.save(results[0])
    before = sha256(path.read_bytes()).hexdigest()

    verification = verify_store(path)

    assert verification.is_valid
    assert verification.findings == ()
    assert verification.snapshot_count == len(results)
    assert verification.occurrence_count == len(results) + 1
    assert verification.to_dict()["verification_version"] == 1
    assert sha256(path.read_bytes()).hexdigest() == before


def test_verify_store_reports_missing_invalid_and_unsupported_schema(
    tmp_path: Path,
) -> None:
    missing = verify_store(tmp_path / "missing.duckdb")
    assert not missing.is_valid
    assert {item.code for item in missing.findings} == {"store.path.missing"}

    invalid_path = tmp_path / "invalid.duckdb"
    invalid_path.write_bytes(b"not a database")
    assert "store.open.invalid" in _codes(invalid_path)

    unsupported_path = tmp_path / "unsupported.duckdb"
    DuckDBStore.create(unsupported_path).close()
    connection = duckdb.connect(str(unsupported_path))
    connection.execute("UPDATE schema_version SET version = 99")
    connection.close()
    assert "store.schema.version_unsupported" in _codes(unsupported_path)

    missing_table_path = tmp_path / "missing-table.duckdb"
    DuckDBStore.create(missing_table_path).close()
    connection = duckdb.connect(str(missing_table_path))
    connection.execute("DROP TABLE bar_rows")
    connection.close()
    assert "store.schema.missing" in _codes(missing_table_path)


def _insert_snapshot(
    path: Path,
    *,
    snapshot_id: str,
    content_hash: str,
    snapshot_order: int,
) -> None:
    result = synthetic.series(periods=2)
    family, scope, payload, retrieved_at = store_module._encode_result(  # pyright: ignore[reportPrivateUsage]
        result
    )
    payload_text = json.dumps(
        store_module._snapshot_payload(payload),  # pyright: ignore[reportPrivateUsage]
        sort_keys=True,
        separators=(",", ":"),
        default=store_module._json,  # pyright: ignore[reportPrivateUsage]
    )
    metadata_text = json.dumps(
        payload["metadata"],
        sort_keys=True,
        separators=(",", ":"),
        default=store_module._json,  # pyright: ignore[reportPrivateUsage]
    )
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        INSERT INTO acquisition_snapshots
        (snapshot_id, family, scope_key, content_hash, payload, saved_order)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [snapshot_id, family, scope, content_hash, payload_text, snapshot_order],
    )
    connection.execute(
        """
        INSERT INTO acquisition_occurrences
        (saved_order, snapshot_id, retrieved_at, metadata)
        VALUES (1, ?, ?, ?)
        """,
        [snapshot_id, retrieved_at, metadata_text],
    )
    connection.close()


def test_verify_store_recomputes_snapshot_identity_and_chronology(tmp_path: Path) -> None:
    identity_path = tmp_path / "identity.duckdb"
    DuckDBStore.create(identity_path).close()
    _insert_snapshot(
        identity_path,
        snapshot_id="wrong-snapshot-id",
        content_hash="wrong-content-hash",
        snapshot_order=1,
    )
    identity_codes = _codes(identity_path)
    assert "store.snapshot.hash" in identity_codes
    assert "store.snapshot.identity" in identity_codes

    chronology_path = tmp_path / "chronology.duckdb"
    DuckDBStore.create(chronology_path).close()
    result = synthetic.series(periods=2)
    family, scope, payload, _retrieved_at = store_module._encode_result(  # pyright: ignore[reportPrivateUsage]
        result
    )
    content_hash = store_module._source_hash(payload)  # pyright: ignore[reportPrivateUsage]
    snapshot_id = sha256(f"{family}\x1f{scope}\x1f{content_hash}".encode()).hexdigest()
    _insert_snapshot(
        chronology_path,
        snapshot_id=snapshot_id,
        content_hash=content_hash,
        snapshot_order=99,
    )
    assert "store.occurrence.chronology" in _codes(chronology_path)


def test_verify_store_detects_payload_metadata_and_typed_row_corruption(
    tmp_path: Path,
) -> None:
    row_path = tmp_path / "row.duckdb"
    with DuckDBStore.create(row_path) as store:
        store.save(synthetic.series(periods=2))
    connection = duckdb.connect(str(row_path))
    connection.execute("UPDATE series_rows SET value = value + 1")
    connection.close()
    assert "store.rows.mismatch" in _codes(row_path)

    metadata_path = tmp_path / "metadata.duckdb"
    with DuckDBStore.create(metadata_path) as store:
        store.save(synthetic.series(periods=2))
    connection = duckdb.connect(str(metadata_path))
    connection.execute("UPDATE acquisition_occurrences SET metadata = '{}'")
    connection.close()
    metadata_codes = _codes(metadata_path)
    assert "store.occurrence.chronology" in metadata_codes
    assert "store.occurrence.decode" in metadata_codes

    payload_path = tmp_path / "payload.duckdb"
    DuckDBStore.create(payload_path).close()
    connection = duckdb.connect(str(payload_path))
    connection.execute(
        """
        INSERT INTO acquisition_snapshots
        VALUES ('bad', 'series', 'scope', 'hash', '{', 1)
        """
    )
    connection.execute(
        """
        INSERT INTO acquisition_occurrences
        VALUES (1, 'bad', ?, '{}')
        """,
        [datetime.now(UTC)],
    )
    connection.close()
    assert "store.snapshot.payload" in _codes(payload_path)


def test_verification_finding_contract_rejects_invalid_codes() -> None:
    from persistra.validation import ValidationFinding, ValidationSeverity

    try:
        ValidationFinding("INVALID", ValidationSeverity.ERROR, "message")
    except ValueError as error:
        assert "code" in str(error)
    else:
        raise AssertionError("invalid finding code was accepted")
