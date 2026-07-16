"""Strict immutable project configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from persistra.db import DatabaseName, ProjectId
    from persistra.domain import QualifiedName


@dataclass(frozen=True, slots=True)
class ResearchDatabaseConfig:
    path: str
    disposable: bool = False


@dataclass(frozen=True, slots=True)
class MarketDatabaseConfig:
    path: str
    verify_copy_on_open: bool = False


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    project_id: ProjectId
    name: str
    state_dir: str = ".persistra"
    research: ResearchDatabaseConfig = field(
        default_factory=lambda: ResearchDatabaseConfig(".persistra/research.duckdb")
    )
    markets: Mapping[DatabaseName, MarketDatabaseConfig] = field(
        default_factory=lambda: MappingProxyType({})
    )
    artifacts: str = ".persistra/artifacts"
    logs: str = ".persistra/logs"
    temporary: str = ".persistra/tmp"
    calendar: QualifiedName | None = None
    universe: QualifiedName | None = None
    benchmark: QualifiedName | None = None
    risk_free: QualifiedName | None = None
    threads: int | None = None
    memory_limit: int | None = None
    temporary_limit: int | None = None
    logging_level: str = "INFO"
    logging_format: str = "console"


@dataclass(frozen=True, slots=True)
class ResolvedMarketDatabaseConfig:
    path: Path
    verify_copy_on_open: bool


@dataclass(frozen=True, slots=True)
class ResolvedProjectConfig:
    project_id: ProjectId
    name: str
    root: Path
    config_path: Path
    state_dir: Path
    research_path: Path
    research_disposable: bool
    markets: Mapping[DatabaseName, ResolvedMarketDatabaseConfig]
    artifacts: Path
    logs: Path
    temporary: Path
    calendar: QualifiedName | None
    universe: QualifiedName | None
    benchmark: QualifiedName | None
    risk_free: QualifiedName | None
    threads: int | None
    memory_limit: int | None
    temporary_limit: int | None
    logging_level: str
    logging_format: str


@dataclass(frozen=True, slots=True)
class ProjectOverrides:
    threads: int | None = None
    memory_limit: str | None = None
    temporary_limit: str | None = None
    logging_level: str | None = None
    calendar: QualifiedName | None = None
    universe: QualifiedName | None = None
    benchmark: QualifiedName | None = None
    risk_free: QualifiedName | None = None
    research_path: Path | None = None
    market_paths: Mapping[DatabaseName, Path] = field(default_factory=lambda: MappingProxyType({}))
    artifacts: Path | None = None
    logs: Path | None = None
    temporary: Path | None = None
