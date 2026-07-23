"""This module contains the validated lightweight dashboard launch configuration."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from persistra.errors import DashboardSecurityError, DashboardSourceError
from persistra.viz import FigureLimits, ThemeRef

if TYPE_CHECKING:
    from pathlib import Path

    from persistra.db import DatabaseId, ProjectId
    from persistra.domain import ContentId


@dataclass(frozen=True, slots=True)
class ProjectDashboardSource:
    project_path: Path
    expected_project_id: ProjectId | None = None
    expected_research_database_id: DatabaseId | None = None

    def __post_init__(self) -> None:
        _validate_source_path(self.project_path, directory=True)


@dataclass(frozen=True, slots=True)
class BackupDashboardSource:
    path: Path
    expected_file_checksum: str | None = None

    def __post_init__(self) -> None:
        _validate_source_path(self.path, directory=False)


@dataclass(frozen=True, slots=True)
class PortableExportSource:
    path: Path
    export_manifest_content_id: ContentId | None = None
    expected_file_checksum: str | None = None

    def __post_init__(self) -> None:
        _validate_source_path(self.path, directory=None)


DashboardSource = ProjectDashboardSource | BackupDashboardSource | PortableExportSource


@dataclass(frozen=True, slots=True)
class DashboardLimits:
    max_runs: int = 10_000
    max_query_rows: int = 200_000
    max_table_display_rows: int = 2_000
    max_cache_entries: int = 64
    max_cache_bytes: int = 256 * 2**20
    figure: FigureLimits = field(
        default_factory=lambda: FigureLimits(
            max_input_rows=200_000,
            max_points_per_trace=25_000,
        )
    )

    def __post_init__(self) -> None:
        if min(
            self.max_runs,
            self.max_query_rows,
            self.max_table_display_rows,
            self.max_cache_entries,
            self.max_cache_bytes,
        ) < 1:
            raise DashboardSourceError("dashboard limits must be positive")
        if self.max_table_display_rows > self.max_query_rows:
            raise DashboardSourceError("table display rows cannot exceed query rows")


@dataclass(frozen=True, slots=True)
class DashboardRequest:
    source: DashboardSource
    bind_address: str = "127.0.0.1"
    port: int = 8501
    open_browser: bool = False
    theme: ThemeRef = field(default_factory=ThemeRef)
    display_timezone: str = "UTC"
    limits: DashboardLimits = field(default_factory=DashboardLimits)
    unsupported_network_override: bool = False

    def __post_init__(self) -> None:
        try:
            address = ipaddress.ip_address(self.bind_address)
        except ValueError as error:
            raise DashboardSecurityError("dashboard bind address must be an IP literal") from error
        if not address.is_loopback and not self.unsupported_network_override:
            raise DashboardSecurityError(
                "dashboard binds only to loopback without an unsupported-development override"
            )
        if not 1024 <= self.port <= 65535:
            raise DashboardSecurityError("dashboard port must be unprivileged and valid")
        if self.display_timezone != "UTC":
            raise DashboardSourceError("v3 dashboard supports UTC display only")


def _validate_source_path(path: Path, *, directory: bool | None) -> None:
    if path.is_symlink():
        raise DashboardSecurityError("dashboard source cannot be a symbolic link")
    resolved = path.resolve()
    if not resolved.exists():
        raise DashboardSourceError(f"dashboard source does not exist: {resolved}")
    if directory is True and not resolved.is_dir():
        raise DashboardSourceError("project dashboard source must be a directory")
    if directory is False and not resolved.is_file():
        raise DashboardSourceError("backup dashboard source must be a file")
