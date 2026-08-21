"""Tests for typed Trading Engine failure diagnostics."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from persistra.integrations.trading_engine import (
    StrategyProtocolError,
    read_strategy_rejection,
    read_strategy_transcript,
    trading_engine_diagnostic_from_json,
)

if TYPE_CHECKING:
    from pathlib import Path


def diagnostic(*, code: str = "strategy.protocol") -> dict[str, object]:
    """Return one version-1 strategy diagnostic document."""
    return {
        "diagnostic_version": "1",
        "code": code,
        "phase": "strategy",
        "message": "strategy initialization rejected the response",
        "context": {"json_path": "$", "sequence": "1"},
        "cause": None,
    }


def rejection_records() -> list[dict[str, object]]:
    """Return one request followed by a distinct rejection diagnostic."""
    return [
        {
            "strategy_protocol_version": "3",
            "transcript_sequence": "1",
            "direction": "engine_to_strategy",
            "message": {
                "strategy_protocol_version": "3",
                "strategy_sequence": "1",
                "message_type": "initialize",
                "payload": {},
            },
        },
        {
            "strategy_diagnostic_version": "1",
            "transcript_sequence": "2",
            "record_type": "rejected_strategy_response",
            "expected_strategy_sequence": "1",
            "diagnostic": diagnostic(),
            "evidence": {
                "encoding": "hex",
                "prefix": "7b",
                "observed_bytes": 1,
                "truncated": False,
            },
        },
    ]


def write_records(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(f"{json.dumps(record, separators=(',', ':'))}\n" for record in records),
        encoding="utf-8",
    )


def test_diagnostic_decoder_uses_versioned_codes_and_typed_context() -> None:
    value = diagnostic(code="resource.limit")
    value["cause"] = {
        "kind": "exception",
        "message": "buffer limit",
        "operation": "read",
    }

    result = trading_engine_diagnostic_from_json(json.dumps(value))

    assert result.version == "1"
    assert result.code == "resource.limit"
    assert result.phase == "strategy"
    assert result.context.json_path == "$"
    assert result.context.sequence == 1
    assert result.cause is not None
    assert result.cause.operation == "read"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("diagnostic_version", "2"), "unsupported.*version"),
        (("code", "unnamespaced"), "must be namespaced"),
        (("phase", "network"), "unsupported.*phase"),
        (("extra", True), "fields differ"),
    ],
)
def test_diagnostic_decoder_rejects_unknown_contracts(
    change: tuple[str, object],
    message: str,
) -> None:
    value = diagnostic()
    value[change[0]] = change[1]
    with pytest.raises(ValueError, match=message):
        trading_engine_diagnostic_from_json(json.dumps(value))
    with pytest.raises(ValueError, match="duplicate"):
        trading_engine_diagnostic_from_json('{"diagnostic_version":"1","diagnostic_version":"1"}')


def test_diagnostic_decoder_accepts_additive_codes_and_context() -> None:
    value = diagnostic(code="strategy.new")
    context = value["context"]
    assert isinstance(context, dict)
    context["artifact"] = "run.strategy.jsonl.partial"

    result = trading_engine_diagnostic_from_json(json.dumps(value))

    assert result.code == "strategy.new"
    assert result.context.sequence == 1


def test_rejection_reader_retains_bounded_evidence_outside_valid_exchanges(
    tmp_path: Path,
) -> None:
    path = tmp_path / "failed.strategy.jsonl.partial"
    write_records(path, rejection_records())

    rejection = read_strategy_rejection(path)

    assert rejection.version == "1"
    assert rejection.transcript_sequence == 2
    assert rejection.expected_strategy_sequence == 1
    assert rejection.diagnostic.code == "strategy.protocol"
    assert rejection.evidence.prefix == b"{"
    assert rejection.evidence.observed_bytes == 1
    assert rejection.evidence.truncated is False
    with pytest.raises(StrategyProtocolError, match="fields differ"):
        read_strategy_transcript(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("strategy_diagnostic_version", "2", "unsupported strategy diagnostic version"),
        ("record_type", "exchange", "unsupported strategy rejection record type"),
        ("expected_strategy_sequence", "2", "sequences do not reconcile"),
    ],
)
def test_rejection_reader_rejects_invalid_envelopes(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    records = rejection_records()
    records[-1][field] = value
    path = tmp_path / "invalid.strategy.jsonl.partial"
    write_records(path, records)

    with pytest.raises(StrategyProtocolError, match=message):
        read_strategy_rejection(path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("prefix", "00" * 257), "prefix must be bounded hex"),
        (("prefix", "GG"), "prefix must be bounded hex"),
        (("observed_bytes", 0), "evidence exceeds observed bytes"),
        (("truncated", True), "truncation is inconsistent"),
    ],
)
def test_rejection_reader_enforces_evidence_bounds(
    tmp_path: Path,
    change: tuple[str, object],
    message: str,
) -> None:
    records = rejection_records()
    rejection = deepcopy(records[-1])
    evidence = rejection["evidence"]
    assert isinstance(evidence, dict)
    evidence[change[0]] = change[1]
    records[-1] = rejection
    path = tmp_path / "invalid-evidence.strategy.jsonl.partial"
    write_records(path, records)

    with pytest.raises(StrategyProtocolError, match=message):
        read_strategy_rejection(path)
