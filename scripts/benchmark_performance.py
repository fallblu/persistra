"""Measure representative Persistra workloads and enforce controlled CI ceilings."""

from __future__ import annotations

import argparse
import gc
import importlib.metadata
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from persistra._inspection import provenance_table, result_summary, result_tables
from persistra.data import DuckDBStore, synthetic
from persistra.integrations.trading_engine._journal_parsing import iter_json_records
from persistra.portfolio import (
    MinimumVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    WeightBounds,
    optimize_portfolio,
)
from persistra.research import fit_time_series_factor_model

ROOT = Path(__file__).resolve().parents[1]
RESULT_FORMAT_VERSION = 1
OPERATIONS = (
    "duckdb_cumulative",
    "factor_regression",
    "portfolio_optimization",
    "journal_parsing",
    "inspector_preparation",
)


@dataclass(frozen=True, slots=True)
class Profile:
    """Deterministic dimensions for one benchmark scale."""

    store_rows: int
    regression_periods: int
    regression_assets: int
    optimization_assets: int
    journal_records: int
    inspector_rows: int


PROFILES = {
    "small": Profile(1_000, 125, 8, 8, 1_000, 1_000),
    "medium": Profile(10_000, 500, 32, 32, 10_000, 10_000),
    "large": Profile(50_000, 1_500, 96, 64, 100_000, 50_000),
    "smoke": Profile(12, 20, 3, 3, 12, 12),
}

type Workload = tuple[Callable[[], int], dict[str, int]]


def _duckdb_cumulative(profile: Profile, directory: Path) -> Workload:
    bars = synthetic.bars(periods=profile.store_rows)
    store_path = directory / "benchmark.duckdb"
    with DuckDBStore.create(store_path) as store:
        store.save(bars)
    instrument_id = bars.instrument.instrument_id

    def run() -> int:
        with DuckDBStore.open(store_path, read_only=True) as store:
            return len(store.query_bars(instrument_id))

    return run, {"rows": profile.store_rows}


def _factor_regression(profile: Profile, _directory: Path) -> Workload:
    generator = np.random.default_rng(140)
    factor_count = 4
    dates = pd.date_range("2010-01-01", periods=profile.regression_periods, freq="D")
    factors = generator.normal(0.0, 0.01, (profile.regression_periods, factor_count))
    loadings = generator.normal(0.0, 1.0, (factor_count, profile.regression_assets))
    noise = generator.normal(0.0, 0.002, (profile.regression_periods, profile.regression_assets))
    factor_frame = pd.DataFrame(
        factors,
        index=dates,
        columns=[f"factor_{position}" for position in range(factor_count)],
    )
    asset_frame = pd.DataFrame(
        factors @ loadings + noise,
        index=dates,
        columns=[f"asset_{position}" for position in range(profile.regression_assets)],
    )

    def run() -> int:
        result = fit_time_series_factor_model(asset_frame, factor_frame, covariance="hc3")
        return result.coefficients.size

    return run, {
        "assets": profile.regression_assets,
        "factors": factor_count,
        "periods": profile.regression_periods,
    }


def _portfolio_optimization(profile: Profile, _directory: Path) -> Workload:
    generator = np.random.default_rng(141)
    assets = pd.Index(
        [f"asset_{position}" for position in range(profile.optimization_assets)],
        name="asset",
    )
    drivers = generator.normal(0.0, 0.1, (profile.optimization_assets, 5))
    covariance = drivers @ drivers.T
    covariance += np.diag(np.linspace(0.05, 0.15, profile.optimization_assets))
    problem = PortfolioProblem(
        covariance=pd.DataFrame(covariance, index=assets, columns=assets),
        objective=MinimumVarianceObjective(),
        constraints=(WeightBounds(0.0, 1.0), NetExposureConstraint(1.0, 1.0)),
    )

    def run() -> int:
        return len(optimize_portfolio(problem).weights)

    return run, {"assets": profile.optimization_assets, "risk_drivers": 5}


def _journal_parsing(profile: Profile, directory: Path) -> Workload:
    journal_path = directory / "benchmark.jsonl"
    with journal_path.open("w", encoding="utf-8") as stream:
        for position in range(profile.journal_records):
            record = {
                "contract_version": "v1",
                "engine_sequence": position + 1,
                "event_type": "valuation",
                "payload": {"equity": 1_000_000 + position},
                "run_id": "benchmark-run",
            }
            stream.write(json.dumps(record, separators=(",", ":")))
            stream.write("\n")

    def run() -> int:
        return sum(1 for _line, _record in iter_json_records(journal_path))

    return run, {"bytes": journal_path.stat().st_size, "records": profile.journal_records}


def _inspector_preparation(profile: Profile, _directory: Path) -> Workload:
    bars = synthetic.bars(periods=profile.inspector_rows)

    def run() -> int:
        tables = result_tables(bars)
        summary = result_summary(bars)
        provenance = provenance_table(bars)
        return sum(len(table.frame) for table in tables) + len(summary) + len(provenance)

    return run, {"rows": profile.inspector_rows}


WORKLOADS: dict[str, Callable[[Profile, Path], Workload]] = {
    "duckdb_cumulative": _duckdb_cumulative,
    "factor_regression": _factor_regression,
    "portfolio_optimization": _portfolio_optimization,
    "journal_parsing": _journal_parsing,
    "inspector_preparation": _inspector_preparation,
}


def _peak_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    multiplier = 1 if sys.platform == "darwin" else 1_024
    return int(peak * multiplier)


