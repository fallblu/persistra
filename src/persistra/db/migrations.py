"""Immutable forward database migration registry."""

from __future__ import annotations

from dataclasses import dataclass

from persistra.domain import ContentId
from persistra.domain.serialization import canonical_bytes

CURRENT_SCHEMA_VERSION = 3
MINIMUM_MIGRATABLE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class MigrationStep:
    number: int
    name: str
    source_version: int
    target_version: int
    statements: tuple[str, ...]
    market_statements: tuple[str, ...]
    research_statements: tuple[str, ...]
    checksum: str


def _step(
    number: int,
    name: str,
    source_version: int,
    target_version: int,
    statements: tuple[str, ...],
    market_statements: tuple[str, ...] = (),
    research_statements: tuple[str, ...] = (),
) -> MigrationStep:
    checksum = str(
        ContentId.from_bytes(
            canonical_bytes(
                {
                    "name": name,
                    "number": number,
                    "source_version": source_version,
                    "statements": statements,
                    "market_statements": market_statements,
                    "research_statements": research_statements,
                    "target_version": target_version,
                }
            )
        )
    )
    return MigrationStep(
        number,
        name,
        source_version,
        target_version,
        statements,
        market_statements,
        research_statements,
        checksum,
    )


MIGRATION_2 = _step(
    2,
    "operation_diagnostics",
    1,
    2,
    (
        """CREATE TABLE _persistra.operation_diagnostics (
            diagnostic_id UUID PRIMARY KEY,
            operation_name VARCHAR NOT NULL,
            outcome VARCHAR NOT NULL,
            evidence_json JSON NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL
        )""",
    ),
    (
        "ALTER TABLE catalog.batches ADD COLUMN expected_batch_content_id VARCHAR",
        "ALTER TABLE catalog.batches ADD COLUMN parent_batch_id UUID",
        """CREATE TABLE catalog.source_state (
            source_id UUID NOT NULL,
            source_version INTEGER NOT NULL,
            latest_catalog_sequence BIGINT NOT NULL,
            revision_count BIGINT NOT NULL,
            terminal_batch_count BIGINT NOT NULL,
            disposition_count BIGINT NOT NULL,
            validation_attempt_count BIGINT NOT NULL,
            finding_count BIGINT NOT NULL,
            state_content_id VARCHAR NOT NULL,
            PRIMARY KEY (source_id, source_version)
        )""",
        """CREATE TABLE catalog.dataset_state (
            dataset_id UUID NOT NULL,
            dataset_version INTEGER NOT NULL,
            latest_catalog_sequence BIGINT NOT NULL,
            revision_count BIGINT NOT NULL,
            terminal_batch_count BIGINT NOT NULL,
            disposition_count BIGINT NOT NULL,
            validation_attempt_count BIGINT NOT NULL,
            finding_count BIGINT NOT NULL,
            state_content_id VARCHAR NOT NULL,
            PRIMARY KEY (dataset_id, dataset_version)
        )""",
    ),
    (
        "ALTER TABLE {database}.research.composite_snapshot_members "
        "ADD COLUMN verified_copy_id UUID",
    ),
)

MIGRATION_3 = _step(
    3,
    "atomic_disposition_groups",
    2,
    3,
    (),
    (
        "ALTER TABLE catalog.batch_records ADD COLUMN disposition_group_id UUID",
        "ALTER TABLE catalog.record_dispositions ADD COLUMN disposition_group_id UUID",
        "ALTER TABLE quality.findings ADD COLUMN disposition_group_id UUID",
        "ALTER TABLE quality.quarantined_records ADD COLUMN disposition_group_id UUID",
    ),
)

MIGRATIONS = (MIGRATION_2, MIGRATION_3)


def migration_statements(
    step: MigrationStep, *, role: str, database_name: str
) -> tuple[str, ...]:
    role_statements = (
        step.market_statements if role == "market" else step.research_statements
    )
    escaped_database = database_name.replace('"', '""')
    database = f'"{escaped_database}"'
    return tuple(
        statement.replace("{database}", database)
        for statement in step.statements + role_statements
    )
