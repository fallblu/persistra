"""This module contains the strict TOML discovery, parsing, substitution, and path resolution."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from persistra.config.models import (
    MarketDatabaseConfig,
    ProjectConfig,
    ProjectOverrides,
    ResearchDatabaseConfig,
    ResolvedMarketDatabaseConfig,
    ResolvedProjectConfig,
)
from persistra.db import DatabaseName, ProjectId
from persistra.domain import QualifiedName
from persistra.errors import ProjectConfigError, ProjectConfigNotFoundError

_TOP_KEYS = frozenset({"project", "databases", "paths", "defaults", "resources", "logging"})
_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
_SIZE_PATTERN = re.compile(r"([0-9]+)(B|KiB|MiB|GiB|TiB)")
_SIZE_MULTIPLIER = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "TiB": 2**40}


def discover_config(path: str | Path = ".") -> Path:
    """Find the nearest resolved ``persistra.toml`` from an explicit path."""
    candidate = Path(path).expanduser().resolve()
    if candidate.is_file():
        if candidate.name != "persistra.toml":
            raise ProjectConfigNotFoundError("configuration file must be named persistra.toml")
        return candidate
    for directory in (candidate, *candidate.parents):
        config = directory / "persistra.toml"
        if config.is_file():
            return config.resolve()
    raise ProjectConfigNotFoundError("no persistra.toml found in the explicit path ancestry")


def parse_byte_size(value: object) -> int:
    """Parse an exact positive binary byte-size string."""
    if not isinstance(value, str) or (match := _SIZE_PATTERN.fullmatch(value)) is None:
        raise ProjectConfigError("byte size must use an integer binary unit")
    result = int(match.group(1)) * _SIZE_MULTIPLIER[match.group(2)]
    if result <= 0 or result >= 2**64:
        raise ProjectConfigError("byte size is outside the unsigned 64-bit range")
    return result


def _section(data: dict[str, Any], name: str, allowed: set[str]) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ProjectConfigError(f"[{name}] must be a TOML table")
    typed = cast("dict[str, Any]", value)
    unknown = set(typed) - allowed
    if unknown:
        raise ProjectConfigError(f"unknown keys in [{name}]: {sorted(unknown)!r}")
    return typed


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ProjectConfigError(f"{field_name} must be text")
    return value


def _path_text(value: Any, field_name: str, environ: dict[str, str]) -> str:
    text = _text(value, field_name)
    if text.startswith("~") or "$" in _ENV_PATTERN.sub("", text) or "%" in text:
        raise ProjectConfigError(f"{field_name} contains unsupported path expansion")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = environ.get(name)
        if not resolved:
            raise ProjectConfigError(f"{field_name} references a missing environment variable")
        return resolved

    expanded = _ENV_PATTERN.sub(replace, text)
    if _ENV_PATTERN.search(expanded):
        raise ProjectConfigError(f"{field_name} path substitution is not recursive")
    return expanded


def load_config(path: str | Path = ".", *, environ: dict[str, str] | None = None) -> ProjectConfig:
    """Parse one discovered configuration with the exact v3 schema."""
    config_path = discover_config(path)
    try:
        with config_path.open("rb") as file:
            raw = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ProjectConfigError("persistra.toml is not valid TOML") from error
    data = raw
    unknown_top = set(data) - _TOP_KEYS
    if unknown_top:
        raise ProjectConfigError(f"unknown configuration sections: {sorted(unknown_top)!r}")
    environment = dict(os.environ if environ is None else environ)
    project = _section(data, "project", {"id", "name", "state_dir"})
    if "id" not in project or "name" not in project:
        raise ProjectConfigError("project.id and project.name are required")
    name = _text(project["name"], "project.name")
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name) is None:
        raise ProjectConfigError("project.name is invalid")
    project_id = ProjectId.parse(_text(project["id"], "project.id"))
    state_dir = _path_text(project.get("state_dir", ".persistra"), "project.state_dir", environment)

    databases = _section(data, "databases", {"research", "markets"})
    research_raw = databases.get("research", {})
    if not isinstance(research_raw, dict):
        raise ProjectConfigError("[databases.research] must be a table")
    research = _section({"research": research_raw}, "research", {"path", "disposable"})
    research_path = _path_text(
        research.get("path", f"{state_dir}/research.duckdb"),
        "databases.research.path",
        environment,
    )
    disposable = research.get("disposable", False)
    if not isinstance(disposable, bool):
        raise ProjectConfigError("databases.research.disposable must be boolean")

    market_values = databases.get("markets", {})
    if not isinstance(market_values, dict):
        raise ProjectConfigError("databases.markets must contain at most 64 tables")
    typed_markets = cast("dict[str, Any]", market_values)
    if len(typed_markets) > 64:
        raise ProjectConfigError("databases.markets must contain at most 64 tables")
    markets: dict[DatabaseName, MarketDatabaseConfig] = {}
    for raw_name, raw_value in typed_markets.items():
        if not isinstance(raw_value, dict):
            raise ProjectConfigError("each market database must be a table")
        market = _section({"market": raw_value}, "market", {"path", "verify_copy_on_open"})
        if "path" not in market:
            raise ProjectConfigError("market database path is required")
        verify = market.get("verify_copy_on_open", False)
        if not isinstance(verify, bool):
            raise ProjectConfigError("verify_copy_on_open must be boolean")
        markets[DatabaseName(raw_name)] = MarketDatabaseConfig(
            _path_text(market["path"], f"databases.markets.{raw_name}.path", environment), verify
        )

    paths = _section(data, "paths", {"artifacts", "logs", "temporary"})
    defaults = _section(data, "defaults", {"calendar", "universe", "benchmark", "risk_free"})
    resources = _section(data, "resources", {"threads", "memory_limit", "temporary_limit"})
    logging = _section(data, "logging", {"level", "format"})
    threads = resources.get("threads")
    if threads is not None and (
        isinstance(threads, bool) or not isinstance(threads, int) or not 1 <= threads <= 1024
    ):
        raise ProjectConfigError("resources.threads must be in 1..1024")
    level = logging.get("level", "INFO")
    format_ = logging.get("format", "console")
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR"} or format_ not in {"console", "json"}:
        raise ProjectConfigError("logging configuration is invalid")

    return ProjectConfig(
        project_id=project_id,
        name=name,
        state_dir=state_dir,
        research=ResearchDatabaseConfig(research_path, disposable),
        markets=MappingProxyType(markets),
        artifacts=_path_text(
            paths.get("artifacts", f"{state_dir}/artifacts"),
            "paths.artifacts",
            environment,
        ),
        logs=_path_text(paths.get("logs", f"{state_dir}/logs"), "paths.logs", environment),
        temporary=_path_text(
            paths.get("temporary", f"{state_dir}/tmp"), "paths.temporary", environment
        ),
        calendar=_qualified(defaults.get("calendar"), "defaults.calendar"),
        universe=_qualified(defaults.get("universe"), "defaults.universe"),
        benchmark=_qualified(defaults.get("benchmark"), "defaults.benchmark"),
        risk_free=_qualified(defaults.get("risk_free"), "defaults.risk_free"),
        threads=threads,
        memory_limit=(
            None if "memory_limit" not in resources else parse_byte_size(resources["memory_limit"])
        ),
        temporary_limit=(
            None
            if "temporary_limit" not in resources
            else parse_byte_size(resources["temporary_limit"])
        ),
        logging_level=cast("str", level),
        logging_format=cast("str", format_),
    )


def _qualified(value: Any, field_name: str) -> QualifiedName | None:
    return None if value is None else QualifiedName(_text(value, field_name))


def resolve_config(
    path: str | Path = ".",
    *,
    overrides: ProjectOverrides | None = None,
    environ: dict[str, str] | None = None,
) -> ResolvedProjectConfig:
    """Resolve portable configuration into immutable absolute paths and byte counts."""
    config_path = discover_config(path)
    config = load_config(config_path, environ=environ)
    root = config_path.parent
    override = overrides or ProjectOverrides()

    def resolved(value: str | Path) -> Path:
        candidate = Path(value)
        return (candidate if candidate.is_absolute() else root / candidate).resolve()

    research_path = resolved(override.research_path or config.research.path)
    market_configs: dict[DatabaseName, ResolvedMarketDatabaseConfig] = {}
    for name, market in config.markets.items():
        market_configs[name] = ResolvedMarketDatabaseConfig(
            resolved(override.market_paths.get(name, market.path)), market.verify_copy_on_open
        )
    db_paths = [research_path, *(market.path for market in market_configs.values())]
    if any(path.suffix != ".duckdb" for path in db_paths) or len(set(db_paths)) != len(db_paths):
        raise ProjectConfigError("database paths must be distinct .duckdb files")
    memory = (
        config.memory_limit
        if override.memory_limit is None
        else parse_byte_size(override.memory_limit)
    )
    temporary_limit = (
        config.temporary_limit
        if override.temporary_limit is None
        else parse_byte_size(override.temporary_limit)
    )
    return ResolvedProjectConfig(
        project_id=config.project_id,
        name=config.name,
        root=root,
        config_path=config_path,
        state_dir=resolved(config.state_dir),
        research_path=research_path,
        research_disposable=config.research.disposable,
        markets=MappingProxyType(market_configs),
        artifacts=resolved(override.artifacts or config.artifacts),
        logs=resolved(override.logs or config.logs),
        temporary=resolved(override.temporary or config.temporary),
        calendar=override.calendar or config.calendar,
        universe=override.universe or config.universe,
        benchmark=override.benchmark or config.benchmark,
        risk_free=override.risk_free or config.risk_free,
        threads=override.threads if override.threads is not None else config.threads,
        memory_limit=memory,
        temporary_limit=temporary_limit,
        logging_level=override.logging_level or config.logging_level,
        logging_format=config.logging_format,
    )
