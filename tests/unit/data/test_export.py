"""Tests for public store exports."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as _pyarrow  # pyright: ignore[reportMissingTypeStubs]
import pyarrow.parquet as _parquet  # pyright: ignore[reportMissingTypeStubs]
import pytest

import persistra.data.export as export_module
from persistra.data import (
    ColumnarFormat,
    CumulativeDatasetSelection,
    DuckDBStore,
    ExactSnapshotSelection,
    export_store,
    synthetic,
)

pa: Any = _pyarrow
pq: Any = _parquet


def _read_arrow(path: Path) -> pd.DataFrame:
    frame: pd.DataFrame = pa.ipc.open_file(path).read_all().to_pandas()
    return frame


def _read_parquet(path: Path) -> pd.DataFrame:
    frame: pd.DataFrame = pq.read_table(path).to_pandas()
    return frame


def test_exact_arrow_export_round_trips_frame_and_provenance(tmp_path: Path) -> None:
    source = synthetic.bars(periods=4)
    with DuckDBStore.create(tmp_path / "store.duckdb") as store:
        snapshot_id = store.save(source)
        exported = export_store(
            store,
            ExactSnapshotSelection(snapshot_id),
            tmp_path / "bars.arrow",
            format=ColumnarFormat.ARROW,
        )

    assert exported.family == "bars"
    assert exported.scope_key == source.instrument.instrument_id
    assert exported.snapshot_id == snapshot_id
    assert exported.files[0].table == "data"
    pd.testing.assert_frame_equal(_read_arrow(exported.files[0].path), source.frame)
    document = json.loads(exported.provenance_path.read_text())
    assert document["schema_version"] == 1
    assert document["selection"]["kind"] == "exact_snapshot"
    assert document["selection"]["snapshot"]["snapshot_id"] == snapshot_id
    assert document["files"] == [
        {
            "path": "bars.arrow",
            "rows": len(source.frame),
            "sha256": sha256(exported.files[0].path.read_bytes()).hexdigest(),
            "table": "data",
        }
    ]


def test_cumulative_parquet_export_preserves_nullable_and_temporal_dtypes(
    tmp_path: Path,
) -> None:
    source = synthetic.vintage_series(periods=3)
    with DuckDBStore.create(tmp_path / "store.duckdb") as store:
        snapshot_id = store.save(source)
        exported = export_store(
            store,
            CumulativeDatasetSelection("vintage_series", source.definition.series_id),
            tmp_path / "vintages.parquet",
            format=ColumnarFormat.PARQUET,
        )
        expected = store.query_vintage_series(source.definition.series_id)

    restored = _read_parquet(exported.files[0].path)
    pd.testing.assert_frame_equal(restored, expected)
    assert str(restored["value"].dtype) == "Float64"
    assert str(restored["available_through"].dtype) == "datetime64[ns]"
    assert str(restored["retrieved_at"].dtype) == "datetime64[ns, UTC]"
    document = json.loads(exported.provenance_path.read_text())
    assert document["selection"]["snapshot_ids"] == [snapshot_id]


def test_option_export_publishes_both_normalized_tables(tmp_path: Path) -> None:
    source = synthetic.option_chain()
    with DuckDBStore.create(tmp_path / "store.duckdb") as store:
        snapshot_id = store.save(source)
        exported = export_store(
            store,
            ExactSnapshotSelection(snapshot_id),
            tmp_path / "options.parquet",
            format=ColumnarFormat.PARQUET,
        )

    assert [item.table for item in exported.files] == ["contracts", "observations"]
    assert [item.path.name for item in exported.files] == [
        "options.contracts.parquet",
        "options.observations.parquet",
    ]
    pd.testing.assert_frame_equal(
        _read_parquet(exported.files[0].path), source.contracts
    )
    pd.testing.assert_frame_equal(
        _read_parquet(exported.files[1].path), source.observations
    )


def test_export_refuses_overwrite_and_validates_selection(tmp_path: Path) -> None:
    source = synthetic.series(periods=2)
    destination = tmp_path / "series.arrow"
    with DuckDBStore.create(tmp_path / "store.duckdb") as store:
        snapshot_id = store.save(source)
        selection = ExactSnapshotSelection(snapshot_id)
        export_store(store, selection, destination, format=ColumnarFormat.ARROW)
        original = destination.read_bytes()
        with pytest.raises(FileExistsError, match="already exists"):
            export_store(store, selection, destination, format=ColumnarFormat.ARROW)
        assert destination.read_bytes() == original
        replaced = export_store(
            store,
            selection,
            destination,
            format=ColumnarFormat.ARROW,
            overwrite=True,
        )
        assert replaced.files[0].path == destination

        with pytest.raises(ValueError, match="snapshot does not exist"):
            export_store(
                store,
                ExactSnapshotSelection("missing"),
                tmp_path / "missing.arrow",
                format=ColumnarFormat.ARROW,
            )
        with pytest.raises(ValueError, match="timezone-aware"):
            CumulativeDatasetSelection(
                "series", source.definition.series_id, datetime(2025, 1, 1)
            )
        CumulativeDatasetSelection(
            "series", source.definition.series_id, datetime(2025, 1, 1, tzinfo=UTC)
        )


def test_export_does_not_publish_when_sidecar_preparation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = synthetic.bars(periods=2)
    destination = tmp_path / "bars.parquet"

    def fail_sidecar(*_args: object, **_kwargs: object) -> Any:
        raise OSError("injected sidecar failure")

    with DuckDBStore.create(tmp_path / "store.duckdb") as store:
        snapshot_id = store.save(source)
        monkeypatch.setattr(export_module, "_prepare_bytes", fail_sidecar)
        with pytest.raises(Exception, match="could not export"):
            export_store(
                store,
                ExactSnapshotSelection(snapshot_id),
                destination,
                format=ColumnarFormat.PARQUET,
            )

    assert not destination.exists()
    assert not destination.with_suffix(".provenance.json").exists()
    assert list(tmp_path.glob(".*.tmp")) == []
