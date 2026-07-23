"""This module contains the sole managed DuckDB connection boundary and bootstrap verification."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import duckdb

from persistra import __version__
from persistra.db.filesystems import inspect_filesystem
from persistra.db.migrations import CURRENT_SCHEMA_VERSION, MIGRATIONS, migration_statements
from persistra.db.models import DatabaseId, DatabaseRole, ProjectId
from persistra.domain import Clock, ContentId, EventId, QualifiedName
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    DatabaseAlreadyExistsError,
    DatabaseCompatibilityError,
    DatabaseRoleError,
    MigrationChecksumError,
    MigrationRequiredError,
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
    """This class represents the internal-only owner of a configured DuckDB connection."""

    __slots__ = ("_connection", "_database_name", "path")

    def __init__(
        self,
        path: Path,
        *,
        read_only: bool,
        threads: int | None = None,
        memory_limit: int | None = None,
        temporary_directory: Path | None = None,
        temporary_limit: int | None = None,
    ) -> None:
        self.path = path
        config: dict[str, str | bool | int | float | list[str]] = {
            "allow_unsigned_extensions": "false",
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
        }
        self._connection = duckdb.connect(str(path), read_only=read_only, config=config)
        database_row = self._connection.execute("SELECT current_database()").fetchone()
        if database_row is None:
            raise UnmanagedDatabaseError("database name is unavailable")
        self._database_name = str(database_row[0])
        self._connection.execute("SET TimeZone = 'UTC'")
        if threads is not None:
            self._connection.execute(f"SET threads = {threads}")
        if memory_limit is not None:
            self._connection.execute(f"SET memory_limit = '{memory_limit}B'")
        if temporary_directory is not None:
            escaped_temporary = str(temporary_directory).replace("'", "''")
            self._connection.execute(f"SET temp_directory = '{escaped_temporary}'")
        if temporary_limit is not None:
            self._connection.execute(
                f"SET max_temp_directory_size = '{temporary_limit}B'"
            )

    def execute(self, sql: str, parameters: list[Any] | None = None) -> Any:
        """Execute internal static SQL. Do not expose this method from a public object."""
        sql = self._qualify_research_sql(sql)
        return self._connection.execute(sql, parameters or [])

    def executemany(self, sql: str, parameters: list[tuple[Any, ...]]) -> Any:
        """Execute one internal static statement against a bounded row sequence."""
        return self._connection.executemany(self._qualify_research_sql(sql), parameters)

    def _qualify_research_sql(self, sql: str) -> str:
        database = self._database_name.replace('"', '""')
        return re.sub(
            r"(?<![A-Za-z0-9_.\"])(research_data|research)\.",
            rf'"{database}"."\1".',
            sql,
        )

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

    def disable_external_access(self) -> None:
        """Close the controlled attachment window for the connection lifetime."""
        self._connection.execute("SET enable_external_access = false")


def _bootstrap_market_catalog(connection: ManagedConnection) -> None:
    statements = (
        """CREATE TABLE catalog.catalog_clock (
            singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
            current_sequence BIGINT NOT NULL CHECK (current_sequence >= 0),
            chain_content_id VARCHAR NOT NULL)""",
        """CREATE TABLE catalog.changes (
            catalog_sequence BIGINT PRIMARY KEY CHECK (catalog_sequence >= 1),
            change_kind VARCHAR NOT NULL, change_entity_id UUID NOT NULL,
            change_content_id VARCHAR NOT NULL, prior_chain_content_id VARCHAR NOT NULL,
            chain_content_id VARCHAR NOT NULL UNIQUE, committed_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE catalog.sources (
            source_id UUID PRIMARY KEY, qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE catalog.source_versions (
            source_id UUID, source_version INTEGER CHECK (source_version >= 1),
            definition_schema_version INTEGER NOT NULL, definition_content_id VARCHAR NOT NULL,
            definition_json JSON NOT NULL, enabled BOOLEAN NOT NULL,
            catalog_sequence BIGINT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (source_id, source_version))""",
        """CREATE TABLE catalog.datasets (
            dataset_id UUID PRIMARY KEY, qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE catalog.dataset_versions (
            dataset_id UUID, dataset_version INTEGER CHECK (dataset_version >= 1),
            definition_schema_version INTEGER NOT NULL, definition_content_id VARCHAR NOT NULL,
            definition_json JSON NOT NULL, catalog_sequence BIGINT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (dataset_id, dataset_version))""",
        """CREATE TABLE catalog.batches (
            batch_id UUID PRIMARY KEY, source_id UUID NOT NULL, source_version INTEGER NOT NULL,
            dataset_id UUID NOT NULL, dataset_version INTEGER NOT NULL,
            submission_key VARCHAR NOT NULL, adapter_name VARCHAR NOT NULL,
            adapter_version VARCHAR NOT NULL, current_status VARCHAR NOT NULL,
            created_at TIMESTAMPTZ NOT NULL, staged_at TIMESTAMPTZ,
            validated_at TIMESTAMPTZ, terminal_at TIMESTAMPTZ,
            batch_content_id VARCHAR, validation_token_content_id VARCHAR,
            validation_input_catalog_sequence BIGINT,
            validation_attempt_id UUID, catalog_sequence BIGINT,
            submitted_count BIGINT NOT NULL DEFAULT 0,
            UNIQUE (source_id, dataset_id, submission_key))""",
        """CREATE TABLE catalog.batch_transitions (
            batch_id UUID, transition_sequence INTEGER CHECK (transition_sequence >= 1),
            from_status VARCHAR, to_status VARCHAR NOT NULL, reason_code VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (batch_id, transition_sequence))""",
        """CREATE TABLE catalog.batch_records (
            submitted_record_id UUID PRIMARY KEY, batch_id UUID NOT NULL,
            record_number BIGINT NOT NULL CHECK (record_number >= 1),
            source_record_key VARCHAR, source_revision_key VARCHAR,
            revision_effect VARCHAR NOT NULL CHECK (revision_effect IN ('upsert','retract')),
            retraction_target_revision_id UUID, retraction_reason_code VARCHAR,
            retraction_evidence_content_id VARCHAR,
            natural_key_content_id VARCHAR NOT NULL, natural_key_json JSON NOT NULL,
            payload_content_id VARCHAR NOT NULL, source_content_id VARCHAR NOT NULL,
            canonical_payload_json JSON NOT NULL, event_at TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL, ingested_at TIMESTAMPTZ NOT NULL,
            UNIQUE (batch_id, record_number))""",
        """CREATE TABLE catalog.validation_attempts (
            validation_attempt_id UUID PRIMARY KEY, batch_id UUID NOT NULL,
            attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
            input_catalog_sequence BIGINT NOT NULL,
            validation_token_content_id VARCHAR NOT NULL, current_status VARCHAR NOT NULL,
            started_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ NOT NULL,
            UNIQUE (batch_id, attempt_number))""",
        """CREATE TABLE catalog.validation_attempt_transitions (
            validation_attempt_id UUID, transition_sequence INTEGER NOT NULL,
            from_status VARCHAR, to_status VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (validation_attempt_id, transition_sequence))""",
        """CREATE TABLE catalog.pending_remediations (
            child_batch_id UUID PRIMARY KEY, parent_batch_id UUID NOT NULL,
            parent_submitted_record_id UUID NOT NULL, relationship VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE catalog.record_dispositions (
            submitted_record_id UUID PRIMARY KEY, batch_id UUID NOT NULL,
            disposition VARCHAR NOT NULL, primary_reason_code VARCHAR NOT NULL,
            canonical_revision_id UUID, recorded_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE catalog.canonical_revisions (
            canonical_revision_id UUID PRIMARY KEY, dataset_id UUID NOT NULL,
            dataset_version INTEGER NOT NULL, source_id UUID NOT NULL,
            natural_key_content_id VARCHAR NOT NULL, natural_key_json JSON NOT NULL,
            revision_ordinal BIGINT NOT NULL CHECK (revision_ordinal >= 1),
            supersedes_revision_id UUID, source_record_key VARCHAR,
            source_revision_key VARCHAR, revision_effect VARCHAR NOT NULL,
            payload_content_id VARCHAR NOT NULL, source_content_id VARCHAR NOT NULL UNIQUE,
            canonical_payload_json JSON NOT NULL, batch_id UUID NOT NULL,
            submitted_record_id UUID NOT NULL UNIQUE, event_at TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL, ingested_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            UNIQUE (dataset_id, source_id, natural_key_content_id, revision_ordinal))""",
        """CREATE TABLE catalog.canonical_retractions (
            canonical_revision_id UUID PRIMARY KEY, retracted_revision_id UUID NOT NULL,
            retraction_reason_code VARCHAR NOT NULL, evidence_content_id VARCHAR NOT NULL)""",
        """CREATE TABLE quality.findings (
            finding_id UUID PRIMARY KEY, batch_id UUID NOT NULL,
            validation_attempt_id UUID NOT NULL, submitted_record_id UUID,
            severity VARCHAR NOT NULL, action VARCHAR NOT NULL,
            reason_code VARCHAR NOT NULL, evidence_content_id VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE quality.quarantined_records (
            quarantine_id UUID PRIMARY KEY, submitted_record_id UUID NOT NULL UNIQUE,
            batch_id UUID NOT NULL, reason_code VARCHAR NOT NULL,
            canonical_payload_json JSON NOT NULL, quarantined_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE quality.remediation_links (
            remediation_id UUID PRIMARY KEY, parent_batch_id UUID NOT NULL,
            parent_submitted_record_id UUID NOT NULL, child_batch_id UUID NOT NULL,
            child_submitted_record_id UUID NOT NULL, relationship VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL,
            UNIQUE (parent_submitted_record_id, child_submitted_record_id))""",
        """CREATE TABLE snapshots.market_snapshots (
            market_snapshot_id UUID PRIMARY KEY, database_id UUID NOT NULL,
            catalog_sequence BIGINT NOT NULL, catalog_chain_content_id VARCHAR NOT NULL,
            manifest_schema_version INTEGER NOT NULL, manifest_content_id VARCHAR NOT NULL UNIQUE,
            manifest_json JSON NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (database_id, catalog_sequence))""",
        """CREATE TABLE snapshots.snapshot_dataset_state (
            market_snapshot_id UUID, dataset_id UUID, dataset_version INTEGER,
            revision_count BIGINT NOT NULL, terminal_batch_count BIGINT NOT NULL,
            latest_catalog_sequence BIGINT NOT NULL, state_content_id VARCHAR NOT NULL,
            PRIMARY KEY (market_snapshot_id, dataset_id, dataset_version))""",
        """CREATE TABLE snapshots.snapshot_source_state (
            market_snapshot_id UUID, source_id UUID, source_version INTEGER,
            terminal_batch_count BIGINT NOT NULL, latest_catalog_sequence BIGINT NOT NULL,
            state_content_id VARCHAR NOT NULL,
            PRIMARY KEY (market_snapshot_id, source_id, source_version))""",
    )
    for statement in statements:
        connection.execute(statement)
    empty_chain = str(
        scoped_content_id({"schema": "persistra.catalog.genesis", "version": 1})
    )
    connection.execute("INSERT INTO catalog.catalog_clock VALUES (true, 0, ?)", [empty_chain])


def _bootstrap_research_catalog(connection: ManagedConnection) -> None:
    database_name = str(connection.execute("SELECT current_database()").fetchone()[0])
    escaped_database = database_name.replace('"', '""')
    prefix = f'"{escaped_database}"."research"'
    connection.execute(
        f"""CREATE TABLE {prefix}.composite_snapshots (
            composite_snapshot_id UUID PRIMARY KEY, project_id UUID NOT NULL,
            manifest_schema_version INTEGER NOT NULL,
            manifest_content_id VARCHAR NOT NULL UNIQUE,
            manifest_json JSON NOT NULL, created_at TIMESTAMPTZ NOT NULL)"""
    )
    connection.execute(
        f"""CREATE TABLE {prefix}.composite_snapshot_members (
            composite_snapshot_id UUID, database_name VARCHAR,
            database_id UUID NOT NULL, market_snapshot_id UUID NOT NULL,
            market_manifest_content_id VARCHAR NOT NULL,
            PRIMARY KEY (composite_snapshot_id, database_name),
            UNIQUE (composite_snapshot_id, database_id))"""
    )


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
        if role is DatabaseRole.MARKET:
            _bootstrap_market_catalog(connection)
        else:
            _bootstrap_research_catalog(connection)
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
        for step in MIGRATIONS:
            database_name = str(
                connection.execute("SELECT current_database()").fetchone()[0]
            )
            for statement in migration_statements(
                step, role=role.value, database_name=database_name
            ):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO _persistra.schema_migrations VALUES (?, ?, ?, ?, ?, NULL, 0)",
                [step.number, step.name, step.checksum, created_at, __version__],
            )
            connection.execute(
                "UPDATE _persistra.database_info SET schema_version = ?",
                [step.target_version],
            )
            migration_payload = canonical_bytes(
                {
                    "database_id": str(database_id),
                    "migration_checksum": step.checksum,
                    "migration_number": step.number,
                    "source_version": step.source_version,
                    "target_version": step.target_version,
                }
            )
            connection.execute(
                "INSERT INTO _persistra.domain_events VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, "
                "NULL, NULL, ?, ?)",
                [
                    EventId.new().value,
                    "persistra.database.migrated",
                    created_at,
                    created_at,
                    created_at,
                    str(QualifiedName("persistra.aggregate.database")),
                    database_id.value,
                    step.number,
                    str(ContentId.from_bytes(migration_payload)),
                    migration_payload,
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
    allow_older_schema: bool = False,
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
        "SELECT migration_number, migration_name, migration_checksum "
        "FROM _persistra.schema_migrations "
        "ORDER BY migration_number"
    ).fetchall()
    numbers = [int(item[0]) for item in migrations]
    if numbers != list(range(1, schema_version + 1)):
        raise DatabaseCompatibilityError("database migration history is not gap-free")
    if not migrations or migrations[0][1:] != ("bootstrap", BOOTSTRAP_CHECKSUM):
        raise DatabaseCompatibilityError("database bootstrap checksum does not match")
    registered = {step.number: step for step in MIGRATIONS}
    for number, name, checksum in migrations[1:]:
        step = registered.get(int(number))
        if step is None or step.name != name or step.checksum != checksum:
            raise MigrationChecksumError("database migration checksum does not match")
    if schema_version > CURRENT_SCHEMA_VERSION:
        raise DatabaseCompatibilityError("database schema is newer than this implementation")
    if schema_version < CURRENT_SCHEMA_VERSION and not allow_older_schema:
        raise MigrationRequiredError("database requires an explicit forward migration")
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
    if role is DatabaseRole.RESEARCH and owner is None:
        raise DatabaseRoleError("research database must have a project owner")
    expected_schemas = {"_persistra", *ROLE_SCHEMAS[role]}
    if schema_version == CURRENT_SCHEMA_VERSION and role is DatabaseRole.RESEARCH:
        expected_schemas.add("research_data")
    actual_schemas = {
        str(item[0])
        for item in connection.execute(
            "SELECT schema_name FROM information_schema.schemata"
        ).fetchall()
    }
    if not expected_schemas <= actual_schemas:
        raise DatabaseCompatibilityError("database is missing required managed schemas")
    required_tables = {
        "database_info",
        "database_lineage",
        "domain_events",
        "schema_migrations",
    }
    if schema_version == CURRENT_SCHEMA_VERSION:
        required_tables.add("operation_diagnostics")
    actual_tables = {
        str(item[0])
        for item in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = '_persistra'"
        ).fetchall()
    }
    if not required_tables <= actual_tables:
        raise DatabaseCompatibilityError("database is missing required metadata tables")
    role_tables = {
        DatabaseRole.MARKET: {
            ("canonical", "bar_specs"),
            ("canonical", "bars"),
            ("canonical", "calendar_dates"),
            ("canonical", "calendar_definitions"),
            ("canonical", "classification_assignments"),
            ("canonical", "classification_nodes"),
            ("canonical", "classification_schemes"),
            ("canonical", "corporate_action_observations"),
            ("canonical", "corporate_actions"),
            ("canonical", "identifier_assignments"),
            ("canonical", "identifier_namespaces"),
            ("canonical", "instrument_observations"),
            ("canonical", "instruments"),
            ("canonical", "issuers"),
            ("canonical", "listings"),
            ("canonical", "securities"),
            ("canonical", "trading_status"),
            ("canonical", "universe_memberships"),
            ("canonical", "venues"),
            ("catalog", "batch_records"),
            ("catalog", "batches"),
            ("catalog", "canonical_retractions"),
            ("catalog", "canonical_revisions"),
            ("catalog", "catalog_clock"),
            ("catalog", "changes"),
            ("catalog", "dataset_state"),
            ("catalog", "dataset_versions"),
            ("catalog", "datasets"),
            ("catalog", "pending_remediations"),
            ("catalog", "record_dispositions"),
            ("catalog", "source_state"),
            ("catalog", "source_versions"),
            ("catalog", "sources"),
            ("catalog", "validation_attempt_transitions"),
            ("catalog", "validation_attempts"),
            ("quality", "findings"),
            ("quality", "quarantined_records"),
            ("quality", "remediation_links"),
            ("snapshots", "market_snapshots"),
            ("snapshots", "snapshot_dataset_state"),
            ("snapshots", "snapshot_source_state"),
        },
        DatabaseRole.RESEARCH: {
            ("research", "composite_snapshot_members"),
            ("research", "composite_snapshots"),
            ("research", "research_dataset_builds"),
            ("research", "research_dataset_input_outcomes"),
            ("research", "research_dataset_row_audit"),
            ("research", "research_dataset_versions"),
            ("research", "research_datasets"),
            ("research", "universe_definitions"),
            ("research", "universe_eligibility"),
            ("research", "universe_evaluations"),
            ("research", "universe_rule_outcomes"),
        },
    }
    actual_role_tables = {
        (str(schema), str(table))
        for schema, table in connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables"
        ).fetchall()
    }
    if schema_version < CURRENT_SCHEMA_VERSION and role is DatabaseRole.MARKET:
        role_tables[role] -= {
            ("catalog", "dataset_state"),
            ("catalog", "source_state"),
        }
    if schema_version < 4:
        role_tables[DatabaseRole.MARKET] -= {
            item for item in role_tables[DatabaseRole.MARKET] if item[0] == "canonical"
        }
        role_tables[DatabaseRole.RESEARCH] -= {
            ("research", "research_dataset_builds"),
            ("research", "research_dataset_input_outcomes"),
            ("research", "research_dataset_row_audit"),
            ("research", "research_dataset_versions"),
            ("research", "research_datasets"),
            ("research", "universe_definitions"),
            ("research", "universe_eligibility"),
            ("research", "universe_evaluations"),
            ("research", "universe_rule_outcomes"),
        }
    if not role_tables[role] <= actual_role_tables:
        raise DatabaseCompatibilityError("database is missing required role tables")
    required_role_columns = {
        DatabaseRole.MARKET: {
            ("catalog", "canonical_revisions"): {
                "availability_quality",
                "available_at",
                "batch_id",
                "canonical_payload_json",
                "canonical_revision_id",
                "catalog_sequence",
                "dataset_id",
                "dataset_version",
                "event_at",
                "ingested_at",
                "natural_key_content_id",
                "natural_key_json",
                "payload_content_id",
                "published_at",
                "revision_effect",
                "revision_ordinal",
                "source_content_id",
                "source_id",
                "source_record_key",
                "source_revision_key",
                "source_updated_at",
                "submitted_record_id",
                "supersedes_revision_id",
            },
            ("catalog", "batches"): {
                "adapter_name",
                "adapter_version",
                "batch_content_id",
                "batch_id",
                "catalog_sequence",
                "created_at",
                "current_status",
                "dataset_id",
                "dataset_version",
                "expected_batch_content_id",
                "parent_batch_id",
                "source_id",
                "source_version",
                "staged_at",
                "submission_key",
                "submitted_count",
                "terminal_at",
                "validated_at",
                "validation_attempt_id",
                "validation_input_catalog_sequence",
                "validation_token_content_id",
            },
            ("catalog", "batch_records"): {"disposition_group_id"},
            ("catalog", "record_dispositions"): {"disposition_group_id"},
            ("quality", "findings"): {"disposition_group_id"},
            ("quality", "quarantined_records"): {"disposition_group_id"},
            ("catalog", "dataset_state"): {
                "dataset_id",
                "dataset_version",
                "disposition_count",
                "finding_count",
                "latest_catalog_sequence",
                "revision_count",
                "state_content_id",
                "terminal_batch_count",
                "validation_attempt_count",
            },
        },
        DatabaseRole.RESEARCH: {
            ("research", "composite_snapshot_members"): {
                "composite_snapshot_id",
                "database_id",
                "database_name",
                "market_manifest_content_id",
                "market_snapshot_id",
                "verified_copy_id",
            }
        },
    }
    if schema_version == CURRENT_SCHEMA_VERSION:
        for (schema, table), required_columns in required_role_columns[role].items():
            actual_columns = {
                str(column)
                for (column,) in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = ? AND table_name = ?",
                    [schema, table],
                ).fetchall()
            }
            if not required_columns <= actual_columns:
                raise DatabaseCompatibilityError(
                    f"managed table {schema}.{table} is incompatible"
                )
    return DatabaseMetadata(database_id, role, owner, row[3], schema_version, bool(row[5]))


def publish_noreplace(temporary: Path, destination: Path) -> None:
    """Atomically publish one same-filesystem file without replacing a peer."""
    os.link(temporary, destination)
    temporary.unlink()


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
        raise DatabaseAlreadyExistsError("database destination already exists")
    if (role is DatabaseRole.RESEARCH) != (project_id is not None):
        raise DatabaseRoleError("database role and project ownership are inconsistent")
    inspect_filesystem(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    database_id = DatabaseId.new()
    temporary = path.with_name(f".{path.name}.partial-{database_id.value}")
    try:
        connection = ManagedConnection(temporary, read_only=False)
        temporary.chmod(0o600)
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
        try:
            publish_noreplace(temporary, path)
        except FileExistsError as error:
            raise DatabaseAlreadyExistsError(
                "database destination appeared during publication"
            ) from error
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return metadata
    finally:
        temporary.unlink(missing_ok=True)
