"""Tests for the Trading Engine subprocess and run-bundle boundary."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from persistra.integrations.trading_engine import (
    StrategyProcess,
    TradingEngineProcessError,
    run_scenario,
    scenario_from_json,
    scenario_to_json,
    write_scenario,
    write_scenario_stream,
)


def empty_scenario():
    """Return a valid zero-slice scenario."""
    return scenario_from_json(
        json.dumps(
            {
                "contract_version": "3",
                "run_id": "empty-demo",
                "base_currency": "USD",
                "initial_cash": [{"currency": "USD", "amount": "10000"}],
                "instruments": [
                    {
                        "instrument_id": "asset-a",
                        "symbol": "AAA",
                        "quote_currency": "USD",
                        "tick_size": "0.01",
                        "lot_size": "1",
                    }
                ],
                "risk": {
                    "max_order_quantity": "1000",
                    "max_long_position": "1000",
                    "max_short_position": "1000",
                    "max_gross_exposure": "1000000",
                    "max_leverage": "2",
                    "initial_margin_bps": 5000,
                    "maintenance_margin_bps": 2500,
                    "short_borrow_bps": 0,
                },
                "execution": {
                    "model": "completed_bar_v1",
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
if '--capabilities' in arguments:
    print(json.dumps({{
      'engine_version':'test-engine-1',
      'scenario_contract_versions':['3'],
      'journal_contract_versions':['3'],
      'scenario_formats':['json','jsonl'],
      'journal_formats':['jsonl'],
      'execution_models':['completed_bar_v1'],
      'strategy_protocol_versions':['2'],
    }}, separators=(',',':')))
    sys.exit(0)
scenario = pathlib.Path(arguments[arguments.index('--input') + 1])
scenario_hash = hashlib.sha256(scenario.read_bytes()).hexdigest()
if '--validate-only' in arguments:
    {failure or "print('valid run=empty-demo instruments=1 schedule=0 slices=0')"}
else:
    valuation = {{
      'base_currency':'USD', 'cash':'10000', 'net_market_value':'0',
      'long_market_value':'0', 'short_market_value':'0', 'gross_exposure':'0',
      'cost_basis':'0', 'realized_pnl':'0', 'unrealized_pnl':'0', 'equity':'10000',
      'dividend_pnl':'0', 'execution_fees':'0', 'borrow_fees':'0', 'total_fees':'0',
      'cash_balances':[{{'currency':'USD','amount':'10000','fx_rate':'1','base_value':'10000'}}],
      'positions':[],
      'margin':{{'initial_requirement':'0','maintenance_requirement':'0','initial_excess':'10000','maintenance_excess':'10000','margin_call':False}},
    }}
    records = [
      {{'contract_version':'3','engine_sequence':'1','event_id':'empty-demo-event-000000000001','causation_ids':[],'run_id':'empty-demo','recorded_at':'1970-01-01T00:00:00.000000Z','event_type':'run_started','payload':{{'scenario_sha256':scenario_hash,'execution_model':'completed_bar_v1'}}}},
      {{'contract_version':'3','engine_sequence':'2','event_id':'empty-demo-event-000000000002','causation_ids':['empty-demo-event-000000000001'],'run_id':'empty-demo','recorded_at':'1970-01-01T00:00:00.000000Z','event_type':'run_completed','payload':{{'scenario_sha256':scenario_hash,'execution_model':'completed_bar_v1','valuation':valuation,'order_counts':{{'total':0,'active':0,'filled':0,'rejected':0,'cancelled':0}}}}}},
    ]
    journal = pathlib.Path(arguments[arguments.index('--journal') + 1])
    encoded = ''.join(json.dumps(item,separators=(',',':'))+'\\n' for item in records)
    journal.write_text(encoded, encoding='utf-8')
    print('run=empty-demo audits=2 orders=0 active=0 filled=0 rejected=0')
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def fake_external_engine(path: Path) -> Path:
    """Write an engine fixture that supervises a real protocol strategy host."""
    script = """#!/usr/bin/env python3
