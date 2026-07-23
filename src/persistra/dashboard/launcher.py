"""This module contains the hardened loopback Streamlit process launcher."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.dashboard.configuration import (
    BackupDashboardSource,
    DashboardRequest,
    PortableExportSource,
    ProjectDashboardSource,
)
from persistra.dashboard.source import source_fingerprint
from persistra.errors import DashboardSecurityError


def launch(request: DashboardRequest) -> int:
    """Validate the source and synchronously launch a no-telemetry loopback app."""
    source_fingerprint(
        request.source,
        max_rows_per_table=request.limits.max_query_rows,
    )
    _verify_available_port(request.bind_address, request.port)
    with TemporaryDirectory(prefix="persistra-dashboard-launch-") as temporary:
        token = Path(temporary) / "request.json"
        token.write_text(
            json.dumps(_wire_request(request), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(token, 0o600)
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).with_name("app.py")),
            "--server.address",
            request.bind_address,
            "--server.port",
            str(request.port),
            "--server.headless",
            "false" if request.open_browser else "true",
            "--server.enableCORS",
            "true",
            "--server.enableXsrfProtection",
            "true",
            "--server.enableStaticServing",
            "false",
            "--server.fileWatcherType",
            "none",
            "--browser.gatherUsageStats",
            "false",
            "--",
            "--request-token",
            str(token),
        ]
        try:
            completed = subprocess.run(command, check=False)
        except KeyboardInterrupt:
            return 130
        return completed.returncode


def _verify_available_port(address: str, port: int) -> None:
    with socket.socket(socket.AF_INET6 if ":" in address else socket.AF_INET) as listener:
        try:
            listener.bind((address, port))
        except OSError as error:
            raise DashboardSecurityError("dashboard port is already in use") from error


def _wire_request(request: DashboardRequest) -> dict[str, object]:
    source = request.source
    if isinstance(source, ProjectDashboardSource):
        kind = "project"
        path = source.project_path
        checksum = None
        source_identity = {
            "expected_project_id": (
                None
                if source.expected_project_id is None
                else str(source.expected_project_id)
            ),
            "expected_research_database_id": (
                None
                if source.expected_research_database_id is None
                else str(source.expected_research_database_id)
            ),
        }
    elif isinstance(source, BackupDashboardSource):
        kind = "backup"
        path = source.path
        checksum = source.expected_file_checksum
        source_identity = {}
    else:
        kind = "portable"
        assert isinstance(source, PortableExportSource)
        path = source.path
        checksum = source.expected_file_checksum
        source_identity = {
            "export_manifest_content_id": (
                None
                if source.export_manifest_content_id is None
                else str(source.export_manifest_content_id)
            )
        }
    return {
        "source_kind": kind,
        "source_path": str(path.resolve()),
        "expected_file_checksum": checksum,
        **source_identity,
        "theme_name": str(request.theme.name),
        "theme_version": request.theme.version,
        "display_timezone": request.display_timezone,
        "limits": {
            "max_runs": request.limits.max_runs,
            "max_query_rows": request.limits.max_query_rows,
            "max_table_display_rows": request.limits.max_table_display_rows,
            "max_cache_entries": request.limits.max_cache_entries,
            "max_cache_bytes": request.limits.max_cache_bytes,
            "figure": {
                "max_input_rows": request.limits.figure.max_input_rows,
                "max_points_per_trace": request.limits.figure.max_points_per_trace,
                "max_traces": request.limits.figure.max_traces,
                "max_figure_json_bytes": (
                    request.limits.figure.max_figure_json_bytes
                ),
            },
        },
    }
