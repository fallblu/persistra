"""Exercise Persistra against a real Trading Engine executable and its schemas."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest
from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from persistra.data import synthetic
from persistra.integrations.trading_engine import (
    BarClockPolicy,
    ExecutionInstrument,
    ExecutionPolicy,
    RiskPolicy,
    SizingPolicy,
    build_scenario,
    run_scenario,
)
from persistra.model import BarSet

if TYPE_CHECKING:
    from collections.abc import Callable

    from jsonschema.protocols import Validator

    from persistra.integrations.trading_engine import (
        ExecutionReplayResult,
        TradingEngineScenario,
    )

_BINARY = os.environ.get("PERSISTRA_TRADING_ENGINE_BINARY")
_SCHEMA_DIRECTORY = os.environ.get("PERSISTRA_TRADING_ENGINE_SCHEMA_DIR")

pytestmark = pytest.mark.skipif(
    not _BINARY or not _SCHEMA_DIRECTORY,
    reason="real Trading Engine integration requires its binary and schema directory",
)


def test_replay_is_deterministic_and_conforms_to_engine_schemas(tmp_path: Path) -> None:
    """Replay a cash-limited target twice and validate every persisted artifact."""
    assert _BINARY is not None
    assert _SCHEMA_DIRECTORY is not None
    binary = Path(_BINARY).resolve(strict=True)
    schema_directory = Path(_SCHEMA_DIRECTORY).resolve(strict=True)
    scenario = _cash_limited_scenario()

    first = run_scenario(
        scenario,
        executable=binary,
        output_directory=tmp_path / "first",
    )
    second = run_scenario(
        scenario,
        executable=binary,
        output_directory=tmp_path / "second",
    )

    assert first.scenario_path.read_bytes() == second.scenario_path.read_bytes()
    assert first.journal_path.read_bytes() == second.journal_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert first.scenario_sha256 == second.scenario_sha256
    assert first.journal_sha256 == second.journal_sha256
    assert first.executable_sha256 == second.executable_sha256
    assert first.manifest_path.is_file()
    assert second.manifest_path.is_file()

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == scenario.run_id
    assert manifest["engine"] == {
        "executable": binary.name,
        "sha256": first.executable_sha256,
    }
    assert manifest["artifacts"] == {
        "scenario": {
            "path": first.scenario_path.name,
            "sha256": first.scenario_sha256,
        },
        "journal": {
            "path": first.journal_path.name,
            "sha256": first.journal_sha256,
        },
    }

    scenario_validator = _validator(schema_directory / "scenario.schema.json")
    journal_validator = _validator(schema_directory / "journal.schema.json")
    scenario_document = json.loads(first.scenario_path.read_text(encoding="utf-8"))
    assert manifest["scenario_metadata"] == scenario_document["metadata"]
    scenario_validator.validate(scenario_document)
    records = [
        json.loads(line) for line in first.journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records
    for record in records:
        journal_validator.validate(record)

    event_types = {event.event_type for event in first.replay.events}
    assert {"run_started", "cash_limited", "run_completed"} <= event_types
    assert not first.replay.cash_limits.empty
    assert first.replay.completion.scenario_sha256 == first.scenario_sha256
    assert first.replay.completion.cash_micros >= 0


def test_replay_rejects_a_journal_changed_after_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never publish or manifest bytes that differ from the imported journal."""
    assert _BINARY is not None
    runner = import_module("persistra.integrations.trading_engine.runner")
    read_journal = cast(
        "Callable[..., ExecutionReplayResult]",
        vars(runner)["read_journal"],
    )

    def read_then_change(path: str | Path, **kwargs: object) -> ExecutionReplayResult:
        replay = read_journal(path, **kwargs)
        Path(path).write_text("changed after reconciliation\n", encoding="utf-8")
        return replay

    monkeypatch.setattr(runner, "read_journal", read_then_change)
    output = tmp_path / "changed-journal"
    with pytest.raises(ValueError, match="changed during reconciliation"):
        run_scenario(
            _cash_limited_scenario(),
            executable=Path(_BINARY),
            output_directory=output,
        )

    assert not (output / "cash-limited-integration.journal.jsonl").exists()
    assert not (output / "cash-limited-integration.manifest.json").exists()


def _cash_limited_scenario() -> TradingEngineScenario:
    bars = _execution_bars()
    instrument_id = bars.instrument.instrument_id
    targets = pd.DataFrame(
        {instrument_id: [1.0]},
        index=pd.DatetimeIndex([bars.frame.loc[0, "timestamp"]]),
    )
    return build_scenario(
        [bars],
        targets,
        instruments=[ExecutionInstrument(instrument_id, "CASH", "USD", "0.01")],
        initial_cash="10000",
        clock_policy=BarClockPolicy(
            source_timestamp_position="start",
            bar_duration=timedelta(minutes=5),
            availability_delay=timedelta(0),
            receipt_delay=timedelta(0),
        ),
        sizing_policy=SizingPolicy(),
        risk=RiskPolicy(max_order_quantity=1_000, max_position=1_000),
        execution=ExecutionPolicy(
            participation_bps=10_000,
            fixed_fee="0.25",
            fee_bps=0,
        ),
        run_id="cash-limited-integration",
    )


def _execution_bars() -> BarSet:
    source = synthetic.bars(
        "CASH",
        periods=4,
        seed=41,
        interval="5min",
        session="regular",
    )
    frame = source.frame.copy(deep=True)
    values = {
        "open": (100.0, 101.0, 102.0, 103.0),
        "high": (100.0, 101.0, 102.0, 103.0),
        "low": (100.0, 101.0, 102.0, 103.0),
        "close": (100.0, 101.0, 102.0, 103.0),
        "volume": (1_000.0, 1_000.0, 1_000.0, 1_000.0),
    }
    for column, column_values in values.items():
        frame[column] = column_values
    frame = frame.astype(
        {
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "Float64",
        }
    )
    return BarSet(source.instrument, frame, source.metadata)


def _validator(path: Path) -> Validator:
    schema = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    validator_type = validator_for(schema)
    validator_type.check_schema(schema)
    return validator_type(schema, format_checker=FormatChecker())
