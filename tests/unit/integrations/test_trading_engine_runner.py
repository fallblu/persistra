"""Tests for the Trading Engine subprocess and run-bundle boundary."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from importlib import import_module
from typing import TYPE_CHECKING, Any

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
    """Return a valid zero-slice scenario."""
    return scenario_from_json(
        json.dumps(
            {
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
                "metadata": {"research": "empty"},
                "schedule": [],
                "slices": [],
            }
        )
    )


def fake_engine(path: Path, *, fail_validation: bool = False) -> Path:
    """Write an executable implementing the CLI calls used by the adapter."""
    failure = "print('invalid fixture', file=sys.stderr); sys.exit(7)" if fail_validation else ""
    script = f"""#!/usr/bin/env python3
import hashlib
import json
import pathlib
import sys

arguments = sys.argv[1:]
scenario = pathlib.Path(arguments[arguments.index('--input') + 1])
scenario_hash = hashlib.sha256(scenario.read_bytes()).hexdigest()
if '--validate-only' in arguments:
    {failure or "print('valid run=empty-demo instruments=1 schedule=0 slices=0')"}
else:
    valuation = {{
      'cash':'10000', 'market_value':'0', 'cost_basis':'0',
      'realized_pnl':'0', 'unrealized_pnl':'0', 'equity':'10000',
      'total_fees':'0',
    }}
    records = [
      {{'engine_sequence':'1','run_id':'empty-demo','recorded_at':'1970-01-01T00:00:00.000000Z','event_type':'run_started','payload':{{'scenario_sha256':scenario_hash}}}},
      {{'engine_sequence':'2','run_id':'empty-demo','recorded_at':'1970-01-01T00:00:00.000000Z','event_type':'run_completed','payload':{{'scenario_sha256':scenario_hash,'valuation':valuation,'order_counts':{{'total':0,'active':0,'filled':0,'rejected':0,'cancelled':0}}}}}},
    ]
    journal = pathlib.Path(arguments[arguments.index('--journal') + 1])
    encoded = ''.join(json.dumps(item,separators=(',',':'))+'\\n' for item in records)
    journal.write_text(encoded, encoding='utf-8')
    print('run=empty-demo audits=2 orders=0 active=0 filled=0 rejected=0')
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_run_scenario_validates_replays_hashes_imports_and_manifests(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine executable")
    output = tmp_path / "output directory"

    result = run_scenario(
        empty_scenario(), executable=executable, output_directory=output, timeout=10
    )

    assert result.executable == executable.resolve()
    assert result.scenario_path == output.resolve() / "empty-demo.scenario.json"
    assert result.journal_path == output.resolve() / "empty-demo.journal.jsonl"
    assert result.manifest_path == output.resolve() / "empty-demo.manifest.json"
    assert len(result.scenario_sha256) == len(result.journal_sha256) == 64
    assert len(result.executable_sha256) == 64
    assert result.replay.scenario_sha256 == result.scenario_sha256
    assert result.validation_stdout.startswith("valid run=empty-demo")
    assert result.replay.completion.equity_micros == 10_000_000_000
    assert result.replay.valuations.empty
    assert not (output / "empty-demo.journal.jsonl.partial").exists()
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["artifacts"]["scenario"] == {
        "path": "empty-demo.scenario.json",
        "sha256": result.scenario_sha256,
    }
    assert manifest["artifacts"]["journal"]["sha256"] == result.journal_sha256
    assert manifest["engine"]["sha256"] == result.executable_sha256
    assert manifest["scenario_metadata"] == {"research": "empty"}


def test_run_scenario_accepts_explicit_paths_and_records_relative_artifacts(
    tmp_path: Path,
) -> None:
    executable = fake_engine(tmp_path / "engine")
    scenario_path = write_scenario(empty_scenario(), tmp_path / "inputs" / "input.json")
    journal = tmp_path / "artifacts" / "audit.jsonl"
    manifest = tmp_path / "bundle" / "manifest.json"

    result = run_scenario(
        scenario_path,
        executable=executable,
        journal_path=journal,
        manifest_path=manifest,
    )
    payload = json.loads(result.manifest_path.read_text())
    assert payload["artifacts"]["scenario"]["path"] == "../inputs/input.json"
    assert payload["artifacts"]["journal"]["path"] == "../artifacts/audit.jsonl"


def test_run_scenario_preserves_validation_failure_details(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "bad-engine", fail_validation=True)
    with pytest.raises(TradingEngineProcessError, match="exit code 7") as captured:
        run_scenario(empty_scenario(), executable=executable, output_directory=tmp_path / "failed")
    assert captured.value.returncode == 7
    assert captured.value.stderr.strip() == "invalid fixture"
    assert captured.value.command[-1] == "--validate-only"


def test_run_scenario_preflights_all_artifacts_before_writing(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine")
    output = tmp_path / "output"
    output.mkdir()
    (output / "empty-demo.manifest.json").write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError, match="artifact path already exists"):
        run_scenario(empty_scenario(), executable=executable, output_directory=output)
    assert not (output / "empty-demo.scenario.json").exists()


def test_run_scenario_rejects_unsafe_locations_timeout_and_executable(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        run_scenario(empty_scenario(), executable=tmp_path / "missing", output_directory=tmp_path)
    executable = fake_engine(tmp_path / "engine")
    with pytest.raises(ValueError, match="positive finite"):
        run_scenario(
            empty_scenario(), executable=executable, output_directory=tmp_path / "o", timeout=0
        )
    with pytest.raises(ValueError, match="provide output_directory"):
        run_scenario(empty_scenario(), executable=executable)
    unsafe = replace(empty_scenario(), run_id="../escape")
    with pytest.raises(ValueError, match="path separators"):
        run_scenario(unsafe, executable=executable, output_directory=tmp_path / "safe")


def test_run_scenario_requires_the_process_to_create_a_journal(tmp_path: Path) -> None:
    executable = tmp_path / "no-journal"
    executable.write_text("#!/usr/bin/env python3\nprint('successful')\n", encoding="utf-8")
    executable.chmod(0o755)
    with pytest.raises(TradingEngineProcessError, match="without creating its journal"):
        run_scenario(empty_scenario(), executable=executable, output_directory=tmp_path / "out")


def test_process_boundary_reports_timeouts_and_start_failures(tmp_path: Path) -> None:
    runner = import_module("persistra.integrations.trading_engine.runner")
    run_process = vars(runner)["_run_process"]
    with pytest.raises(TradingEngineProcessError, match="timed out"):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(1)"],
            timeout=0.01,
            stage="test",
        )
    with pytest.raises(TradingEngineProcessError, match="could not start"):
        run_process([str(tmp_path / "vanished")], timeout=1, stage="test")
    with pytest.raises(TradingEngineProcessError, match="exit code 9: stdout detail"):
        run_process(
            [sys.executable, "-c", "print('stdout detail'); raise SystemExit(9)"],
            timeout=1,
            stage="test",
        )
    assert vars(runner)["_process_text"](b"byte output") == "byte output"
    assert vars(runner)["_process_text"]("text output") == "text output"


def test_finalize_journal_rejects_changed_bytes_and_existing_final(tmp_path: Path) -> None:
    runner = import_module("persistra.integrations.trading_engine.runner")
    finalize = vars(runner)["_finalize_journal"]
    partial = tmp_path / "journal.partial"
    final = tmp_path / "journal.jsonl"
    partial.write_bytes(b"complete journal\n")
    with pytest.raises(ValueError, match="changed before it was finalized"):
        finalize(partial, final, expected_sha256="0" * 64)
    assert not final.exists()

    digest = hashlib.sha256(partial.read_bytes()).hexdigest()
    final.write_text("preserve\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        finalize(partial, final, expected_sha256=digest)
    assert final.read_text(encoding="utf-8") == "preserve\n"
    assert partial.exists()
    assert not list(tmp_path.glob(".*.staging"))


def test_run_scenario_rejects_a_path_changed_after_its_bound_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = import_module("persistra.integrations.trading_engine.runner")
    scenario_path = write_scenario(empty_scenario(), tmp_path / "input.json")
    original = vars(runner)["_scenario_artifact"]

    def change_after_read(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        result[1].write_bytes(result[1].read_bytes() + b"\n")
        return result

    monkeypatch.setattr(runner, "_scenario_artifact", change_after_read)
    with pytest.raises(ValueError, match="changed before validation"):
        run_scenario(
            scenario_path,
            executable=fake_engine(tmp_path / "engine"),
            output_directory=tmp_path / "output",
        )


def test_run_scenario_requires_a_regular_scenario_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a regular file"):
        run_scenario(
            tmp_path,
            executable=fake_engine(tmp_path / "engine"),
            output_directory=tmp_path / "output",
        )


def test_run_scenario_does_not_publish_a_journal_changed_after_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = import_module("persistra.integrations.trading_engine.runner")
    original = vars(runner)["read_journal"]

    def change_after_read(path: Any, **kwargs: Any):
        replay = original(path, **kwargs)
        path.write_text("changed\n", encoding="utf-8")
        return replay

    monkeypatch.setattr(runner, "read_journal", change_after_read)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="changed during reconciliation"):
        run_scenario(
            empty_scenario(),
            executable=fake_engine(tmp_path / "engine"),
            output_directory=output,
        )
    assert not (output / "empty-demo.journal.jsonl").exists()
    assert not (output / "empty-demo.manifest.json").exists()
    assert not list(output.glob(".*.staging"))
