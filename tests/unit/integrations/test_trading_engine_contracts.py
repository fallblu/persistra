"""Tests for authoritative Trading Engine schema loading."""

import hashlib
import json
from pathlib import Path

import pytest

from persistra.integrations.trading_engine import (
    ConservativeBarExecutionPolicy,
    TradingEngineContractError,
    TradingEngineContractSchemas,
)


def contract_directory(root: Path) -> Path:
    """Write a minimal linked contract schema set."""
    directory = root / "v1"
    directory.mkdir(parents=True)
    identifier = "https://github.com/fallblu/trading-engine/contracts/v1"
    scenario = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{identifier}/scenario.schema.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["contract_version", "execution", "run_id"],
        "properties": {
            "contract_version": {"const": "1"},
            "run_id": {"type": "string"},
            "execution": {
                "oneOf": [
                    {
                        "type": "object",
                        "required": ["model"],
                        "properties": {"model": {"const": "completed_bar_v1"}},
                    },
                    {
                        "type": "object",
                        "required": ["model"],
                        "properties": {
                            "model": {
                                "enum": [
                                    "completed_bar_next_open_v1",
                                    "completed_bar_adverse_touch_v1",
                                ]
                            }
                        },
                    },
                ]
            },
        },
    }
    stream = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{identifier}/scenario-stream.schema.json",
        "type": "object",
        "required": ["contract_version"],
        "properties": {"contract_version": {"const": "1"}},
    }
    journal = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{identifier}/journal.schema.json",
        "type": "object",
        "required": ["contract_version", "event_type"],
        "properties": {
            "contract_version": {"const": "1"},
            "event_type": {"type": "string"},
        },
    }
    for name, value in (
        ("scenario.schema.json", scenario),
        ("scenario-stream.schema.json", stream),
        ("journal.schema.json", journal),
    ):
        (directory / name).write_text(json.dumps(value), encoding="utf-8")
    return directory


def test_contract_schemas_are_fingerprinted_and_derive_execution_models(
    tmp_path: Path,
) -> None:
    directory = contract_directory(tmp_path)
    first = TradingEngineContractSchemas.load(directory)
    second = TradingEngineContractSchemas.load(directory)

    assert first.version == "1"
    assert first.sha256 == second.sha256
    assert len(first.sha256) == 64
    assert first.execution_models == (
        "completed_bar_adverse_touch_v1",
        "completed_bar_next_open_v1",
        "completed_bar_v1",
    )
    first.validate_scenario(
        {
            "contract_version": "1",
            "execution": {"model": "completed_bar_next_open_v1"},
            "run_id": "run-a",
        }
    )
    first.validate_stream_record({"contract_version": "1"}, line_number=1)


def test_schema_validation_reports_artifact_and_field_without_payload(
    tmp_path: Path,
) -> None:
    schemas = TradingEngineContractSchemas.load(contract_directory(tmp_path))
    with pytest.raises(
        TradingEngineContractError,
        match=r"scenario violates contract v1 at contract_version",
    ):
        schemas.validate_scenario(
            {
                "contract_version": "2",
                "execution": {"model": "completed_bar_v1"},
                "run_id": "run-a",
                "secret": "do-not-report",
            }
        )


def test_journal_validation_streams_records_and_reports_line(tmp_path: Path) -> None:
    schemas = TradingEngineContractSchemas.load(contract_directory(tmp_path))
    valid = tmp_path / "valid.jsonl"
    valid.write_text(
        '{"contract_version":"1","event_type":"run_started"}\n'
        '{"contract_version":"1","event_type":"run_completed"}\n',
        encoding="utf-8",
    )
    assert schemas.validate_journal(valid) == 2

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(
        '{"contract_version":"1","event_type":"run_started"}\n'
        '{"contract_version":"2","event_type":"run_completed"}\n',
        encoding="utf-8",
    )
    with pytest.raises(TradingEngineContractError, match=r"journal line 2.*contract_version"):
        schemas.validate_journal(invalid)


def test_contract_loader_rejects_missing_or_misversioned_schemas(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="named vN"):
        TradingEngineContractSchemas.load(tmp_path)
    directory = contract_directory(tmp_path)
    (directory / "journal.schema.json").unlink()
    with pytest.raises(ValueError, match=r"missing journal\.schema\.json"):
        TradingEngineContractSchemas.load(directory)


