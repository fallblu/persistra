"""Project lifecycle and capability ownership."""

from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from persistra.config import ProjectOverrides, ResolvedProjectConfig, resolve_config
from persistra.db import (
    DatabaseName,
    DatabaseRole,
    DatabaseSelector,
    MaintenanceIntent,
    MarketDatabase,
    PathDatabase,
    ProjectId,
    ProjectInspection,
    ProjectLayout,
    ProjectMode,
    ResearchDatabase,
)
from persistra.db.connection import (
    DatabaseMetadata,
    ManagedConnection,
    create_database_file,
    inspect_database,
)
from persistra.db.leases import DatabaseLease, LeaseMode, acquire_lease
from persistra.db.services import (
    DatabaseService,
    DiagnosticsService,
    ProjectServices,
    TransactionService,
    inspect_open_database,
)
from persistra.domain import Clock, Duration, SystemClock
from persistra.errors import (
    DatabaseNotFoundError,
    ProjectAlreadyExistsError,
    ProjectClosedError,
    ProjectCloseError,
    ProjectConfigError,
    ProjectProcessError,
    ProjectThreadError,
)

_ZERO_DURATION = Duration(0)
_SYSTEM_CLOCK = SystemClock()


@dataclass(slots=True)
class _OpenDatabase:
    logical_name: str
    path: Path
    connection: ManagedConnection
    metadata: DatabaseMetadata
    lease_mode: LeaseMode


