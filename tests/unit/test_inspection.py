"""Tests for read-only local store inspection."""

import errno
from collections.abc import Callable, Iterator
from dataclasses import replace
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
from persistra.project import create_project


def _store(path: Path, *results: object) -> Path:
    with DuckDBStore.create(path) as store:
        for result in results:
            store.save(result)
    return path


def _panel_widgets(app: Any) -> dict[str, Any]:
    return {widget.name: widget for widget in app.sidebar[0]}


def _rendered_overview(app: Any) -> dict[str, object]:
    rendered = app.main[-1][0]
    overview = rendered[0]
    frame = overview[1].value
    return dict(zip(frame["field"], frame["value"], strict=True))


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

    inspection = discover_stores(tmp_path, allow_empty=True)
    assert inspection.stores == ()
    assert len(inspection.warnings) == 1
    assert "bad.duckdb" in inspection.warnings[0]


def test_recursive_discovery_reports_sorted_errors_and_continues_readable_subtrees(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    readable = tmp_path / "readable"
    readable.mkdir()
    store_path = _store(readable / "data.duckdb", synthetic.bars(periods=1))
    first_blocked = tmp_path / "a-blocked"
    last_blocked = tmp_path / "z-blocked"
    first_blocked.mkdir()
    last_blocked.mkdir()

    def walk(
        root: str | Path,
        *,
        followlinks: bool,
        onerror: Callable[[OSError], None],
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        assert Path(root) == tmp_path.resolve()
        assert followlinks is False
        yield str(root), [last_blocked.name, readable.name, first_blocked.name], []
        onerror(PermissionError(errno.EACCES, "Permission denied", last_blocked))
        onerror(PermissionError(errno.EACCES, "Permission denied", first_blocked))
        yield str(readable), [], [store_path.name]

    monkeypatch.setattr(_inspection.os, "walk", walk)
    inspection = discover_stores(tmp_path, recursive=True)

    assert [store.path for store in inspection.stores] == [store_path.resolve()]
    assert inspection.warnings == (
        f"{first_blocked}: could not traverse directory: Permission denied",
        f"{last_blocked}: could not traverse directory: Permission denied",
    )


def test_recursive_discovery_includes_traversal_errors_when_no_store_is_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()

    def walk(
        root: str | Path,
        *,
        followlinks: bool,
        onerror: Callable[[OSError], None],
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        assert followlinks is False
        yield str(root), [blocked.name], []
        onerror(PermissionError(errno.EACCES, "Permission denied", blocked))

    monkeypatch.setattr(_inspection.os, "walk", walk)

    with pytest.raises(InspectionError, match="no supported Persistra stores") as raised:
        discover_stores(tmp_path, recursive=True)
    assert f"{blocked}: could not traverse directory: Permission denied" in str(raised.value)


def test_discovery_presents_valid_project_metadata_and_warns_on_invalid_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "research"
    create_project(root, name="Research_Project")
    inspection = discover_stores(root)
    assert inspection.project_name == "research-project"
    assert inspection.project_format_version == 1
    assert inspection.warnings == ()
    assert [store.path for store in inspection.stores] == [(root / "data.duckdb").resolve()]

    (root / "persistra.toml").write_text("format_version = false\n", encoding="utf-8")
    invalid = discover_stores(root)
    assert invalid.project_name is None
    assert invalid.project_format_version is None
    assert len(invalid.stores) == 1
    assert len(invalid.warnings) == 1
    assert "persistra.toml" in invalid.warnings[0]


def test_view_model_loads_exact_and_cumulative_data(tmp_path: Path) -> None:
    bars = synthetic.bars(periods=2)
    path = _store(tmp_path / "data.duckdb", bars)
    model = InspectorViewModel(discover_stores(tmp_path))
    discovered = model.store(path)
    dataset = discovered.datasets[0]
    history = model.snapshots(path, dataset.family, dataset.scope_key)
    exact = model.exact_result(path, dataset.family, dataset.scope_key, history[0].snapshot_id)
    assert type(exact) is type(bars)
    cumulative = model.cumulative_table(path, dataset.family, dataset.scope_key)
    assert cumulative.name == "Cumulative retained data"
    pd.testing.assert_frame_equal(cumulative.frame, bars.frame)

    with pytest.raises(InspectionError, match="not part"):
        model.store(tmp_path / "other.duckdb")
    with pytest.raises(InspectionError, match="not available"):
        model.cumulative_table(path, "quotes", "AAA")
    with pytest.raises(InspectionError, match="not part of the selected dataset"):
        model.exact_result(path, dataset.family, dataset.scope_key, "missing")

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
        model.exact_result(path, "bars", model.store(path).datasets[0].scope_key, snapshot)


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
    pn = pytest.importorskip("panel")

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


def test_populated_initial_store_attaches_and_serializes_as_a_server_document(
    tmp_path: Path,
) -> None:
    pn = pytest.importorskip("panel")

    path = _store(tmp_path / "data.duckdb", synthetic.bars(periods=1))
    model = InspectorViewModel(discover_stores(tmp_path))
    app = build_panel_app(model, panel=pn)
    document = app.server_doc()

    assert document.to_json() is not None
    assert isinstance(model.store(path).path, Path)
    assert _rendered_overview(app)["store_path"] == str(path.resolve())


def test_panel_selection_moves_from_an_empty_store_to_a_populated_store(
    tmp_path: Path,
) -> None:
    pn = pytest.importorskip("panel")

    empty = _store(tmp_path / "a-empty.duckdb")
    populated = _store(tmp_path / "b-populated.duckdb", synthetic.bars(periods=1))
    model = InspectorViewModel(discover_stores(tmp_path))
    app = build_panel_app(model, panel=pn)
    document = app.server_doc()
    widgets = _panel_widgets(app)

    assert widgets["Store"].value == empty.resolve()
    assert widgets["Family"].value is None
    widgets["Store"].value = populated.resolve()

    dataset = model.store(populated).datasets[0]
    assert widgets["Family"].value == dataset.family
    assert widgets["Dataset scope"].value == dataset.scope_key
    assert widgets["Snapshot"].value == dataset.latest_snapshot_id
    overview = _rendered_overview(app)
    assert overview["store_path"] == str(populated.resolve())
    assert overview["result_type"] == "BarSet"
    assert document.to_json() is not None


@pytest.mark.parametrize(
    ("first_family", "second_family", "result_type"),
    [
        ("index_catalog", "market_status", "MarketStatusResult"),
        ("market_status", "index_catalog", "IndexCatalogResult"),
        ("quotes", "top_of_book", "TopOfBookSet"),
        ("top_of_book", "quotes", "QuoteSet"),
    ],
)
def test_family_transitions_refresh_shared_scope_snapshot_context(
    tmp_path: Path,
    first_family: str,
    second_family: str,
    result_type: str,
) -> None:
    pn = pytest.importorskip("panel")

    path = _store(
        tmp_path / "families.duckdb",
        synthetic.index_catalog(),
        synthetic.market_status(),
        synthetic.quotes(),
        synthetic.top_of_book(),
    )
    model = InspectorViewModel(discover_stores(tmp_path))
    app = build_panel_app(model, panel=pn)
    widgets = _panel_widgets(app)
    datasets = {dataset.family: dataset for dataset in model.store(path).datasets}

    widgets["Family"].value = first_family
    stale_snapshot = widgets["Snapshot"].value
    widgets["Family"].value = second_family

    selected = datasets[second_family]
    assert selected.scope_key == datasets[first_family].scope_key
    assert widgets["Dataset scope"].value == selected.scope_key
    assert widgets["Snapshot"].value == selected.latest_snapshot_id
    assert widgets["Snapshot"].value != stale_snapshot
    overview = _rendered_overview(app)
    assert overview["family"] == second_family
    assert overview["result_type"] == result_type


def test_scope_and_store_transitions_refresh_the_complete_snapshot_context(
    tmp_path: Path,
) -> None:
    pn = pytest.importorskip("panel")

    bars_path = _store(
        tmp_path / "a-bars.duckdb",
        synthetic.bars("AAA", periods=1),
        synthetic.bars("BBB", periods=1),
    )
    first_catalog = synthetic.index_catalog()
    second_catalog = synthetic.index_catalog()
    changed_frame = second_catalog.frame.copy()
    changed_frame.loc[0, "name"] = "Changed catalog row"
    second_catalog = replace(second_catalog, frame=changed_frame)
    first_store = _store(tmp_path / "b-first.duckdb", first_catalog)
    second_store = _store(tmp_path / "c-second.duckdb", second_catalog)
    model = InspectorViewModel(discover_stores(tmp_path))
    app = build_panel_app(model, panel=pn)
    widgets = _panel_widgets(app)

    bar_datasets = model.store(bars_path).datasets
    widgets["Dataset scope"].value = bar_datasets[1].scope_key
    assert widgets["Snapshot"].value == bar_datasets[1].latest_snapshot_id
    assert _rendered_overview(app)["scope_key"] == bar_datasets[1].scope_key

    widgets["Store"].value = first_store.resolve()
    first_snapshot = widgets["Snapshot"].value
    widgets["Store"].value = second_store.resolve()

    selected = model.store(second_store).datasets[0]
    assert selected.family == model.store(first_store).datasets[0].family
    assert selected.scope_key == model.store(first_store).datasets[0].scope_key
    assert widgets["Family"].value == selected.family
    assert widgets["Dataset scope"].value == selected.scope_key
    assert widgets["Snapshot"].value == selected.latest_snapshot_id
    assert widgets["Snapshot"].value != first_snapshot
    overview = _rendered_overview(app)
    assert overview["store_path"] == str(second_store.resolve())
    assert overview["result_type"] == "IndexCatalogResult"


def test_exact_result_rejects_a_snapshot_from_another_selected_dataset(
    tmp_path: Path,
) -> None:
    path = _store(
        tmp_path / "data.duckdb",
        synthetic.index_catalog(),
        synthetic.market_status(),
    )
    model = InspectorViewModel(discover_stores(tmp_path))
    datasets = {dataset.family: dataset for dataset in model.store(path).datasets}

    with pytest.raises(InspectionError, match="not part of the selected dataset"):
        model.exact_result(
            path,
            "market_status",
            datasets["market_status"].scope_key,
            datasets["index_catalog"].latest_snapshot_id,
        )


def test_panel_app_supports_an_empty_store(tmp_path: Path) -> None:
    pn = pytest.importorskip("panel")

    path = _store(tmp_path / "data.duckdb")
    model = InspectorViewModel(discover_stores(tmp_path))
    app = build_panel_app(model, panel=pn)

    assert app.title == "Persistra Inspector"
    assert model.store(path).datasets == ()


def test_optional_panel_import_and_server_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(_name: str) -> Any:
        raise ImportError

    monkeypatch.setattr(_inspection, "import_module", missing)
    with pytest.raises(InspectionError, match=r"persistra\[inspect\]"):
        _inspection._load_panel()  # pyright: ignore[reportPrivateUsage]

    calls: dict[str, object] = {}
    built_models: list[object] = []

    def serve(app: object, **kwargs: object) -> object:
        calls.update(app=app, **kwargs)
        return server

    def build(model: object, panel: object) -> str:
        del panel
        built_models.append(model)
        return "app"

    def run_until_shutdown() -> None:
        return None

    def stop_server(*, wait: bool) -> None:
        del wait

    server = SimpleNamespace(
        port=43123,
        run_until_shutdown=run_until_shutdown,
        stop=stop_server,
    )
    fake_panel = SimpleNamespace(
        serve=serve,
    )
    inspection = _inspection.DirectoryInspection(Path("/tmp"), (), ())
    monkeypatch.setattr(_inspection, "_load_panel", lambda: fake_panel)
    monkeypatch.setattr(_inspection, "build_panel_app", build)
    _inspection.serve_inspector(inspection, open_browser=False)
    app_factory = calls.pop("app")
    assert callable(app_factory)
    assert app_factory() == "app"
    assert app_factory() == "app"
    assert built_models[0] is not built_models[1]
    assert calls == {
        "address": "127.0.0.1",
        "port": 0,
        "show": False,
        "start": False,
        "verbose": False,
    }
    assert capsys.readouterr().out == "Persistra inspector: http://127.0.0.1:43123\n"
    with pytest.raises(InspectionError, match="between"):
        _inspection.serve_inspector(inspection, port=0)


def test_inspector_server_reports_an_occupied_explicit_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def serve(_app: object, **kwargs: object) -> None:
        selected_port = kwargs["port"]
        assert isinstance(selected_port, int)
        calls.append(selected_port)
        raise OSError(errno.EADDRINUSE, "Address already in use")

    fake_panel = SimpleNamespace(serve=serve)
    inspection = _inspection.DirectoryInspection(Path("/tmp"), (), ())
    monkeypatch.setattr(_inspection, "_load_panel", lambda: fake_panel)

    with pytest.raises(
        InspectionError,
        match=r"port 8123 is already in use.*choose another port or omit --port",
    ):
        _inspection.serve_inspector(inspection, port=8123)
    assert calls == [8123]


def test_inspector_server_cleans_up_after_a_partial_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def fail() -> None:
        events.append("run")
        raise RuntimeError("startup failed")

    def stop(*, wait: bool) -> None:
        events.append(f"stop:{wait}")

    server = SimpleNamespace(port=43123, run_until_shutdown=fail, stop=stop)

    def serve(_app: object, **_kwargs: object) -> object:
        return server

    fake_panel = SimpleNamespace(serve=serve)
    inspection = _inspection.DirectoryInspection(Path("/tmp"), (), ())
    monkeypatch.setattr(_inspection, "_load_panel", lambda: fake_panel)

    with pytest.raises(RuntimeError, match="startup failed"):
        _inspection.serve_inspector(inspection)
    assert events == ["run", "stop:False"]


def test_panel_app_factory_isolates_every_session_selector(tmp_path: Path) -> None:
    pn = pytest.importorskip("panel")

    _store(tmp_path / "a.duckdb", synthetic.bars("AAA", periods=1))
    second = _store(
        tmp_path / "b.duckdb",
        synthetic.bars("BBB", periods=1),
        synthetic.series("SYNTH_GDP", periods=1),
        synthetic.series("SYNTH_GDP", periods=2),
        synthetic.series("SYNTH_CPI", periods=1),
    )
    inspection = discover_stores(tmp_path)
    factory = _inspection._panel_app_factory(  # pyright: ignore[reportPrivateUsage]
        inspection, pn
    )
    changed_app = factory()
    untouched_app = factory()
    changed = _panel_widgets(changed_app)
    untouched = _panel_widgets(untouched_app)
    untouched_values = {name: widget.value for name, widget in untouched.items()}

    changed["Store"].value = second.resolve()
    changed["Family"].value = "series"
    target = next(
        dataset
        for dataset in inspection.stores[1].datasets
        if dataset.family == "series" and dataset.snapshot_count == 2
    )
    changed["Dataset scope"].value = target.scope_key
    snapshots = tuple(changed["Snapshot"].options.values())
    changed["Snapshot"].value = snapshots[-1]
    changed["View mode"].value = "Cumulative retained data"

    assert changed["Store"].value != untouched_values["Store"]
    assert changed["Family"].value != untouched_values["Family"]
    assert changed["Dataset scope"].value != untouched_values["Dataset scope"]
    assert changed["Snapshot"].value != untouched_values["Snapshot"]
    assert changed["View mode"].value != untouched_values["View mode"]
    assert {name: widget.value for name, widget in untouched.items()} == untouched_values


def test_panel_app_factory_applies_theme_per_http_session(tmp_path: Path) -> None:
    pn = pytest.importorskip("panel")
    tornado = pytest.importorskip("tornado.ioloop")

    _store(tmp_path / "data.duckdb", synthetic.bars(periods=1))
    inspection = discover_stores(tmp_path)
    factory = _inspection._panel_app_factory(  # pyright: ignore[reportPrivateUsage]
        inspection, pn
    )
    loop = tornado.IOLoop(make_current=False)
    server = pn.serve(
        factory,
        address="127.0.0.1",
        port=0,
        loop=loop,
        show=False,
        start=False,
        verbose=False,
    )
    context = server._tornado.applications["/"]

    def session_theme(session_id: str, arguments: dict[str, list[bytes]], uri: str) -> str:
        request = SimpleNamespace(
            arguments=arguments,
            cookies={},
            headers={},
            protocol="http",
            host=f"127.0.0.1:{server.port}",
            uri=uri,
            path="/",
            app_path="/",
        )
        session = loop.run_sync(
            lambda: context.create_session_if_needed(session_id, request=request)
        )
        return str(session.document.template_variables["theme"])

    try:
        default = session_theme("default", {}, "/")
        dark = session_theme("dark", {"theme": [b"dark"]}, "/?theme=dark")
        restored = session_theme("restored", {}, "/")
    finally:
        server.stop()
        loop.close(all_fds=True)

    assert default == "default"
    assert dark == "dark"
    assert restored == "default"
