"""Read-only store discovery, inspection views, and optional Panel adapter."""

from __future__ import annotations

import errno
import os
from dataclasses import dataclass, fields
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import matplotlib.pyplot as plt
import pandas as pd

from persistra.data import DuckDBStore, StoredDataset, StoredResult, StoredSnapshot
from persistra.errors import ProjectError, StoreError
from persistra.model import (
    BarSet,
    CommoditySpotQuote,
    ExchangeRateQuote,
    InstrumentSearchResult,
    OptionChain,
    SeriesSet,
    VintageSeriesSet,
)
from persistra.project import PROJECT_FORMAT_VERSION, PersistraProject
from persistra.viz import (
    plot_candlesticks,
    plot_greek_profile,
    plot_implied_volatility_smile,
    plot_implied_volatility_surface,
    plot_option_chain_prices,
    plot_option_volume_open_interest,
    plot_scalar_series,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class DiscoveredStore:
    """One supported store found beneath an explicit directory."""

    path: Path
    schema_version: int
    datasets: tuple[StoredDataset, ...]


@dataclass(frozen=True, slots=True)
class DirectoryInspection:
    """Validated store discovery results and nonfatal warnings."""

    directory: Path
    stores: tuple[DiscoveredStore, ...]
    warnings: tuple[str, ...]
    project_name: str | None = None
    project_format_version: int | None = None


@dataclass(frozen=True, slots=True)
class NamedTable:
    """One labeled read-only table for a normalized result."""

    name: str
    frame: pd.DataFrame


class InspectionError(ValueError):
    """Raised when an inspector request cannot be fulfilled."""


def discover_stores(directory: str | Path, *, recursive: bool = False) -> DirectoryInspection:
    """Discover supported Persistra stores without following symlinks."""
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise InspectionError(f"inspection directory does not exist or is not a directory: {root}")
    candidates, traversal_warnings = _candidate_paths(root, recursive=recursive)
    stores: list[DiscoveredStore] = []
    warnings = list(traversal_warnings)
    project_name: str | None = None
    project_format_version: int | None = None
    manifest_path = root / "persistra.toml"
    if manifest_path.exists() or manifest_path.is_symlink():
        try:
            project = PersistraProject.open(root)
            project_name = project.name
            project_format_version = PROJECT_FORMAT_VERSION
        except ProjectError as error:
            warnings.append(f"{manifest_path}: {error}")
    for path in candidates:
        try:
            with DuckDBStore.open(path, read_only=True) as store:
                stores.append(DiscoveredStore(path, store.schema_version, store.list_datasets()))
        except (StoreError, OSError, RuntimeError) as error:
            warnings.append(f"{path}: {error}")
    if not stores:
        detail = f" Warnings: {'; '.join(warnings)}" if warnings else ""
        raise InspectionError(f"no supported Persistra stores found in {root}.{detail}")
    return DirectoryInspection(
        root,
        tuple(stores),
        tuple(warnings),
        project_name,
        project_format_version,
    )


def _candidate_paths(
    root: Path, *, recursive: bool
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    if not recursive:
        entries = (path for path in root.iterdir() if path.parent == root)
        paths = tuple(
            sorted(
                path.resolve()
                for path in entries
                if path.suffix == ".duckdb" and path.is_file() and not path.is_symlink()
            )
        )
        return paths, ()
    found: list[Path] = []
    warnings: list[str] = []

    def record_error(error: OSError) -> None:
        failed_path = root if error.filename is None else Path(os.fsdecode(error.filename))
        detail = error.strerror or str(error)
        warnings.append(f"{failed_path}: could not traverse directory: {detail}")

    for current, directories, files in os.walk(
        root, followlinks=False, onerror=record_error
    ):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories if not (current_path / name).is_symlink()
        )
        for name in sorted(files):
            path = current_path / name
            if path.suffix == ".duckdb" and path.is_file() and not path.is_symlink():
                found.append(path.resolve())
    return tuple(found), tuple(sorted(warnings))


class InspectorViewModel:
    """Framework-neutral read-only access to discovered stores."""

    def __init__(self, inspection: DirectoryInspection) -> None:
        self.inspection = inspection
        self._stores = {store.path: store for store in inspection.stores}

    def store(self, path: str | Path) -> DiscoveredStore:
        """Return one discovered store by its resolved path."""
        target = Path(path).resolve()
        try:
            return self._stores[target]
        except KeyError as error:
            raise InspectionError(f"store is not part of this inspection: {target}") from error

    def snapshots(
        self, path: str | Path, family: str, scope_key: str
    ) -> tuple[StoredSnapshot, ...]:
        """Load current snapshot history from a read-only connection."""
        target = self.store(path).path
        try:
            with DuckDBStore.open(target, read_only=True) as store:
                return store.list_snapshots(family, scope_key)
        except (StoreError, OSError, RuntimeError) as error:
            raise InspectionError(f"could not inspect {target}: {error}") from error

    def exact_result(
        self,
        path: str | Path,
        family: str,
        scope_key: str,
        snapshot_id: str,
    ) -> StoredResult:
        """Load one exact snapshot after validating its selected dataset context."""
        target = self.store(path).path
        try:
            with DuckDBStore.open(target, read_only=True) as store:
                history = store.list_snapshots(family, scope_key)
                if snapshot_id not in {snapshot.snapshot_id for snapshot in history}:
                    raise InspectionError(
                        "snapshot is not part of the selected dataset: "
                        f"{family}/{scope_key}/{snapshot_id}"
                    )
                result = store.load_snapshot(snapshot_id)
        except (StoreError, OSError, RuntimeError, ValueError, TypeError) as error:
            if isinstance(error, InspectionError):
                raise
            raise InspectionError(f"could not decode snapshot {snapshot_id}: {error}") from error
        if result is None:
            raise InspectionError(f"snapshot no longer exists: {snapshot_id}")
        return result

    def cumulative_table(
        self,
        path: str | Path,
        family: str,
        scope_key: str,
    ) -> NamedTable:
        """Load the cumulative retained table for a supported family."""
        target = self.store(path).path
        try:
            with DuckDBStore.open(target, read_only=True) as store:
                if family == "bars":
                    frame = store.query_bars(scope_key)
                elif family == "series":
                    frame = store.query_series(scope_key)
                elif family == "vintage_series":
                    frame = store.query_vintage_series(scope_key)
                else:
                    raise InspectionError(f"cumulative mode is not available for {family}")
        except (StoreError, OSError, RuntimeError, ValueError, TypeError) as error:
            if isinstance(error, InspectionError):
                raise
            raise InspectionError(
                f"could not inspect cumulative data in {target}: {error}"
            ) from error
        return NamedTable("Cumulative retained data", frame)


def result_tables(result: StoredResult) -> tuple[NamedTable, ...]:
    """Convert every supported normalized result into display tables."""
    if isinstance(result, OptionChain):
        return (
            NamedTable("Contracts", result.contracts.copy()),
            NamedTable("Observations", result.observations.copy()),
        )
    frame = getattr(result, "frame", None)
    if isinstance(frame, pd.DataFrame):
        return (NamedTable("Data", frame.copy()),)
    if isinstance(result, (ExchangeRateQuote, CommoditySpotQuote)):
        values = {
            field.name: getattr(result, field.name)
            for field in fields(result)
            if field.name != "metadata"
        }
        return (NamedTable("Details", _details_frame(values)),)
    raise TypeError(f"unsupported stored result: {type(result).__name__}")


def provenance_table(result: StoredResult) -> pd.DataFrame:
    """Return every acquisition metadata field as a key/value table."""
    metadata = result.metadata
    values = {field.name: getattr(metadata, field.name) for field in fields(metadata)}
    values["request_parameters"] = dict(metadata.request_parameters)
    values["diagnostics"] = tuple(metadata.diagnostics)
    return _details_frame(values)


def result_summary(result: StoredResult) -> pd.DataFrame:
    """Return basic identity and row summaries without deriving research measures."""
    values: dict[str, object] = {"result_type": type(result).__name__}
    tables = result_tables(result)
    values["table_count"] = len(tables)
    values["row_count"] = sum(len(table.frame) for table in tables)
    if isinstance(result, BarSet):
        values["identity"] = result.instrument.instrument_id
    elif isinstance(result, (SeriesSet, VintageSeriesSet)):
        values["identity"] = result.definition.series_id
    elif isinstance(result, OptionChain):
        values["identity"] = result.underlying_instrument_id
        values["chain_date"] = result.chain_date
    elif isinstance(result, InstrumentSearchResult):
        values["identity"] = result.query
    elif isinstance(result, (ExchangeRateQuote, CommoditySpotQuote)):
        values["identity"] = getattr(result, "instrument_id", getattr(result, "series_id", ""))
    return _details_frame(values)


def _details_frame(values: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(
        {"field": tuple(values), "value": tuple(_display_value(value) for value in values.values())}
    )


def _display_value(value: object) -> object:
    if isinstance(value, os.PathLike):
        return os.fsdecode(cast("os.PathLike[str]", value))
    if isinstance(value, dict):
        return repr(cast("dict[object, object]", value))
    if isinstance(value, tuple):
        return repr(cast("tuple[object, ...]", value))
    return value


def build_panel_app(view_model: InspectorViewModel, panel: Any | None = None) -> Any:
    """Build the thin Panel application without starting a server."""
    pn = panel if panel is not None else _load_panel()
    pn.extension("tabulator")
    first = view_model.inspection.stores[0]
    store_select = pn.widgets.Select(
        label="Store",
        options={
            str(item.path.relative_to(view_model.inspection.directory)): item.path
            for item in view_model.inspection.stores
        },
        value=first.path,
    )
    family_select = pn.widgets.Select(label="Family")
    scope_select = pn.widgets.Select(label="Dataset scope")
    snapshot_select = pn.widgets.Select(label="Snapshot")
    mode_select = pn.widgets.RadioButtonGroup(
        label="View mode",
        options=["Exact snapshot", "Cumulative retained data"],
        value="Exact snapshot",
    )
    content = pn.Column()
    updating = False

    def render(
        store: Path,
        family: str | None,
        scope: str | None,
        snapshot: str | None,
        mode: str,
    ) -> Any:
        if family is None or scope is None:
            return pn.pane.Alert(
                "This store contains no saved datasets.",
                alert_type="info",
            )
        if snapshot is None:
            return pn.pane.Alert(
                "This dataset contains no saved snapshots.",
                alert_type="info",
            )
        try:
            return _render_selection(pn, view_model, store, family, scope, snapshot, mode)
        except (InspectionError, StoreError, OSError, RuntimeError, ValueError, TypeError) as error:
            return pn.pane.Alert(str(error), alert_type="danger")

    def render_current(*_events: object) -> None:
        if updating:
            return
        content.objects = [
            render(
                cast("Path", store_select.value),
                cast("str | None", family_select.value),
                cast("str | None", scope_select.value),
                cast("str | None", snapshot_select.value),
                str(mode_select.value),
            )
        ]

    def refresh_context(*_events: object) -> None:
        nonlocal updating
        if updating:
            return
        updating = True
        try:
            store = view_model.store(cast("Path", store_select.value))
            families = tuple(sorted({dataset.family for dataset in store.datasets}))
            selected_family = (
                family_select.value
                if family_select.value in families
                else next(iter(families), None)
            )
            family_select.options = list(families)
            family_select.value = selected_family

            scopes = tuple(
                dataset.scope_key
                for dataset in store.datasets
                if dataset.family == selected_family
            )
            selected_scope = (
                scope_select.value if scope_select.value in scopes else next(iter(scopes), None)
            )
            scope_options = {scope: scope for scope in scopes}
            scope_select.options = scope_options
            scope_select.value = selected_scope

            history = (
                ()
                if selected_family is None or selected_scope is None
                else view_model.snapshots(store.path, selected_family, selected_scope)
            )
            snapshot_options = {
                f"{snapshot.first_seen.isoformat()} · {snapshot.snapshot_id[:12]}": (
                    snapshot.snapshot_id
                )
                for snapshot in history
            }
            snapshot_ids = tuple(snapshot_options.values())
            selected_snapshot = (
                snapshot_select.value
                if snapshot_select.value in snapshot_ids
                else next(iter(snapshot_ids), None)
            )
            snapshot_select.options = snapshot_options
            snapshot_select.value = selected_snapshot

            modes = (
                ["Exact snapshot", "Cumulative retained data"]
                if selected_family in {"bars", "series", "vintage_series"}
                else ["Exact snapshot"]
            )
            mode_select.options = modes
            mode_select.value = mode_select.value if mode_select.value in modes else modes[0]
        finally:
            updating = False
        render_current()

    store_select.param.watch(refresh_context, "value")
    family_select.param.watch(refresh_context, "value")
    scope_select.param.watch(refresh_context, "value")
    snapshot_select.param.watch(render_current, "value")
    mode_select.param.watch(render_current, "value")
    refresh_context()
    warning = (
        pn.pane.Alert("\n".join(view_model.inspection.warnings), alert_type="warning")
        if view_model.inspection.warnings
        else None
    )
    sidebar = pn.Column(store_select, family_select, scope_select, snapshot_select, mode_select)
    main = [warning, content] if warning is not None else [content]
    return pn.template.FastListTemplate(
        title="Persistra Inspector",
        sidebar=[sidebar],
        main=main,
    )


def _render_selection(
    pn: Any,
    view_model: InspectorViewModel,
    store_path: Path,
    family: str,
    scope: str,
    snapshot_id: str,
    mode: str,
) -> Any:
    discovered = view_model.store(store_path)
    dataset = next(
        (
            item
            for item in discovered.datasets
            if item.family == family and item.scope_key == scope
        ),
        None,
    )
    if dataset is None:
        raise InspectionError(f"dataset is not part of this inspection: {family}/{scope}")
    overview_values: dict[str, object] = {
        "store_path": discovered.path,
        "schema_version": discovered.schema_version,
        "family": family,
        "scope_key": scope,
        "snapshot_count": dataset.snapshot_count,
        "first_seen": dataset.first_seen,
        "last_seen": dataset.last_seen,
        "latest_snapshot_id": dataset.latest_snapshot_id,
        "view_mode": mode,
    }
    if view_model.inspection.project_name is not None:
        overview_values["project_name"] = view_model.inspection.project_name
        overview_values["project_format_version"] = (
            view_model.inspection.project_format_version
        )
    history = view_model.snapshots(store_path, family, scope)
    history_frame = pd.DataFrame(
        [
            {
                "snapshot_id": item.snapshot_id,
                "content_hash": item.content_hash,
                "first_seen": item.first_seen,
                "last_seen": item.last_seen,
                "saved_order": item.saved_order,
            }
            for item in history
        ]
    )
    if mode == "Cumulative retained data":
        table = view_model.cumulative_table(store_path, family, scope)
        overview = pn.Column(
            pn.pane.Alert(
                "This view combines retained rows across snapshots. "
                "It is not one acquisition snapshot.",
                alert_type="info",
            ),
            _tabulator(pn, _details_frame(overview_values)),
        )
        return pn.Tabs(
            ("Overview", overview),
            ("Data", _tabulator(pn, table.frame)),
            ("Visualization", pn.pane.Markdown("Cumulative mode is tabular in this release.")),
            (
                "Provenance",
                pn.pane.Markdown(
                    "Cumulative rows do not share one snapshot provenance record."
                ),
            ),
            ("Snapshot history", _tabulator(pn, history_frame)),
        )
    result = view_model.exact_result(store_path, family, scope, snapshot_id)
    summary = result_summary(result)
    overview = pn.Column(
        pn.pane.Alert("This view is one exact acquisition snapshot.", alert_type="success"),
        _tabulator(pn, pd.concat([_details_frame(overview_values), summary], ignore_index=True)),
    )
    tables = result_tables(result)
    data_view = (
        _tabulator(pn, tables[0].frame)
        if len(tables) == 1
        else pn.Tabs(*((table.name, _tabulator(pn, table.frame)) for table in tables))
    )
    return pn.Tabs(
        ("Overview", overview),
        ("Data", data_view),
        ("Visualization", _visualization_panel(pn, result)),
        ("Provenance", _tabulator(pn, provenance_table(result))),
        ("Snapshot history", _tabulator(pn, history_frame)),
    )


def _tabulator(pn: Any, frame: pd.DataFrame) -> Any:
    return pn.widgets.Tabulator(
        _browser_frame(frame),
        disabled=True,
        show_index=False,
        pagination="local",
        page_size=25,
        header_filters=True,
        sizing_mode="stretch_width",
    )


def _browser_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy tabular display data and serialize filesystem values for the browser."""
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == object:
            result[column] = result[column].map(_display_value)
    return result


def _visualization_panel(pn: Any, result: StoredResult) -> Any:
    try:
        if isinstance(result, BarSet):
            axes = plot_candlesticks(result)
            return _figure_pane(pn, axes.price.figure)
        if isinstance(result, SeriesSet):
            axes = plot_scalar_series(result)
            return _figure_pane(pn, axes.figure)
        if isinstance(result, OptionChain):
            expirations = tuple(sorted(set(result.contracts["expiration"].dt.date)))
            expiration = pn.widgets.Select(label="Expiration", options=list(expirations))
            side = pn.widgets.Select(label="Option type", options=[None, "call", "put"])
            greek = pn.widgets.Select(
                label="Greek", options=["delta", "gamma", "theta", "vega", "rho"]
            )

            def option_tabs(
                selected_expiration: object,
                selected_side: object,
                selected_greek: str,
            ) -> Any:
                try:
                    prices = plot_option_chain_prices(result)
                    volume = plot_option_volume_open_interest(result)
                    smile = plot_implied_volatility_smile(
                        result,
                        expiration=cast("Any", selected_expiration),
                        option_type=cast("str | None", selected_side),
                    )
                    surface = plot_implied_volatility_surface(result)
                    greek_axes = plot_greek_profile(
                        result,
                        selected_greek,
                        expiration=cast("Any", selected_expiration),
                        option_type=cast("str | None", selected_side),
                    )
                    return pn.Tabs(
                        ("Prices", _figure_pane(pn, prices.figure)),
                        ("Volume and open interest", _figure_pane(pn, volume.figure)),
                        ("Volatility smile", _figure_pane(pn, smile.figure)),
                        ("Volatility surface", _figure_pane(pn, surface.figure)),
                        ("Greek profile", _figure_pane(pn, greek_axes.figure)),
                    )
                except (ValueError, TypeError, KeyError) as error:
                    plt.close("all")
                    return pn.pane.Alert(str(error), alert_type="warning")

            return pn.Column(
                pn.Row(expiration, side, greek),
                pn.bind(option_tabs, expiration, side, greek),
            )
        return pn.pane.Markdown("This normalized family has a table-only view in this release.")
    except (ValueError, TypeError, KeyError) as error:
        plt.close("all")
        return pn.pane.Alert(str(error), alert_type="warning")


def _figure_pane(pn: Any, figure: Any) -> Any:
    pane = pn.pane.Matplotlib(figure, tight=True)
    plt.close(figure)
    return pane


def _load_panel() -> Any:
    try:
        return import_module("panel")
    except ImportError as error:
        raise InspectionError(
            "the inspector requires the optional dependency: install persistra[inspect]"
        ) from error


def _panel_app_factory(inspection: DirectoryInspection, pn: Any) -> Callable[[], Any]:
    """Return a factory that constructs isolated state for each browser session."""

    def create_app() -> Any:
        return build_panel_app(InspectorViewModel(inspection), panel=pn)

    return create_app


def serve_inspector(
    inspection: DirectoryInspection,
    *,
    port: int | None = None,
    open_browser: bool = True,
) -> None:
    """Serve the local inspector on the loopback interface."""
    if port is not None and not 1 <= port <= 65535:
        raise InspectionError("port must be between 1 and 65535")
    pn = _load_panel()
    server = None
    try:
        server = pn.serve(
            _panel_app_factory(inspection, pn),
            address="127.0.0.1",
            port=0 if port is None else port,
            show=open_browser,
            start=False,
            verbose=False,
        )
        selected_port = server.port
        if not isinstance(selected_port, int) or not 1 <= selected_port <= 65535:
            raise InspectionError("the inspector server did not report its bound port")
        print(f"Persistra inspector: http://127.0.0.1:{selected_port}")
        server.run_until_shutdown()
    except OSError as error:
        if server is not None:
            server.stop(wait=False)
        if port is not None and error.errno == errno.EADDRINUSE:
            raise InspectionError(
                f"port {port} is already in use on 127.0.0.1; "
                "choose another port or omit --port"
            ) from error
        raise InspectionError(f"could not start the inspector server: {error}") from error
    except Exception:
        if server is not None:
            server.stop(wait=False)
        raise
