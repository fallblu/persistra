"""Tests for the trading-engine subprocess boundary."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from importlib import import_module
from typing import TYPE_CHECKING

import pytest

from persistra.integrations.trading_engine import (
    TradingEngineProcessError,
    run_scenario,
    scenario_from_json,
    write_scenario,
)

if TYPE_CHECKING:
    from pathlib import Path


def empty_scenario():
    """Return a valid zero-bar target-only scenario."""
    return scenario_from_json(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "empty-demo",
                "base_currency": "USD",
                "initial_cash": "10000",
                "instruments": [
                    {
                        "instrument_id": "asset-a",
                        "symbol": "AAA",
                        "quote_currency": "USD",
                        "tick_size": "0.01",
                        "lot_size": "1",
                    }
                ],
                "risk": {"max_order_quantity": "1000", "max_position": "1000"},
                "execution": {
                    "participation_bps": 5000,
                    "fixed_fee": "0",
                    "fee_bps": 0,
                },
                "max_internal_events": 1000,
                "schedule": [],
                "bars": [],
            }
        )
    )


def completion_journal() -> str:
    """Return the exact journal for the empty replay."""
    return (
        json.dumps(
            {
                "schema_version": 1,
                "engine_sequence": "1",
                "run_id": "empty-demo",
                "recorded_at": "1970-01-01T00:00:00.000000Z",
                "event_type": "run_completed",
                "payload": {
                    "valuation": {
                        "cash": "10000",
                        "market_value": "0",
                        "cost_basis": "0",
                        "realized_pnl": "0",
                        "unrealized_pnl": "0",
                        "equity": "10000",
                        "total_fees": "0",
                    },
                    "order_counts": {
                        "total": 0,
                        "active": 0,
                        "filled": 0,
                        "rejected": 0,
                        "cancelled": 0,
                    },
                },
            },
            separators=(",", ":"),
        )
        + "\n"
    )


def fake_engine(path: Path, *, fail_validation: bool = False) -> Path:
    """Write an executable that implements the CLI calls used by the adapter."""
    failure = "print('invalid fixture', file=sys.stderr); sys.exit(7)" if fail_validation else ""
    script = f"""#!/usr/bin/env python3
import pathlib
import sys

arguments = sys.argv[1:]
if '--validate-only' in arguments:
    {failure or "print('valid run=empty-demo schema=1 instruments=1 schedule=0 bars=0')"}
else:
    journal = pathlib.Path(arguments[arguments.index('--journal') + 1])
    journal.write_text({completion_journal()!r}, encoding='utf-8')
    print('run=empty-demo audits=1 orders=0 active=0 filled=0 rejected=0')
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_run_scenario_validates_replays_hashes_and_imports(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine executable")
    output = tmp_path / "output directory"

    result = run_scenario(
        empty_scenario(),
        executable=executable,
        output_directory=output,
        timeout=10,
    )

    assert result.executable == executable.resolve()
    assert result.scenario_path == output.resolve() / "empty-demo.scenario.json"
    assert result.journal_path == output.resolve() / "empty-demo.journal.jsonl"
    assert len(result.scenario_sha256) == 64
    assert len(result.journal_sha256) == 64
    assert result.validation_stdout.startswith("valid run=empty-demo")
    assert result.stdout.startswith("run=empty-demo")
    assert result.replay.completion.equity_micros == 10_000_000_000
    assert result.replay.valuations.empty


def test_run_scenario_accepts_a_path_and_explicit_journal(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine")
    scenario_path = write_scenario(empty_scenario(), tmp_path / "input.json")
    journal = tmp_path / "artifacts" / "audit.jsonl"

    result = run_scenario(
        scenario_path,
        executable=executable,
        journal_path=journal,
    )

    assert result.scenario_path == scenario_path.resolve()
    assert result.journal_path == journal.resolve()


def test_run_scenario_preserves_validation_failure_details(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "bad-engine", fail_validation=True)

    with pytest.raises(TradingEngineProcessError, match="exit code 7") as captured:
        run_scenario(
            empty_scenario(),
            executable=executable,
            output_directory=tmp_path / "failed-output",
        )

    assert captured.value.returncode == 7
    assert captured.value.stderr.strip() == "invalid fixture"
    assert captured.value.command[-1] == "--validate-only"


def test_run_scenario_rejects_unsafe_artifact_conditions(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        run_scenario(
            empty_scenario(),
            executable=tmp_path / "missing",
            output_directory=tmp_path,
        )

    executable = fake_engine(tmp_path / "engine")
    scenario_path = write_scenario(empty_scenario(), tmp_path / "scenario.json")
    journal = tmp_path / "existing.jsonl"
    journal.write_text("preserve me", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        run_scenario(
            scenario_path,
            executable=executable,
            journal_path=journal,
        )


def test_run_scenario_requires_a_positive_timeout_and_output_location(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine")
    with pytest.raises(ValueError, match="positive finite"):
        run_scenario(
            empty_scenario(),
            executable=executable,
            output_directory=tmp_path / "output",
            timeout=0,
        )
    with pytest.raises(ValueError, match="provide output_directory or journal_path"):
        run_scenario(empty_scenario(), executable=executable)


def test_run_scenario_rejects_same_artifact_and_nonexecutables(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine")
    scenario_path = write_scenario(empty_scenario(), tmp_path / "same.json")
    with pytest.raises(ValueError, match="paths must differ"):
        run_scenario(scenario_path, executable=executable, journal_path=scenario_path)

    not_executable = tmp_path / "plain-file"
    not_executable.write_text("plain", encoding="utf-8")
    with pytest.raises(ValueError, match="not an executable file"):
        run_scenario(
            empty_scenario(),
            executable=not_executable,
            output_directory=tmp_path / "output",
        )

    unsafe = replace(empty_scenario(), run_id="../escape")
    with pytest.raises(ValueError, match="path separators"):
        run_scenario(
            unsafe,
            executable=executable,
            output_directory=tmp_path / "safe-output",
        )
    assert not (tmp_path / "escape.scenario.json").exists()


def test_run_scenario_requires_the_successful_process_to_create_a_journal(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "no-journal"
    executable.write_text(
        "#!/usr/bin/env python3\nprint('successful but incomplete')\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    with pytest.raises(TradingEngineProcessError, match="without creating its journal"):
        run_scenario(
            empty_scenario(),
            executable=executable,
            output_directory=tmp_path / "missing-journal-output",
        )


def test_process_boundary_reports_timeouts_and_start_failures(tmp_path: Path) -> None:
    runner = import_module("persistra.integrations.trading_engine.runner")
    run_process = vars(runner)["_run_process"]
    with pytest.raises(TradingEngineProcessError, match="timed out") as captured:
        run_process(
            [sys.executable, "-c", "import time; print('started'); time.sleep(1)"],
            timeout=0.01,
            stage="test",
        )
    assert captured.value.returncode is None

    missing = tmp_path / "vanished"
    with pytest.raises(TradingEngineProcessError, match="could not start"):
        run_process([str(missing)], timeout=1, stage="test")

    with pytest.raises(TradingEngineProcessError, match="exit code 9: stdout detail"):
        run_process(
            [sys.executable, "-c", "print('stdout detail'); raise SystemExit(9)"],
            timeout=1,
            stage="test",
        )
