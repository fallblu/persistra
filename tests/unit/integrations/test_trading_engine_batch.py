"""Tests for deterministic bounded replay suites."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from persistra import _cli
from persistra.integrations.trading_engine import (
    ReplaySuite,
    ReplaySuiteEntry,
    ReplaySuiteError,
    ReplaySuiteResult,
    batch,
    read_replay_suite,
    run_replay_suite,
)

if TYPE_CHECKING:
    from persistra.integrations.trading_engine import (
        ReplayBundleVerification,
        ReplaySuiteFailurePolicy,
    )


def suite(root: Path, *run_ids: str) -> ReplaySuite:
    """Return an in-memory suite with placeholder scenario paths."""
    manifest = root / "suite.json"
    return ReplaySuite(
        manifest,
        tuple(ReplaySuiteEntry(run_id, root / f"{run_id}.json") for run_id in run_ids),
    )


def verification(run_id: str) -> ReplayBundleVerification:
    """Return the verification surface consumed by suite aggregation."""
    completion = SimpleNamespace(
        equity_micros=10_000,
        realized_pnl_micros=100,
        unrealized_pnl_micros=20,
        total_fees_micros=5,
        total_orders=3,
        filled_orders=2,
        rejected_orders=1,
        cancelled_orders=0,
    )
    return cast(
        "ReplayBundleVerification",
        SimpleNamespace(run_id=run_id, replay=SimpleNamespace(completion=completion)),
    )


def install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail: set[str] | None = None,
    delay: float = 0,
) -> tuple[list[str], list[int]]:
    """Install deterministic scenario, engine, and verifier fakes."""
    failures: set[str] = set() if fail is None else fail
    calls: list[str] = []
    concurrency = [0, 0]
    lock = threading.Lock()

    def read(path: Path) -> SimpleNamespace:
        run_id = path.parent.name if path.name == "scenario.json" else path.stem
        return SimpleNamespace(run_id=run_id)

    def run(
        scenario: SimpleNamespace,
        *,
        executable: str | Path,
        output_directory: Path,
        timeout: float,
    ) -> None:
        del executable, timeout
        with lock:
            calls.append(scenario.run_id)
            concurrency[0] += 1
            concurrency[1] = max(concurrency)
        try:
            if delay:
                time.sleep(delay)
            if scenario.run_id in failures:
                raise TimeoutError("fixture timeout")
            output_directory.mkdir(parents=True)
            (output_directory / f"{scenario.run_id}.manifest.json").write_text(
                "{}", encoding="utf-8"
            )
        finally:
            with lock:
                concurrency[0] -= 1

    def verify(path: str | Path) -> ReplayBundleVerification:
        directory = Path(path)
        result = verification(directory.name)
        return cast(
            "ReplayBundleVerification",
            SimpleNamespace(
                run_id=result.run_id,
                scenario_path=directory / "scenario.json",
                replay=result.replay,
            ),
        )

    monkeypatch.setattr(batch, "_read_suite_scenario", read)
    monkeypatch.setattr(batch, "run_scenario", run)
    monkeypatch.setattr(batch, "verify_replay_bundle", verify)
    return calls, concurrency


def test_suite_manifest_is_exact_ordered_and_path_safe(tmp_path: Path) -> None:
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "suite.json"
    manifest.write_text(
        json.dumps(
            {
                "suite_version": "1",
                "runs": [
                    {"id": "b", "scenario": "b.json"},
                    {"id": "a", "scenario": "a.json"},
                ],
            }
        ),
        encoding="utf-8",
    )

    parsed = read_replay_suite(manifest)

    assert [entry.run_id for entry in parsed.entries] == ["b", "a"]
    assert parsed.entries[0].scenario_path == (tmp_path / "b.json").resolve()

    manifest.write_text(
        json.dumps(
            {
                "suite_version": "1",
                "runs": [
                    {"id": "a", "scenario": "a.json"},
                    {"id": "a", "scenario": "b.json"},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReplaySuiteError, match="duplicate"):
        read_replay_suite(manifest)

    manifest.write_text(
        json.dumps({"suite_version": "1", "runs": [{"id": "a", "scenario": "../a.json"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ReplaySuiteError, match="unsafe"):
        read_replay_suite(manifest)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "must contain"),
        ({"suite_version": "2", "runs": []}, "unsupported"),
        ({"suite_version": "1", "runs": []}, "at least one"),
        ({"suite_version": "1", "runs": [None]}, "must be an object"),
        (
            {"suite_version": "1", "runs": [{"id": "bad/id", "scenario": "a.json"}]},
            "run id",
        ),
        (
            {
                "suite_version": "1",
                "runs": [{"id": "a", "scenario": "a.json", "extra": True}],
            },
            "unsupported fields",
        ),
        (
            {"suite_version": "1", "runs": [{"id": "a", "scenario": "missing.json"}]},
            "missing",
        ),
    ],
)
def test_suite_manifest_rejects_malformed_documents(
    tmp_path: Path, document: object, message: str
) -> None:
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "suite.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ReplaySuiteError, match=message):
        read_replay_suite(manifest)


def test_suite_manifest_normalizes_missing_and_invalid_json(tmp_path: Path) -> None:
    with pytest.raises(ReplaySuiteError, match="does not exist"):
        read_replay_suite(tmp_path / "missing.json")
    manifest = tmp_path / "suite.json"
    manifest.write_text("{", encoding="utf-8")
    with pytest.raises(ReplaySuiteError, match="not valid JSON"):
        read_replay_suite(manifest)


def test_suite_uses_bounded_parallelism_and_deterministic_result_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, concurrency = install_fakes(monkeypatch, delay=0.02)

    result = run_replay_suite(
        suite(tmp_path, "c", "a", "b"),
        executable="engine",
        output_directory=tmp_path / "output",
        workers=2,
    )

    assert set(calls) == {"a", "b", "c"}
    assert concurrency[1] == 2
    assert [run.run_id for run in result.runs] == ["c", "a", "b"]
    assert all(run.status == "succeeded" for run in result.runs)
    assert result.runs[0].metrics["equity_micros"] == 10_000
    assert result.to_dict()["status"] == "complete"


def test_suite_continues_or_fails_fast_after_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, _ = install_fakes(monkeypatch, fail={"bad"})
    continued = run_replay_suite(
        suite(tmp_path, "good", "bad", "later"),
        executable="engine",
        output_directory=tmp_path / "continue",
        workers=1,
        failure_policy="continue",
        timeout=1,
    )
    assert [run.status for run in continued.runs] == ["succeeded", "failed", "succeeded"]
    assert "TimeoutError" in cast("str", continued.runs[1].error)
    assert not continued.is_complete

    calls.clear()
    failed_fast = run_replay_suite(
        suite(tmp_path, "good", "bad", "later"),
        executable="engine",
        output_directory=tmp_path / "fail-fast",
        workers=1,
        failure_policy="fail_fast",
    )
    assert calls == ["good", "bad"]
    assert [run.status for run in failed_fast.runs] == ["succeeded", "failed", "skipped"]


def test_suite_resumes_only_verified_completed_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, _ = install_fakes(monkeypatch)
    output = tmp_path / "output"
    completed = output / "done"
    completed.mkdir(parents=True)
    (completed / "done.manifest.json").write_text("{}", encoding="utf-8")

    result = run_replay_suite(
        suite(tmp_path, "done", "new"),
        executable="engine",
        output_directory=output,
        workers=1,
        resume=True,
    )

    assert calls == ["new"]
    assert [run.status for run in result.runs] == ["resumed", "succeeded"]
    assert result.resumed == 1
    assert result.failed == result.skipped == 0


def test_suite_rejects_resume_when_declared_scenario_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch)
    output = tmp_path / "output" / "done"
    output.mkdir(parents=True)
    (output / "done.manifest.json").write_text("{}", encoding="utf-8")

    def read(path: Path) -> SimpleNamespace:
        return SimpleNamespace(run_id="done", source=path.name)

    monkeypatch.setattr(batch, "_read_suite_scenario", read)
    result = run_replay_suite(
        suite(tmp_path, "done"),
        executable="engine",
        output_directory=tmp_path / "output",
        resume=True,
    )

    assert result.runs[0].status == "failed"
    assert "differs" in cast("str", result.runs[0].error)


def test_suite_cli_routes_controls_and_renders_human_and_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install_fakes(monkeypatch)
    result = run_replay_suite(
        suite(tmp_path, "run"),
        executable="engine",
        output_directory=tmp_path / "actual",
    )
    calls: dict[str, object] = {}

    def invoke(manifest: str, **kwargs: object) -> ReplaySuiteResult:
        calls.update(manifest=manifest, **kwargs)
        return result

    monkeypatch.setattr(_cli, "run_replay_suite", invoke)
    arguments = [
        "trading-engine",
        "suite",
        "run",
        "suite.json",
        "--executable",
        "engine",
        "--output",
        "artifacts",
        "--workers",
        "3",
        "--failure-policy",
        "fail_fast",
        "--timeout",
        "12",
        "--resume",
    ]
    assert _cli.run(arguments) == 0
    assert "Replay suite complete: 1 run(s)" in capsys.readouterr().out
    assert calls == {
        "manifest": "suite.json",
        "executable": "engine",
        "output_directory": "artifacts",
        "workers": 3,
        "failure_policy": "fail_fast",
        "timeout": 12.0,
        "resume": True,
    }

    assert _cli.run([*arguments, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "complete"


def test_suite_rejects_invalid_execution_controls(tmp_path: Path) -> None:
    selected = suite(tmp_path, "run")
    with pytest.raises(ReplaySuiteError, match="workers"):
        run_replay_suite(
            selected,
            executable="engine",
            output_directory=tmp_path / "output",
            workers=0,
        )
    with pytest.raises(ReplaySuiteError, match="failure_policy"):
        run_replay_suite(
            selected,
            executable="engine",
            output_directory=tmp_path / "output",
            failure_policy=cast("ReplaySuiteFailurePolicy", "invalid"),
        )
    with pytest.raises(ReplaySuiteError, match="timeout"):
        run_replay_suite(
            selected,
            executable="engine",
            output_directory=tmp_path / "output",
            timeout=0,
        )
