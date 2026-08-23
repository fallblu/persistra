"""Tests for structured Trading Engine automation results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

import pytest

from persistra.integrations.trading_engine import (
    StrategyResponseEvidence,
    StrategyResponseRejection,
    StructuredEngineFailureStatus,
    TradingEngineDiagnostic,
    TradingEngineDiagnosticCause,
    TradingEngineDiagnosticContext,
    TradingEngineProcessError,
    bind_engine_status_manifest,
    structured_engine_failure,
    trading_engine_success_from_json,
    verify_trading_engine_success,
)

if TYPE_CHECKING:
    from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    scenario = tmp_path / "run.scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "run_id": "automation-run",
                "instruments": [{"instrument_id": "ABC"}],
                "schedule": [{"slice_id": "one", "intents": []}],
                "slices": [{"slice_id": "one"}],
            }
        ),
        encoding="utf-8",
    )
    journal = tmp_path / "run.journal.jsonl"
    records: list[dict[str, object]] = [
        {"event_type": "run_started", "payload": {}},
        {
            "event_type": "run_completed",
            "payload": {
                "valuation": {"equity": "1000", "currency": "USD"},
                "order_counts": {
                    "total": 3,
                    "active": 1,
                    "filled": 1,
                    "rejected": 1,
                },
            },
        },
    ]
    journal.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records),
        encoding="utf-8",
    )
    transcript = tmp_path / "run.strategy.jsonl"
    transcript.write_text('{"exchange":1}\n', encoding="utf-8")
    return scenario, journal, transcript


def success_document(
    scenario: Path,
    journal: Path | None = None,
    transcript: Path | None = None,
) -> dict[str, object]:
    replay = journal is not None
    return {
        "result_version": "1",
        "status": "success",
        "operation": "replay" if replay else "validate",
        "run_id": "automation-run",
        "hashes": {
            "scenario_sha256": sha256(scenario),
            "journal_sha256": None if journal is None else sha256(journal),
            "strategy_transcript_sha256": (None if transcript is None else sha256(transcript)),
        },
        "counts": {
            "instruments": 1,
            "schedule_batches": 1,
            "slices": 1,
            "audits": 0 if journal is None else 2,
            "orders": 0 if journal is None else 3,
            "active_orders": 0 if journal is None else 1,
            "filled_orders": 0 if journal is None else 1,
            "rejected_orders": 0 if journal is None else 1,
        },
        "valuation": {} if journal is None else {"equity": "1000", "currency": "USD"},
        "artifacts": {
            "journal": None if journal is None else str(journal),
            "strategy_transcript": None if transcript is None else str(transcript),
        },
    }


def parse(document: dict[str, object]):  # type: ignore[no-untyped-def]
    return trading_engine_success_from_json(json.dumps(document))


def test_parses_and_verifies_validation_success(tmp_path: Path) -> None:
    scenario, _, _ = artifacts(tmp_path)

    result = parse(success_document(scenario))

    assert result.operation == "validate"
    assert result.hashes.journal_sha256 is None
    assert result.to_dict()["status"] == "success"
    verify_trading_engine_success(result, scenario)
    with pytest.raises(ValueError, match="cannot verify replay artifacts"):
        verify_trading_engine_success(result, scenario, journal_path=scenario)


def test_parses_and_cross_checks_replay_artifacts(tmp_path: Path) -> None:
    scenario, journal, transcript = artifacts(tmp_path)
    result = parse(success_document(scenario, journal, transcript))

    verify_trading_engine_success(
        result,
        scenario,
        journal_path=journal,
        strategy_transcript_path=transcript,
    )

    manifest = bind_engine_status_manifest({"run_id": result.run_id}, result)
    assert manifest["status"]["operation"] == "replay"
    with pytest.raises(ValueError, match="already contains status"):
        bind_engine_status_manifest(manifest, result)


def test_verifies_json_lines_scenario_identity(tmp_path: Path) -> None:
    scenario = tmp_path / "stream.jsonl"
    records = [
        {
            "record_type": "scenario_header",
            "payload": {"run_id": "automation-run", "instruments": [{"id": "ABC"}]},
        },
        {"record_type": "market_slice", "payload": {"intents": [{"kind": "order"}]}},
    ]
    scenario.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records),
        encoding="utf-8",
    )
    document = success_document(scenario)

    verify_trading_engine_success(parse(document), scenario)


@pytest.mark.parametrize(
    ("section", "field", "replacement", "message"),
    [
        (None, "status", "failed", "status must be success"),
        (None, "result_version", "2", "unsupported.*version"),
        (None, "operation", "inspect", "unsupported.*operation"),
        (None, "extra", True, "fields differ"),
        ("hashes", "scenario_sha256", "ABC", "lowercase SHA-256"),
        ("counts", "active_orders", 1, "status counts exceed"),
        ("artifacts", "journal", "unexpected", "validation success must not declare"),
    ],
)
def test_rejects_invalid_success_contracts(
    tmp_path: Path,
    section: str | None,
    field: str,
    replacement: object,
    message: str,
) -> None:
    scenario, _, _ = artifacts(tmp_path)
    document = success_document(scenario)
    target = document if section is None else cast("dict[str, object]", document[section])
    target[field] = replacement

    with pytest.raises(ValueError, match=message):
        parse(document)


def test_rejects_duplicate_and_non_json_documents() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        trading_engine_success_from_json('{"status":"success","status":"success"}')
    with pytest.raises(ValueError, match=r"invalid.*JSON"):
        trading_engine_success_from_json("{")
    with pytest.raises(TypeError, match="must be a string"):
        trading_engine_success_from_json(1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("run_id", "another-run"), "run_id differs"),
        (("instruments", 2), "instruments differs"),
        (("audits", 3), "audit count differs"),
        (("orders", 4), "orders differs"),
    ],
)
def test_detects_success_summary_mismatches(
    tmp_path: Path,
    change: tuple[str, object],
    message: str,
) -> None:
    scenario, journal, _ = artifacts(tmp_path)
    document = success_document(scenario, journal)
    target = document if change[0] == "run_id" else document["counts"]
    assert isinstance(target, dict)
    target[change[0]] = change[1]

    with pytest.raises(ValueError, match=message):
        verify_trading_engine_success(parse(document), scenario, journal_path=journal)


def test_detects_artifact_hash_and_payload_mismatches(tmp_path: Path) -> None:
    scenario, journal, transcript = artifacts(tmp_path)
    document = success_document(scenario, journal, transcript)
    result = parse(document)

    scenario.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="scenario hash differs"):
        verify_trading_engine_success(result, scenario, journal_path=journal)

    scenario, journal, transcript = artifacts(tmp_path)
    result = parse(success_document(scenario, journal, transcript))
    journal.write_text('{"event_type":"run_started","payload":{}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="journal hash differs"):
        verify_trading_engine_success(result, scenario, journal_path=journal)

    scenario, journal, transcript = artifacts(tmp_path)
    result = parse(success_document(scenario, journal, transcript))
    transcript.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="transcript hash differs"):
        verify_trading_engine_success(
            result,
            scenario,
            journal_path=journal,
            strategy_transcript_path=transcript,
        )


def test_detects_missing_and_inconsistent_journal_evidence(tmp_path: Path) -> None:
    scenario, journal, transcript = artifacts(tmp_path)
    result = parse(success_document(scenario, journal))
    with pytest.raises(ValueError, match="requires a retained journal"):
        verify_trading_engine_success(result, scenario)
    with pytest.raises(ValueError, match="does not declare a strategy transcript"):
        verify_trading_engine_success(
            result,
            scenario,
            journal_path=journal,
            strategy_transcript_path=transcript,
        )

    journal.write_text('{"event_type":"run_started","payload":{}}\n', encoding="utf-8")
    document = success_document(scenario, journal)
    counts = cast("dict[str, object]", document["counts"])
    counts["audits"] = 1
    with pytest.raises(ValueError, match="exactly one completion"):
        verify_trading_engine_success(parse(document), scenario, journal_path=journal)


def test_detects_terminal_valuation_mismatch(tmp_path: Path) -> None:
    scenario, journal, _ = artifacts(tmp_path)
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    completion = cast("dict[str, Any]", records[-1])
    payload = cast("dict[str, Any]", completion["payload"])
    payload["valuation"]["equity"] = "999"
    journal.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")

    with pytest.raises(ValueError, match="valuation differs"):
        verify_trading_engine_success(
            parse(success_document(scenario, journal)), scenario, journal_path=journal
        )


def test_structures_failure_context_and_hashes_bounded_evidence(tmp_path: Path) -> None:
    _, journal, transcript = artifacts(tmp_path)
    diagnostic = TradingEngineDiagnostic(
        version="1",
        code="strategy.protocol",
        phase="strategy",
        message="response rejected",
        context=TradingEngineDiagnosticContext(
            json_path="$.response",
            line=7,
            sequence=1,
            event_id="event-1",
            order_id="order-1",
            causation_ids=("cause-1",),
        ),
        cause=TradingEngineDiagnosticCause(
            kind="io_error",
            message="invalid response",
            operation="read",
            target="strategy stdout",
        ),
    )
    rejection = StrategyResponseRejection(
        version="1",
        transcript_sequence=2,
        expected_strategy_sequence=1,
        diagnostic=diagnostic,
        evidence=StrategyResponseEvidence(
            prefix=b'{"invalid":', observed_bytes=300, truncated=True
        ),
    )
    error = TradingEngineProcessError(
        message="strategy failed",
        command=("trading-engine",),
        returncode=2,
        stdout="sensitive stdout",
        stderr="sensitive stderr",
        journal_path=journal,
        strategy_transcript_path=transcript,
        diagnostic=diagnostic,
        strategy_rejection=rejection,
    )

    status = structured_engine_failure(error)
    value = status.to_dict()
    context = cast("dict[str, object]", value["context"])
    failure_artifacts = cast("dict[str, Any]", value["artifacts"])
    rejected = cast("dict[str, object]", value["rejection"])

    assert value["code"] == "strategy.protocol"
    assert context == {
        "json_path": "$.response",
        "line": 7,
        "sequence": 1,
        "event_id": "event-1",
        "order_id": "order-1",
        "causation_ids": ["cause-1"],
    }
    assert failure_artifacts["journal"]["sha256"] == sha256(journal)
    assert rejected["prefix_sha256"] == hashlib.sha256(rejection.evidence.prefix).hexdigest()
    assert "sensitive" not in json.dumps(value)


def test_failure_status_requires_typed_diagnostic() -> None:
    error = TradingEngineProcessError("failed", ("engine",), 1)
    with pytest.raises(ValueError, match="structured diagnostic"):
        structured_engine_failure(error)
    with pytest.raises(TypeError, match="TradingEngineProcessError"):
        structured_engine_failure(ValueError("failed"))  # type: ignore[arg-type]


def test_public_status_models_enforce_versions_and_semantics(tmp_path: Path) -> None:
    scenario, _, _ = artifacts(tmp_path)
    success = parse(success_document(scenario))
    with pytest.raises(ValueError, match=r"unsupported.*version"):
        replace(success, version="2")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=r"unsupported.*operation"):
        replace(success, operation="inspect")  # type: ignore[arg-type]

    status = StructuredEngineFailureStatus(
        code="scenario.invalid",
        phase="validation",
        message="invalid scenario",
        context={},
        cause=None,
        artifacts={},
    )
    with pytest.raises(ValueError, match=r"unsupported.*version"):
        replace(status, diagnostic_version="2")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="nonempty string"):
        replace(status, message="")
