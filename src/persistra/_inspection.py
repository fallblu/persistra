"""Read-only store discovery, inspection views, and optional Panel adapter."""

from __future__ import annotations

import errno
import os
from collections import OrderedDict
from dataclasses import dataclass, fields, replace
from datetime import date, datetime
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.data import DuckDBStore, StoredDataset, StoredPage, StoredResult, StoredSnapshot
from persistra.errors import ProjectError, StoreError
from persistra.model import (
    BarSet,
    CommoditySpotQuote,
    ExchangeRateQuote,
    InstrumentSearchResult,
    OptionChain,
    SeriesSet,
    VintageDatesResult,
    VintageSeriesSet,
)
from persistra.project import PROJECT_FORMAT_VERSION, PersistraProject

if TYPE_CHECKING:
    from collections.abc import Callable


INSPECTION_INVENTORY_VERSION = 1
INSPECTOR_PAGE_SIZE = 100
INSPECTOR_EXACT_ROW_LIMIT = 1_000
INSPECTOR_PLOT_SAMPLE_LIMIT = 2_000
_OPTION_VISUALIZATION_CACHE_LIMIT = 8


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
    recursive: bool = False


@dataclass(frozen=True, slots=True)
class InspectionRefresh:
    """One rediscovery result with deterministic store changes."""

    inspection: DirectoryInspection
    added: tuple[Path, ...]
    removed: tuple[Path, ...]
    invalid: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class CumulativeFilters:
    """Validated optional filters for one cumulative store query."""

    interval: str | None = None
    start: date | datetime | None = None
    end: date | datetime | None = None
    start_label: str | None = None
    end_label: str | None = None
    available_on: date | None = None
    retrieved_before: datetime | None = None


@dataclass(frozen=True, slots=True)
class NamedTable:
    """One labeled read-only table for a normalized result."""

    name: str
    frame: pd.DataFrame


class InspectionError(ValueError):
    """Raised when an inspector request cannot be fulfilled."""


def discover_stores(
    directory: str | Path,
    *,
    recursive: bool = False,
    allow_empty: bool = False,
) -> DirectoryInspection:
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
    if not stores and not allow_empty:
        detail = f" Warnings: {'; '.join(warnings)}" if warnings else ""
        raise InspectionError(f"no supported Persistra stores found in {root}.{detail}")
    return DirectoryInspection(
        root,
        tuple(stores),
        tuple(warnings),
        project_name,
        project_format_version,
        recursive,
    )


def parse_cumulative_filters(
    family: str,
    *,
    interval: str = "",
    start: str = "",
    end: str = "",
    start_label: str = "",
    end_label: str = "",
    available_on: str = "",
    retrieved_before: str = "",
) -> CumulativeFilters:
    """Parse family-specific cumulative filters before any store query."""
    if family not in {"bars", "series", "vintage_series"}:
        raise InspectionError(f"cumulative filters are not available for {family}")
    retrieval = _parse_datetime(retrieved_before, "retrieval cutoff")
    if family == "bars":
        start_bound = _parse_date_or_datetime(start, "start")
        end_bound = _parse_date_or_datetime(end, "end")
        if (
            start_bound is not None
            and end_bound is not None
            and isinstance(start_bound, datetime) != isinstance(end_bound, datetime)
        ):
            raise InspectionError("start and end must both be dates or timezone-aware datetimes")
        if start_bound is not None and end_bound is not None and start_bound > end_bound:
            raise InspectionError("start must not follow end")
        return CumulativeFilters(
            interval=_optional_text(interval),
            start=start_bound,
            end=end_bound,
            retrieved_before=retrieval,
        )
    first_label = _optional_text(start_label)
    last_label = _optional_text(end_label)
    if first_label is not None and last_label is not None and first_label > last_label:
        raise InspectionError("start label must not follow end label")
    return CumulativeFilters(
        start_label=first_label,
        end_label=last_label,
        available_on=(
            _parse_date(available_on, "availability date") if family == "vintage_series" else None
        ),
        retrieved_before=retrieval,
    )