def test_contract_loader_rejects_malformed_schema_sets(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "v1"
    with pytest.raises(ValueError, match="does not exist"):
        TradingEngineContractSchemas.load(missing)

    invalid_json = contract_directory(tmp_path / "invalid-json")
    (invalid_json / "scenario.schema.json").write_text("{", encoding="utf-8")
    with pytest.raises(TradingEngineContractError, match="invalid contract schema"):
        TradingEngineContractSchemas.load(invalid_json)

    non_object = contract_directory(tmp_path / "non-object")
    (non_object / "scenario.schema.json").write_text("[]", encoding="utf-8")
    with pytest.raises(TradingEngineContractError, match="must be an object"):
        TradingEngineContractSchemas.load(non_object)

    wrong_contract_id = contract_directory(tmp_path / "wrong-contract-id")
    scenario_path = wrong_contract_id / "scenario.schema.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["$id"] = "https://example.test/contracts/unsupported/scenario.schema.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    with pytest.raises(TradingEngineContractError, match="does not declare version"):
        TradingEngineContractSchemas.load(wrong_contract_id)

    invalid_schema = contract_directory(tmp_path / "invalid-schema")
    scenario_path = invalid_schema / "scenario.schema.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["type"] = "not-a-json-schema-type"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    with pytest.raises(TradingEngineContractError, match="invalid contract schema"):
        TradingEngineContractSchemas.load(invalid_schema)

    no_models = contract_directory(tmp_path / "no-models")
    scenario_path = no_models / "scenario.schema.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["properties"]["execution"] = {"type": "object"}
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    with pytest.raises(TradingEngineContractError, match="no execution models"):
        TradingEngineContractSchemas.load(no_models)

    unresolved = contract_directory(tmp_path / "unresolved")
    scenario_path = unresolved / "scenario.schema.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["properties"]["extra"] = {"$ref": "missing.schema.json"}
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    with pytest.raises(TradingEngineContractError, match="unresolved reference"):
        TradingEngineContractSchemas.load(unresolved)


def test_schema_replay_rejects_invalid_json_and_empty_journal(tmp_path: Path) -> None:
    schemas = TradingEngineContractSchemas.load(contract_directory(tmp_path))
    scenario = tmp_path / "scenario.json"
    scenario.write_text("{", encoding="utf-8")
    journal = tmp_path / "journal.jsonl"
    journal.write_text("", encoding="utf-8")
    with pytest.raises(TradingEngineContractError, match="invalid scenario JSON"):
        schemas.read_replay(scenario, journal)

    scenario.write_text(
        json.dumps(
            {
                "contract_version": "1",
                "execution": {"model": "completed_bar_v1"},
                "run_id": "run-a",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TradingEngineContractError, match="journal must not be empty"):
        schemas.read_replay(scenario, journal)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"run_id": "run-b"}, "run_id differs"),
        ({"engine_sequence": "7"}, "breaks engine sequence"),
        ({"event_type": "not_started"}, "must begin with run_started"),
        ({"payload": "invalid"}, "run_started payload is invalid"),
        ({"payload": {"execution_model": "completed_bar_v1"}}, "scenario hash differs"),
    ],
)
def test_schema_replay_rejects_inconsistent_journal_identity(
    tmp_path: Path, mutation: dict[str, object], message: str
) -> None:
    schemas = TradingEngineContractSchemas.load(contract_directory(tmp_path))
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "contract_version": "1",
                "execution": {"model": "completed_bar_v1"},
                "run_id": "run-a",
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(scenario.read_bytes()).hexdigest()
    started: dict[str, object] = {
        "contract_version": "1",
        "engine_sequence": "1",
        "run_id": "run-a",
        "event_type": "run_started",
        "payload": {
            "scenario_sha256": digest,
            "execution_model": "completed_bar_v1",
        },
    }
    started.update(mutation)
    completed = {
        "contract_version": "1",
        "engine_sequence": "2",
        "run_id": "run-a",
        "event_type": "run_completed",
        "payload": {
            "scenario_sha256": digest,
            "execution_model": "completed_bar_v1",
        },
    }
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        json.dumps(started) + "\n" + json.dumps(completed) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(TradingEngineContractError, match=message):
        schemas.read_replay(scenario, journal)


