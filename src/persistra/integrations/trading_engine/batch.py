"""Deterministic bounded execution of declared Trading Engine replay suites."""

from __future__ import annotations

import json
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, cast

from persistra.integrations.trading_engine.bundle import (
    ReplayBundleComparison,
    ReplayBundleVerification,
    compare_replay_bundles,
    verify_replay_bundle,
)
from persistra.integrations.trading_engine.runner import run_scenario
from persistra.integrations.trading_engine.scenario import (
    read_scenario,
    read_scenario_stream,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from persistra.integrations.trading_engine.model import TradingEngineScenario

type ReplaySuiteFailurePolicy = Literal["continue", "fail_fast"]
type ReplaySuiteRunStatus = Literal["succeeded", "resumed", "failed", "skipped"]


class ReplaySuiteError(ValueError):
    """A replay suite manifest or execution request is invalid."""


@dataclass(frozen=True, slots=True)
class ReplaySuiteEntry:
    """One deterministic replay declaration in a suite."""

    run_id: str
    scenario_path: Path
    baseline_bundle: Path | None = None


@dataclass(frozen=True, slots=True)
class ReplaySuite:
    """One versioned ordered replay suite."""

    manifest_path: Path
    entries: tuple[ReplaySuiteEntry, ...]
    version: Literal["1"] = "1"


@dataclass(frozen=True, slots=True)
class ReplaySuiteRun:
    """Outcome, verification, metrics, and optional comparison for one suite entry."""

    run_id: str
    status: ReplaySuiteRunStatus
    output_directory: Path
    verification: ReplayBundleVerification | None = None
    comparison: ReplayBundleComparison | None = None
    metrics: Mapping[str, int | float] = field(default_factory=lambda: MappingProxyType({}))
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_directory", Path(self.output_directory))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    def to_dict(self) -> dict[str, object]:
        """Return a stable machine-readable run summary."""
        return {
            "run_id": self.run_id,
            "status": self.status,
            "output_directory": str(self.output_directory),
            "metrics": dict(self.metrics),
            "comparison": None if self.comparison is None else self.comparison.to_dict(),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ReplaySuiteResult:
    """Deterministically ordered aggregate suite result."""

    suite: ReplaySuite
    output_directory: Path
    runs: tuple[ReplaySuiteRun, ...]

    @property
    def succeeded(self) -> int:
        return sum(run.status == "succeeded" for run in self.runs)

    @property
    def resumed(self) -> int:
        return sum(run.status == "resumed" for run in self.runs)

    @property
    def failed(self) -> int:
        return sum(run.status == "failed" for run in self.runs)

    @property
    def skipped(self) -> int:
        return sum(run.status == "skipped" for run in self.runs)

    @property
    def is_complete(self) -> bool:
        return self.failed == 0 and self.skipped == 0

    def to_dict(self) -> dict[str, object]:
        """Return stable JSON-ready suite status and metrics."""
        return {
            "suite_version": self.suite.version,
            "suite_manifest": str(self.suite.manifest_path),
            "output_directory": str(self.output_directory),
            "status": "complete" if self.is_complete else "incomplete",
            "counts": {
                "total": len(self.runs),
                "succeeded": self.succeeded,
                "resumed": self.resumed,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "runs": [run.to_dict() for run in self.runs],
        }


def read_replay_suite(path: str | Path) -> ReplaySuite:
    """Read one exact version-1 suite manifest with contained input paths."""
    try:
        manifest = Path(path).expanduser().resolve(strict=True)
    except FileNotFoundError as error:
        raise ReplaySuiteError("replay suite manifest does not exist") from error
    if not manifest.is_file():
        raise ReplaySuiteError("replay suite manifest is not a regular file")
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReplaySuiteError("replay suite manifest is not valid JSON") from error
    if not isinstance(document, dict):
        raise ReplaySuiteError("replay suite manifest must contain suite_version and runs")
    document_item = cast("dict[str, object]", document)
    if set(document_item) != {"suite_version", "runs"}:
        raise ReplaySuiteError("replay suite manifest must contain suite_version and runs")
    if document_item["suite_version"] != "1" or not isinstance(document_item["runs"], list):
        raise ReplaySuiteError("unsupported replay suite manifest")
    entries: list[ReplaySuiteEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(cast("list[object]", document_item["runs"])):
        if not isinstance(raw, dict):
            raise ReplaySuiteError(f"suite run {index} must be an object")
        item = cast("dict[object, object]", raw)
        if set(item) not in ({"id", "scenario"}, {"id", "scenario", "baseline_bundle"}):
            raise ReplaySuiteError(f"suite run {index} has unsupported fields")
        run_id = _run_id(item.get("id"))
        if run_id in seen:
            raise ReplaySuiteError(f"duplicate suite run id: {run_id}")
        seen.add(run_id)
        scenario = _contained_path(manifest.parent, item.get("scenario"), name="scenario")
        baseline = (
            None
            if "baseline_bundle" not in item
            else _contained_path(
                manifest.parent,
                item["baseline_bundle"],
                name="baseline bundle",
            )
        )
        entries.append(ReplaySuiteEntry(run_id, scenario, baseline))
    if not entries:
        raise ReplaySuiteError("replay suite must contain at least one run")
    return ReplaySuite(manifest, tuple(entries))


def run_replay_suite(
    suite: ReplaySuite | str | Path,
    *,
    executable: str | Path,
    output_directory: str | Path,
    workers: int = 1,
    failure_policy: ReplaySuiteFailurePolicy = "continue",
    timeout: float = 300.0,
    resume: bool = False,
) -> ReplaySuiteResult:
    """Execute a suite with bounded parallelism and deterministic result ordering."""
    selected = read_replay_suite(suite) if isinstance(suite, str | Path) else suite
    workers_value = cast("object", workers)
    if isinstance(workers_value, bool) or not isinstance(workers_value, int) or workers_value <= 0:
        raise ReplaySuiteError("workers must be a positive integer")
    if failure_policy not in {"continue", "fail_fast"}:
        raise ReplaySuiteError("failure_policy must be continue or fail_fast")
    timeout_value = cast("object", timeout)
    if (
        isinstance(timeout_value, bool)
        or not isinstance(timeout_value, int | float)
        or timeout_value <= 0
    ):
        raise ReplaySuiteError("timeout must be positive")
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    outcomes: dict[str, ReplaySuiteRun] = {}
    pending_entries = iter(selected.entries)
    stopped = False

    def submit_next(
        executor: ThreadPoolExecutor,
        futures: dict[Future[ReplaySuiteRun], ReplaySuiteEntry],
    ) -> bool:
        try:
            entry = next(pending_entries)
        except StopIteration:
            return False
        future = executor.submit(
            _execute_suite_entry,
            entry,
            executable=executable,
            output_directory=output / entry.run_id,
            timeout=float(timeout),
            resume=resume,
        )
        futures[future] = entry
        return True

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="persistra-replay") as executor:
        futures: dict[Future[ReplaySuiteRun], ReplaySuiteEntry] = {}
        for _ in range(min(workers, len(selected.entries))):
            submit_next(executor, futures)
        while futures:
            completed, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in completed:
                entry = futures.pop(future)
                outcome = future.result()
                outcomes[entry.run_id] = outcome
                if outcome.status == "failed" and failure_policy == "fail_fast":
                    stopped = True
            while not stopped and len(futures) < workers and submit_next(executor, futures):
                pass

    if stopped:
        for entry in pending_entries:
            outcomes[entry.run_id] = ReplaySuiteRun(
                entry.run_id,
                "skipped",
                output / entry.run_id,
                error="not started after fail-fast failure",
            )
    ordered = tuple(outcomes[entry.run_id] for entry in selected.entries)
    return ReplaySuiteResult(selected, output, ordered)


def _execute_suite_entry(
    entry: ReplaySuiteEntry,
    *,
    executable: str | Path,
    output_directory: Path,
    timeout: float,
    resume: bool,
) -> ReplaySuiteRun:
    try:
        if output_directory.exists() and any(output_directory.iterdir()):
            if not resume:
                raise ReplaySuiteError("run output directory is not empty")
            verification = verify_replay_bundle(output_directory)
            expected_scenario = _read_suite_scenario(entry.scenario_path)
            bundled_scenario = _read_suite_scenario(verification.scenario_path)
            if expected_scenario.run_id != entry.run_id:
                raise ReplaySuiteError("suite run id must match scenario run_id")
            if verification.run_id != entry.run_id or bundled_scenario != expected_scenario:
                raise ReplaySuiteError("resumed bundle scenario differs from suite scenario")
            return _successful_run(entry, output_directory, verification, status="resumed")
        scenario = _read_suite_scenario(entry.scenario_path)
        if scenario.run_id != entry.run_id:
            raise ReplaySuiteError("suite run id must match scenario run_id")
        run_scenario(
            scenario,
            executable=executable,
            output_directory=output_directory,
            timeout=timeout,
        )
        verification = verify_replay_bundle(output_directory)
        return _successful_run(entry, output_directory, verification, status="succeeded")
    except Exception as error:
        return ReplaySuiteRun(
            entry.run_id,
            "failed",
            output_directory,
            error=f"{type(error).__name__}: {error}",
        )


def _successful_run(
    entry: ReplaySuiteEntry,
    output_directory: Path,
    verification: ReplayBundleVerification,
    *,
    status: Literal["succeeded", "resumed"],
) -> ReplaySuiteRun:
    completion = verification.replay.completion
    comparison = (
        None
        if entry.baseline_bundle is None
        else compare_replay_bundles(entry.baseline_bundle, verification)
    )
    metrics: Mapping[str, int | float] = {
        "equity_micros": completion.equity_micros,
        "realized_pnl_micros": completion.realized_pnl_micros,
        "unrealized_pnl_micros": completion.unrealized_pnl_micros,
        "total_fees_micros": completion.total_fees_micros,
        "total_orders": completion.total_orders,
        "filled_orders": completion.filled_orders,
        "rejected_orders": completion.rejected_orders,
        "cancelled_orders": completion.cancelled_orders,
    }
    return ReplaySuiteRun(
        entry.run_id,
        status,
        output_directory,
        verification=verification,
        comparison=comparison,
        metrics=metrics,
    )


def _read_suite_scenario(path: Path) -> TradingEngineScenario:
    return read_scenario_stream(path) if path.suffix == ".jsonl" else read_scenario(path)


def _run_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in value
        )
    ):
        raise ReplaySuiteError("suite run id must use letters, digits, hyphens, or underscores")
    return value


def _contained_path(root: Path, value: object, *, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ReplaySuiteError(f"{name} path must be a nonempty string")
    supplied = Path(value)
    if supplied.is_absolute() or ".." in supplied.parts:
        raise ReplaySuiteError(f"{name} path is unsafe")
    try:
        resolved = (root / supplied).resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (FileNotFoundError, ValueError) as error:
        raise ReplaySuiteError(f"{name} path is missing or escapes the suite") from error
    return resolved
