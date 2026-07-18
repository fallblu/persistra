"""Dependency-closed portable run exports with checksum verification."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import CapabilityUnavailableError, ResultQueryLimitError
from persistra.results.models import ExportAttemptId, ExportRef
from persistra.simulation import RunRecordId

if TYPE_CHECKING:
    from persistra.db.services import TransactionContext
    from persistra.project import Project
    from persistra.results.services import RunHandle

_TABLES = (
    "equity",
    "returns",
    "positions",
    "cash",
    "targets",
    "fills",
    "costs",
    "journal",
)


class ExportService:
    """Write and independently verify closed DuckDB, Parquet, or CSV exports."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def create(
        self,
        run: RunHandle,
        destination: str | Path,
        *,
        export_format: str = "duckdb",
        max_rows_per_table: int = 2_000_000,
    ) -> ExportRef:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("exports require research_write mode")
        if export_format not in {"duckdb", "parquet", "csv"}:
            raise ResultQueryLimitError("export format is unsupported")
        if max_rows_per_table <= 0:
            raise ResultQueryLimitError("max_rows_per_table must be positive")
        output = Path(destination).resolve()
        if output.exists():
            raise FileExistsError(f"export destination already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        frames = {
            name: getattr(run, name)(max_rows=max_rows_per_table) for name in _TABLES
        }
        roots = {
            name: str(_frame_content_id(frame))
            for name, frame in frames.items()
        }
        manifest = {
            "format_version": 1,
            "export_format": export_format,
            "run_record_id": str(run.id.value),
            "execution_content_id": str(run.summary().execution_content_id),
            "result_manifest_content_id": str(
                run.summary().result_manifest_content_id
            ),
            "fidelity_findings": list(run.fidelity()),
            "tables": {
                name: {"row_count": len(frames[name]), "content_id": roots[name]}
                for name in _TABLES
            },
        }
        manifest_content_id = scoped_content_id(
            {"schema": "persistra.results.export_manifest@1", "manifest": manifest}
        )
        if export_format == "duckdb":
            checksum, byte_count = self._write_duckdb(
                output, frames, manifest, manifest_content_id
            )
        else:
            checksum, byte_count = self._write_bundle(
                output, frames, manifest, manifest_content_id, export_format
            )
        self.verify(output)
        export_id = ExportAttemptId.new()

        def operation(context: TransactionContext) -> ExportRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            connection.execute(
                "INSERT INTO results.export_attempts VALUES "
                "(?, ?, ?, 'completed', ?, ?, ?, ?, ?)",
                [
                    export_id.value,
                    run.id.value,
                    export_format,
                    str(manifest_content_id),
                    checksum,
                    byte_count,
                    context.recorded_at,
                    context.recorded_at,
                ],
            )
            return ExportRef(
                export_id,
                run.id,
                export_format,
                manifest_content_id,
                checksum,
                byte_count,
            )

        return self._project.services.transactions.run("result_export_create", operation)

    def verify(self, path: str | Path) -> ContentId:
        source = Path(path).resolve()
        if source.is_file():
            connection = duckdb.connect(str(source), read_only=True)
            try:
                row = connection.execute(
                    "SELECT manifest_json, manifest_content_id FROM "
                    "_persistra_export_manifest"
                ).fetchone()
                if row is None:
                    raise ValueError("export manifest is missing")
                manifest = json.loads(row[0])
                for name, details in manifest["tables"].items():
                    count_row = connection.execute(
                        f'SELECT count(*) FROM "{name}"'
                    ).fetchone()
                    if count_row is None:
                        raise ValueError("export table is missing")
                    if int(count_row[0]) != int(details["row_count"]):
                        raise ValueError("export table count does not verify")
                    frame = connection.execute(f'SELECT * FROM "{name}"').fetchdf()
                    root = _frame_content_id(frame)
                    if str(root) != details["content_id"]:
                        raise ValueError("export table content does not verify")
                return ContentId.parse(row[1])
            finally:
                connection.close()
        manifest_path = source / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        content_id = ContentId.parse(manifest["manifest_content_id"])
        for item in manifest["files"]:
            file_path = source / item["name"]
            if _sha256(file_path) != item["sha256"]:
                raise ValueError("export file checksum does not verify")
        return content_id

    @staticmethod
    def _write_duckdb(
        output: Path,
        frames: dict[str, pd.DataFrame],
        manifest: dict[str, Any],
        content_id: ContentId,
    ) -> tuple[str, int]:
        staging = output.with_name(f".{output.name}.partial")
        connection = duckdb.connect(str(staging))
        try:
            for name, frame in frames.items():
                connection.register("_frame", frame)
                connection.execute(f'CREATE TABLE "{name}" AS SELECT * FROM _frame')
                connection.unregister("_frame")
            connection.execute(
                "CREATE TABLE _persistra_export_manifest "
                "(manifest_json JSON NOT NULL, manifest_content_id VARCHAR NOT NULL)"
            )
            connection.execute(
                "INSERT INTO _persistra_export_manifest VALUES (?, ?)",
                [json.dumps(manifest, sort_keys=True), str(content_id)],
            )
            connection.execute("CHECKPOINT")
        finally:
            connection.close()
        os.replace(staging, output)
        return _sha256(output), output.stat().st_size

    @staticmethod
    def _write_bundle(
        output: Path,
        frames: dict[str, pd.DataFrame],
        manifest: dict[str, Any],
        content_id: ContentId,
        export_format: str,
    ) -> tuple[str, int]:
        staging = output.with_name(f".{output.name}.partial")
        staging.mkdir()
        files: list[dict[str, Any]] = []
        connection = duckdb.connect()
        try:
            for name, frame in frames.items():
                suffix = "parquet" if export_format == "parquet" else "csv"
                filename = f"{name}.{suffix}"
                path = staging / filename
                connection.register("_frame", frame)
                if export_format == "parquet":
                    connection.execute(
                        "COPY _frame TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                        [str(path)],
                    )
                else:
                    connection.execute(
                        "COPY _frame TO ? (FORMAT CSV, HEADER, DELIMITER ',')",
                        [str(path)],
                    )
                connection.unregister("_frame")
                files.append(
                    {
                        "name": filename,
                        "sha256": _sha256(path),
                        "byte_count": path.stat().st_size,
                    }
                )
        finally:
            connection.close()
        bundle_manifest = {
            **manifest,
            "manifest_content_id": str(content_id),
            "files": files,
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(bundle_manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(staging, output)
        byte_count = sum(path.stat().st_size for path in output.iterdir())
        digest = hashlib.sha256()
        for path in sorted(output.iterdir()):
            digest.update(path.name.encode())
            digest.update(bytes.fromhex(_sha256(path)))
        return digest.hexdigest(), byte_count


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_content_id(frame: pd.DataFrame) -> ContentId:
    normalized = frame.copy()
    for column in normalized.columns:
        if pd.api.types.is_datetime64_any_dtype(normalized[column].dtype):
            normalized[column] = pd.to_datetime(
                normalized[column], utc=True
            ).dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            normalized[column] = normalized[column].map(
                lambda value: "<NULL>" if pd.isna(value) else str(value)
            )
    return ContentId.from_bytes(normalized.to_csv(index=False).encode("utf-8"))


@dataclass(frozen=True, slots=True)
class PortableRunSummary:
    """Run identity available from a verified portable export."""

    run_record_id: RunRecordId
    execution_content_id: ContentId
    result_manifest_content_id: ContentId
    decision_count: int
    fill_count: int
    fidelity_findings: tuple[str, ...]


class PortableRunHandle:
    """Bounded read-only run handle backed by a verified portable export."""

    __slots__ = ("_manifest", "_manifest_content_id", "_path", "_summary")

    def __init__(
        self,
        path: Path,
        manifest: dict[str, Any],
        manifest_content_id: ContentId,
    ) -> None:
        self._path = path
        self._manifest = manifest
        self._manifest_content_id = manifest_content_id
        tables = manifest["tables"]
        self._summary = PortableRunSummary(
            RunRecordId.parse(manifest["run_record_id"]),
            ContentId.parse(manifest["execution_content_id"]),
            ContentId.parse(manifest["result_manifest_content_id"]),
            int(tables["equity"]["row_count"]) - 1,
            int(tables["fills"]["row_count"]),
            tuple(manifest.get("fidelity_findings", ())),
        )

    @property
    def id(self) -> RunRecordId:
        return self._summary.run_record_id

    @property
    def manifest_content_id(self) -> ContentId:
        return self._manifest_content_id

    def summary(self) -> PortableRunSummary:
        return self._summary

    def provenance(self) -> dict[str, str]:
        return {
            "execution_content_id": str(self._summary.execution_content_id),
            "result_manifest_content_id": str(self._summary.result_manifest_content_id),
        }

    def fidelity(self) -> tuple[str, ...]:
        return self._summary.fidelity_findings

    def equity(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("equity", max_rows)

    def returns(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("returns", max_rows)

    def positions(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("positions", max_rows)

    def cash(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("cash", max_rows)

    def targets(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("targets", max_rows)

    def fills(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("fills", max_rows)

    def costs(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("costs", max_rows)

    def journal(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("journal", max_rows)

    def verify(self, *, max_rows_per_table: int = 2_000_000) -> None:
        """Verify every table within an explicit materialization bound."""
        for table in _TABLES:
            self._table(table, max_rows_per_table)

    def _table(self, name: str, max_rows: int) -> pd.DataFrame:
        if name not in _TABLES or max_rows < 1:
            raise ResultQueryLimitError("portable result table or max_rows is invalid")
        expected = int(self._manifest["tables"][name]["row_count"])
        if expected > max_rows:
            raise ResultQueryLimitError("portable result rows exceed max_rows")
        if self._path.is_file():
            connection = duckdb.connect(str(self._path), read_only=True)
            try:
                frame = connection.execute(f'SELECT * FROM "{name}"').fetchdf()
            finally:
                connection.close()
        else:
            details = next(
                item
                for item in self._manifest["files"]
                if Path(item["name"]).stem == name
            )
            source = self._path / details["name"]
            connection = duckdb.connect()
            try:
                relation = (
                    "read_parquet(?)"
                    if source.suffix == ".parquet"
                    else "read_csv_auto(?, header = true)"
                )
                frame = connection.execute(
                    f"SELECT * FROM {relation}", [str(source)]
                ).fetchdf()
            finally:
                connection.close()
        if len(frame) != expected or _frame_content_id(frame) != ContentId.parse(
            self._manifest["tables"][name]["content_id"]
        ):
            raise ValueError("portable result table content does not verify")
        for column in frame.columns:
            if column.endswith("_id"):
                frame[column] = frame[column].astype("string")
            if column.endswith("_at") or column in {"interval_start", "interval_end"}:
                frame[column] = pd.to_datetime(frame[column], utc=True)
        return frame


def open_export(
    path: str | Path,
    *,
    max_rows_per_table: int = 2_000_000,
) -> PortableRunHandle:
    """Verify and open one closed portable run export read-only."""
    source = Path(path).resolve()
    if source.is_file():
        connection = duckdb.connect(str(source), read_only=True)
        try:
            row = connection.execute(
                "SELECT manifest_json, manifest_content_id "
                "FROM _persistra_export_manifest"
            ).fetchone()
            if row is None:
                raise ValueError("portable export manifest is missing")
            manifest = json.loads(row[0])
            manifest_content_id = ContentId.parse(row[1])
        finally:
            connection.close()
    else:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        manifest_content_id = ContentId.parse(manifest["manifest_content_id"])
    handle = PortableRunHandle(source, manifest, manifest_content_id)
    handle.verify(max_rows_per_table=max_rows_per_table)
    return handle