def test_conservative_bar_execution_is_typed_and_contract_gated(tmp_path: Path) -> None:
    policy = ConservativeBarExecutionPolicy(
        model="completed_bar_next_open_v1",
        participation_bps=5_000,
        fee_schedules=({"schedule_id": "fees-a", "tiers": [{"threshold": "0", "bps": 1}]},),
        half_spread_bps=4,
        impact_coefficient_bps=7,
        missing_volume_policy="zero_impact",
    )
    schemas = TradingEngineContractSchemas.load(contract_directory(tmp_path))
    policy.require_contract(schemas)
    assert policy.to_contract_payload() == {
        "model": "completed_bar_next_open_v1",
        "configuration": {
            "version": "1",
            "participation_bps": 5_000,
            "fee_schedules": [{"schedule_id": "fees-a", "tiers": [{"threshold": "0", "bps": 1}]}],
            "spread_model": {"model": "fixed_half_spread_v1", "half_spread_bps": 4},
            "impact_model": {
                "model": "linear_participation_v1",
                "coefficient_bps": 7,
                "missing_volume_policy": "zero_impact",
            },
        },
    }
    with pytest.raises(ValueError, match="participation_bps"):
        ConservativeBarExecutionPolicy(
            model="completed_bar_next_open_v1",
            participation_bps=10_001,
            fee_schedules=({},),
        )
    with pytest.raises(ValueError, match="fee_schedules"):
        ConservativeBarExecutionPolicy(
            model="completed_bar_next_open_v1",
            participation_bps=1,
            fee_schedules=(),
        )
    json.dumps(policy.to_contract_payload())


def test_schema_replay_uses_stable_empty_execution_price_columns(
    tmp_path: Path,
) -> None:
    schemas = TradingEngineContractSchemas.load(contract_directory(tmp_path))
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "contract_version": "1",
                "execution": {"model": "completed_bar_v1"},
                "run_id": "run-a",
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(scenario.read_bytes()).hexdigest()
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        "\n".join(
            json.dumps(
                {
                    "contract_version": "1",
                    "engine_sequence": str(sequence),
                    "run_id": "run-a",
                    "event_type": event_type,
                    "payload": {
                        "scenario_sha256": digest,
                        "execution_model": "completed_bar_v1",
                    },
                }
            )
            for sequence, event_type in ((1, "run_started"), (2, "run_completed"))
        )
        + "\n",
        encoding="utf-8",
    )

    result = schemas.read_replay(scenario, journal)

    assert result.execution_prices.empty
    assert list(result.execution_prices) == [
        "engine_sequence",
        "order_id",
        "instrument_id",
        "side",
        "reference_price",
        "spread_adjustment",
        "impact_adjustment",
        "final_price",
    ]


def test_schema_replay_reconciles_model_hash_sequence_and_price_evidence(
    tmp_path: Path,
) -> None:
    schemas = TradingEngineContractSchemas.load(contract_directory(tmp_path))
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "contract_version": "1",
                "execution": {"model": "completed_bar_next_open_v1"},
                "run_id": "run-a",
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(scenario.read_bytes()).hexdigest()
    journal = tmp_path / "journal.jsonl"
    records = [
        {
            "contract_version": "1",
            "engine_sequence": "1",
            "run_id": "run-a",
            "event_type": "run_started",
            "payload": {
                "scenario_sha256": digest,
                "execution_model": "completed_bar_next_open_v1",
            },
        },
        {
            "contract_version": "1",
            "engine_sequence": "2",
            "run_id": "run-a",
            "event_type": "execution_price_selected",
            "payload": {
                "order_id": "order-a",
                "reference_price": "10",
                "final_price": "10.01",
            },
        },
        {
            "contract_version": "1",
            "engine_sequence": "3",
            "run_id": "run-a",
            "event_type": "run_completed",
            "payload": {
                "scenario_sha256": digest,
                "execution_model": "completed_bar_next_open_v1",
            },
        },
    ]
    journal.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    replay = schemas.read_replay(scenario, journal)
    assert replay.execution_model == "completed_bar_next_open_v1"
    assert replay.journal_records == 3
    assert replay.execution_prices.iloc[0]["order_id"] == "order-a"
    records[2]["payload"] = {
        "scenario_sha256": digest,
        "execution_model": "completed_bar_adverse_touch_v1",
    }
    journal.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    with pytest.raises(TradingEngineContractError, match="execution model differs"):
        schemas.read_replay(scenario, journal)
