"""Structural validation for Trading Engine journal records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pandas as pd

from persistra.integrations.trading_engine._scalars import (
    exact_fields,
    identifier,
    quantity_value,
    rfc3339_string,
)
from persistra.integrations.trading_engine.model import (
    TRADING_ENGINE_CONTRACT_VERSION,
    ExecutionModel,
)

EVENT_FIELDS = {
    "contract_version",
    "engine_sequence",
    "event_id",
    "causation_ids",
    "run_id",
    "recorded_at",
    "event_type",
    "payload",
}


@dataclass(frozen=True, slots=True)
class JournalEnvelope:
    """Validated fields shared by every journal event."""

    engine_sequence: int
    event_id: str
    run_id: str
    recorded_at: pd.Timestamp
    event_type: str
    payload: object


def envelope(record: object, *, line_number: int) -> JournalEnvelope:
    """Validate one versioned journal envelope."""
    item = exact_fields(record, EVENT_FIELDS, name=f"journal record {line_number}")
    if item["contract_version"] != TRADING_ENGINE_CONTRACT_VERSION:
        raise ValueError(
            "unsupported journal contract_version "
            f"{item['contract_version']!r} "
            f"(expected {TRADING_ENGINE_CONTRACT_VERSION!r})"
        )
    engine_sequence = quantity_value(
        item["engine_sequence"], name="engine_sequence", positive=True
    )
    run_id = identifier(item["run_id"], name="run_id")
    event_id = identifier(item["event_id"], name="event_id")
    return JournalEnvelope(
        engine_sequence=engine_sequence,
        event_id=event_id,
        run_id=run_id,
        recorded_at=timestamp(item["recorded_at"], name="recorded_at"),
        event_type=identifier(item["event_type"], name="event_type"),
        payload=item["payload"],
    )


def execution_model(value: object) -> ExecutionModel:
    """Validate the execution model supported by this importer."""
    model = identifier(value, name="execution_model")
    if model != "completed_bar_v1":
        raise ValueError(f"unsupported execution model {model!r}")
    return model


def causation_ids(
    value: object,
    *,
    run_id: str,
    engine_sequence: int,
    seen_event_ids: set[str],
) -> tuple[str, ...]:
    """Validate canonical backward-only causal references."""
    if not isinstance(value, list):
        raise ValueError("causation_ids must be an array")
    causes = tuple(
        identifier(item, name="causation_id")
        for item in cast("list[object]", value)
    )
    if len(causes) != len(set(causes)):
        raise ValueError("causation_ids must not contain duplicates")
    if causes != tuple(sorted(causes)):
        raise ValueError("causation_ids must use canonical event identifier order")
    prefix = f"{run_id}-event-"
    for cause in causes:
        if cause in seen_event_ids:
            continue
        if not cause.startswith(prefix):
            raise ValueError("causation_ids must not reference another run")
        suffix = cause.removeprefix(prefix)
        if len(suffix) == 12 and suffix.isdigit() and int(suffix) >= engine_sequence:
            raise ValueError("causation_ids must not reference a forward event")
        raise ValueError("causation_ids must reference known prior events")
    return causes


def timestamp(value: object, *, name: str) -> pd.Timestamp:
    """Parse one canonical RFC 3339 timestamp."""
    text = rfc3339_string(value, name=name)
    try:
        result = pd.Timestamp(text)
    except ValueError as error:
        raise ValueError(f"{name} must be an RFC3339 timestamp") from error
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    result = result.tz_convert("UTC")
    if result.nanosecond % 1_000:
        raise ValueError(f"{name} must not exceed microsecond precision")
    return result


def choice(value: object, choices: set[str], *, name: str) -> str:
    """Require a string from a closed vocabulary."""
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"unsupported {name}")
    return value


def json_integer(value: object, *, name: str, positive: bool = False) -> int:
    """Require an exact JSON integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a JSON integer")
    if value < 0 or (positive and value == 0):
        requirement = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be {requirement}")
    return value
