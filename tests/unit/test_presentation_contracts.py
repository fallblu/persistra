from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from persistra import Project
from persistra.cli import parser
from persistra.dashboard import ProjectDashboardSource
from persistra.dashboard import launcher as dashboard_launcher
from persistra.dashboard.cache import DashboardCacheKey, DashboardDataCache
from persistra.dashboard.configuration import DashboardLimits, DashboardRequest
from persistra.dashboard.pages import PAGE_KEYS, DashboardPage
from persistra.domain import ContentId
from persistra.errors import DashboardSecurityError, FigureInputError, FigureResourceLimitError
from persistra.viz._core import reduce_xy
from persistra.viz.models import FigureConfig, FigureLimits, VisualReductionPolicy

if TYPE_CHECKING:
    from pathlib import Path


def test_visual_reduction_is_explicit_deterministic_and_extrema_preserving() -> None:
    x = list(range(12))
    y: list[float | None] = [4, 3, 2, -10, 1, 2, 3, 20, 2, 1, 0, 5]
    config = FigureConfig(
        reduction=VisualReductionPolicy.min_max_envelope(3),
        limits=FigureLimits(max_points_per_trace=12),
    )
    reduced_x, reduced_y, evidence = reduce_xy(x, y, config)
    assert reduced_x == sorted(set(reduced_x))
    assert {-10, 20} <= set(reduced_y)
    assert reduced_x[0] == 0
    assert reduced_x[-1] == 11
    assert evidence["policy"] == "min_max_envelope"

    strict = FigureConfig(limits=FigureLimits(max_points_per_trace=3))
    with pytest.raises(FigureResourceLimitError):
        reduce_xy(x, y, strict)
    with pytest.raises(FigureInputError):
        VisualReductionPolicy.every_nth(0)


def test_dashboard_cache_keys_cover_roots_and_cache_detaches_values() -> None:
    source = ContentId.from_bytes(b"source")
    subject = ContentId.from_bytes(b"subject")
    key = DashboardCacheKey.build(
        source_fingerprint=source,
        subject_root=subject,
        page="performance",
        parameters={"limit": 10},
    )
    changed = DashboardCacheKey.build(
        source_fingerprint=source,
        subject_root=ContentId.from_bytes(b"changed"),
        page="performance",
        parameters={"limit": 10},
    )
    assert key != changed
    cache = DashboardDataCache(max_entries=1, max_bytes=1000)
    value = {"rows": [1]}
    cache.put(key, value, byte_count=10)
    value["rows"].append(2)
    assert cache.get(key) == {"rows": [1]}
    cache.put(changed, {"rows": [3]}, byte_count=10)
    assert cache.get(key) is None
    cache.clear()


def test_dashboard_source_security_and_eight_page_contract(tmp_path: Path) -> None:
    request = DashboardRequest(ProjectDashboardSource(tmp_path))
    assert request.bind_address == "127.0.0.1"
    with pytest.raises(DashboardSecurityError):
        DashboardRequest(
            ProjectDashboardSource(tmp_path),
            bind_address="0.0.0.0",
        )
    assert len(DashboardPage) == 8
    assert set(PAGE_KEYS.values()) == {
        "overview",
        "performance",
        "portfolio",
        "execution",
        "attribution",
        "diagnostics",
        "studies",
        "inspection",
    }
    limits = DashboardLimits(max_query_rows=10, max_table_display_rows=10)
    assert limits.figure.max_input_rows == 200_000
    arguments = parser().parse_args(["dashboard", "--project", str(tmp_path)])
    assert arguments.command == "dashboard"


def test_dashboard_namespace_import_does_not_import_streamlit() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import persistra.dashboard; "
            "assert 'streamlit' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_dashboard_interrupt_exits_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def available_spec(_name: str) -> object:
        return object()

    def fingerprint(_source: object, *, max_rows_per_table: int) -> ContentId:
        return ContentId.from_bytes(str(max_rows_per_table).encode())

    def available_port(_address: str, _port: int) -> None:
        return None

    monkeypatch.setattr(
        dashboard_launcher.importlib.util,
        "find_spec",
        available_spec,
    )
    monkeypatch.setattr(
        dashboard_launcher,
        "source_fingerprint",
        fingerprint,
    )
    monkeypatch.setattr(
        dashboard_launcher,
        "_verify_available_port",
        available_port,
    )

    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(dashboard_launcher.subprocess, "run", interrupt)
    assert (
        dashboard_launcher.launch(
            DashboardRequest(ProjectDashboardSource(tmp_path))
        )
        == 130
    )


@pytest.mark.browser
@pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None,
    reason="dashboard extra is not installed",
)
def test_streamlit_loopback_shell_smoke(tmp_path: Path) -> None:
    from streamlit.testing.v1 import AppTest

    root = Project.init(tmp_path / "dashboard-project").root
    token = tmp_path / "request.json"
    token.write_text(
        json.dumps(
            {
                "source_kind": "project",
                "source_path": str(root),
                "limits": {},
            }
        ),
        encoding="utf-8",
    )
    app = AppTest.from_string(
        "from pathlib import Path\n"
        "from persistra.dashboard.app import run_app\n"
        f"run_app(Path({str(token)!r}))\n"
    ).run(timeout=10)
    assert not app.exception
    assert app.title[0].value == "Persistra read-only dashboard"
    assert app.info[0].value == "No completed runs are available."
