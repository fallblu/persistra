"""Sole managed DuckDB connection boundary and bootstrap verification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import duckdb

from persistra import __version__
from persistra.db.models import DatabaseId, DatabaseRole, ProjectId
from persistra.domain import Clock, ContentId, EventId, QualifiedName
from persistra.domain.serialization import canonical_bytes
from persistra.errors import (
    DatabaseCompatibilityError,
    DatabaseRoleError,
    UnmanagedDatabaseError,
)

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

BOOTSTRAP_CHECKSUM = str(ContentId.from_bytes(b"persistra.database.bootstrap@1"))
ROLE_SCHEMAS: dict[DatabaseRole, tuple[str, ...]] = {
    DatabaseRole.MARKET: ("catalog", "canonical", "quality", "snapshots"),
    DatabaseRole.RESEARCH: (
        "workspace",
        "research",
        "experiments",
        "results",
        "analysis",
        "annotations",
    ),
}


@dataclass(frozen=True, slots=True)
class DatabaseMetadata:
    database_id: DatabaseId
    role: DatabaseRole
    owner_project_id: ProjectId | None
    created_at: datetime
    schema_version: int
    disposable: bool


class ManagedConnection:
    """Internal-only owner of a configured DuckDB connection."""

    __slots__ = ("_connection", "path")

    def __init__(self, path: Path, *, read_only: bool) -> None:
        self.path = path
        config: dict[str, str | bool | int | float | list[str]] = {
            "allow_unsigned_extensions": "false",
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
        }
        self._connection = duckdb.connect(str(path), read_only=read_only, config=config)
        self._connection.execute("SET TimeZone = 'UTC'")

    def execute(self, sql: str, parameters: list[Any] | None = None) -> Any:
        """Execute internal static SQL; never exposed from a public object."""
        return self._connection.execute(sql, parameters or [])

    def begin(self) -> None:
        self._connection.begin()

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def attach_market(self, name: str, path: Path) -> None:
        alias = f"market_{name}"
        escaped_path = str(path).replace("'", "''")
        self._connection.execute(f"ATTACH '{escaped_path}' AS \"{alias}\" (READ_ONLY)")


def bootstrap_database(
    connection: ManagedConnection,
    *,
    database_id: DatabaseId,
    role: DatabaseRole,
    owner_project_id: ProjectId | None,
    created_at: datetime,
    disposable: bool,
) -> None:
    """Apply immutable migration 1 to a new empty database in one transaction."""
    connection.begin()
    try:
        connection.execute("CREATE SCHEMA _persistra")
        for schema in ROLE_SCHEMAS[role]:
            connection.execute(f'CREATE SCHEMA "{schema}"')
        connection.execute(
            """
            CREATE TABLE _persistra.database_info (
                singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
                database_id UUID NOT NULL,
                role VARCHAR NOT NULL CHECK (role IN ('market', 'research')),
                owner_project_id UUID,
                created_at TIMESTAMPTZ NOT NULL,
                created_by_version VARCHAR NOT NULL,
                schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
                disposable BOOLEAN NOT NULL DEFAULT false
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE _persistra.schema_migrations (
                migration_number INTEGER PRIMARY KEY CHECK (migration_number >= 1),
                migration_name VARCHAR NOT NULL UNIQUE,
                migration_checksum VARCHAR NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL,
                applied_by_version VARCHAR NOT NULL,
                backup_copy_id UUID,
                duration_us BIGINT NOT NULL CHECK (duration_us >= 0)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE _persistra.database_lineage (
                lineage_id UUID PRIMARY KEY,
                parent_database_id UUID NOT NULL,
                source_copy_id UUID NOT NULL,
                relation VARCHAR NOT NULL CHECK (relation IN ('restore', 'fork')),
                recorded_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE _persistra.domain_events (
                event_id UUID PRIMARY KEY,
                event_name VARCHAR NOT NULL,
                event_schema_version INTEGER NOT NULL CHECK (event_schema_version >= 1),
                event_at TIMESTAMPTZ NOT NULL,
                available_at TIMESTAMPTZ NOT NULL,
                recorded_at TIMESTAMPTZ NOT NULL,
                aggregate_kind VARCHAR NOT NULL,
                aggregate_id UUID NOT NULL,
                aggregate_sequence BIGINT NOT NULL CHECK (aggregate_sequence >= 1),
                correlation_id UUID,
                causation_id UUID,
                payload_content_id VARCHAR NOT NULL,
                payload_json_utf8 BLOB NOT NULL,
                UNIQUE (aggregate_kind, aggregate_id, aggregate_sequence)
            )
            """
        )
        connection.execute(
            "INSERT INTO _persistra.database_info VALUES (true, ?, ?, ?, ?, ?, 1, ?)",
            [
                database_id.value,
                role.value,
                None if owner_project_id is None else owner_project_id.value,
                created_at,
                __version__,
                disposable,
            ],
        )
        connection.execute(
            "INSERT INTO _persistra.schema_migrations VALUES (1, ?, ?, ?, ?, NULL, 0)",
            ["bootstrap", BOOTSTRAP_CHECKSUM, created_at, __version__],
        )
        payload = canonical_bytes(
            {
                "database_id": str(database_id),
                "disposable": disposable,
                "owner_project_id": (
                    None if owner_project_id is None else str(owner_project_id)
                ),
                "role": role.value,
                "schema_version": 1,
            }
        )
        connection.execute(
            "INSERT INTO _persistra.domain_events VALUES (?, ?, 1, ?, ?, ?, ?, ?, 1, "
            "NULL, NULL, ?, ?)",
            [
                EventId.new().value,
                "persistra.database.created",
                created_at,
                created_at,
                created_at,
                str(QualifiedName("persistra.aggregate.database")),
                database_id.value,
                str(ContentId.from_bytes(payload)),
                payload,
            ],
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def inspect_database(
    connection: ManagedConnection,
    *,
    expected_role: DatabaseRole | None = None,
    expected_project_id: ProjectId | None = None,
) -> DatabaseMetadata:
    """Validate bootstrap singleton, role ownership, and migration chain."""
    try:
        rows = connection.execute(
            "SELECT database_id, role, owner_project_id, created_at, schema_version, disposable "
            "FROM _persistra.database_info"
        ).fetchall()
    except duckdb.Error as error:
        raise UnmanagedDatabaseError(
            "database has no valid Persistra bootstrap metadata"
        ) from error
    if len(rows) != 1:
        raise UnmanagedDatabaseError("database_info must contain exactly one row")
    row = rows[0]
    database_id = DatabaseId.parse(row[0])
    role = DatabaseRole(row[1])
    owner = None if row[2] is None else ProjectId.parse(row[2])
    schema_version = int(row[4])
    migrations = connection.execute(
        "SELECT migration_number, migration_checksum FROM _persistra.schema_migrations "
        "ORDER BY migration_number"
    ).fetchall()
    numbers = [int(item[0]) for item in migrations]
    if numbers != list(range(1, schema_version + 1)):
        raise DatabaseCompatibilityError("database migration history is not gap-free")
    if not migrations or migrations[0][1] != BOOTSTRAP_CHECKSUM:
        raise DatabaseCompatibilityError("database bootstrap checksum does not match")
    if schema_version != 1:
        raise DatabaseCompatibilityError("database schema is newer than this implementation")
    if expected_role is not None and role is not expected_role:
        raise DatabaseRoleError("database role does not match the selected capability")
    if (
        role is DatabaseRole.RESEARCH
        and expected_project_id is not None
        and owner != expected_project_id
    ):
        raise DatabaseRoleError("research database belongs to a different project")
    if role is DatabaseRole.MARKET and owner is not None:
        raise DatabaseRoleError("market database cannot have a project owner")
    return DatabaseMetadata(database_id, role, owner, row[3], schema_version, bool(row[5]))


def create_database_file(
    path: Path,
    *,
    role: DatabaseRole,
    project_id: ProjectId | None,
    disposable: bool,
    clock: Clock,
) -> DatabaseMetadata:
    """Build, verify, fsync, and atomically publish one managed database."""
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    database_id = DatabaseId.new()
    temporary = path.with_name(f".{path.name}.partial-{database_id.value}")
    connection = ManagedConnection(temporary, read_only=False)
    try:
        bootstrap_database(
            connection,
            database_id=database_id,
            role=role,
            owner_project_id=project_id if role is DatabaseRole.RESEARCH else None,
            created_at=clock.now(),
            disposable=disposable,
        )
    finally:
        connection.close()
    descriptor = os.open(temporary, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    verify = ManagedConnection(temporary, read_only=True)
    try:
        metadata = inspect_database(
            verify,
            expected_role=role,
            expected_project_id=project_id if role is DatabaseRole.RESEARCH else None,
        )
    finally:
        verify.close()
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return metadata