def _measure(operation: str, profile_name: str, directory: Path) -> dict[str, object]:
    profile = PROFILES[profile_name]
    workload, dimensions = WORKLOADS[operation](profile, directory)
    samples: list[float] = []
    traced_peaks: list[int] = []
    result_count: int | None = None
    tracemalloc.start()
    try:
        for _ in range(3):
            gc.collect()
            tracemalloc.reset_peak()
            started = time.perf_counter()
            observed = workload()
            elapsed = time.perf_counter() - started
            _current, traced_peak = tracemalloc.get_traced_memory()
            if result_count is not None and observed != result_count:
                raise RuntimeError("benchmark result changed between repetitions")
            result_count = observed
            samples.append(elapsed)
            traced_peaks.append(traced_peak)
    finally:
        tracemalloc.stop()
    return {
        "dimensions": dimensions,
        "median_seconds": statistics.median(samples),
        "operation": operation,
        "peak_rss_bytes": _peak_rss_bytes(),
        "peak_traced_bytes": max(traced_peaks),
        "profile": profile_name,
        "result_count": result_count,
        "samples_seconds": samples,
    }


def _worker(operation: str, profile_name: str) -> None:
    with tempfile.TemporaryDirectory(prefix="persistra-benchmark-") as temporary:
        result = _measure(operation, profile_name, Path(temporary))
    print(json.dumps(result, sort_keys=True))


def environment() -> dict[str, object]:
    """Return reproducibility metadata for benchmark evidence."""
    dependencies: dict[str, str] = {}
    for distribution in ("duckdb", "numpy", "pandas", "persistra", "scipy"):
        dependencies[distribution] = importlib.metadata.version(distribution)
    return {
        "cpu_count": os.cpu_count(),
        "dependencies": dependencies,
        "executable": sys.executable,
        "git_sha": os.environ.get("GITHUB_SHA"),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }


def _run_case(operation: str, profile_name: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            operation,
            profile_name,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return cast("dict[str, object]", json.loads(completed.stdout))


def load_thresholds(path: Path) -> dict[str, dict[str, int | float | str]]:
    """Load the versioned stable-case ceilings."""
    with path.open("rb") as stream:
        document = cast("dict[str, object]", tomllib.load(stream))
    if document.get("version") != 1:
        raise ValueError("performance threshold version must be 1")
    raw_value = document.get("thresholds")
    if not isinstance(raw_value, dict):
        raise ValueError("performance thresholds must be a table")
    raw = cast("dict[str, object]", raw_value)
    if set(raw) != set(OPERATIONS):
        raise ValueError("performance thresholds must cover every benchmark operation")
    thresholds: dict[str, dict[str, int | float | str]] = {}
    for operation, value in raw.items():
        if not isinstance(value, dict):
            raise TypeError(f"threshold for {operation} must be a table")
        threshold = cast("dict[str, int | float | str]", value)
        if threshold.get("profile") not in {"small", "medium", "large"}:
            raise ValueError(f"threshold for {operation} has an unsupported profile")
        for field in ("max_seconds", "max_peak_rss_bytes", "max_peak_traced_bytes"):
            limit = threshold.get(field)
            if not isinstance(limit, (int, float)) or isinstance(limit, bool) or limit <= 0:
                raise ValueError(f"threshold for {operation} has an invalid {field}")
        thresholds[operation] = threshold
    return thresholds


def evaluate_thresholds(
    results: list[dict[str, object]],
    thresholds: dict[str, dict[str, int | float | str]],
) -> list[str]:
    """Return stable-case threshold violations without judging informational cases."""
    indexed = {(result["operation"], result["profile"]): result for result in results}
    failures: list[str] = []
    fields = (
        ("median_seconds", "max_seconds"),
        ("peak_rss_bytes", "max_peak_rss_bytes"),
        ("peak_traced_bytes", "max_peak_traced_bytes"),
    )
    for operation, threshold in thresholds.items():
        profile_name = threshold["profile"]
        result = indexed.get((operation, profile_name))
        if result is None:
            failures.append(f"missing stable case {operation}/{profile_name}")
            continue
        for result_field, threshold_field in fields:
            observed = cast("int | float", result[result_field])
            limit = cast("int | float", threshold[threshold_field])
            if observed > limit:
                failures.append(
                    f"{operation}/{profile_name} {result_field} {observed} exceeds {limit}"
                )
    return failures


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=("small", "medium", "large"),
        default=("small", "medium", "large"),
    )
    parser.add_argument("--operations", nargs="+", choices=OPERATIONS, default=OPERATIONS)
    parser.add_argument("--thresholds", type=Path, default=ROOT / "performance-thresholds.toml")
    parser.add_argument(
        "--worker",
        nargs=2,
        metavar=("OPERATION", "PROFILE"),
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> None:
    """Run isolated workloads and optionally enforce the controlled-CI ceilings."""
    arguments = _arguments()
    if arguments.worker is not None:
        operation, profile_name = arguments.worker
        if operation not in WORKLOADS or profile_name not in PROFILES:
            raise ValueError("unsupported benchmark worker case")
        _worker(operation, profile_name)
        return

    results: list[dict[str, object]] = []
    for operation in arguments.operations:
        for profile_name in arguments.profiles:
            print(f"benchmarking {operation}/{profile_name}", file=sys.stderr, flush=True)
            results.append(_run_case(operation, profile_name))
    thresholds = load_thresholds(arguments.thresholds)
    failures = evaluate_thresholds(results, thresholds) if arguments.enforce else []
    document: dict[str, Any] = {
        "environment": environment(),
        "format_version": RESULT_FORMAT_VERSION,
        "results": results,
        "threshold_policy": {
            "enforced": arguments.enforce,
            "failures": failures,
            "stable_cases": {
                operation: threshold["profile"] for operation, threshold in thresholds.items()
            },
        },
    }
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if failures:
        for failure in failures:
            print(f"performance threshold failed: {failure}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
