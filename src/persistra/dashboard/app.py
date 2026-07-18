"""Lazy Streamlit application shell."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, cast

from persistra.dashboard.configuration import (
    BackupDashboardSource,
    DashboardLimits,
    PortableExportSource,
    ProjectDashboardSource,
)
from persistra.dashboard.data import DashboardData
from persistra.dashboard.pages import PAGE_KEYS, DashboardPage
from persistra.db import DatabaseId, ProjectId
from persistra.domain import ContentId, QualifiedName
from persistra.viz import FigureLimits, ThemeRef


def run_app(request_path: Path) -> None:
    """Render the eight-page read-only dashboard."""
    try:
        pio = cast("Any", importlib.import_module("plotly.io"))
        st = cast("Any", importlib.import_module("streamlit"))
    except ImportError as error:  # pragma: no cover - isolated optional install check
        from persistra.errors import DashboardExtraRequiredError

        raise DashboardExtraRequiredError(
            "dashboard requires `pip install persistra[dashboard]`"
        ) from error
    request = json.loads(request_path.read_text(encoding="utf-8"))
    source = _source(request)
    limit_values = dict(request.get("limits", {}))
    figure_values = dict(limit_values.pop("figure", {}))
    limits = DashboardLimits(
        **limit_values,
        figure=FigureLimits(**figure_values),
    )
    theme = ThemeRef(
        QualifiedName(request.get("theme_name", "persistra.default_light")),
        int(request.get("theme_version", 1)),
    )
    data_key = "persistra.dashboard.shell.data@1"
    if data_key not in st.session_state:
        st.session_state[data_key] = DashboardData(
            source,
            limits=limits,
            theme=theme,
            display_timezone=str(request.get("display_timezone", "UTC")),
        )
    data = cast("DashboardData", st.session_state[data_key])
    st.set_page_config(
        page_title="Persistra dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("Persistra read-only dashboard")
    st.caption("Immutable result and analysis views · UTC · no writes")
    runs = data.runs()
    if runs.empty:
        st.info("No completed runs are available.")
        return
    choices = [str(value) for value in runs["run_record_id"]]
    selected = str(
        st.sidebar.selectbox(
            "Run",
            choices,
            key="persistra.dashboard.shell.run@1",
        )
    )
    page = cast(
        "DashboardPage",
        st.sidebar.radio(
            "Page",
            list(DashboardPage),
            format_func=_page_label,
            key="persistra.dashboard.shell.page@1",
        ),
    )
    result = data.query(str(selected), PAGE_KEYS[page])
    st.header(page.value)
    st.caption(f"Result root: {result.source_root}")
    for warning in result.warnings:
        st.warning(warning)
    for message in result.unavailable:
        st.info(message)
    for item in result.figures:
        st.plotly_chart(
            pio.from_json(item.figure_json),
            width="stretch",
            key=f"persistra.dashboard.{result.page}.figure.{item.name}@1",
        )
    for item in result.tables:
        st.subheader(item.name)
        st.dataframe(
            item.frame.head(limits.max_table_display_rows),
            width="stretch",
            hide_index=True,
        )


def _source(value: dict[str, Any]) -> Any:
    kind = value["source_kind"]
    path = Path(value["source_path"])
    if kind == "project":
        expected_project = value.get("expected_project_id")
        expected_database = value.get("expected_research_database_id")
        return ProjectDashboardSource(
            path,
            None if expected_project is None else ProjectId.parse(expected_project),
            None if expected_database is None else DatabaseId.parse(expected_database),
        )
    if kind == "backup":
        return BackupDashboardSource(path, value.get("expected_file_checksum"))
    expected_manifest = value.get("export_manifest_content_id")
    return PortableExportSource(
        path,
        None if expected_manifest is None else ContentId.parse(expected_manifest),
        expected_file_checksum=value.get("expected_file_checksum"),
    )


def _page_label(value: DashboardPage) -> str:
    return value.value


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--request-token", type=Path, required=True)
    arguments = parser.parse_args()
    run_app(arguments.request_token)


if __name__ == "__main__":
    main()
