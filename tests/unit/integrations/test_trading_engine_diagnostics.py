"""Tests for typed Trading Engine v1 diagnostics."""

from __future__ import annotations

import json

import pytest

from persistra.integrations.trading_engine import trading_engine_diagnostic_from_json


def diagnostic(*, code: str = "strategy.protocol") -> dict[str, object]:
    return {
        "diagnostic_version": "1",
        "code": code,
        "phase": "strategy",
        "message": "strategy initialization rejected the response",
        "context": {"json_path": "$", "sequence": "1"},
        "cause": None,
    }


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
        trading_engine_diagnostic_from_json(
            '{"diagnostic_version":"1","diagnostic_version":"1"}'
        )


def test_diagnostic_decoder_accepts_additive_codes_and_context() -> None:
    value = diagnostic(code="strategy.new")
    context = value["context"]
    assert isinstance(context, dict)
    context["artifact"] = "run.strategy.jsonl.partial"

    result = trading_engine_diagnostic_from_json(json.dumps(value))

    assert result.code == "strategy.new"
    assert result.context.sequence == 1
