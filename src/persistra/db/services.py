"""Capability-scoped project database, transaction, and diagnostic services."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from persistra.db.models import (
    DatabaseInspection,
    DatabaseRole,
    DoctorFinding,
    MaintenanceIntent,
    ProjectMode,
)
from persistra.errors import (
    CapabilityUnavailableError,
    DatabaseAlreadyExistsError,
    ProjectConfigError,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from persistra.db.connection import DatabaseMetadata
    from persistra.project import Project

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class TransactionContext:
    """Narrow transaction evidence without connection lifecycle authority."""

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

    def migrate(self, **_: Any) -> None:
        raise CapabilityUnavailableError("no migration beyond bootstrap is registered")

    def backup(self, **_: Any) -> None:
        raise CapabilityUnavailableError("backup is unavailable for this project mode")

    snapshot_copy = backup
    verify_copy = backup
    restore = backup
    fork = backup


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
        return tuple(findings)

    def events(self, limit: int = 100, level: str | None = None) -> tuple[dict[str, Any], ...]:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        if not 0 <= limit <= 10_000:
            raise ProjectConfigError("event limit must be between zero and 10000")
        _ = level
        return ()


@dataclass(frozen=True, slots=True)
class ProjectServices:
    databases: DatabaseService
    transactions: TransactionService
    diagnostics: DiagnosticsService


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
