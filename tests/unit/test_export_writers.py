from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
import pytest

from persistra._identity import scoped_identity_content_id
from persistra.db.migrations import CURRENT_SCHEMA_VERSION
from persistra.domain import ContentId
from persistra.errors import ExportSecurityError, ExportVerificationError
from persistra.results.exports import (
    _MANIFEST_SCHEMA,  # pyright: ignore[reportPrivateUsage]
    _TABLES,  # pyright: ignore[reportPrivateUsage]
    ExportService,
    _load_verified_export,  # pyright: ignore[reportPrivateUsage]
    _sha256,  # pyright: ignore[reportPrivateUsage]
    _validate_semantic_manifest,  # pyright: ignore[reportPrivateUsage]
)
from persistra.simulation import RunRecordId

if TYPE_CHECKING:
    from pathlib import Path


def _semantic_manifest(equity_rows: int) -> dict[str, Any]:
    tables = {
        name: {
            "row_count": 0,
            "content_id": str(ContentId.from_bytes(name.encode())),
        }
        for name in _TABLES
    }
    tables["equity"]["row_count"] = equity_rows
    return {
        "format_version": 2,
        "database_schema_version": CURRENT_SCHEMA_VERSION,
        "writer_version": "0",
        "duckdb_version": "0",
        "export_format": "duckdb",
        "run_record_id": str(RunRecordId.new().value),
        "simulation_kind": "vectorized",
        "simulation_id": "simulation",
        "execution_content_id": str(ContentId.from_bytes(b"execution")),
        "result_manifest_content_id": str(ContentId.from_bytes(b"result")),
        "fidelity_findings": [],
        "tables": tables,
    }


def _write_valid_bundle(root: Path) -> Path:
    import json

    bundle = root / "bundle"
    bundle.mkdir(parents=True)
    semantic = _semantic_manifest(1)
    semantic["export_format"] = "csv"
    files: list[dict[str, Any]] = []
    for table in _TABLES:
        file_path = bundle / f"{table}.csv"
        file_path.write_text(f"value\n{table}\n", encoding="utf-8")
        files.append(
            {
                "name": file_path.name,
                "sha256": _sha256(file_path),
                "byte_count": file_path.stat().st_size,
            }
        )
    content_id = scoped_identity_content_id(
        {"schema": _MANIFEST_SCHEMA, "manifest": semantic}
    )
    (bundle / "manifest.json").write_text(
        json.dumps(
            {**semantic, "manifest_content_id": str(content_id), "files": files},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return bundle


def _rewrite_manifest(bundle: Path, mutate: Any) -> None:
    import json

    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def test_bundle_verification_rejects_tampering(tmp_path: Path) -> None:
    valid = _write_valid_bundle(tmp_path)
    manifest, content_id = _load_verified_export(valid)
    assert manifest["export_format"] == "csv"
    assert str(content_id).startswith("sha256:")

    unlisted = _write_valid_bundle(tmp_path / "unlisted")
    (unlisted / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ExportSecurityError):
        _load_verified_export(unlisted)

    tampered = _write_valid_bundle(tmp_path / "tampered")
    (tampered / "equity.csv").write_text("value\naltered\n", encoding="utf-8")
    with pytest.raises(ExportVerificationError):
        _load_verified_export(tampered)

    escaping = _write_valid_bundle(tmp_path / "escaping")

    def rename_entry(manifest: dict[str, Any]) -> None:
        manifest["files"][0]["name"] = "../evil.csv"

    _rewrite_manifest(escaping, rename_entry)
    with pytest.raises((ExportSecurityError, ExportVerificationError)):
        _load_verified_export(escaping)

    duplicated = _write_valid_bundle(tmp_path / "duplicated")

    def duplicate_entry(manifest: dict[str, Any]) -> None:
        manifest["files"][1] = manifest["files"][0]

    _rewrite_manifest(duplicated, duplicate_entry)
    with pytest.raises(ExportVerificationError):
        _load_verified_export(duplicated)

    unkeyed = _write_valid_bundle(tmp_path / "unkeyed")

    def drop_key(manifest: dict[str, Any]) -> None:
        del manifest["fidelity_findings"]

    _rewrite_manifest(unkeyed, drop_key)
    with pytest.raises(ExportVerificationError):
        _load_verified_export(unkeyed)

    relabeled = _write_valid_bundle(tmp_path / "relabeled")

    def change_identity(manifest: dict[str, Any]) -> None:
        manifest["manifest_content_id"] = str(ContentId.from_bytes(b"other"))

    _rewrite_manifest(relabeled, change_identity)
    with pytest.raises(ExportVerificationError):
        _load_verified_export(relabeled)

    missing = tmp_path / "does-not-exist"
    with pytest.raises(ExportVerificationError):
        _load_verified_export(missing)


def test_manifest_validation_rejects_an_empty_equity_table() -> None:
    _validate_semantic_manifest(_semantic_manifest(1), expected_format="duckdb")
    with pytest.raises(ExportVerificationError):
        _validate_semantic_manifest(_semantic_manifest(0), expected_format="duckdb")


def test_duckdb_writer_cleans_staging_and_supports_retry(tmp_path: Path) -> None:
    output = tmp_path / "export.duckdb"
    staging = tmp_path / ".export.duckdb.partial"
    staging.write_bytes(b"stale partial content")
    frame = pd.DataFrame({"value": [1, 2]})

    with pytest.raises(TypeError):
        ExportService._write_duckdb(  # pyright: ignore[reportPrivateUsage]
            output,
            {"rows": frame},
            {"unserializable": object()},
            ContentId.from_bytes(b"manifest"),
        )
    assert not staging.exists()
    assert not output.exists()

    checksum, byte_count = ExportService._write_duckdb(  # pyright: ignore[reportPrivateUsage]
        output,
        {"rows": frame},
        {"ok": 1},
        ContentId.from_bytes(b"manifest"),
    )
    assert output.is_file()
    assert not staging.exists()
    assert byte_count == output.stat().st_size
    assert len(checksum) == 64


def test_bundle_writer_cleans_staging_and_supports_retry(tmp_path: Path) -> None:
    output = tmp_path / "export-bundle"
    staging = tmp_path / ".export-bundle.partial"
    staging.mkdir()
    (staging / "stale.csv").write_text("stale", encoding="utf-8")
    frame = pd.DataFrame({"value": [1, 2]})

    with pytest.raises(TypeError):
        ExportService._write_bundle(  # pyright: ignore[reportPrivateUsage]
            output,
            {"rows": frame},
            {"unserializable": object()},
            ContentId.from_bytes(b"manifest"),
            "csv",
        )
    assert not staging.exists()
    assert not output.exists()

    checksum, byte_count = ExportService._write_bundle(  # pyright: ignore[reportPrivateUsage]
        output,
        {"rows": frame},
        {"ok": 1},
        ContentId.from_bytes(b"manifest"),
        "csv",
    )
    assert output.is_dir()
    assert not staging.exists()
    assert (output / "manifest.json").is_file()
    assert byte_count > 0
    assert len(checksum) == 64
