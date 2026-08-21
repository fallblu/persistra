"""Decode versioned Trading Engine diagnostics without parsing prose."""

from __future__ import annotations

import json
from typing import Any, cast

from persistra.integrations.trading_engine._scalars import exact_fields, quantity_value
from persistra.integrations.trading_engine.model import (
    TradingEngineDiagnostic,
    TradingEngineDiagnosticCause,
    TradingEngineDiagnosticContext,
)

__all__ = ["trading_engine_diagnostic_from_json"]

_CONTEXT_FIELDS = {
    "json_path",
    "line",
    "sequence",
    "event_id",
    "order_id",
    "causation_ids",
}
_CAUSE_FIELDS = {"kind", "message", "operation", "target"}


def trading_engine_diagnostic_from_json(document: str) -> TradingEngineDiagnostic:
    """Decode one strict version-1 Trading Engine diagnostic document."""
    raw_document = cast("object", document)
    if not isinstance(raw_document, str):
        raise TypeError("Trading Engine diagnostic document must be a string")
    try:
        value = json.loads(document, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"invalid Trading Engine diagnostic JSON: {error}") from error
    return diagnostic_from_object(value)


def diagnostic_from_object(value: object) -> TradingEngineDiagnostic:
    item = exact_fields(
        value,
        {"diagnostic_version", "code", "phase", "message", "context", "cause"},
        name="Trading Engine diagnostic",
    )
    return TradingEngineDiagnostic(
        version=_string(item["diagnostic_version"], name="diagnostic_version"),
        code=_string(item["code"], name="diagnostic code"),
        phase=_string(item["phase"], name="diagnostic phase"),
        message=_string(item["message"], name="diagnostic message", nonempty=True),
        context=_context_from_object(item["context"]),
        cause=None if item["cause"] is None else _cause_from_object(item["cause"]),
    )


def _context_from_object(value: object) -> TradingEngineDiagnosticContext:
    item = _optional_fields(
        value,
        _CONTEXT_FIELDS,
        name="diagnostic context",
        allow_additive=True,
    )
    raw_causation_ids = cast("object", item.get("causation_ids", []))
    if not isinstance(raw_causation_ids, list):
        raise ValueError("diagnostic causation_ids must be a JSON array")
    causation_ids = cast("list[object]", raw_causation_ids)
    return TradingEngineDiagnosticContext(
        json_path=_optional_string(item.get("json_path"), name="diagnostic json_path"),
        line=_optional_quantity(item.get("line"), name="diagnostic line"),
        sequence=_optional_quantity(item.get("sequence"), name="diagnostic sequence"),
        event_id=_optional_string(item.get("event_id"), name="diagnostic event_id"),
        order_id=_optional_string(item.get("order_id"), name="diagnostic order_id"),
        causation_ids=tuple(
            _string(entry, name="diagnostic causation_id") for entry in causation_ids
        ),
    )


def _cause_from_object(value: object) -> TradingEngineDiagnosticCause:
    item = _optional_fields(value, _CAUSE_FIELDS, name="diagnostic cause")
    missing = {"kind", "message"}.difference(item)
    if missing:
        raise ValueError(f"diagnostic cause fields differ: missing={sorted(missing)}, extra=[]")
    return TradingEngineDiagnosticCause(
        kind=_string(item["kind"], name="diagnostic cause kind", nonempty=True),
        message=_string(item["message"], name="diagnostic cause message"),
        operation=_optional_string(item.get("operation"), name="diagnostic cause operation"),
        target=_optional_string(item.get("target"), name="diagnostic cause target"),
    )


def _optional_fields(
    value: object,
    allowed: set[str],
    *,
    name: str,
    allow_additive: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    result = cast("dict[str, Any]", value)
    extra = sorted(set(result).difference(allowed))
    if extra and not allow_additive:
        raise ValueError(f"{name} fields differ: missing=[], extra={extra}")
    return {key: item for key, item in result.items() if key in allowed}


def _string(value: object, *, name: str, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if nonempty and not value:
        raise ValueError(f"{name} must be nonempty")
    return value


def _optional_string(value: object, *, name: str) -> str | None:
    return None if value is None else _string(value, name=name)


def _optional_quantity(value: object, *, name: str) -> int | None:
    return None if value is None else quantity_value(value, name=name, positive=True)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate Trading Engine diagnostic field: {key!r}")
        result[key] = value
    return result