class Project:
    """Thread-owned entry point for one explicitly leased project lifecycle."""

    def __init__(
        self,
        config: ResolvedProjectConfig,
        mode: ProjectMode,
        clock: Clock,
        leases: list[DatabaseLease],
        databases: list[_OpenDatabase],
        maintenance_target: tuple[str, Path, DatabaseRole | None] | None,
        maintenance_intent: MaintenanceIntent | None,
    ) -> None:
        self._config = config
        self._mode = mode
        self._clock = clock
        self._leases = leases
        self._databases = databases
        self._maintenance_target = maintenance_target
        self._maintenance_intent = maintenance_intent
        self._pid = os.getpid()
        self._thread = threading.get_ident()
        self._closed = False
        self._services = ProjectServices(
            DatabaseService(self), TransactionService(self), DiagnosticsService(self)
        )

    @classmethod
    def init(
        cls,
        path: str | Path,
        *,
        name: str | None = None,
        create_research_database: bool = True,
    ) -> ProjectLayout:
        """Atomically initialize a new local project and optional research database."""
        root = Path(path).resolve()
        root.mkdir(parents=True, exist_ok=True)
        config_path = root / "persistra.toml"
        state_path = root / ".persistra"
        if config_path.exists() or state_path.exists():
            raise ProjectAlreadyExistsError("managed project destinations already exist")
        resolved_name = name or re.sub(r"[^a-z0-9_-]+", "-", root.name.lower()).strip("-_")
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", resolved_name or "") is None:
            raise ProjectConfigError("project name must be supplied explicitly")
        project_id = ProjectId.new()
        staging = root / f".persistra.partial-{project_id.value}"
        created: list[Path] = []
        try:
            for directory in (staging / "artifacts", staging / "logs", staging / "tmp"):
                directory.mkdir(parents=True)
            (staging / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
            database_path = staging / "research.duckdb"
            if create_research_database:
                create_database_file(
                    database_path,
                    role=DatabaseRole.RESEARCH,
                    project_id=project_id,
                    disposable=False,
                    clock=SystemClock(),
                )
            os.replace(staging, state_path)
            created.append(state_path)
            config_text = (
                f'[project]\nid = "{project_id}"\nname = "{resolved_name}"\n'
                'state_dir = ".persistra"\n\n[databases.research]\n'
                'path = ".persistra/research.duckdb"\ndisposable = false\n\n'
                '[paths]\nartifacts = ".persistra/artifacts"\nlogs = ".persistra/logs"\n'
                'temporary = ".persistra/tmp"\n'
            )
            temporary_config = root / f".persistra.toml.partial-{project_id.value}"
            temporary_config.write_text(config_text, encoding="utf-8")
            os.replace(temporary_config, config_path)
            created.append(config_path)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging)
            if state_path in created and not config_path.exists():
                shutil.rmtree(state_path)
            raise
        research = state_path / "research.duckdb" if create_research_database else None
        return ProjectLayout(
            project_id,
            root,
            config_path,
            state_path,
            research,
            tuple(created),
            create_research_database,
        )

    @classmethod
    def open(
        cls,
        path: str | Path = ".",
        *,
        mode: ProjectMode = ProjectMode.RESEARCH_WRITE,
        writable_market: DatabaseName | None = None,
        maintenance_database: DatabaseSelector | None = None,
        maintenance_intent: MaintenanceIntent | None = None,
        overrides: ProjectOverrides | None = None,
        allow_verified_remote_read: bool = False,
        wait_timeout: Duration = _ZERO_DURATION,
        clock: Clock = _SYSTEM_CLOCK,
    ) -> Self:
        """Open an exact capability mode after acquiring every required lease."""
        _validate_mode(mode, writable_market, maintenance_database, maintenance_intent)
        _ = allow_verified_remote_read
        config = resolve_config(path, overrides=overrides)
        targets = _targets(config, mode, writable_market, maintenance_database)
        leases: list[DatabaseLease] = []
        databases: list[_OpenDatabase] = []
        try:
            for logical, target, role, lease_mode, read_only in sorted(
                targets, key=lambda item: os.fsencode(item[1])
            ):
                if not target.exists():
                    if (
                        mode is ProjectMode.MAINTENANCE
                        and maintenance_intent is MaintenanceIntent.CREATE
                    ):
                        lease = acquire_lease(
                            target,
                            lease_mode,
                            timeout=wait_timeout,
                            operation="database_create",
                            project_id=str(config.project_id),
                            project_name=config.name,
                        )
                        leases.append(lease)
                        continue
                    raise DatabaseNotFoundError(f"configured database is missing: {logical}")
                lease = acquire_lease(
                    target,
                    lease_mode,
                    timeout=wait_timeout,
                    project_id=str(config.project_id),
                    project_name=config.name,
                )
                leases.append(lease)
                connection = ManagedConnection(target, read_only=read_only)
                metadata = inspect_database(
                    connection,
                    expected_role=role,
                    expected_project_id=(
                        config.project_id if role is DatabaseRole.RESEARCH else None
                    ),
                )
                databases.append(_OpenDatabase(logical, target, connection, metadata, lease_mode))
            if mode in {ProjectMode.READ_ONLY, ProjectMode.RESEARCH_WRITE} and databases:
                research = next(
                    database
                    for database in databases
                    if database.metadata.role is DatabaseRole.RESEARCH
                )
                market_databases = [
                    database
                    for database in databases
                    if database.metadata.role is DatabaseRole.MARKET
                ]
                identities = {database.metadata.database_id for database in databases}
                if len(identities) != len(databases):
                    raise ProjectConfigError(
                        "configured databases must have distinct database identities"
                    )
                for market in market_databases:
                    research.connection.attach_market(market.logical_name, market.path)
            maintenance_target = None
            if mode is ProjectMode.MAINTENANCE:
                logical, target, role, _, _ = targets[0]
                maintenance_target = (logical, target, role)
            return cls(
                config,
                mode,
                clock,
                leases,
                databases,
                maintenance_target,
                maintenance_intent,
            )
        except BaseException:
            for database in reversed(databases):
                database.connection.close()
            for lease in reversed(leases):
                lease.close()
            raise

    @property
    def config(self) -> ResolvedProjectConfig:
        self._guard()
        return self._config

    @property
    def services(self) -> ProjectServices:
        self._guard()
        return self._services

    def inspect(self) -> ProjectInspection:
        self._guard()
        records = tuple(
            inspect_open_database(
                item.logical_name, item.path, item.metadata, item.lease_mode.value
            )
            for item in self._databases
        )
        return ProjectInspection(
            self._config.project_id, self._config.name, self._config.root, self._mode, records
        )

    def close(self) -> None:
        if self._closed:
            return
        errors: list[BaseException] = []
        for database in reversed(self._databases):
            try:
                database.connection.close()
            except BaseException as error:
                errors.append(error)
        for lease in reversed(self._leases):
            try:
                lease.close()
            except BaseException as error:
                errors.append(error)
        self._closed = True
        if errors:
            raise ProjectCloseError("one or more managed resources failed to close")

    def __enter__(self) -> Self:
        self._guard()
        return self

    def __exit__(self, *exc_info: object) -> None:
        try:
            self.close()
        except BaseException as close_error:
            body_error = exc_info[1]
            if isinstance(body_error, BaseException):
                body_error.add_note(f"project close also failed: {close_error}")
            else:
                raise

    def _guard(self) -> None:
        if os.getpid() != self._pid:
            raise ProjectProcessError("project cannot cross a process boundary")
        if threading.get_ident() != self._thread:
            raise ProjectThreadError("project cannot cross a thread boundary")
        if self._closed:
            raise ProjectClosedError("project is closed")

    def _primary_connection(self) -> ManagedConnection:
        self._guard()
        if not self._databases:
            raise ProjectClosedError("project mode has no open database")
        return self._databases[0].connection

    def _register_created_database(
        self, logical_name: str, path: Path, metadata: DatabaseMetadata
    ) -> _OpenDatabase:
        """Open a just-created maintenance target under the already-owned lease."""
        self._guard()
        connection = ManagedConnection(path, read_only=False)
        opened = _OpenDatabase(
            logical_name, path, connection, metadata, self._leases[0].mode
        )
        self._databases.append(opened)
        return opened


