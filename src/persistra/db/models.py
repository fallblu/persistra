"""Immutable database identities, selectors, roles, and project modes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pathlib import Path

from persistra.domain import EntityId
from persistra.errors import ProjectConfigError


class ProjectId(EntityId):
    KIND: ClassVar[str] = "project"


class DatabaseId(EntityId):
    KIND: ClassVar[str] = "database"


class LeaseId(EntityId):
    KIND: ClassVar[str] = "lease"


class CopyId(EntityId):
    KIND: ClassVar[str] = "copy"


class DatabaseRole(StrEnum):
    """Immutable ownership role of a managed DuckDB file."""

    MARKET = "market"
    RESEARCH = "research"


class ProjectMode(StrEnum):
    """Connection and capability ownership mode for one project lifecycle."""

    READ_ONLY = "read_only"
    RESEARCH_WRITE = "research_write"
    MARKET_WRITE = "market_write"
    MAINTENANCE = "maintenance"


class MaintenanceIntent(StrEnum):
    """Single permitted maintenance operation for an isolated target."""

    CREATE = "create"
    INSPECT = "inspect"
    BACKUP = "backup"
    SNAPSHOT_COPY = "snapshot_copy"
    VERIFY_COPY = "verify_copy"
    MIGRATE = "migrate"
    RESTORE = "restore"
    FORK = "fork"


@dataclass(frozen=True, slots=True, init=False)
class DatabaseName:
    """Validated logical market-database name."""

    value: str
    _RESERVED: ClassVar[frozenset[str]] = frozenset({"research", "temp", "system", "main"})

    def __init__(self, value: object) -> None:
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value) is None
            or value in self._RESERVED
        ):
            raise ProjectConfigError("invalid market database name")
        object.__setattr__(self, "value", value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ResearchDatabase:
    """Selector for the configured research database."""


@dataclass(frozen=True, slots=True)
class MarketDatabase:
    """Selector for one configured market database."""

    name: DatabaseName


@dataclass(frozen=True, slots=True)
class PathDatabase:
    """Explicit managed path selector for maintenance workflows."""

    path: Path


DatabaseSelector = ResearchDatabase | MarketDatabase | PathDatabase


@dataclass(frozen=True, slots=True)
class ProjectLayout:
    project_id: ProjectId
    root: Path
    config_path: Path
    state_path: Path
    research_database_path: Path | None
    created_paths: tuple[Path, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class DatabaseInspection:
    logical_name: str
    path_sha256: str
    database_id: DatabaseId
    role: DatabaseRole
    schema_version: int
    lease_mode: str


@dataclass(frozen=True, slots=True)
class ProjectInspection:
    project_id: ProjectId
    name: str
    root: Path
    mode: ProjectMode
    databases: tuple[DatabaseInspection, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    code: str
    severity: str
    subject: str
    evidence: str
    remediation: str
