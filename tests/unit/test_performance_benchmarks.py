"""Tests for the controlled performance benchmark policy."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from scripts.benchmark_performance import (
    OPERATIONS,
    environment,
    evaluate_thresholds,
    load_thresholds,
)


def _result(operation: str, *, seconds: float = 1.0) -> dict[str, object]:
    return {
        "median_seconds": seconds,
        "operation": operation,
        "peak_rss_bytes": 100,
        "peak_traced_bytes": 50,
        "profile": "medium",
    }


def test_checked_in_thresholds_cover_only_stable_medium_cases() -> None:
    thresholds = load_thresholds(Path("performance-thresholds.toml"))

    assert set(thresholds) == set(OPERATIONS)
    assert {threshold["profile"] for threshold in thresholds.values()} == {"medium"}


def test_threshold_evaluation_rejects_regressions_and_missing_stable_cases() -> None:
    thresholds = {
        operation: {
            "profile": "medium",
            "max_seconds": 2.0,
            "max_peak_rss_bytes": 200,
            "max_peak_traced_bytes": 100,
        }
        for operation in OPERATIONS
    }
    results = [_result(operation) for operation in OPERATIONS]
    results[0]["median_seconds"] = 2.1
    results.pop()

    failures = evaluate_thresholds(results, thresholds)

    assert failures == [
        "duckdb_cumulative/medium median_seconds 2.1 exceeds 2.0",
        "missing stable case inspector_preparation/medium",
    ]


def test_environment_records_runtime_and_dependency_versions() -> None:
    observed = environment()

    assert observed["python_version"]
    assert observed["platform"]
    assert observed["machine"]
    dependencies = cast("dict[str, str]", observed["dependencies"])
    assert set(dependencies) == {"duckdb", "numpy", "pandas", "persistra", "scipy"}
