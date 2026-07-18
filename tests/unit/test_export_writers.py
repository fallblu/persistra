from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
import pytest

from persistra.db.migrations import CURRENT_SCHEMA_VERSION
from persistra.domain import ContentId
from persistra.errors import ExportVerificationError
from persistra.results.exports import (
    _TABLES,  # pyright: ignore[reportPrivateUsage]
    ExportService,
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
