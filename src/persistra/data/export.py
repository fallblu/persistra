"""Atomic Arrow and Parquet exports for retained store data."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum, StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow as _pyarrow  # pyright: ignore[reportMissingTypeStubs]
import pyarrow.parquet as _parquet  # pyright: ignore[reportMissingTypeStubs]

from persistra._files import file_identity, unlink_if_identity
from persistra._portable import thaw_portable_mapping
from persistra.errors import StoreError
from persistra.model import (
    BarSet,
    ExchangeRateQuote,
    IndexCatalogResult,
    InstrumentSearchResult,
    MarketStatusResult,
    OptionChain,
    QuoteSet,
    ResultMetadata,
    SeriesSet,
    TopOfBookSet,
    VintageDatesResult,
    VintageSeriesSet,
)

if TYPE_CHECKING:
    from persistra.data.store import DuckDBStore, StoredResult, StoredSnapshot

pa: Any = _pyarrow
pq: Any = _parquet

EXPORT_SCHEMA_VERSION = 1


class ColumnarFormat(StrEnum):
    """Supported interoperable columnar file formats."""

    ARROW = "arrow"
    PARQUET = "parquet"


@dataclass(frozen=True, slots=True)
class ExactSnapshotSelection:
    """Select one immutable store snapshot by identity."""

    snapshot_id: str

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("snapshot_id must not be empty")


@dataclass(frozen=True, slots=True)
class CumulativeDatasetSelection:
    """Select the latest observed rows in one cumulative dataset."""

    family: str
    scope_key: str
    retrieved_before: datetime | None = None

    def __post_init__(self) -> None:
        if self.family not in {"bars", "series", "vintage_series", "vintage_dates"}:
            raise ValueError("family does not support cumulative export")
        if not self.scope_key.strip():
            raise ValueError("scope_key must not be empty")
        if self.retrieved_before is not None and self.retrieved_before.tzinfo is None:
            raise ValueError("retrieved_before must be timezone-aware")


type StoreExportSelection = ExactSnapshotSelection | CumulativeDatasetSelection


@dataclass(frozen=True, slots=True)
class ColumnarExportFile:
    """One complete columnar file produced by an export."""

    table: str
    path: Path
    row_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ColumnarExport:
    """Published export files and their explicit provenance sidecar."""

    format: ColumnarFormat
    family: str
    scope_key: str
    snapshot_id: str | None
    files: tuple[ColumnarExportFile, ...]
    provenance_path: Path


@dataclass(frozen=True, slots=True)
class _PreparedFile:
    table: str
    target: Path
    staging: Path
    identity: tuple[int, int]
    row_count: int
    digest: str


def export_store(
    store: DuckDBStore,
    selection: StoreExportSelection,
    destination: str | Path,
    *,
    format: ColumnarFormat,
    overwrite: bool = False,
) -> ColumnarExport:
    """Export an exact snapshot or cumulative dataset with provenance.

    ``destination`` names the data file for a single-table export. Multi-table option
    snapshots insert each table name before the suffix. The provenance sidecar replaces
    the destination suffix with ``.provenance.json``.
    """
    target = Path(destination)
    _validate_destination(target, format)
    family, scope_key, snapshot_id, frames, provenance = _select(store, selection)
    targets = _table_targets(target, tuple(frames), format)
    sidecar = target.with_suffix(".provenance.json")
    all_targets = (*targets.values(), sidecar)
    if len(set(all_targets)) != len(all_targets):
        raise ValueError("export paths must be distinct")
    if not overwrite:
        existing = next((path for path in all_targets if path.exists()), None)
        if existing is not None:
            raise FileExistsError(f"export path already exists: {existing}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StoreError(f"could not create export directory: {target.parent}") from error

    prepared: list[_PreparedFile] = []
    sidecar_prepared: _PreparedFile | None = None
    try:
        for table_name, frame in frames.items():
            prepared.append(
                _prepare_columnar(table_name, frame, targets[table_name], format, target.parent)
            )
        file_records = [
            {
                "table": item.table,
                "path": item.target.name,
                "rows": item.row_count,
                "sha256": item.digest,
            }
            for item in prepared
        ]
        document = {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "format": format.value,
            "selection": provenance,
            "files": file_records,
        }
        sidecar_bytes = json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_value,
        ).encode()
        sidecar_prepared = _prepare_bytes("provenance", sidecar_bytes, sidecar, target.parent)
        _publish((*prepared, sidecar_prepared), overwrite=overwrite)
    except Exception as error:
        for item in (*prepared, *((sidecar_prepared,) if sidecar_prepared is not None else ())):
            unlink_if_identity(item.staging, item.identity)
        if isinstance(error, (FileExistsError, StoreError, ValueError)):
            raise
        raise StoreError(f"could not export stored data to {target}") from error

    files = tuple(
        ColumnarExportFile(item.table, item.target, item.row_count, item.digest)
        for item in prepared
    )
    return ColumnarExport(format, family, scope_key, snapshot_id, files, sidecar)


def _validate_destination(path: Path, format: ColumnarFormat) -> None:
    if not path.name or path.name in {".", ".."}:
        raise ValueError("destination must name a file")
    expected = f".{format.value}"
    if path.suffix.casefold() != expected:
        raise ValueError(f"destination must use the {expected} suffix")


def _select(
    store: DuckDBStore, selection: StoreExportSelection
) -> tuple[str, str, str | None, dict[str, pd.DataFrame], dict[str, Any]]:
    if isinstance(selection, ExactSnapshotSelection):
        result = store.load_snapshot(selection.snapshot_id)
        if result is None:
            raise ValueError(f"snapshot does not exist: {selection.snapshot_id}")
        snapshot = _find_snapshot(store, selection.snapshot_id)
        frames = _result_frames(result)
        provenance = {
            "kind": "exact_snapshot",
            "snapshot": asdict(snapshot),
            "metadata": _metadata_document(result.metadata),
        }
        return snapshot.family, snapshot.scope_key, snapshot.snapshot_id, frames, provenance
    frame = _cumulative_frame(store, selection)
    snapshots = tuple(
        snapshot
        for snapshot in store.list_snapshots(selection.family, selection.scope_key)
        if selection.retrieved_before is None or snapshot.first_seen <= selection.retrieved_before
    )
    provenance = {
        "kind": "cumulative_dataset",
        "family": selection.family,
        "scope_key": selection.scope_key,
        "retrieved_before": selection.retrieved_before,
        "snapshot_ids": [snapshot.snapshot_id for snapshot in snapshots],
    }
    return selection.family, selection.scope_key, None, {"data": frame}, provenance


def _find_snapshot(store: DuckDBStore, snapshot_id: str) -> StoredSnapshot:
    for dataset in store.list_datasets():
        for snapshot in store.list_snapshots(dataset.family, dataset.scope_key):
            if snapshot.snapshot_id == snapshot_id:
                return snapshot
    raise ValueError(f"snapshot does not exist: {snapshot_id}")


def _metadata_document(metadata: ResultMetadata) -> dict[str, Any]:
    return {
        "provider": metadata.provider,
        "operation": metadata.operation,
        "request_parameters": thaw_portable_mapping(metadata.request_parameters),
        "retrieved_at": metadata.retrieved_at,
        "provider_as_of": metadata.provider_as_of,
        "entitlement": metadata.entitlement,
        "cache_status": metadata.cache_status,
        "schema_version": metadata.schema_version,
        "diagnostics": [asdict(item) for item in metadata.diagnostics],
    }


def _cumulative_frame(
    store: DuckDBStore, selection: CumulativeDatasetSelection
) -> pd.DataFrame:
    if selection.family == "bars":
        return store.query_bars(
            selection.scope_key, retrieved_before=selection.retrieved_before
        )
    if selection.family == "series":
        return store.query_series(
            selection.scope_key, retrieved_before=selection.retrieved_before
        )
    if selection.family == "vintage_series":
        return store.query_vintage_series(
            selection.scope_key, retrieved_before=selection.retrieved_before
        )
    return store.query_vintage_dates(
        selection.scope_key, retrieved_before=selection.retrieved_before
    )


def _result_frames(result: StoredResult) -> dict[str, pd.DataFrame]:
    if isinstance(result, OptionChain):
        return {"contracts": result.contracts, "observations": result.observations}
    if isinstance(
        result,
        (
            BarSet,
            QuoteSet,
            TopOfBookSet,
            SeriesSet,
            VintageSeriesSet,
            InstrumentSearchResult,
            MarketStatusResult,
            IndexCatalogResult,
        ),
    ):
        return {"data": result.frame}
    if isinstance(result, VintageDatesResult):
        return {
            "data": pd.DataFrame(
                {
                    "provider_series": pd.Series(
                        [result.provider_series] * len(result.dates), dtype="string"
                    ),
                    "vintage_date": pd.Series(result.dates, dtype="datetime64[ns]"),
                }
            )
        }
    if isinstance(result, ExchangeRateQuote):
        fields = (
            "instrument_id",
            "provider",
            "base_currency",
            "quote_currency",
            "exchange_rate",
            "bid",
            "ask",
            "provider_timestamp",
            "provider_timezone",
            "retrieved_at",
        )
    else:
        fields = (
            "series_id",
            "provider",
            "metal",
            "value",
            "unit",
            "provider_timestamp",
            "retrieved_at",
        )
    return {"data": pd.DataFrame([{field: getattr(result, field) for field in fields}])}


def _table_targets(
    destination: Path, tables: tuple[str, ...], format: ColumnarFormat
) -> dict[str, Path]:
    if len(tables) == 1:
        return {tables[0]: destination}
    return {
        table: destination.with_name(f"{destination.stem}.{table}.{format.value}")
        for table in tables
    }


def _prepare_columnar(
    table_name: str,
    frame: pd.DataFrame,
    target: Path,
    format: ColumnarFormat,
    directory: Path,
) -> _PreparedFile:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=directory
    )
    os.close(descriptor)
    staging = Path(name)
    identity = file_identity(staging)
    try:
        table = pa.Table.from_pandas(frame, preserve_index=False)
        if format is ColumnarFormat.ARROW:
            with pa.OSFile(str(staging), "wb") as sink:
                with pa.ipc.new_file(sink, table.schema) as writer:
                    writer.write_table(table)
        else:
            pq.write_table(table, staging)
        _sync(staging)
        digest = _file_digest(staging)
    except Exception:
        unlink_if_identity(staging, identity)
        raise
    return _PreparedFile(table_name, target, staging, identity, len(frame), digest)


def _prepare_bytes(table: str, document: bytes, target: Path, directory: Path) -> _PreparedFile:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=directory
    )
    staging = Path(name)
    identity = file_identity(staging)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        unlink_if_identity(staging, identity)
        raise
    return _PreparedFile(table, target, staging, identity, 1, sha256(document).hexdigest())


def _sync(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _publish(files: tuple[_PreparedFile, ...], *, overwrite: bool) -> None:
    published: list[_PreparedFile] = []
    try:
        for item in files:
            if file_identity(item.staging) != item.identity:
                raise OSError(f"private staging path changed before publication: {item.staging}")
            if overwrite:
                os.replace(item.staging, item.target)
            else:
                os.link(item.staging, item.target)
            published.append(item)
    except Exception:
        if not overwrite:
            for item in published:
                unlink_if_identity(item.target, item.identity)
        raise
    finally:
        for item in files:
            unlink_if_identity(item.staging, item.identity)


def _json_value(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")