def _optional_text(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None


def _parse_date(value: str, name: str) -> date | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError as error:
        raise InspectionError(f"{name} must be an ISO 8601 date") from error


def _parse_datetime(value: str, name: str) -> datetime | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        moment = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise InspectionError(f"{name} must be an ISO 8601 datetime") from error
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise InspectionError(f"{name} must include a timezone offset")
    return moment


def _parse_date_or_datetime(value: str, name: str) -> date | datetime | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    if "T" not in normalized and " " not in normalized:
        return _parse_date(normalized, name)
    return _parse_datetime(normalized, name)


def inventory_document(inspection: DirectoryInspection) -> dict[str, object]:
    """Return a deterministic versioned document for one directory inspection."""
    project = (
        None
        if inspection.project_name is None
        else {
            "name": inspection.project_name,
            "format_version": inspection.project_format_version,
        }
    )
    return {
        "inventory_version": INSPECTION_INVENTORY_VERSION,
        "directory": str(inspection.directory),
        "project": project,
        "warnings": list(inspection.warnings),
        "store_count": len(inspection.stores),
        "stores": [
            {
                "path": str(store.path),
                "schema_version": store.schema_version,
                "dataset_count": len(store.datasets),
                "datasets": [
                    {
                        "family": dataset.family,
                        "scope_key": dataset.scope_key,
                        "snapshot_count": dataset.snapshot_count,
                        "first_seen": dataset.first_seen.isoformat(),
                        "last_seen": dataset.last_seen.isoformat(),
                        "latest_snapshot_id": dataset.latest_snapshot_id,
                    }
                    for dataset in store.datasets
                ],
            }
            for store in inspection.stores
        ],
    }


def _candidate_paths(root: Path, *, recursive: bool) -> tuple[tuple[Path, ...], tuple[str, ...]]:
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

    for current, directories, files in os.walk(root, followlinks=False, onerror=record_error):
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

    def refresh(self) -> InspectionRefresh:
        """Repeat the original discovery and replace the current read-only inventory."""
        previous = set(self._stores)
        inspection = discover_stores(
            self.inspection.directory,
            recursive=self.inspection.recursive,
            allow_empty=True,
        )
        current = {store.path for store in inspection.stores}
        lost = previous - current
        invalid = {
            path
            for path in lost
            if any(warning.startswith(f"{path}:") for warning in inspection.warnings)
        }
        self.inspection = inspection
        self._stores = {store.path: store for store in inspection.stores}
        return InspectionRefresh(
            inspection,
            tuple(sorted(current - previous)),
            tuple(sorted(lost - invalid)),
            tuple(sorted(invalid)),
        )

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
        filters: CumulativeFilters | None = None,
    ) -> NamedTable:
        """Load the cumulative retained table for a supported family."""
        target = self.store(path).path
        selected = CumulativeFilters() if filters is None else filters
        try:
            with DuckDBStore.open(target, read_only=True) as store:
                if family == "bars":
                    frame = store.query_bars(
                        scope_key,
                        interval=selected.interval,
                        start=selected.start,
                        end=selected.end,
                        retrieved_before=selected.retrieved_before,
                    )
                elif family == "series":
                    frame = store.query_series(
                        scope_key,
                        start_label=selected.start_label,
                        end_label=selected.end_label,
                        retrieved_before=selected.retrieved_before,
                    )
                elif family == "vintage_series":
                    frame = store.query_vintage_series(
                        scope_key,
                        start_label=selected.start_label,
                        end_label=selected.end_label,
                        available_on=selected.available_on,
                        retrieved_before=selected.retrieved_before,
                    )
                else:
                    raise InspectionError(f"cumulative mode is not available for {family}")
        except (StoreError, OSError, RuntimeError, ValueError, TypeError) as error:
            if isinstance(error, InspectionError):
                raise
            raise InspectionError(
                f"could not inspect cumulative data in {target}: {error}"
            ) from error
        return NamedTable("Cumulative retained data", frame)

    def cumulative_page(
        self,
        path: str | Path,
        family: str,
        scope_key: str,
        filters: CumulativeFilters | None = None,
        *,
        limit: int = INSPECTOR_PAGE_SIZE,
        offset: int = 0,
        sort_by: str | None = None,
        descending: bool = False,
    ) -> StoredPage:
        """Load one bounded cumulative page with an exact filtered total."""
        target = self.store(path).path
        selected = CumulativeFilters() if filters is None else filters
        try:
            with DuckDBStore.open(target, read_only=True) as store:
                if family == "bars":
                    page = store.query_bars_page(
                        scope_key,
                        interval=selected.interval,
                        start=selected.start,
                        end=selected.end,
                        retrieved_before=selected.retrieved_before,
                        limit=limit,
                        offset=offset,
                        sort_by=sort_by,
                        descending=descending,
                    )
                elif family == "series":
                    page = store.query_series_page(
                        scope_key,
                        start_label=selected.start_label,
                        end_label=selected.end_label,
                        retrieved_before=selected.retrieved_before,
                        limit=limit,
                        offset=offset,
                        sort_by=sort_by,
                        descending=descending,
                    )
                elif family == "vintage_series":
                    page = store.query_vintage_series_page(
                        scope_key,
                        start_label=selected.start_label,
                        end_label=selected.end_label,
                        available_on=selected.available_on,
                        retrieved_before=selected.retrieved_before,
                        limit=limit,
                        offset=offset,
                        sort_by=sort_by,
                        descending=descending,
                    )
                else:
                    raise InspectionError(f"cumulative mode is not available for {family}")
        except (StoreError, OSError, RuntimeError, ValueError, TypeError) as error:
            if isinstance(error, InspectionError):
                raise
            raise InspectionError(
                f"could not inspect cumulative data in {target}: {error}"
            ) from error
        return page


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
    if isinstance(result, VintageDatesResult):
        frame = pd.DataFrame(
            {
                "provider_series": [result.provider_series] * len(result.dates),
                "vintage_date": result.dates,
            }
        )
        return (NamedTable("Vintage dates", frame),)
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
    elif isinstance(result, VintageDatesResult):
        values["identity"] = result.provider_series
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
    refresh_button = pn.widgets.Button(label="Refresh", color="primary")
    interval_input = pn.widgets.TextInput(label="Interval", placeholder="daily")
    start_input = pn.widgets.TextInput(label="Start", placeholder="YYYY-MM-DD or ISO datetime")
    end_input = pn.widgets.TextInput(label="End", placeholder="YYYY-MM-DD or ISO datetime")
    start_label_input = pn.widgets.TextInput(label="Start label")
    end_label_input = pn.widgets.TextInput(label="End label")
    available_on_input = pn.widgets.TextInput(label="Availability date", placeholder="YYYY-MM-DD")
    retrieved_before_input = pn.widgets.TextInput(
        label="Retrieval cutoff", placeholder="ISO datetime with timezone"
    )
    apply_filters = pn.widgets.Button(label="Apply filters", color="primary")
    filter_families = (
        (interval_input, frozenset({"bars"})),
        (start_input, frozenset({"bars"})),
        (end_input, frozenset({"bars"})),
        (start_label_input, frozenset({"series", "vintage_series"})),
        (end_label_input, frozenset({"series", "vintage_series"})),
        (available_on_input, frozenset({"vintage_series"})),
        (retrieved_before_input, frozenset({"bars", "series", "vintage_series"})),
    )
    content = pn.Column()
    warnings_content = pn.Column()
    refresh_status = pn.Column()
    updating = False
    filter_family: str | None = None

    def configure_filters(family: str | None, mode: str) -> None:
        nonlocal filter_family
        if family != filter_family:
            for widget, families in filter_families:
                if family not in families:
                    widget.value = ""
            filter_family = family
        cumulative = mode == "Cumulative retained data"
        for widget, families in filter_families:
            widget.visible = cumulative and family in families
        apply_filters.visible = cumulative and family in {
            "bars",
            "series",
            "vintage_series",
        }

    def selected_filters(family: str, mode: str) -> CumulativeFilters:
        if mode != "Cumulative retained data":
            return CumulativeFilters()
        return parse_cumulative_filters(
            family,
            interval=str(interval_input.value),
            start=str(start_input.value),
            end=str(end_input.value),
            start_label=str(start_label_input.value),
            end_label=str(end_label_input.value),
            available_on=str(available_on_input.value),
            retrieved_before=str(retrieved_before_input.value),
        )

    def update_warnings() -> None:
        warnings_content.objects = (
            [
                pn.pane.Alert(
                    "\n".join(view_model.inspection.warnings),
                    alert_type="warning",
                )
            ]
            if view_model.inspection.warnings
            else []
        )

    def render(
        store: Path | None,
        family: str | None,
        scope: str | None,
        snapshot: str | None,
        mode: str,
    ) -> Any:
        if store is None:
            return pn.pane.Alert(
                "No supported Persistra stores are currently available.",
                alert_type="warning",
            )
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
            return _render_selection(
                pn,
                view_model,
                store,
                family,
                scope,
                snapshot,
                mode,
                selected_filters(family, mode),
            )
        except (InspectionError, StoreError, OSError, RuntimeError, ValueError, TypeError) as error:
            return pn.pane.Alert(str(error), alert_type="danger")

    def render_current(*_events: object) -> None:
        if updating:
            return
        content.objects = [
            render(
                cast("Path | None", store_select.value),
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
            selected_store = cast("Path | None", store_select.value)
            store = None if selected_store is None else view_model.store(selected_store)
            families = (
                () if store is None else tuple(sorted({item.family for item in store.datasets}))
            )
            selected_family = (
                family_select.value
                if family_select.value in families
                else next(iter(families), None)
            )
            family_select.options = list(families)
            family_select.value = selected_family

            scopes = (
                ()
                if store is None
                else tuple(
                    dataset.scope_key
                    for dataset in store.datasets
                    if dataset.family == selected_family
                )
            )
            selected_scope = (
                scope_select.value if scope_select.value in scopes else next(iter(scopes), None)
            )
            scope_select.options = {scope: scope for scope in scopes}
            scope_select.value = selected_scope

            history = (
                ()
                if store is None or selected_family is None or selected_scope is None
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
            configure_filters(selected_family, str(mode_select.value))
        finally:
            updating = False
        render_current()

    def mode_changed(*_events: object) -> None:
        if updating:
            return
        configure_filters(cast("str | None", family_select.value), str(mode_select.value))
        render_current()

    def refresh_discovery(*_events: object) -> None:
        nonlocal updating
        try:
            refreshed = view_model.refresh()
        except (InspectionError, OSError, RuntimeError) as error:
            refresh_status.objects = [pn.pane.Alert(str(error), alert_type="danger")]
            return
        selected_store = cast("Path | None", store_select.value)
        options = {
            str(item.path.relative_to(refreshed.inspection.directory)): item.path
            for item in refreshed.inspection.stores
        }
        paths = tuple(options.values())
        updating = True
        try:
            store_select.options = options
            store_select.value = (
                selected_store if selected_store in paths else next(iter(paths), None)
            )
        finally:
            updating = False
        update_warnings()
        changes: list[str] = []
        if refreshed.added:
            changes.append(
                f"added {len(refreshed.added)}: " + ", ".join(str(path) for path in refreshed.added)
            )
        if refreshed.removed:
            changes.append(
                f"removed {len(refreshed.removed)}: "
                + ", ".join(str(path) for path in refreshed.removed)
            )
        if refreshed.invalid:
            changes.append(
                f"newly invalid {len(refreshed.invalid)}: "
                + ", ".join(str(path) for path in refreshed.invalid)
            )
        if refreshed.inspection.warnings:
            changes.append(f"warnings {len(refreshed.inspection.warnings)}")
        detail = ", ".join(changes) if changes else "no store changes"
        refresh_status.objects = [
            pn.pane.Alert(
                f"Discovery refreshed: {detail}.",
                alert_type=(
                    "warning"
                    if refreshed.inspection.warnings or not refreshed.inspection.stores
                    else "success"
                ),
            )
        ]
        refresh_context()

    store_select.param.watch(refresh_context, "value")
    family_select.param.watch(refresh_context, "value")
    scope_select.param.watch(refresh_context, "value")
    snapshot_select.param.watch(render_current, "value")
    mode_select.param.watch(mode_changed, "value")
    apply_filters.on_click(render_current)
    refresh_button.on_click(refresh_discovery)
    refresh_context()
    update_warnings()
    sidebar = pn.Column(
        refresh_button,
        store_select,
        family_select,
        scope_select,
        snapshot_select,
        mode_select,
        interval_input,
        start_input,
        end_input,
        start_label_input,
        end_label_input,
        available_on_input,
        retrieved_before_input,
        apply_filters,
    )
    return pn.template.FastListTemplate(
        title="Persistra Inspector",
        sidebar=[sidebar],
        main=[warnings_content, refresh_status, content],
    )


def _render_selection(
    pn: Any,
    view_model: InspectorViewModel,
    store_path: Path,
    family: str,
    scope: str,
    snapshot_id: str,
    mode: str,
    filters: CumulativeFilters | None = None,
) -> Any:
    discovered = view_model.store(store_path)
    dataset = next(
        (item for item in discovered.datasets if item.family == family and item.scope_key == scope),
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
        overview_values["project_format_version"] = view_model.inspection.project_format_version
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
            (
                "Data",
                _cumulative_data_panel(
                    pn,
                    view_model,
                    store_path,
                    family,
                    scope,
                    filters,
                ),
            ),
            ("Visualization", pn.pane.Markdown("Cumulative mode is tabular in this release.")),
            (
                "Provenance",
                pn.pane.Markdown("Cumulative rows do not share one snapshot provenance record."),
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
        _bounded_table_view(pn, tables[0].frame)
        if len(tables) == 1
        else pn.Tabs(*((table.name, _bounded_table_view(pn, table.frame)) for table in tables))
    )
    return pn.Tabs(
        ("Overview", overview),
        ("Data", data_view),
        ("Visualization", _visualization_panel(pn, result)),
        ("Provenance", _tabulator(pn, provenance_table(result))),
        ("Snapshot history", _tabulator(pn, history_frame)),
    )


def _cumulative_data_panel(
    pn: Any,
    view_model: InspectorViewModel,
    store_path: Path,
    family: str,
    scope: str,
    filters: CumulativeFilters | None,
) -> Any:
    current_page = view_model.cumulative_page(
        store_path,
        family,
        scope,
        filters,
        limit=INSPECTOR_PAGE_SIZE,
    )
    sort_options: dict[str, str | None] = {"Default order": None}
    sort_options.update({column: column for column in current_page.frame.columns})
    sort = pn.widgets.Select(label="Sort column", options=sort_options, value=None)
    descending = pn.widgets.Checkbox(label="Descending", value=False)
    previous = pn.widgets.Button(label="Previous page")
    following = pn.widgets.Button(label="Next page")
    status = pn.pane.Markdown()
    warning = pn.Column()
    table = pn.Column()

    def display(page: StoredPage) -> None:
        nonlocal current_page
        current_page = page
        first_row = 0 if page.frame.empty else page.offset + 1
        last_row = page.offset + len(page.frame)
        status.object = f"Rows {first_row:,}-{last_row:,} of {page.total_count:,}"
        previous.disabled = not page.has_previous
        following.disabled = not page.has_next
        table.objects = [_tabulator(pn, page.frame, local_pagination=False)]

    def load(offset: int) -> None:
        try:
            page = view_model.cumulative_page(
                store_path,
                family,
                scope,
                filters,
                limit=INSPECTOR_PAGE_SIZE,
                offset=offset,
                sort_by=cast("str | None", sort.value),
                descending=bool(descending.value),
            )
        except InspectionError as error:
            warning.objects = [pn.pane.Alert(str(error), alert_type="danger")]
            return
        warning.objects = []
        display(page)

    def reset_sort(*_events: object) -> None:
        load(0)

    def previous_page(_event: object) -> None:
        load(max(0, current_page.offset - current_page.limit))

    def next_page(_event: object) -> None:
        load(current_page.offset + current_page.limit)

    previous.on_click(previous_page)
    following.on_click(next_page)
    sort.param.watch(reset_sort, "value")
    descending.param.watch(reset_sort, "value")
    display(current_page)
    return pn.Column(
        pn.Row(sort, descending, previous, following),
        status,
        warning,
        table,
    )


def _bounded_table_view(pn: Any, frame: pd.DataFrame) -> Any:
    if len(frame) <= INSPECTOR_EXACT_ROW_LIMIT:
        return _tabulator(pn, frame)
    return pn.Column(
        pn.pane.Alert(
            f"Showing the first {INSPECTOR_EXACT_ROW_LIMIT:,} of {len(frame):,} rows. "
            "Use the public paged store queries for bounded access to cumulative data.",
            alert_type="info",
        ),
        _tabulator(pn, frame.iloc[:INSPECTOR_EXACT_ROW_LIMIT].reset_index(drop=True)),
    )


def _tabulator(pn: Any, frame: pd.DataFrame, *, local_pagination: bool = True) -> Any:
    options: dict[str, object] = {
        "disabled": True,
        "show_index": False,
        "header_filters": local_pagination,
        "sizing_mode": "stretch_width",
    }
    if local_pagination:
        options.update({"pagination": "local", "page_size": 25})
    return pn.widgets.Tabulator(
        _browser_frame(frame),
        **options,
    )


def _browser_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy tabular display data and serialize filesystem values for the browser."""
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == object:
            result[column] = result[column].map(_display_value)
    return result


def _visualization_panel(pn: Any, result: StoredResult) -> Any:
    visualization = _load_visualization()
    sampled_result, sample_message = _sample_result_for_visualization(result)
    try:
        if isinstance(sampled_result, BarSet):
            content = _figure_pane(pn, visualization.plot_candlesticks(sampled_result))
        elif isinstance(sampled_result, SeriesSet):
            content = _figure_pane(pn, visualization.plot_scalar_series(sampled_result))
        elif isinstance(sampled_result, OptionChain):
            content = _lazy_option_visualizations(pn, sampled_result, visualization)
        else:
            content = pn.pane.Markdown(
                "This normalized family has a table-only view in this release."
            )
        if sample_message is None:
            return content
        return pn.Column(pn.pane.Alert(sample_message, alert_type="info"), content)
    except (ValueError, TypeError, KeyError) as error:
        return pn.pane.Alert(str(error), alert_type="warning")


def _sample_result_for_visualization(result: StoredResult) -> tuple[StoredResult, str | None]:
    if isinstance(result, (BarSet, SeriesSet)):
        if len(result.frame) <= INSPECTOR_PLOT_SAMPLE_LIMIT:
            return result, None
        sampled = _even_sample(result.frame, INSPECTOR_PLOT_SAMPLE_LIMIT)
        return (
            replace(result, frame=sampled),
            f"Plotting a deterministic sample of {len(sampled):,} of {len(result.frame):,} rows.",
        )
    if not isinstance(result, OptionChain) or len(result.contracts) <= INSPECTOR_PLOT_SAMPLE_LIMIT:
        return result, None
    groups = tuple(
        group
        for _, group in result.contracts.groupby(
            ["expiration", "option_type"], sort=True, observed=True
        )
    )
    base, remainder = divmod(INSPECTOR_PLOT_SAMPLE_LIMIT, len(groups))
    sampled_contracts = (
        pd.concat(
            [
                _even_sample(group, base + (position < remainder))
                for position, group in enumerate(groups)
                if base + (position < remainder) > 0
            ],
            ignore_index=True,
        )
        .sort_values(
            ["expiration", "strike", "option_type", "contract_id"],
            kind="stable",
            na_position="last",
        )
        .reset_index(drop=True)
    )
    keys = set(sampled_contracts[["provider", "contract_id"]].itertuples(index=False, name=None))
    observation_mask = [
        key in keys
        for key in result.observations[["provider", "contract_id"]].itertuples(
            index=False, name=None
        )
    ]
    sampled_observations = result.observations.loc[observation_mask].reset_index(drop=True)
    sampled_result = replace(
        result,
        contracts=sampled_contracts,
        observations=sampled_observations,
    )
    return (
        sampled_result,
        "Plotting a deterministic, expiration-and-side-stratified sample of "
        f"{len(sampled_contracts):,} of {len(result.contracts):,} contracts.",
    )


def _even_sample(frame: pd.DataFrame, limit: int) -> pd.DataFrame:
    if limit <= 0:
        return frame.iloc[:0].copy().reset_index(drop=True)
    if limit == 1:
        return frame.iloc[[0]].copy().reset_index(drop=True)
    if len(frame) <= limit:
        return frame.copy().reset_index(drop=True)
    positions = [position * (len(frame) - 1) // (limit - 1) for position in range(limit)]
    return frame.iloc[positions].copy().reset_index(drop=True)


def _lazy_option_visualizations(
    pn: Any,
    result: OptionChain,
    visualization: Any,
) -> Any:
    expirations = tuple(sorted(set(result.contracts["expiration"].dt.date)))
    expiration = pn.widgets.Select(label="Expiration", options=list(expirations))
    side = pn.widgets.Select(
        label="Option type",
        options={"All options": None, "Calls": "call", "Puts": "put"},
        value=None,
    )
    greek = pn.widgets.Select(label="Greek", options=["delta", "gamma", "theta", "vega", "rho"])
    labels = (
        "Prices",
        "Volume and open interest",
        "Volatility smile",
        "Volatility surface",
        "Greek profile",
    )
    containers = [pn.Column(pn.pane.Markdown("Open this tab to render its plot.")) for _ in labels]
    tabs = pn.Tabs(*zip(labels, containers, strict=True))
    cache: OrderedDict[tuple[object, ...], Any] = OrderedDict()

    def key(index: int) -> tuple[object, ...]:
        if index == 2:
            return ("smile", expiration.value, side.value)
        if index == 4:
            return ("greek", expiration.value, side.value, greek.value)
        return (("prices",), ("volume",), (), ("surface",))[index]

    def build(index: int) -> Any:
        if index == 0:
            return visualization.plot_option_chain_prices(result)
        if index == 1:
            return visualization.plot_option_volume_open_interest(result)
        if index == 2:
            return visualization.plot_implied_volatility_smile(
                result,
                expiration=expiration.value,
                option_type=cast("str | None", side.value),
            )
        if index == 3:
            return visualization.plot_implied_volatility_surface(result)
        return visualization.plot_greek_profile(
            result,
            cast("str", greek.value),
            expiration=expiration.value,
            option_type=cast("str | None", side.value),
        )

    def render(index: int) -> None:
        cache_key = key(index)
        pane = cache.get(cache_key)
        if pane is None:
            try:
                pane = _figure_pane(pn, build(index))
            except Exception as error:
                containers[index].objects = [pn.pane.Alert(str(error), alert_type="warning")]
                return
            cache[cache_key] = pane
            while len(cache) > _OPTION_VISUALIZATION_CACHE_LIMIT:
                _, evicted = cache.popitem(last=False)
                for container in containers:
                    if any(item is evicted for item in container.objects):
                        container.objects = [pn.pane.Markdown("Open this tab to render its plot.")]
                _release_visualization_pane(evicted)
        else:
            cache.move_to_end(cache_key)
        containers[index].objects = [pane]

    def render_active(*_events: object) -> None:
        render(int(tabs.active))

    def option_selection_changed(_event: object) -> None:
        if tabs.active in (2, 4):
            render_active()

    def greek_selection_changed(_event: object) -> None:
        if tabs.active == 4:
            render_active()

    tabs.param.watch(render_active, "active")
    expiration.param.watch(option_selection_changed, "value")
    side.param.watch(option_selection_changed, "value")
    greek.param.watch(greek_selection_changed, "value")
    render_active()
    return pn.Column(pn.Row(expiration, side, greek), tabs)


def _release_visualization_pane(pane: Any) -> None:
    try:
        pane.object = None
    except (AttributeError, TypeError, ValueError):
        return


def _figure_pane(pn: Any, figure: Any) -> Any:
    return pn.pane.Plotly(
        figure,
        config={"displaylogo": False, "responsive": True},
        sizing_mode="stretch_width",
    )


def _load_visualization() -> Any:
    try:
        return import_module("persistra.viz")
    except ImportError as error:
        raise InspectionError(
            "the inspector requires optional dependencies: install persistra[inspect]"
        ) from error


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
                f"port {port} is already in use on 127.0.0.1; choose another port or omit --port"
            ) from error
        raise InspectionError(f"could not start the inspector server: {error}") from error
    except Exception:
        if server is not None:
            server.stop(wait=False)
        raise
