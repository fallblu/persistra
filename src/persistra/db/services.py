"""This module contains project database, transaction, and diagnostic services for each
capability."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from persistra import __version__
from persistra.db.models import (
    DatabaseInspection,
    DatabaseRole,
    DoctorFinding,
    MaintenanceIntent,
    ProjectMode,
)
from persistra.domain import ContentId, EventId, QualifiedName
from persistra.domain.serialization import canonical_bytes
from persistra.errors import (
    CapabilityUnavailableError,
    DatabaseAlreadyExistsError,
    MigrationFailedError,
    ProjectConfigError,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from persistra.accounting.services import AccountingService
    from persistra.analysis.services import AnalysisService
    from persistra.catalog.models import MarketSnapshotId
    from persistra.catalog.services import CatalogService, IngestionService, SnapshotService
    from persistra.db.connection import DatabaseMetadata
    from persistra.db.models import (
        CopyResult,
        CopyVerification,
        MigrationResult,
        ProjectId,
        RestoreResult,
    )
    from persistra.experiments.services import ExperimentService
    from persistra.market.services import MarketService
    from persistra.portfolio.services import PortfolioService
    from persistra.project import Project
    from persistra.reference.services import ReferenceService
    from persistra.reference.universes import UniverseService
    from persistra.reports.services import ReportService
    from persistra.research.services import ResearchService
    from persistra.results.services import ResultService
    from persistra.simulation.services import SimulationService

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class TransactionContext:
    """This class represents the narrow transaction evidence without connection lifecycle
    authority."""

    operation_name: str
    recorded_at: datetime


class TransactionService:
    __slots__ = ("_active", "_project")

    def __init__(self, project: Project) -> None:
        self._project = project
        self._active = False

    def in_transaction(self) -> bool:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        return self._active

    def run(self, operation_name: str, fn: Callable[[TransactionContext], ResultT]) -> ResultT:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        if self._project._mode not in {  # pyright: ignore[reportPrivateUsage]
            ProjectMode.RESEARCH_WRITE,
            ProjectMode.MARKET_WRITE,
        }:
            raise CapabilityUnavailableError(
                "transactions require research_write or market_write mode"
            )
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        if self._active:
            raise ProjectConfigError("nested public transactions are forbidden")
        if not operation_name:
            raise ProjectConfigError("transaction operation name is required")
        connection.begin()
        self._active = True
        context = TransactionContext(
            operation_name,
            self._project._clock.now(),  # pyright: ignore[reportPrivateUsage]
        )
        try:
            result = fn(context)
            connection.commit()
            return result
        except BaseException:
            try:
                connection.rollback()
            except BaseException:
                pass
            raise
        finally:
            self._active = False


class DatabaseService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def inspect(self) -> tuple[DatabaseInspection, ...]:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        return self._project.inspect().databases

    def _reopen_maintenance_connection(self, opened: Any) -> None:
        from persistra.db.connection import ManagedConnection

        opened.connection = ManagedConnection(
            opened.path,
            read_only=(
                self._project._maintenance_intent  # pyright: ignore[reportPrivateUsage]
                is MaintenanceIntent.VERIFY_COPY
            ),
            threads=self._project._config.threads,  # pyright: ignore[reportPrivateUsage]
            memory_limit=self._project._config.memory_limit,  # pyright: ignore[reportPrivateUsage]
            temporary_directory=self._project._config.temporary,  # pyright: ignore[reportPrivateUsage]
            temporary_limit=self._project._config.temporary_limit,  # pyright: ignore[reportPrivateUsage]
        )

    def create(
        self, *, role: DatabaseRole, path: Path, disposable: bool = False
    ) -> DatabaseInspection:
        """Create and open the exact destination selected by this maintenance lifecycle."""
        from persistra.db.connection import create_database_file

        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        if (
            self._project._mode is not ProjectMode.MAINTENANCE  # pyright: ignore[reportPrivateUsage]
            or self._project._maintenance_intent  # pyright: ignore[reportPrivateUsage]
            is not MaintenanceIntent.CREATE
        ):
            raise CapabilityUnavailableError(
                "database creation requires a create maintenance project"
            )
        target = self._project._maintenance_target  # pyright: ignore[reportPrivateUsage]
        if target is None or path.resolve() != target[1]:
            raise ProjectConfigError("creation path must match the maintenance selector")
        if target[2] is not None and role is not target[2]:
            raise ProjectConfigError("creation role must match the configured selector")
        if target[1].exists():
            raise DatabaseAlreadyExistsError("database creation destination already exists")
        metadata = create_database_file(
            target[1],
            role=role,
            project_id=(
                self._project._config.project_id  # pyright: ignore[reportPrivateUsage]
                if role is DatabaseRole.RESEARCH
                else None
            ),
            disposable=disposable,
            clock=self._project._clock,  # pyright: ignore[reportPrivateUsage]
        )
        opened = self._project._register_created_database(  # pyright: ignore[reportPrivateUsage]
            target[0], target[1], metadata
        )
        return inspect_open_database(target[0], target[1], metadata, opened.lease_mode.value)

    def migrate(self) -> MigrationResult:
        """Apply each registered forward migration after a verified physical backup."""
        from persistra.db.connection import ManagedConnection, inspect_database
        from persistra.db.copies import publish_backup
        from persistra.db.migrations import (
            CURRENT_SCHEMA_VERSION,
            MIGRATIONS,
            migration_statements,
        )
        from persistra.db.models import CopyId, MigrationResult

        opened = self._require_maintenance_source(MaintenanceIntent.MIGRATE)
        pending = tuple(
            step for step in MIGRATIONS if step.number > opened.metadata.schema_version
        )
        if not pending:
            return MigrationResult(
                opened.metadata.database_id,
                opened.metadata.schema_version,
                (),
            )
        backups = (
            self._project._config.state_dir / "backups"  # pyright: ignore[reportPrivateUsage]
        )
        backups.mkdir(parents=True, exist_ok=True)
        backup_path = backups / (
            f"migration-{opened.metadata.database_id.value}-"
            f"schema-{opened.metadata.schema_version}-{CopyId.new().value}.duckdb"
        )
        opened.connection.close()
        try:
            backup = publish_backup(
                opened.path,
                backup_path,
                expected_role=opened.metadata.role,
                logical_name=opened.logical_name,
                clock=self._project._clock,  # pyright: ignore[reportPrivateUsage]
                project_id=str(self._project._config.project_id),  # pyright: ignore[reportPrivateUsage]
                project_name=self._project._config.name,  # pyright: ignore[reportPrivateUsage]
                allow_older_schema=True,
            )
        except BaseException:
            self._reopen_maintenance_connection(opened)
            raise
        connection: ManagedConnection | None = None
        committed = False
        try:
            connection = ManagedConnection(opened.path, read_only=False)
            metadata = inspect_database(
                connection,
                expected_role=opened.metadata.role,
                expected_project_id=opened.metadata.owner_project_id,
                allow_older_schema=True,
            )
            connection.begin()
            recorded_at = self._project._clock.now()  # pyright: ignore[reportPrivateUsage]
            for step in pending:
                if metadata.schema_version != step.source_version:
                    raise MigrationFailedError("migration source version is not contiguous")
                database_name = str(
                    connection.execute("SELECT current_database()").fetchone()[0]
                )
                for statement in migration_statements(
                    step, role=metadata.role.value, database_name=database_name
                ):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO _persistra.schema_migrations VALUES (?, ?, ?, ?, ?, ?, 0)",
                    [
                        step.number,
                        step.name,
                        step.checksum,
                        recorded_at,
                        __version__,
                        backup.copy_id.value,
                    ],
                )
                connection.execute(
                    "UPDATE _persistra.database_info SET schema_version = ?",
                    [step.target_version],
                )
                payload = canonical_bytes(
                    {
                        "backup_copy_id": str(backup.copy_id),
                        "database_id": str(metadata.database_id),
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
                        recorded_at,
                        recorded_at,
                        recorded_at,
                        str(QualifiedName("persistra.aggregate.database")),
                        metadata.database_id.value,
                        step.number,
                        str(ContentId.from_bytes(payload)),
                        payload,
                    ],
                )
                metadata = type(metadata)(
                    metadata.database_id,
                    metadata.role,
                    metadata.owner_project_id,
                    metadata.created_at,
                    step.target_version,
                    metadata.disposable,
                )
            diagnostic_evidence = canonical_bytes(
                {
                    "applied_migrations": tuple(step.number for step in pending),
                    "backup_copy_id": str(backup.copy_id),
                    "database_id": str(metadata.database_id),
                    "schema_version": metadata.schema_version,
                }
            ).decode()
            connection.execute(
                "INSERT INTO _persistra.operation_diagnostics VALUES (?, ?, ?, ?, ?)",
                [
                    EventId.new().value,
                    "database.migrate",
                    "succeeded",
                    diagnostic_evidence,
                    recorded_at,
                ],
            )
            connection.commit()
            committed = True
            connection.execute("CHECKPOINT")
            connection.close()
            connection = None
            verifier = ManagedConnection(opened.path, read_only=True)
            try:
                verified = inspect_database(
                    verifier,
                    expected_role=opened.metadata.role,
                    expected_project_id=opened.metadata.owner_project_id,
                )
            finally:
                verifier.close()
            if verified.schema_version != CURRENT_SCHEMA_VERSION:
                raise MigrationFailedError("migration did not reach the registered head")
            opened.metadata = verified
            return MigrationResult(
                verified.database_id,
                verified.schema_version,
                tuple(step.number for step in pending),
                backup.copy_id,
            )
        except BaseException as error:
            if connection is not None:
                if not committed:
                    try:
                        connection.rollback()
                    except BaseException:
                        pass
                connection.close()
            if committed:
                marker = opened.path.with_name(f"{opened.path.name}.recovery-required")
                marker.write_text("post-commit migration verification failed\n", encoding="utf-8")
            if isinstance(error, MigrationFailedError):
                raise
            raise MigrationFailedError("database migration failed") from error
        finally:
            self._reopen_maintenance_connection(opened)

    def backup(self, *, destination: Path) -> CopyResult:
        """Publish a verified immutable copy of the selected maintenance database."""
        from persistra.db.copies import publish_backup

        opened = self._require_maintenance_source(MaintenanceIntent.BACKUP)
        opened.connection.execute("CHECKPOINT")
        opened.connection.close()
        try:
            return publish_backup(
                opened.path,
                destination,
                expected_role=opened.metadata.role,
                logical_name=opened.logical_name,
                clock=self._project._clock,  # pyright: ignore[reportPrivateUsage]
                project_id=str(self._project._config.project_id),  # pyright: ignore[reportPrivateUsage]
                project_name=self._project._config.name,  # pyright: ignore[reportPrivateUsage]
            )
        finally:
            self._reopen_maintenance_connection(opened)

    def verify_copy(self) -> CopyVerification:
        """Verify the selected copy against its immutable publication metadata."""
        from persistra.db.copies import verify_published_copy

        opened = self._require_maintenance_source(MaintenanceIntent.VERIFY_COPY)
        return verify_published_copy(opened.path, expected_role=opened.metadata.role)

    def _require_maintenance_source(self, intent: MaintenanceIntent) -> Any:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        self._project._validate_leases()  # pyright: ignore[reportPrivateUsage]
        if (
            self._project._mode is not ProjectMode.MAINTENANCE  # pyright: ignore[reportPrivateUsage]
            or self._project._maintenance_intent is not intent  # pyright: ignore[reportPrivateUsage]
            or len(self._project._databases) != 1  # pyright: ignore[reportPrivateUsage]
        ):
            raise CapabilityUnavailableError(
                f"operation requires maintenance intent {intent.value}"
            )
        return self._project._databases[0]  # pyright: ignore[reportPrivateUsage]

    def snapshot_copy(
        self, *, snapshot_id: MarketSnapshotId, destination: Path
    ) -> CopyResult:
        """Publish a verified market copy pinned to one committed logical snapshot."""
        from persistra.db.copies import publish_backup

        opened = self._require_maintenance_source(MaintenanceIntent.SNAPSHOT_COPY)
        if opened.metadata.role is not DatabaseRole.MARKET:
            raise CapabilityUnavailableError("snapshot copies require a market database")
        row = opened.connection.execute(
            "SELECT catalog_sequence, manifest_content_id FROM snapshots.market_snapshots "
            "WHERE market_snapshot_id = ? AND database_id = ?",
            [snapshot_id.value, opened.metadata.database_id.value],
        ).fetchone()
        if row is None:
            raise ProjectConfigError("market snapshot is not committed in the selected database")
        from persistra.catalog.models import SnapshotRef
        from persistra.catalog.services import verify_snapshot_integrity

        snapshot = SnapshotRef(
            opened.metadata.database_id,
            snapshot_id,
            int(row[0]),
            ContentId.parse(row[1]),
        )
        verify_snapshot_integrity(opened.connection, snapshot)
        opened.connection.execute("CHECKPOINT")
        opened.connection.close()
        try:
            return publish_backup(
                opened.path,
                destination,
                expected_role=DatabaseRole.MARKET,
                logical_name=opened.logical_name,
                clock=self._project._clock,  # pyright: ignore[reportPrivateUsage]
                project_id=str(self._project._config.project_id),  # pyright: ignore[reportPrivateUsage]
                project_name=self._project._config.name,  # pyright: ignore[reportPrivateUsage]
                kind="market_snapshot",
                market_snapshot_id=str(snapshot_id),
                market_snapshot_manifest_content_id=row[1],
            )
        finally:
            self._reopen_maintenance_connection(opened)

    def restore(self, *, backup_path: Path) -> RestoreResult:
        """Restore a verified backup into the selected destination that does not exist."""
        return self._restore_or_fork(
            backup_path=backup_path,
            relation="restore",
            destination_project_id=None,
        )

    def fork(
        self, *, backup_path: Path, destination_project_id: ProjectId
    ) -> RestoreResult:
        """Fork a verified backup into a new selected database lineage."""
        return self._restore_or_fork(
            backup_path=backup_path,
            relation="fork",
            destination_project_id=destination_project_id,
        )

    def _restore_or_fork(
        self,
        *,
        backup_path: Path,
        relation: str,
        destination_project_id: ProjectId | None,
    ) -> RestoreResult:
        from persistra.db.copies import restore_verified_copy

        intent = (
            MaintenanceIntent.RESTORE if relation == "restore" else MaintenanceIntent.FORK
        )
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        if (
            self._project._mode is not ProjectMode.MAINTENANCE  # pyright: ignore[reportPrivateUsage]
            or self._project._maintenance_intent is not intent  # pyright: ignore[reportPrivateUsage]
            or self._project._databases  # pyright: ignore[reportPrivateUsage]
        ):
            raise CapabilityUnavailableError(
                f"operation requires an absent destination and maintenance intent {intent.value}"
            )
        target = self._project._maintenance_target  # pyright: ignore[reportPrivateUsage]
        if target is None:
            raise ProjectConfigError("restore destination is unavailable")
        result, metadata = restore_verified_copy(
            backup_path,
            target[1],
            relation=relation,
            opening_project_id=self._project._config.project_id,  # pyright: ignore[reportPrivateUsage]
            destination_project_id=destination_project_id,
            clock=self._project._clock,  # pyright: ignore[reportPrivateUsage]
        )
        if target[2] is not None and metadata.role is not target[2]:
            target[1].unlink(missing_ok=True)
            raise ProjectConfigError("restored database role does not match the selector")
        self._project._register_created_database(  # pyright: ignore[reportPrivateUsage]
            target[0], target[1], metadata
        )
        return result


class DiagnosticsService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def doctor(self) -> tuple[DoctorFinding, ...]:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        inspection = self._project.inspect()
        findings: list[DoctorFinding] = []
        for database in inspection.databases:
            findings.append(
                DoctorFinding(
                    code="db.schema.current",
                    severity="info",
                    subject=database.logical_name,
                    evidence=f"schema {database.schema_version}",
                    remediation="none",
                )
            )
        from persistra.catalog.models import BatchStatus

        terminal = {
            BatchStatus.ABORTED.value,
            BatchStatus.COMMITTED.value,
            BatchStatus.COMMITTED_WITH_QUARANTINE.value,
            BatchStatus.QUARANTINED.value,
            BatchStatus.REJECTED.value,
        }
        for opened in self._project._databases:  # pyright: ignore[reportPrivateUsage]
            if opened.metadata.role is not DatabaseRole.MARKET:
                continue
            from persistra.catalog.services import verify_registered_state

            verify_registered_state(opened.connection)
            nonterminal = opened.connection.execute(
                "SELECT batch_id, current_status FROM catalog.batches "
                "WHERE current_status NOT IN (?, ?, ?, ?, ?) ORDER BY created_at",
                sorted(terminal),
            ).fetchall()
            for batch_id, status in nonterminal:
                findings.append(
                    DoctorFinding(
                        code="ingestion.batch.nonterminal",
                        severity="warning",
                        subject=str(batch_id),
                        evidence=f"batch is {status}",
                        remediation="resume staging, revalidate, commit, or abort the batch",
                    )
                )
            current_sequence = int(
                opened.connection.execute(
                    "SELECT current_sequence FROM catalog.catalog_clock"
                ).fetchone()[0]
            )
            latest_snapshot = opened.connection.execute(
                "SELECT max(catalog_sequence) FROM snapshots.market_snapshots"
            ).fetchone()[0]
            if latest_snapshot is None or int(latest_snapshot) < current_sequence:
                findings.append(
                    DoctorFinding(
                        code="snapshot.catalog.unpinned",
                        severity="warning",
                        subject=opened.logical_name,
                        evidence=f"catalog sequence {current_sequence} has no latest snapshot",
                        remediation="create a market snapshot after writes complete",
                    )
                )
        return tuple(findings)

    def events(self, limit: int = 100, level: str | None = None) -> tuple[dict[str, Any], ...]:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        if not 0 <= limit <= 10_000:
            raise ProjectConfigError("event limit must be between zero and 10000")
        if level is not None and level not in {"info", "warning", "error"}:
            raise ProjectConfigError("event level filter is invalid")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        rows = connection.execute(
            "SELECT event_name, event_schema_version, recorded_at, aggregate_kind, "
            "aggregate_id, aggregate_sequence, payload_content_id, payload_json_utf8 "
            "FROM _persistra.domain_events ORDER BY recorded_at DESC, event_id DESC LIMIT ?",
            [limit],
        ).fetchall()
        return tuple(
            {
                "aggregate_id": str(row[4]),
                "aggregate_kind": row[3],
                "aggregate_sequence": int(row[5]),
                "event_name": row[0],
                "event_schema_version": int(row[1]),
                "payload": json.loads(bytes(row[7])),
                "payload_content_id": row[6],
                "recorded_at": row[2],
            }
            for row in rows
        )


@dataclass(frozen=True, slots=True)
class ProjectServices:
    databases: DatabaseService
    transactions: TransactionService
    diagnostics: DiagnosticsService
    catalog: CatalogService
    ingestion: IngestionService
    snapshots: SnapshotService
    reference: ReferenceService
    universes: UniverseService
    market: MarketService
    research: ResearchService
    portfolio: PortfolioService
    accounting: AccountingService
    simulation: SimulationService
    experiments: ExperimentService
    results: ResultService
    analysis: AnalysisService
    reports: ReportService


def inspect_open_database(
    logical_name: str,
    path: Path,
    metadata: DatabaseMetadata,
    lease_mode: str,
) -> DatabaseInspection:
    return DatabaseInspection(
        logical_name=logical_name,
        path_sha256=hashlib.sha256(str(path).encode()).hexdigest(),
        database_id=metadata.database_id,
        role=metadata.role,
        schema_version=metadata.schema_version,
        lease_mode=lease_mode,
    )
