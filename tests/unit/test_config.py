from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from persistra.config import discover_config, load_config, parse_byte_size, resolve_config
from persistra.db import DatabaseName, ProjectId
from persistra.errors import ProjectConfigError, ProjectConfigNotFoundError

if TYPE_CHECKING:
    from pathlib import Path


def _config(project_id: ProjectId, market_path: str = "${MARKET_ROOT}/market.duckdb") -> str:
    return f'''[project]
id = "{project_id}"
name = "test-project"

[databases.research]
path = ".persistra/research.duckdb"
disposable = false

[databases.markets.primary]
path = "{market_path}"
verify_copy_on_open = false

[resources]
threads = 4
memory_limit = "8GiB"

[logging]
level = "INFO"
format = "json"
'''


def test_discovery_parse_and_resolution(tmp_path: Path) -> None:
    root = tmp_path / "project"
    child = root / "nested" / "child"
    child.mkdir(parents=True)
    config_path = root / "persistra.toml"
    config_path.write_text(_config(ProjectId.new()), encoding="utf-8")
    assert discover_config(child) == config_path
    parsed = load_config(child, environ={"MARKET_ROOT": str(tmp_path / "market")})
    assert parsed.name == "test-project"
    assert parsed.threads == 4
    assert parsed.memory_limit == 8 * 2**30
    assert DatabaseName("primary") in parsed.markets
    resolved = resolve_config(child, environ={"MARKET_ROOT": str(tmp_path / "market")})
    assert resolved.research_path == root / ".persistra" / "research.duckdb"
    assert next(iter(resolved.markets.values())).path == tmp_path / "market" / "market.duckdb"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1B", 1), ("2KiB", 2048), ("3MiB", 3 * 2**20), ("4GiB", 4 * 2**30)],
)
def test_byte_sizes(text: str, expected: int) -> None:
    assert parse_byte_size(text) == expected


@pytest.mark.parametrize("value", ["0B", "1KB", "1.5GiB", "-1B", 10])
def test_invalid_byte_sizes(value: object) -> None:
    with pytest.raises(ProjectConfigError):
        parse_byte_size(value)


def test_strict_schema_and_environment(tmp_path: Path) -> None:
    config = tmp_path / "persistra.toml"
    config.write_text(_config(ProjectId.new()), encoding="utf-8")
    with pytest.raises(ProjectConfigError):
        load_config(config, environ={})
    config.write_text(_config(ProjectId.new()) + "\n[secrets]\ntoken='x'\n", encoding="utf-8")
    with pytest.raises(ProjectConfigError):
        load_config(config, environ={"MARKET_ROOT": "/tmp"})


def test_not_found_and_database_name_boundaries(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigNotFoundError):
        discover_config(tmp_path)
    assert str(DatabaseName("market_1")) == "market_1"
    for value in ["research", "UPPER", "1market", "a" * 33]:
        with pytest.raises(ProjectConfigError):
            DatabaseName(value)
