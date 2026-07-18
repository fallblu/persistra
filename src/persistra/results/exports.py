"""Dependency-closed portable run exports with checksum verification."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import duckdb
import pandas as pd

from persistra import __version__
from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.db import ProjectMode
from persistra.db.migrations import CURRENT_SCHEMA_VERSION
from persistra.domain import ContentId
from persistra.errors import (
    CapabilityUnavailableError,
    ExportCompatibilityError,
    ExportSecurityError,
    ExportVerificationError,
    ResultQueryLimitError,
)
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
    "exposures",
    "rebalances",
    "trade_intents",
    "targets",
    "orders",
    "order_transitions",
    "fills",
    "costs",
    "events",
    "journal",
    "settlements",
    "lots",
    "lot_events",
    "borrow",
    "cash_flows",
    "quality",
    "logs",
)
_MANIFEST_SCHEMA = "persistra.results.export_manifest@2"
_FORMAT_VERSION = 2
_MANIFEST_KEYS = frozenset(
    {
        "format_version",
        "database_schema_version",
        "writer_version",
        "duckdb_version",
        "export_format",
        "run_record_id",
        "simulation_kind",
        "simulation_id",
        "execution_content_id",
        "result_manifest_content_id",
        "fidelity_findings",
        "tables",
    }
)
_BUNDLE_MANIFEST_KEYS = _MANIFEST_KEYS | {"manifest_content_id", "files"}


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
            raise ExportSecurityError("export destination already exists")
        output.parent.mkdir(parents=True, exist_ok=True)
        frames = {
            name: getattr(run, name)(max_rows=max_rows_per_table) for name in _TABLES
        }
        roots = {
            name: str(_frame_content_id(frame))
            for name, frame in frames.items()
        }
        manifest = {
            "format_version": _FORMAT_VERSION,
            "database_schema_version": CURRENT_SCHEMA_VERSION,
            "writer_version": __version__,
            "duckdb_version": duckdb.__version__,
            "export_format": export_format,
            "run_record_id": str(run.id.value),
            "simulation_kind": run.summary().simulation_kind,
            "simulation_id": run.summary().simulation_id,
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
            {"schema": _MANIFEST_SCHEMA, "manifest": manifest}
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
        _, content_id = _load_verified_export(Path(path))
        return content_id

    @staticmethod
    def _write_duckdb(
        output: Path,
        frames: dict[str, pd.DataFrame],
        manifest: dict[str, Any],
        content_id: ContentId,
    ) -> tuple[str, int]:
        staging = output.with_name(f".{output.name}.partial")
        staging.unlink(missing_ok=True)
        try:
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
        except BaseException:
            staging.unlink(missing_ok=True)
            raise
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
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        try:
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
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
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
    simulation_kind: str
    simulation_id: str
    execution_content_id: ContentId
    result_manifest_content_id: ContentId
    decision_count: int
    fill_count: int
    fidelity_findings: tuple[str, ...]


class PortableRunHandle:
    """Bounded read-only run handle backed by a verified portable export.

    Each table's content checksum is verified on its first materialization and
    trusted for the remaining lifetime of this handle; reopen the export to
    force complete re-verification.
    """

    __slots__ = (
        "_manifest",
        "_manifest_content_id",
        "_path",
        "_summary",
        "_verified_tables",
    )

    def __init__(
        self,
        path: Path,
        manifest: dict[str, Any],
        manifest_content_id: ContentId,
    ) -> None:
        self._path = path
        self._manifest = manifest
        self._manifest_content_id = manifest_content_id
        self._verified_tables: set[str] = set()
        tables = manifest["tables"]
        self._summary = PortableRunSummary(
            RunRecordId.parse(manifest["run_record_id"]),
            str(manifest["simulation_kind"]),
            str(manifest["simulation_id"]),
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

    def exposures(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("exposures", max_rows)

    def rebalances(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("rebalances", max_rows)

    def trade_intents(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("trade_intents", max_rows)

    def orders(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("orders", max_rows)

    def order_transitions(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("order_transitions", max_rows)

    def fills(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("fills", max_rows)

    def costs(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("costs", max_rows)

    def journal(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("journal", max_rows)

    def events(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("events", max_rows)

    def settlements(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("settlements", max_rows)

    def lots(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("lots", max_rows)

    def lot_events(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("lot_events", max_rows)

    def borrow(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("borrow", max_rows)

    def cash_flows(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("cash_flows", max_rows)

    def quality(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._table("quality", max_rows)

    def logs(self, *, max_rows: int = 100_000) -> pd.DataFrame:
        return self._table("logs", max_rows)

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
        if len(frame) != expected or (
            name not in self._verified_tables
            and _frame_content_id(frame)
            != ContentId.parse(self._manifest["tables"][name]["content_id"])
        ):
            raise ExportVerificationError(
                "portable result table content does not verify",
                context={"table": name},
            )
        self._verified_tables.add(name)
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
    requested = Path(path)
    source = requested.resolve()
    manifest, manifest_content_id = _load_verified_export(requested)
    handle = PortableRunHandle(source, manifest, manifest_content_id)
    handle.verify(max_rows_per_table=max_rows_per_table)
    return handle


def _load_verified_export(path: Path) -> tuple[dict[str, Any], ContentId]:
    source = path.resolve()
    if not source.exists():
        raise ExportVerificationError(
            "portable export does not exist",
            context={"path_name": source.name},
        )
    try:
        if path.is_symlink():
            raise ExportSecurityError("portable export must not be a symlink")
        if source.is_file():
            return _verify_duckdb(source)
        if source.is_dir():
            return _verify_bundle(source)
        raise ExportSecurityError("portable export must be a regular file or directory")
    except ExportVerificationError:
        raise
    except (duckdb.Error, OSError, TypeError, ValueError, KeyError) as exc:
        raise ExportVerificationError(
            "portable export verification failed",
            context={"path_name": source.name},
        ) from exc


def _verify_duckdb(source: Path) -> tuple[dict[str, Any], ContentId]:
    connection = duckdb.connect(str(source), read_only=True)
    try:
        connection.execute("SET enable_external_access = false")
        table_rows = connection.execute(
            "SELECT table_name FROM duckdb_tables() "
            "WHERE database_name = current_database() AND schema_name = 'main' "
            "ORDER BY table_name"
        ).fetchall()
        actual_tables = {str(row[0]) for row in table_rows}
        expected_tables = {*_TABLES, "_persistra_export_manifest"}
        if actual_tables != expected_tables:
            raise ExportVerificationError(
                "portable DuckDB table closure does not verify",
                context={
                    "missing": sorted(expected_tables - actual_tables),
                    "extra": sorted(actual_tables - expected_tables),
                },
            )
        view_count = connection.execute(
            "SELECT count(*) FROM duckdb_views() "
            "WHERE database_name = current_database() AND schema_name = 'main' "
            "AND NOT internal"
        ).fetchone()
        if view_count is None or int(view_count[0]) != 0:
            raise ExportSecurityError("portable DuckDB must not contain views")
        rows = connection.execute(
            "SELECT manifest_json, manifest_content_id FROM _persistra_export_manifest"
        ).fetchall()
        if len(rows) != 1:
            raise ExportVerificationError(
                "portable DuckDB must contain exactly one manifest"
            )
        manifest = _parse_json_object(rows[0][0])
        _validate_semantic_manifest(manifest, expected_format="duckdb")
        content_id = _parse_content_id(rows[0][1], field="manifest_content_id")
        _verify_manifest_content_id(manifest, content_id)
        _verify_duckdb_tables(connection, manifest)
        return manifest, content_id
    finally:
        connection.close()


def _verify_duckdb_tables(
    connection: duckdb.DuckDBPyConnection,
    manifest: dict[str, Any],
) -> None:
    tables = cast("dict[str, dict[str, Any]]", manifest["tables"])
    for name in _TABLES:
        details = tables[name]
        count_row = connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()
        if count_row is None or int(count_row[0]) != details["row_count"]:
            raise ExportVerificationError(
                "portable DuckDB table count does not verify",
                context={"table": name},
            )
        frame = connection.execute(f'SELECT * FROM "{name}"').fetchdf()
        if str(_frame_content_id(frame)) != details["content_id"]:
            raise ExportVerificationError(
                "portable DuckDB table content does not verify",
                context={"table": name},
            )


def _verify_bundle(source: Path) -> tuple[dict[str, Any], ContentId]:
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ExportSecurityError("portable bundle manifest must be a regular file")
    manifest = _parse_json_object(manifest_path.read_text(encoding="utf-8"))
    if set(manifest) != set(_BUNDLE_MANIFEST_KEYS):
        raise ExportVerificationError("portable bundle manifest fields do not verify")
    export_format = manifest.get("export_format")
    if export_format not in {"parquet", "csv"}:
        raise ExportCompatibilityError("portable bundle format is unsupported")
    semantic_manifest = {key: manifest[key] for key in _MANIFEST_KEYS}
    _validate_semantic_manifest(
        semantic_manifest,
        expected_format=cast("str", export_format),
    )
    content_id = _parse_content_id(
        manifest["manifest_content_id"],
        field="manifest_content_id",
    )
    _verify_manifest_content_id(semantic_manifest, content_id)
    raw_files = cast("object", manifest.get("files"))
    if not isinstance(raw_files, list):
        raise ExportVerificationError("portable bundle file manifest does not verify")
    files = cast("list[object]", raw_files)
    if len(files) != len(_TABLES):
        raise ExportVerificationError("portable bundle file manifest does not verify")
    suffix = "parquet" if export_format == "parquet" else "csv"
    expected_names = {f"{table}.{suffix}" for table in _TABLES}
    described_names: set[str] = set()
    for raw_item in files:
        if not isinstance(raw_item, dict):
            raise ExportVerificationError("portable bundle file entry is invalid")
        item = cast("dict[str, object]", raw_item)
        if set(item) != {
            "name",
            "sha256",
            "byte_count",
        }:
            raise ExportVerificationError("portable bundle file entry is invalid")
        name = _validate_bundle_name(item["name"])
        if name in described_names:
            raise ExportVerificationError("portable bundle contains duplicate file entries")
        described_names.add(name)
        file_path = source / name
        if not file_path.is_file() or file_path.is_symlink():
            raise ExportSecurityError(
                "portable bundle entry must be a regular file",
                context={"file_name": name},
            )
        byte_count = item["byte_count"]
        if (
            not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count < 0
            or file_path.stat().st_size != byte_count
        ):
            raise ExportVerificationError(
                "portable bundle file size does not verify",
                context={"file_name": name},
            )
        sha256 = item["sha256"]
        if not _is_sha256(sha256) or _sha256(file_path) != sha256:
            raise ExportVerificationError(
                "portable bundle file checksum does not verify",
                context={"file_name": name},
            )
    if described_names != expected_names:
        raise ExportVerificationError("portable bundle table files do not verify")
    expected_file_set = expected_names | {"manifest.json"}
    actual_names = {entry.name for entry in source.iterdir()}
    if actual_names != expected_file_set:
        raise ExportSecurityError(
            "portable bundle file closure does not verify",
            context={
                "missing": sorted(expected_file_set - actual_names),
                "extra": sorted(actual_names - expected_file_set),
            },
        )
    return manifest, content_id


def _validate_semantic_manifest(
    manifest: dict[str, Any],
    *,
    expected_format: str,
) -> None:
    if set(manifest) != set(_MANIFEST_KEYS):
        raise ExportVerificationError("portable export manifest fields do not verify")
    if manifest.get("format_version") != _FORMAT_VERSION:
        raise ExportCompatibilityError(
            "portable export format version is unsupported",
            context={"supported": _FORMAT_VERSION},
        )
    if manifest.get("export_format") != expected_format:
        raise ExportVerificationError("portable export kind does not match its container")
    if manifest.get("database_schema_version") != CURRENT_SCHEMA_VERSION:
        raise ExportCompatibilityError(
            "portable export database schema version is unsupported",
            context={"supported": CURRENT_SCHEMA_VERSION},
        )
    for field in (
        "writer_version",
        "duckdb_version",
        "simulation_kind",
        "simulation_id",
    ):
        _require_string(manifest, field)
    if manifest["simulation_kind"] not in {"vectorized", "event"}:
        raise ExportCompatibilityError("portable export simulation kind is unsupported")
    RunRecordId.parse(_require_string(manifest, "run_record_id"))
    _parse_content_id(
        manifest.get("execution_content_id"),
        field="execution_content_id",
    )
    _parse_content_id(
        manifest.get("result_manifest_content_id"),
        field="result_manifest_content_id",
    )
    raw_fidelity = cast("object", manifest.get("fidelity_findings"))
    if not isinstance(raw_fidelity, list):
        raise ExportVerificationError("portable export fidelity findings are invalid")
    fidelity = cast("list[object]", raw_fidelity)
    if any(
        not isinstance(finding, str) for finding in fidelity
    ):
        raise ExportVerificationError("portable export fidelity findings are invalid")
    raw_tables = cast("object", manifest.get("tables"))
    if not isinstance(raw_tables, dict):
        raise ExportVerificationError("portable export table manifest does not verify")
    tables = cast("dict[str, object]", raw_tables)
    if set(tables) != set(_TABLES):
        raise ExportVerificationError("portable export table manifest does not verify")
    for name in _TABLES:
        raw_details = tables[name]
        if not isinstance(raw_details, dict):
            raise ExportVerificationError(
                "portable export table entry is invalid",
                context={"table": name},
            )
        details = cast("dict[str, object]", raw_details)
        if set(details) != {
            "row_count",
            "content_id",
        }:
            raise ExportVerificationError(
                "portable export table entry is invalid",
                context={"table": name},
            )
        row_count = details["row_count"]
        minimum_rows = 1 if name == "equity" else 0
        if (
            not isinstance(row_count, int)
            or isinstance(row_count, bool)
            or row_count < minimum_rows
        ):
            raise ExportVerificationError(
                "portable export table count is invalid",
                context={"table": name},
            )
        _parse_content_id(
            details["content_id"],
            field=f"tables.{name}.content_id",
        )


def _verify_manifest_content_id(
    manifest: dict[str, Any],
    stored: ContentId,
) -> None:
    recomputed = scoped_content_id({"schema": _MANIFEST_SCHEMA, "manifest": manifest})
    if recomputed != stored:
        raise ExportVerificationError(
            "portable export manifest identity does not verify",
            context={"expected": str(recomputed), "actual": str(stored)},
        )


def _parse_json_object(value: object) -> dict[str, Any]:
    parsed = cast("object", json.loads(value)) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ExportVerificationError("portable export manifest must be a JSON object")
    raw = cast("dict[object, object]", parsed)
    if any(not isinstance(key, str) for key in raw):
        raise ExportVerificationError("portable export manifest keys must be strings")
    return cast("dict[str, Any]", raw)


def _parse_content_id(value: object, *, field: str) -> ContentId:
    if not isinstance(value, str):
        raise ExportVerificationError(
            "portable export content identity is invalid",
            field_path=field,
        )
    try:
        return ContentId.parse(value)
    except ValueError as exc:
        raise ExportVerificationError(
            "portable export content identity is invalid",
            field_path=field,
        ) from exc


def _require_string(manifest: dict[str, Any], field: str) -> str:
    value = manifest.get(field)
    if not isinstance(value, str):
        raise ExportVerificationError(
            "portable export field must be a string",
            field_path=field,
        )
    return value


def _validate_bundle_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ExportSecurityError("portable bundle file name is invalid")
    path = Path(value)
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or value in {".", ".."}
        or "\\" in value
        or "/" in value
    ):
        raise ExportSecurityError(
            "portable bundle file path is unsafe",
            context={"file_name": value},
        )
    return value


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
