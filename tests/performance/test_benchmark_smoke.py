from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from benchmarks.daily_equity_1000x10 import (
    BenchmarkShape,
    generate_fixture,
    run,
)
from benchmarks.validator import validate_fixture

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.performance
def test_daily_equity_benchmark_generator_runner_and_validator(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.duckdb"
    manifest = generate_fixture(
        fixture, BenchmarkShape(8, "2024-01-02", "2024-02-29")
    )
    validate_fixture(fixture, manifest["bar_count"])
    definition = tmp_path / "manifest.json"
    definition.write_text(
        json.dumps(
            {"schema": "persistra.benchmark.daily_equity_1000x10@1.manifest@1"}
        ),
        encoding="utf-8",
    )
    result = run(fixture, tmp_path / "output", definition)
    assert result["feature_rows"] == manifest["bar_count"]
    assert result["decision_rows"] == manifest["bar_count"]
