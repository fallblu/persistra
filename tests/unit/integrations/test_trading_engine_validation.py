"""Boundary validation for the maintained Trading Engine v1 values."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from persistra.integrations.trading_engine._scalars import (
    INT64_MAX,
    decimal_string,
    decimal_value,
    exact_fields,
    identifier,
    metric_name,
    quantity_value,
    rfc3339_string,
    weight_toward_zero,
)
from persistra.integrations.trading_engine.model import (
    ConservativeBarExecutionPolicy,
    EngineCapabilities,
    EngineResourceLimits,
    ExecutionInstrument,
    StrategyResponseEvidence,
    StrategyResponseRejection,
    TradingEngineDiagnostic,
    TradingEngineDiagnosticCause,
    TradingEngineDiagnosticContext,
    TradingEngineProcessError,
)


def resource_limits(**changes: Any) -> EngineResourceLimits:
    values: dict[str, Any] = {
        "version": "1",
        "scenario_record_bytes": 1_048_576,
        "strategy_message_bytes": 1_048_576,
        "internal_events": 100_000,
        "catalog_instruments": 4_096,
        "intents_per_batch": 4_096,
        "artifact_record_bytes": 2_097_152,
    }
    values.update(changes)
    return EngineResourceLimits(**values)


def capabilities(**changes: Any) -> EngineCapabilities:
    values: dict[str, Any] = {
        "engine_version": "test-engine",
        "scenario_contract_versions": ("1",),
        "journal_contract_versions": ("1",),
        "scenario_formats": ("json",),
        "journal_formats": ("jsonl",),
        "execution_models": ("completed_bar_next_open_v1",),
        "strategy_protocol_versions": ("1",),
        "resource_limits": resource_limits(),
    }
    values.update(changes)
    return EngineCapabilities(**values)


@pytest.mark.parametrize(
    ("value", "error", "message", "options"),
    [
        (True, TypeError, "decimal number", {}),
        (object(), TypeError, "decimal number", {}),
        (".", ValueError, "decimal number", {}),
        ("NaN", ValueError, "finite", {}),
        ("1.0000001", ValueError, "at most six", {}),
        (0, ValueError, "positive", {"positive": True}),
        (-1, ValueError, "nonnegative", {"nonnegative": True}),
        (Decimal(INT64_MAX) + 1, ValueError, "supported range", {}),
    ],
)
def test_decimal_value_rejects_unsupported_values(
    value: object,
    error: type[Exception],
    message: str,
    options: dict[str, bool],
) -> None:
    with pytest.raises(error, match=message):
        decimal_value(value, name="value", **options)


def test_decimal_helpers_preserve_exact_values() -> None:
    assert decimal_value(Decimal("1.250000"), name="value") == Decimal("1.250000")
    assert decimal_value(2.5, name="value") == Decimal("2.5")
    assert decimal_string(Decimal("1.250000")) == "1.25"
    assert decimal_string(Decimal("-0.000000")) == "0"
    assert weight_toward_zero(Decimal("-1"), equity=Decimal("3")) == Decimal("-0.333333")
    with pytest.raises(ValueError, match="equity must be positive"):
        weight_toward_zero(Decimal(1), equity=Decimal(0))


@pytest.mark.parametrize(
    ("value", "error", "message", "positive"),
    [
        (True, TypeError, "whole number", False),
        (Decimal("1.5"), ValueError, "whole number", False),
        (1.5, ValueError, "whole number", False),
        ("", ValueError, "whole number", False),
        ("no", ValueError, "whole number", False),
        ("01", ValueError, "canonical", False),
        (object(), TypeError, "whole number", False),
        (-1, ValueError, "nonnegative", False),
        (0, ValueError, "positive", True),
        (INT64_MAX + 1, ValueError, "supported range", False),
    ],
)
def test_quantity_value_rejects_unsupported_values(
    value: object,
    error: type[Exception],
    message: str,
    positive: bool,
) -> None:
    with pytest.raises(error, match=message):
        quantity_value(value, name="quantity", positive=positive)


def test_scalar_boundary_helpers_accept_canonical_values() -> None:
    assert quantity_value(Decimal(2), name="quantity") == 2
    assert quantity_value(3.0, name="quantity") == 3
    assert quantity_value("4", name="quantity") == 4
    assert identifier("engine-v1", name="identifier") == "engine-v1"
    assert metric_name("daily signal") == "daily signal"
    assert rfc3339_string("2026-01-02T14:30:00.123456Z", name="time").endswith("Z")
    assert exact_fields({"value": 1}, {"value"}, name="item") == {"value": 1}


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: identifier(1, name="identifier"), "string"),
        (lambda: identifier(" padded", name="identifier"), "empty or padded"),
        (lambda: identifier("line\nbreak", name="identifier"), "whitespace or control"),
        (lambda: metric_name(1), "string"),
        (lambda: metric_name(" padded"), "nonempty and trimmed"),
        (lambda: rfc3339_string("not-a-time", name="time"), "RFC3339"),
        (lambda: exact_fields([], {"value"}, name="item"), "JSON object"),
        (lambda: exact_fields({"other": 1}, {"value"}, name="item"), "fields differ"),
    ],
)
def test_scalar_boundary_helpers_reject_ambiguous_values(call: Any, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        call()


def test_engine_capabilities_validate_current_contract_collections() -> None:
    assert capabilities().scenario_contract_versions == ("1",)
    with pytest.raises(TypeError, match="must be a tuple"):
        capabilities(scenario_formats=["json"])
    with pytest.raises(ValueError, match="must not be empty"):
        capabilities(journal_formats=())
    with pytest.raises(ValueError, match="must not contain duplicates"):
        capabilities(execution_models=("completed_bar_next_open_v1",) * 2)
    with pytest.raises(TypeError, match="EngineResourceLimits or None"):
        capabilities(resource_limits={})


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_engine_resource_limits_require_positive_integers(value: object) -> None:
    with pytest.raises(TypeError, match="scenario_record_bytes must be an integer"):
        resource_limits(scenario_record_bytes=value)
    with pytest.raises(ValueError, match="internal_events must be positive"):
        resource_limits(internal_events=0)


def diagnostic_context() -> TradingEngineDiagnosticContext:
    return TradingEngineDiagnosticContext("$", 1, 2, "event-1", "order-1", ("cause-1",))


def diagnostic() -> TradingEngineDiagnostic:
    return TradingEngineDiagnostic(
        "1",
        "strategy.protocol",
        "strategy",
        "response rejected",
        TradingEngineDiagnosticContext(sequence=1),
    )


def test_diagnostic_models_validate_typed_boundaries() -> None:
    assert diagnostic_context().line == 1
    assert TradingEngineDiagnosticCause("exception", "failed", "read", "response").operation == (
        "read"
    )
    with pytest.raises(TypeError, match="json_path"):
        TradingEngineDiagnosticContext(json_path=cast("Any", 1))
    with pytest.raises(TypeError, match="causation_ids"):
        TradingEngineDiagnosticContext(causation_ids=cast("Any", []))
    with pytest.raises(TypeError, match="message"):
        TradingEngineDiagnosticCause("exception", cast("Any", 1))
    with pytest.raises(TypeError, match="operation"):
        TradingEngineDiagnosticCause("exception", "failed", cast("Any", 1))
    with pytest.raises(ValueError, match="diagnostic version"):
        TradingEngineDiagnostic(
            "2", "strategy.protocol", "strategy", "failed", diagnostic_context()
        )
    with pytest.raises(ValueError, match="namespaced"):
        TradingEngineDiagnostic("1", "protocol", "strategy", "failed", diagnostic_context())
    with pytest.raises(ValueError, match="phase"):
        TradingEngineDiagnostic("1", "strategy.protocol", "network", "failed", diagnostic_context())
    with pytest.raises(ValueError, match="nonempty"):
        TradingEngineDiagnostic("1", "strategy.protocol", "strategy", "", diagnostic_context())
    with pytest.raises(TypeError, match="context"):
        TradingEngineDiagnostic("1", "strategy.protocol", "strategy", "failed", cast("Any", {}))


def test_strategy_rejection_models_reconcile_sequences_and_evidence() -> None:
    evidence = StrategyResponseEvidence(b"{}", 2, False)
    rejection = StrategyResponseRejection("1", 2, 1, diagnostic(), evidence)
    assert rejection.transcript_sequence == 2
    with pytest.raises(TypeError, match="prefix"):
        StrategyResponseEvidence(cast("Any", "{}"), 2, False)
    with pytest.raises(ValueError, match="256 bytes"):
        StrategyResponseEvidence(b"x" * 257, 257, False)
    with pytest.raises(ValueError, match="exceeds observed"):
        StrategyResponseEvidence(b"{}", 1, False)
    with pytest.raises(ValueError, match="inconsistent"):
        StrategyResponseEvidence(b"{}", 3, False)
    with pytest.raises(ValueError, match="diagnostic version"):
        StrategyResponseRejection("2", 2, 1, diagnostic(), evidence)
    with pytest.raises(ValueError, match="do not reconcile"):
        StrategyResponseRejection("1", 3, 1, diagnostic(), evidence)


def execution_policy(**changes: Any) -> ConservativeBarExecutionPolicy:
    values: dict[str, Any] = {
        "model": "completed_bar_next_open_v1",
        "participation_bps": 1_000,
        "fee_schedules": ({"components": [{"model": "per_quantity_v1", "rate": 1.0}]},),
    }
    values.update(changes)
    return ConservativeBarExecutionPolicy(**values)


def test_execution_models_emit_current_contract_payloads() -> None:
    instrument = ExecutionInstrument("asset-a", "AAA", "USD", "0.01", "1")
    assert instrument.tick_size == Decimal("0.01")
    policy = execution_policy()
    payload = policy.to_contract_payload()
    assert cast("dict[str, object]", payload["configuration"])["version"] == "1"
    policy.require_contract(
        cast(
            "Any",
            SimpleNamespace(version="1", execution_models=("completed_bar_next_open_v1",)),
        )
    )
    with pytest.raises(ValueError, match="contract v1"):
        policy.require_contract(cast("Any", SimpleNamespace(version="2", execution_models=())))
    with pytest.raises(ValueError, match="compatible contract"):
        policy.require_contract(cast("Any", SimpleNamespace(version="1", execution_models=())))


@pytest.mark.parametrize(
    ("changes", "error", "message"),
    [
        ({"model": "future"}, ValueError, "unsupported conservative"),
        ({"participation_bps": 10_001}, ValueError, "must not exceed"),
        ({"fee_schedules": ()}, ValueError, "nonempty tuple"),
        ({"fee_schedules": (["bad"],)}, TypeError, "must be mappings"),
        ({"fee_schedules": ({1: "bad"},)}, TypeError, "keys must be strings"),
        ({"fee_schedules": ({"rate": float("nan")},)}, ValueError, "finite"),
        ({"fee_schedules": ({"rate": Decimal(1)},)}, TypeError, "JSON-compatible"),
        ({"missing_volume_policy": "future"}, ValueError, "missing-volume"),
    ],
)
def test_execution_policy_rejects_invalid_configuration(
    changes: dict[str, object], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        execution_policy(**changes)


def test_process_error_preserves_paths_and_message() -> None:
    error = TradingEngineProcessError("failed", ("engine",), 2, journal_path=Path("journal.jsonl"))
    assert str(error) == "failed"
    assert error.journal_path == Path("journal.jsonl")
