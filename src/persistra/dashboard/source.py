"""Verified dashboard sources and short-lived read scopes."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from persistra import Project, ProjectMode
from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.dashboard.configuration import (
    BackupDashboardSource,
    DashboardSource,
    PortableExportSource,
    ProjectDashboardSource,
)
from persistra.db import DatabaseRole
from persistra.db.connection import ManagedConnection, inspect_database
from persistra.db.copies import verify_published_copy
from persistra.errors import (
    CopyVerificationError,
    DashboardCompatibilityError,
    DashboardSecurityError,
    DashboardSourceError,
)
from persistra.results import PortableRunHandle, open_export

if TYPE_CHECKING:
    from collections.abc import Generator

    from persistra.domain import ContentId


def source_fingerprint(
    source: DashboardSource,
    *,
    max_rows_per_table: int = 2_000_000,
) -> ContentId:
    """Verify a source and return its immutable cache authority."""
    if isinstance(source, PortableExportSource):
        run = open_export(source.path, max_rows_per_table=max_rows_per_table)
        if (
            source.export_manifest_content_id is not None
            and run.manifest_content_id != source.export_manifest_content_id
        ):
            raise DashboardCompatibilityError("portable export expected root does not match")
        _verify_checksum(source.path, source.expected_file_checksum)
        return scoped_content_id(
            {
                "schema": "persistra.dashboard.portable_source@1",
                "run": run.provenance(),
                "checksum": _path_checksum(source.path),
            }
        )
    with project_scope(source) as project:
        inspection = project.inspect()
        if (
            isinstance(source, ProjectDashboardSource)
            and source.expected_project_id is not None
            and inspection.project_id != source.expected_project_id
        ):
            raise DashboardCompatibilityError("project identity does not match")
        research = next(
            (item for item in inspection.databases if item.role is DatabaseRole.RESEARCH),
            None,
        )
        if research is None:
            raise DashboardSourceError("dashboard source has no research database")
        if (
            isinstance(source, ProjectDashboardSource)
            and source.expected_research_database_id is not None
            and research.database_id != source.expected_research_database_id
        ):
            raise DashboardCompatibilityError("research database identity does not match")
        return scoped_content_id(
            {
                "schema": "persistra.dashboard.project_source@1",
                "project": inspection.project_id,
                "database": research.database_id,
                "schema_version": research.schema_version,
                "path_authority": research.path_sha256,
            }
        )


@contextmanager
def project_scope(
    source: ProjectDashboardSource | BackupDashboardSource,
) -> Generator[Project, None, None]:
    """Open one thread-owned read-only scope and close it deterministically."""
    if isinstance(source, ProjectDashboardSource):
        try:
            project = Project.open(source.project_path, mode=ProjectMode.READ_ONLY)
        except Exception as error:
            raise DashboardSourceError("read-only project source could not be opened") from error
        try:
            yield project
        finally:
            project.close()
        return
    if source.path.is_symlink():
        raise DashboardSecurityError("dashboard backup source must not be a symlink")
    _verify_checksum(source.path, source.expected_file_checksum)
    try:
        verification = verify_published_copy(
            source.path,
            expected_role=DatabaseRole.RESEARCH,
        )
    except CopyVerificationError as error:
        raise DashboardSecurityError(
            "dashboard backup is not a verified published copy"
        ) from error
    if verification.kind != "backup":
        raise DashboardCompatibilityError(
            "dashboard backup source must have backup copy kind"
        )
    connection = ManagedConnection(source.path.resolve(), read_only=True)
    try:
        metadata = inspect_database(connection, expected_role=DatabaseRole.RESEARCH)
    finally:
        connection.close()
    if metadata.owner_project_id is None:
        raise DashboardCompatibilityError("backup has no owning project identity")
    with TemporaryDirectory(prefix="persistra-dashboard-") as temporary:
        root = Path(temporary)
        config = root / "persistra.toml"
        config.write_text(
            f'[project]\nid = "{metadata.owner_project_id}"\nname = "dashboard-backup"\n'
            f'\n[databases.research]\npath = "{source.path.resolve()}"\ndisposable = false\n'
            '\n[paths]\nartifacts = "artifacts"\nlogs = "logs"\ntemporary = "tmp"\n',
            encoding="utf-8",
        )
        try:
            project = Project.open(config, mode=ProjectMode.READ_ONLY)
        except Exception as error:
            raise DashboardSourceError("read-only backup source could not be opened") from error
        try:
            yield project
        finally:
            project.close()


def portable_run(
    source: PortableExportSource,
    *,
    max_rows_per_table: int = 2_000_000,
) -> PortableRunHandle:
    _verify_checksum(source.path, source.expected_file_checksum)
    return open_export(source.path, max_rows_per_table=max_rows_per_table)


def _verify_checksum(path: Path, expected: str | None) -> None:
    if expected is not None and _path_checksum(path) != expected:
        raise DashboardSecurityError("dashboard source checksum does not match")


def _path_checksum(path: Path) -> str:
    if path.is_symlink():
        raise DashboardSecurityError("dashboard source must not be a symlink")
    resolved = path.resolve()
    if resolved.is_file():
        return _file_checksum(resolved)
    digest = hashlib.sha256()
    for member in sorted(resolved.iterdir()):
        if member.is_symlink() or not member.is_file():
            raise DashboardSecurityError("dashboard source closure contains an unsafe entry")
        digest.update(member.name.encode("utf-8"))
        digest.update(bytes.fromhex(_file_checksum(member)))
    return digest.hexdigest()


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