def _validate_mode(
    mode: ProjectMode,
    writable_market: DatabaseName | None,
    maintenance_database: DatabaseSelector | None,
    maintenance_intent: MaintenanceIntent | None,
) -> None:
    if mode is ProjectMode.MARKET_WRITE:
        if (
            writable_market is None
            or maintenance_database is not None
            or maintenance_intent is not None
        ):
            raise ProjectConfigError("market_write requires only writable_market")
    elif mode is ProjectMode.MAINTENANCE:
        if (
            writable_market is not None
            or maintenance_database is None
            or maintenance_intent is None
        ):
            raise ProjectConfigError("maintenance requires a database and intent")
    elif any(
        value is not None for value in (writable_market, maintenance_database, maintenance_intent)
    ):
        raise ProjectConfigError("ordinary project modes reject target-specific arguments")


def _targets(
    config: ResolvedProjectConfig,
    mode: ProjectMode,
    writable_market: DatabaseName | None,
    maintenance_database: DatabaseSelector | None,
) -> list[tuple[str, Path, DatabaseRole | None, LeaseMode, bool]]:
    if mode in {ProjectMode.READ_ONLY, ProjectMode.RESEARCH_WRITE}:
        research_mode = LeaseMode.SHARED if mode is ProjectMode.READ_ONLY else LeaseMode.EXCLUSIVE
        result: list[tuple[str, Path, DatabaseRole | None, LeaseMode, bool]] = [
            (
                "research",
                config.research_path,
                DatabaseRole.RESEARCH,
                research_mode,
                mode is ProjectMode.READ_ONLY,
            )
        ]
        result.extend(
            (name.value, market.path, DatabaseRole.MARKET, LeaseMode.SHARED, True)
            for name, market in config.markets.items()
        )
        return result
    if mode is ProjectMode.MARKET_WRITE:
        assert writable_market is not None
        market = config.markets.get(writable_market)
        if market is None:
            raise ProjectConfigError("writable market is not configured")
        return [
            (
                writable_market.value,
                market.path,
                DatabaseRole.MARKET,
                LeaseMode.EXCLUSIVE,
                False,
            )
        ]
    assert maintenance_database is not None
    if isinstance(maintenance_database, ResearchDatabase):
        return [
            (
                "research",
                config.research_path,
                DatabaseRole.RESEARCH,
                LeaseMode.EXCLUSIVE,
                False,
            )
        ]
    if isinstance(maintenance_database, MarketDatabase):
        market = config.markets.get(maintenance_database.name)
        if market is None:
            raise ProjectConfigError("maintenance market is not configured")
        return [
            (
                maintenance_database.name.value,
                market.path,
                DatabaseRole.MARKET,
                LeaseMode.EXCLUSIVE,
                False,
            )
        ]
    assert isinstance(maintenance_database, PathDatabase)
    return [
        (
            "path",
            maintenance_database.path.resolve(),
            None,
            LeaseMode.EXCLUSIVE,
            False,
        )
    ]