import hashlib
import json
import pathlib
import subprocess
import sys

arguments = sys.argv[1:]
if '--capabilities' in arguments:
    print(json.dumps({
      'engine_version':'test-engine-1',
      'scenario_contract_versions':['3'],
      'journal_contract_versions':['3'],
      'scenario_formats':['json','jsonl'],
      'journal_formats':['jsonl'],
      'execution_models':['completed_bar_v1'],
      'strategy_protocol_versions':['2'],
    }, separators=(',',':')))
    sys.exit(0)

scenario = pathlib.Path(arguments[arguments.index('--input') + 1])
scenario_hash = hashlib.sha256(scenario.read_bytes()).hexdigest()
if '--validate-only' in arguments:
    print('valid run=empty-demo instruments=1 schedule=0 slices=0')
    sys.exit(0)

strategy_command = [arguments[arguments.index('--strategy-executable') + 1]]
for index, argument in enumerate(arguments):
    if argument == '--strategy-arg':
        strategy_command.append(arguments[index + 1])
    elif argument.startswith('--strategy-arg='):
        strategy_command.append(argument.split('=', 1)[1])
process = subprocess.Popen(
    strategy_command,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
assert process.stdin is not None
assert process.stdout is not None
assert process.stderr is not None
transcript = pathlib.Path(arguments[arguments.index('--strategy-transcript') + 1])
records = []

def exchange(sequence, message_type, payload):
    message = {
      'strategy_protocol_version':'2',
      'strategy_sequence':str(sequence),
      'message_type':message_type,
      'payload':payload,
    }
    records.append({
      'strategy_protocol_version':'2',
      'transcript_sequence':str(len(records) + 1),
      'direction':'engine_to_strategy',
      'message':message,
    })
    transcript.write_text(
        ''.join(json.dumps(item,separators=(',',':')) + '\\n' for item in records),
        encoding='utf-8',
    )
    process.stdin.write(json.dumps(message, separators=(',',':')) + '\\n')
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError('strategy closed stdout: ' + process.stderr.read())
    response = json.loads(line)
    records.append({
      'strategy_protocol_version':'2',
      'transcript_sequence':str(len(records) + 1),
      'direction':'strategy_to_engine',
      'message':response,
    })
    transcript.write_text(
        ''.join(json.dumps(item,separators=(',',':')) + '\\n' for item in records),
        encoding='utf-8',
    )
    if response['strategy_sequence'] != str(sequence):
        raise RuntimeError('strategy sequence mismatch')
    if response['message_type'] == 'error':
        raise RuntimeError(response['payload']['message'])
    return response

if scenario.suffix == '.jsonl':
    scenario_payload = json.loads(scenario.read_text(encoding='utf-8').splitlines()[0])['payload']
else:
    scenario_payload = json.loads(scenario.read_text(encoding='utf-8'))
initialization = {
  'engine_version':'test-engine-1',
  'scenario_contract_version':'3',
  'scenario_sha256':scenario_hash,
  'run_id':scenario_payload['run_id'],
  'base_currency':scenario_payload['base_currency'],
  'initial_cash':scenario_payload['initial_cash'],
  'instruments':scenario_payload['instruments'],
  'risk':scenario_payload['risk'],
  'execution':scenario_payload['execution'],
  'metadata':scenario_payload['metadata'],
}
try:
    ready = exchange(1, 'initialize', initialization)
    if ready['message_type'] != 'ready':
        raise RuntimeError('strategy did not become ready')
    stopped = exchange(2, 'shutdown', {})
    if stopped['message_type'] != 'stopped':
        raise RuntimeError('strategy did not stop')
    process.stdin.close()
    returncode = process.wait(timeout=5)
    if returncode != 0:
        raise RuntimeError(f'strategy exited with code {returncode}: {process.stderr.read()}')
except Exception as error:
    process.kill()
    process.wait()
    print(str(error), file=sys.stderr)
    sys.exit(9)

valuation = {
  'base_currency':'USD', 'cash':'10000', 'net_market_value':'0',
  'long_market_value':'0', 'short_market_value':'0', 'gross_exposure':'0',
  'cost_basis':'0', 'realized_pnl':'0', 'unrealized_pnl':'0', 'equity':'10000',
  'dividend_pnl':'0', 'execution_fees':'0', 'borrow_fees':'0', 'total_fees':'0',
  'cash_balances':[{'currency':'USD','amount':'10000','fx_rate':'1','base_value':'10000'}],
  'positions':[],
  'margin':{'initial_requirement':'0','maintenance_requirement':'0','initial_excess':'10000','maintenance_excess':'10000','margin_call':False},
}
journal_records = [
  {'contract_version':'3','engine_sequence':'1','event_id':'empty-demo-event-000000000001','causation_ids':[],'run_id':'empty-demo','recorded_at':'1970-01-01T00:00:00.000000Z','event_type':'run_started','payload':{'scenario_sha256':scenario_hash,'execution_model':'completed_bar_v1'}},
  {'contract_version':'3','engine_sequence':'2','event_id':'empty-demo-event-000000000002','causation_ids':['empty-demo-event-000000000001'],'run_id':'empty-demo','recorded_at':'1970-01-01T00:00:00.000000Z','event_type':'run_completed','payload':{'scenario_sha256':scenario_hash,'execution_model':'completed_bar_v1','valuation':valuation,'order_counts':{'total':0,'active':0,'filled':0,'rejected':0,'cancelled':0}}},
]
journal = pathlib.Path(arguments[arguments.index('--journal') + 1])
journal.write_text(
    ''.join(json.dumps(item,separators=(',',':')) + '\\n' for item in journal_records),
    encoding='utf-8',
)
print('run=empty-demo audits=2 orders=0 active=0 filled=0 rejected=0 strategy=unit-host')
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def hosted_strategy(path: Path, *, fail: bool = False) -> Path:
    """Write a strategy process using Persistra's public host."""
    failure = "raise RuntimeError('fixture failure')" if fail else "self.value = config.read_text()"
    source_root = Path(__file__).resolve().parents[3] / "src"
    script = f"""from pathlib import Path
import sys
sys.path.insert(0, {str(source_root)!r})
from persistra.integrations.trading_engine import serve_strategy

class Strategy:
    name = 'unit-host'
    version = '1'
    def initialize(self, initialization):
        assert sys.argv[1] == '--configuration'
        config = Path(sys.argv[2])
        {failure}
    def on_event(self, context, event):
        return ()
    def shutdown(self):
        pass

serve_strategy(Strategy())
"""
    path.write_text(script, encoding="utf-8")
    return path


def test_run_scenario_validates_replays_hashes_imports_and_manifests(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine executable")
    output = tmp_path / "output directory"

    result = run_scenario(
        empty_scenario(), executable=executable, output_directory=output, timeout=10
    )

    assert result.executable == executable.resolve()
    assert result.scenario_path == output.resolve() / "empty-demo.scenario.jsonl"
    assert result.journal_path == output.resolve() / "empty-demo.journal.jsonl"
    assert result.manifest_path == output.resolve() / "empty-demo.manifest.json"
    assert len(result.scenario_sha256) == len(result.journal_sha256) == 64
    assert len(result.executable_sha256) == 64
    assert result.capabilities.engine_version == "test-engine-1"
    assert result.replay.scenario_sha256 == result.scenario_sha256
    assert result.validation_stdout.startswith("valid run=empty-demo")
    assert result.replay.completion.equity_micros == 10_000_000_000
    assert result.replay.valuations.empty
    assert result.strategy is None
    assert not (output / "empty-demo.journal.jsonl.partial").exists()
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["artifacts"]["scenario"] == {
        "path": "empty-demo.scenario.jsonl",
        "sha256": result.scenario_sha256,
        "format": "jsonl",
    }
    assert manifest["artifacts"]["journal"]["sha256"] == result.journal_sha256
    assert manifest["contract"] == {"version": "3"}
    assert manifest["execution"] == {"model": "completed_bar_v1"}
    assert manifest["persistra"]["version"] == "4.1.1"
    assert set(manifest["persistra"]["vcs"]) == {"revision", "dirty"}
    assert manifest["engine"] == {
        "version": "test-engine-1",
        "capabilities": {
            "engine_version": "test-engine-1",
            "scenario_contract_versions": ["3"],
            "journal_contract_versions": ["3"],
            "scenario_formats": ["json", "jsonl"],
            "journal_formats": ["jsonl"],
            "execution_models": ["completed_bar_v1"],
            "strategy_protocol_versions": ["2"],
        },
        "executable": {
            "name": executable.name,
            "sha256": result.executable_sha256,
        },
        "vcs": {"revision": None, "dirty": None},
    }
    assert manifest["scenario_metadata"] == {"research": "empty"}


def test_run_scenario_hosts_external_strategy_and_binds_its_artifacts(tmp_path: Path) -> None:
    executable = fake_external_engine(tmp_path / "external-engine")
    strategy_script = hosted_strategy(tmp_path / "strategy.py")
    configuration = tmp_path / "strategy.toml"
    configuration.write_text("threshold = 2\n", encoding="utf-8")
    output = tmp_path / "external-output"

    result = run_scenario(
        empty_scenario(),
        executable=executable,
        output_directory=output,
        strategy=StrategyProcess(
            command=(
                sys.executable,
                strategy_script,
                "--configuration",
                configuration,
            ),
            artifacts=(strategy_script, configuration),
            response_timeout=2,
        ),
    )

    assert result.strategy is not None
    assert result.strategy.identity.name == "unit-host"
    assert result.strategy.identity.version == "1"
    assert result.strategy.executable == Path(sys.executable).absolute()
    assert result.strategy.transcript_path == output.resolve() / "empty-demo.strategy.jsonl"
    assert result.strategy.transcript_path.is_file()
    assert result.strategy.event_count == 0
    assert len(result.strategy.transcript_sha256) == 64
    assert [item.path for item in result.strategy.artifacts] == [
        strategy_script.resolve(),
        configuration.resolve(),
    ]
    assert not (output / "empty-demo.strategy.jsonl.partial").exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["strategy_transcript"] == {
        "path": "empty-demo.strategy.jsonl",
        "sha256": result.strategy.transcript_sha256,
        "format": "jsonl",
    }
    assert manifest["strategy"]["protocol_version"] == "2"
    assert manifest["strategy"]["identity"] == {"name": "unit-host", "version": "1"}
    assert manifest["strategy"]["response_timeout_seconds"] == 2.0
    assert [Path(item["path"]).name for item in manifest["strategy"]["artifacts"]] == [
        strategy_script.name,
        configuration.name,
    ]


def test_run_scenario_preserves_external_strategy_failure_diagnostics(tmp_path: Path) -> None:
    executable = fake_external_engine(tmp_path / "external-engine")
    strategy_script = hosted_strategy(tmp_path / "broken-strategy.py", fail=True)
    configuration = tmp_path / "strategy.toml"
    configuration.write_text("threshold = 2\n", encoding="utf-8")
    output = tmp_path / "failed-external"

    with pytest.raises(TradingEngineProcessError, match="exit code 9") as captured:
        run_scenario(
            empty_scenario(),
            executable=executable,
            output_directory=output,
            strategy=StrategyProcess(
                command=(
                    sys.executable,
                    strategy_script,
                    "--configuration",
                    configuration,
                ),
                artifacts=(strategy_script, configuration),
            ),
        )

    diagnostic = captured.value.strategy_transcript_path
    assert diagnostic == (output / "empty-demo.strategy.jsonl.partial").resolve()
    assert diagnostic is not None
    assert diagnostic.is_file()
    assert not (output / "empty-demo.strategy.jsonl").exists()
    assert not (output / "empty-demo.journal.jsonl").exists()
    assert not (output / "empty-demo.manifest.json").exists()


def test_run_scenario_preflights_external_strategy_requirements(tmp_path: Path) -> None:
    executable = fake_external_engine(tmp_path / "external-engine")
    strategy_script = hosted_strategy(tmp_path / "strategy.py")
    process = StrategyProcess(command=(sys.executable, strategy_script))

    with pytest.raises(ValueError, match="strategy_transcript_path requires"):
        run_scenario(
            empty_scenario(),
            executable=executable,
            output_directory=tmp_path / "no-strategy",
            strategy_transcript_path=tmp_path / "unexpected.jsonl",
        )
    scheduled_document = json.loads(scenario_to_json(empty_scenario()))
    scheduled_document["slices"] = [
        {
            "slice_sequence": "1",
            "start_at": "2026-01-02T14:30:00Z",
            "end_at": "2026-01-02T14:35:00Z",
            "available_at": "2026-01-02T14:35:01Z",
            "received_at": "2026-01-02T14:35:02Z",
            "bars": [
                {
                    "instrument_id": "asset-a",
                    "open": "99",
                    "high": "102",
                    "low": "98",
                    "close": "101",
                    "volume": "100",
                }
            ],
            "fx_rates": [{"currency": "USD", "rate": "1"}],
            "corporate_actions": [],
        }
    ]
    scheduled_document["schedule"] = [
        {
            "after_slice_sequence": "1",
            "intents": [{"type": "emit_metric", "name": "signal", "value": "1"}],
        }
    ]
    scheduled = scenario_from_json(json.dumps(scheduled_document))
    with pytest.raises(ValueError, match="requires an empty scenario schedule"):
        run_scenario(
            scheduled,
            executable=executable,
            output_directory=tmp_path / "scheduled",
            strategy=process,
        )
    unsupported = fake_external_engine(tmp_path / "unsupported-engine")
    unsupported.write_text(
        unsupported.read_text(encoding="utf-8").replace(
            "'strategy_protocol_versions':['2']",
            "'strategy_protocol_versions':['1']",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing strategy protocol version '2'"):
        run_scenario(
            empty_scenario(),
            executable=unsupported,
            output_directory=tmp_path / "unsupported",
            strategy=process,
        )


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
    assert payload["artifacts"]["scenario"]["format"] == "json"
    assert payload["artifacts"]["journal"]["path"] == "../artifacts/audit.jsonl"


def test_run_scenario_accepts_an_existing_stream_artifact(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine")
    scenario_path = write_scenario_stream(empty_scenario(), tmp_path / "input.jsonl")

    result = run_scenario(
        scenario_path,
        executable=executable,
        output_directory=tmp_path / "output",
    )

    payload = json.loads(result.manifest_path.read_text())
    assert result.scenario_path == scenario_path.resolve()
    assert payload["artifacts"]["scenario"]["format"] == "jsonl"


def test_run_scenario_preserves_validation_failure_details(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "bad-engine", fail_validation=True)
    with pytest.raises(TradingEngineProcessError, match="exit code 7") as captured:
        run_scenario(empty_scenario(), executable=executable, output_directory=tmp_path / "failed")
    assert captured.value.returncode == 7
    assert captured.value.stderr.strip() == "invalid fixture"
    assert captured.value.command[-3:] == ("--input-format", "jsonl", "--validate-only")
    assert captured.value.command[-1] == "--validate-only"


def test_run_scenario_rejects_incompatible_engine_before_writing_artifacts(
    tmp_path: Path,
) -> None:
    executable = fake_engine(tmp_path / "incompatible-engine")
    document = executable.read_text(encoding="utf-8").replace(
        "'scenario_contract_versions':['3']",
        "'scenario_contract_versions':['2']",
    )
    executable.write_text(document, encoding="utf-8")
    output = tmp_path / "incompatible"

    with pytest.raises(ValueError, match="missing scenario contract_version '3'"):
        run_scenario(empty_scenario(), executable=executable, output_directory=output)

    assert not (output / "empty-demo.scenario.jsonl").exists()
    assert not (output / "empty-demo.journal.jsonl").exists()

    format_engine = fake_engine(tmp_path / "batch-only-engine")
    format_document = format_engine.read_text(encoding="utf-8").replace(
        "'scenario_formats':['json','jsonl']",
        "'scenario_formats':['json']",
    )
    format_engine.write_text(format_document, encoding="utf-8")
    with pytest.raises(ValueError, match="missing JSONL scenarios"):
        run_scenario(
            empty_scenario(),
            executable=format_engine,
            output_directory=tmp_path / "batch-only",
        )
    assert not (tmp_path / "batch-only" / "empty-demo.scenario.jsonl").exists()

    model_engine = fake_engine(tmp_path / "unsupported-model-engine")
    model_document = model_engine.read_text(encoding="utf-8").replace(
        "'execution_models':['completed_bar_v1']",
        "'execution_models':['future_model']",
    )
    model_engine.write_text(model_document, encoding="utf-8")
    with pytest.raises(ValueError, match="missing execution model 'completed_bar_v1'"):
        run_scenario(
            empty_scenario(),
            executable=model_engine,
            output_directory=tmp_path / "unsupported-model",
        )
    assert not (tmp_path / "unsupported-model" / "empty-demo.scenario.jsonl").exists()


def test_run_scenario_rejects_malformed_capabilities(tmp_path: Path) -> None:
    executable = tmp_path / "malformed-engine"
    executable.write_text("#!/usr/bin/env python3\nprint('not JSON')\n", encoding="utf-8")
    executable.chmod(0o755)

    with pytest.raises(TradingEngineProcessError, match="invalid document") as captured:
        run_scenario(
            empty_scenario(),
            executable=executable,
            output_directory=tmp_path / "malformed",
        )

    assert captured.value.command[-1] == "--capabilities"


def test_run_scenario_preflights_all_artifacts_before_writing(tmp_path: Path) -> None:
    executable = fake_engine(tmp_path / "engine")
    output = tmp_path / "output"
    output.mkdir()
    (output / "empty-demo.manifest.json").write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError, match="artifact path already exists"):
        run_scenario(empty_scenario(), executable=executable, output_directory=output)
    assert not (output / "empty-demo.scenario.jsonl").exists()


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

    ambiguous = tmp_path / "scenario.txt"
    ambiguous.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match=r"must end in \.json or \.jsonl"):
        run_scenario(ambiguous, executable=executable, output_directory=tmp_path / "ambiguous")


def test_run_scenario_requires_the_process_to_create_a_journal(tmp_path: Path) -> None:
    executable = tmp_path / "no-journal"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import sys
if '--capabilities' in sys.argv:
    print(json.dumps({'engine_version':'test-engine-1','scenario_contract_versions':['3'],'journal_contract_versions':['3'],'scenario_formats':['json','jsonl'],'journal_formats':['jsonl'],'execution_models':['completed_bar_v1'],'strategy_protocol_versions':['2']}))
else:
    print('successful')
""",
        encoding="utf-8",
    )
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
    with pytest.raises(TradingEngineProcessError, match="exit code 9") as invalid_utf8:
        run_process(
            [
                sys.executable,
                "-c",
                "import os; os.write(2, bytes([255])); raise SystemExit(9)",
            ],
            timeout=1,
            stage="test",
        )
    assert invalid_utf8.value.stderr == "\N{REPLACEMENT CHARACTER}"
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


def test_finalize_journal_cleans_staging_after_a_private_hash_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = import_module("persistra.integrations.trading_engine.runner")
    finalize = vars(runner)["_finalize_journal"]
    partial = tmp_path / "journal.partial"
    final = tmp_path / "journal.jsonl"
    partial.write_bytes(b"complete journal\n")
    digest = hashlib.sha256(partial.read_bytes()).hexdigest()

    def fail_hash(path: Path) -> str:
        if path.name.endswith(".staging"):
            raise OSError("private staging hash failed")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    monkeypatch.setattr(runner, "_sha256", fail_hash)
    with pytest.raises(OSError, match="private staging hash failed"):
        finalize(partial, final, expected_sha256=digest)

    assert partial.exists()
    assert not final.exists()
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
