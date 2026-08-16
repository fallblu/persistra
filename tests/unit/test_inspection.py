"""Tests for read-only local store inspection."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from persistra import _inspection
from persistra._inspection import (
    InspectionError,
    InspectorViewModel,
    build_panel_app,
    discover_stores,
    provenance_table,
    result_summary,
    result_tables,
)
from persistra.data import DuckDBStore, synthetic


def _store(path: Path, *results: object) -> Path:
    with DuckDBStore.create(path) as store:
        for result in results:
            store.save(result)
    return path


def test_discovery_is_immediate_by_default_and_recursive_without_symlinks(
    tmp_path: Path,
) -> None:
    root_store = _store(tmp_path / "root.duckdb", synthetic.bars(periods=1))
    nested = tmp_path / "nested"
    nested.mkdir()
    nested_store = _store(nested / "nested.duckdb", synthetic.series(periods=1))
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    (tmp_path / "invalid.duckdb").write_text("not a store", encoding="utf-8")
    (tmp_path / "linked.duckdb").symlink_to(nested_store)
    linked_directory = tmp_path / "linked-directory"
    linked_directory.symlink_to(nested, target_is_directory=True)

    immediate = discover_stores(tmp_path)
    assert [store.path for store in immediate.stores] == [root_store.resolve()]
    assert len(immediate.warnings) == 1
    assert "invalid.duckdb" in immediate.warnings[0]

    recursive = discover_stores(tmp_path, recursive=True)
    assert [store.path for store in recursive.stores] == [
        root_store.resolve(),
        nested_store.resolve(),
    ]
    assert all("linked" not in warning for warning in recursive.warnings)


def test_discovery_rejects_bad_directories_and_no_supported_stores(tmp_path: Path) -> None:
    with pytest.raises(InspectionError, match="does not exist"):
        discover_stores(tmp_path / "missing")
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(InspectionError, match="not a directory"):
        discover_stores(file_path)
    (tmp_path / "bad.duckdb").write_text("bad", encoding="utf-8")
    with pytest.raises(InspectionError, match=r"no supported.*Warnings"):
        discover_stores(tmp_path)


def test_view_model_loads_exact_and_cumulative_data(tmp_path: Path) -> None:
    bars = synthetic.bars(periods=2)
    path = _store(tmp_path / "data.duckdb", bars)
    model = InspectorViewModel(discover_stores(tmp_path))
    discovered = model.store(path)
    dataset = discovered.datasets[0]
    history = model.snapshots(path, dataset.family, dataset.scope_key)
    exact = model.exact_result(path, history[0].snapshot_id)
    assert type(exact) is type(bars)
    cumulative = model.cumulative_table(path, dataset.family, dataset.scope_key)
    assert cumulative.name == "Cumulative retained data"
    pd.testing.assert_frame_equal(cumulative.frame, bars.frame)

    with pytest.raises(InspectionError, match="not part"):
        model.store(tmp_path / "other.duckdb")
    with pytest.raises(InspectionError, match="not available"):
        model.cumulative_table(path, "quotes", "AAA")
    with pytest.raises(InspectionError, match="no longer exists"):
        model.exact_result(path, "missing")

    path.unlink()
    with pytest.raises(InspectionError, match="could not inspect"):
        model.snapshots(path, dataset.family, dataset.scope_key)


def test_view_model_decoding_failure_is_actionable(tmp_path: Path) -> None:
    path = _store(tmp_path / "data.duckdb", synthetic.bars(periods=1))
    model = InspectorViewModel(discover_stores(tmp_path))
    snapshot = model.store(path).datasets[0].latest_snapshot_id
    with DuckDBStore.open(path) as store:
        store._connection.execute(  # pyright: ignore[reportPrivateUsage]
            "UPDATE acquisition_snapshots SET payload = 'bad' WHERE snapshot_id = ?",
            [snapshot],
        )
    with pytest.raises(InspectionError, match="could not decode"):
        model.exact_result(path, snapshot)


def test_table_and_provenance_views_cover_every_family() -> None:
    results = (
        synthetic.bars(periods=1),
        synthetic.quotes(),
        synthetic.top_of_book(),
        synthetic.option_chain(),
        synthetic.series(periods=1),
        synthetic.vintage_series(periods=1),
        synthetic.exchange_rate(),
        synthetic.commodity_spot(),
        synthetic.search(),
        synthetic.market_status(),
        synthetic.index_catalog(),
    )
    for result in results:
        tables = result_tables(result)  # type: ignore[arg-type]
        assert tables
        assert all(isinstance(table.frame, pd.DataFrame) for table in tables)
        assert "provider" in provenance_table(result)["field"].tolist()  # type: ignore[arg-type]
        assert result_summary(result).loc[0, "value"] == type(result).__name__  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="unsupported"):
        result_tables(SimpleNamespace())  # type: ignore[arg-type]


def test_panel_app_and_visualizations_smoke_without_figure_leaks(tmp_path: Path) -> None:
    import panel as pn

    bars = synthetic.bars(periods=2)
    path = _store(tmp_path / "data.duckdb", bars)
    model = InspectorViewModel(discover_stores(tmp_path))
    before = set(plt.get_fignums())
    app = build_panel_app(model, panel=pn)
    assert app.title == "Persistra Inspector"
    assert set(plt.get_fignums()) == before

    for result in (bars, synthetic.series(periods=2), synthetic.option_chain()):
        pane = _inspection._visualization_panel(pn, result)  # pyright: ignore[reportPrivateUsage]
        assert pane is not None
        assert set(plt.get_fignums()) == before

    path.unlink()


def test_optional_panel_import_and_server_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> Any:
        raise ImportError

    monkeypatch.setattr(_inspection, "import_module", missing)
    with pytest.raises(InspectionError, match=r"persistra\[inspect\]"):
        _inspection._load_panel()  # pyright: ignore[reportPrivateUsage]

    calls: dict[str, object] = {}

    def serve(app: object, **kwargs: object) -> None:
        calls.update(app=app, **kwargs)

    def build(model: object, panel: object) -> str:
        del model, panel
        return "app"

    fake_panel = SimpleNamespace(
        serve=serve,
    )
    inspection = _inspection.DirectoryInspection(Path("/tmp"), (), ())
    monkeypatch.setattr(_inspection, "_load_panel", lambda: fake_panel)
    monkeypatch.setattr(_inspection, "build_panel_app", build)
    _inspection.serve_inspector(inspection, port=8123, open_browser=False)
    assert calls == {
        "app": "app",
        "address": "127.0.0.1",
        "port": 8123,
        "show": False,
        "websocket_origin": ["127.0.0.1:8123"],
    }
    assert 1 <= _inspection.available_port() <= 65535
    with pytest.raises(InspectionError, match="between"):
        _inspection.serve_inspector(inspection, port=0)
