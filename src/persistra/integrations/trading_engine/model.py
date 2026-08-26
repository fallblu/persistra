"""Shared typed values for the current Trading Engine v1 contract."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from persistra.integrations.trading_engine._scalars import (
    decimal_value,
    execution_quantity,
    identifier,
    quantity_value,
)

if TYPE_CHECKING:
    from pathlib import Path

    from persistra.integrations.trading_engine.contracts import TradingEngineContractSchemas

type MissingBarVolumePolicy = Literal["reject", "zero_impact"]

TRADING_ENGINE_CONTRACT_VERSION: Final = "1"
_STRATEGY_PROTOCOL_MAX_MESSAGE_BYTES: Final = 1_048_576
_TRADING_ENGINE_DIAGNOSTIC_PHASES: Final = {
    "cli",
    "input",
    "validation",
    "replay",
    "reducer",
    "strategy",
    "artifact",
}


@dataclass(frozen=True, slots=True)
class EngineResourceLimits:
    """Versioned inclusive resource ceilings advertised by an engine."""

    version: str
    scenario_record_bytes: int
    strategy_message_bytes: int
    internal_events: int
    catalog_instruments: int
    intents_per_batch: int
    artifact_record_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", identifier(self.version, name="resource limit version"))
        for name in (
            "scenario_record_bytes",
            "strategy_message_bytes",
            "internal_events",
            "catalog_instruments",
            "intents_per_batch",
            "artifact_record_bytes",
        ):
            value = cast("object", getattr(self, name))
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """Machine-readable compatibility surface advertised by an engine executable."""

    engine_version: str
    scenario_contract_versions: tuple[str, ...]
    journal_contract_versions: tuple[str, ...]
    scenario_formats: tuple[str, ...]
    journal_formats: tuple[str, ...]
    execution_models: tuple[str, ...]
    strategy_protocol_versions: tuple[str, ...]
    resource_limits: EngineResourceLimits | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "engine_version",
            identifier(self.engine_version, name="engine_version"),
        )
        for name in (
            "scenario_contract_versions",
            "journal_contract_versions",
            "scenario_formats",
            "journal_formats",
            "execution_models",
            "strategy_protocol_versions",
        ):
            raw = cast("object", getattr(self, name))
            if not isinstance(raw, tuple):
                raise TypeError(f"{name} must be a tuple")
            values = tuple(identifier(item, name=name) for item in cast("tuple[object, ...]", raw))
            if not values:
                raise ValueError(f"{name} must not be empty")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, values)
        resource_limits = cast("object", self.resource_limits)
        if resource_limits is not None and not isinstance(resource_limits, EngineResourceLimits):
            raise TypeError("resource_limits must be EngineResourceLimits or None")


@dataclass(frozen=True, slots=True)
class TradingEngineDiagnosticContext:
    """Typed location and causality fields from one engine diagnostic."""

    json_path: str | None = None
    line: int | None = None
    sequence: int | None = None
    event_id: str | None = None
    order_id: str | None = None
    causation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        raw_json_path = cast("object", self.json_path)
        if raw_json_path is not None and not isinstance(raw_json_path, str):
            raise TypeError("diagnostic json_path must be a string or None")
        for name in ("line", "sequence"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    quantity_value(value, name=f"diagnostic {name}", positive=True),
                )
        for name in ("event_id", "order_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, identifier(value, name=f"diagnostic {name}"))
        if not isinstance(cast("object", self.causation_ids), tuple):
            raise TypeError("diagnostic causation_ids must be a tuple")
        object.__setattr__(
            self,
            "causation_ids",
            tuple(
                identifier(value, name="diagnostic causation_id") for value in self.causation_ids
            ),
        )


@dataclass(frozen=True, slots=True)
class TradingEngineDiagnosticCause:
    """Sanitized exception cause supplied by Trading Engine."""

    kind: str
    message: str
    operation: str | None = None
    target: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", identifier(self.kind, name="diagnostic cause kind"))
        if not isinstance(cast("object", self.message), str):
            raise TypeError("diagnostic cause message must be a string")
        for name in ("operation", "target"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"diagnostic cause {name} must be a string or None")


@dataclass(frozen=True, slots=True)
class TradingEngineDiagnostic:
    """Version-1 machine-readable failure reported by Trading Engine."""

    version: str
    code: str
    phase: str
    message: str
    context: TradingEngineDiagnosticContext
    cause: TradingEngineDiagnosticCause | None = None

    def __post_init__(self) -> None:
        if self.version != "1":
            raise ValueError(f"unsupported Trading Engine diagnostic version: {self.version!r}")
        object.__setattr__(self, "code", identifier(self.code, name="diagnostic code"))
        if "." not in self.code:
            raise ValueError("Trading Engine diagnostic code must be namespaced")
        if self.phase not in _TRADING_ENGINE_DIAGNOSTIC_PHASES:
            raise ValueError(f"unsupported Trading Engine diagnostic phase: {self.phase!r}")
        raw_message = cast("object", self.message)
        if not isinstance(raw_message, str) or not raw_message:
            raise ValueError("Trading Engine diagnostic message must be a nonempty string")
        if not isinstance(cast("object", self.context), TradingEngineDiagnosticContext):
            raise TypeError("diagnostic context must be TradingEngineDiagnosticContext")
        raw_cause = cast("object", self.cause)
        if raw_cause is not None and not isinstance(raw_cause, TradingEngineDiagnosticCause):
            raise TypeError("diagnostic cause must be TradingEngineDiagnosticCause or None")


@dataclass(frozen=True, slots=True)
class StrategyResponseEvidence:
    """Bounded raw response bytes retained after protocol rejection."""

    prefix: bytes
    observed_bytes: int
    truncated: bool

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.prefix), bytes):
            raise TypeError("strategy response evidence prefix must be bytes")
        if len(self.prefix) > 256:
            raise ValueError("strategy response evidence prefix exceeds 256 bytes")
        observed = quantity_value(self.observed_bytes, name="strategy response observed_bytes")
        if observed > _STRATEGY_PROTOCOL_MAX_MESSAGE_BYTES + 1:
            raise ValueError("strategy response observed_bytes exceeds the diagnostic bound")
        if observed < len(self.prefix):
            raise ValueError("strategy response evidence exceeds observed bytes")
        if not isinstance(cast("object", self.truncated), bool):
            raise TypeError("strategy response evidence truncated must be a boolean")
        if self.truncated != (observed > len(self.prefix)):
            raise ValueError("strategy response evidence truncation is inconsistent")
        object.__setattr__(self, "observed_bytes", observed)


@dataclass(frozen=True, slots=True)
class StrategyResponseRejection:
    """Version-1 diagnostic record ending one failed strategy transcript."""

    version: str
    transcript_sequence: int
    expected_strategy_sequence: int
    diagnostic: TradingEngineDiagnostic
    evidence: StrategyResponseEvidence

    def __post_init__(self) -> None:
        if self.version != "1":
            raise ValueError(f"unsupported strategy diagnostic version: {self.version!r}")
        transcript_sequence = quantity_value(
            self.transcript_sequence,
            name="rejection transcript_sequence",
            positive=True,
        )
        expected_sequence = quantity_value(
            self.expected_strategy_sequence,
            name="rejection expected_strategy_sequence",
            positive=True,
        )
        if transcript_sequence != expected_sequence * 2:
            raise ValueError("rejection transcript and strategy sequences do not reconcile")
        if not isinstance(cast("object", self.diagnostic), TradingEngineDiagnostic):
            raise TypeError("rejection diagnostic must be TradingEngineDiagnostic")
        if self.diagnostic.context.sequence != expected_sequence:
            raise ValueError("rejection diagnostic sequence does not match its response")
        if not isinstance(cast("object", self.evidence), StrategyResponseEvidence):
            raise TypeError("rejection evidence must be StrategyResponseEvidence")
        object.__setattr__(self, "transcript_sequence", transcript_sequence)
        object.__setattr__(self, "expected_strategy_sequence", expected_sequence)


@dataclass(frozen=True, slots=True)
class ExecutionInstrument:
    """Executable metadata supplied separately from research identity."""

    instrument_id: str
    symbol: str
    quote_currency: str
    tick_size: Decimal | str | int | float
    lot_size: Decimal | str | int | float = Decimal(1)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        object.__setattr__(self, "symbol", identifier(self.symbol, name="symbol"))
        object.__setattr__(
            self,
            "quote_currency",
            identifier(self.quote_currency, name="quote_currency"),
        )
        object.__setattr__(
            self,
            "tick_size",
            decimal_value(self.tick_size, name="tick_size", positive=True),
        )
        object.__setattr__(
            self,
            "lot_size",
            execution_quantity(self.lot_size, name="lot_size", positive=True),
        )


@dataclass(frozen=True, slots=True)
class ConservativeBarExecutionPolicy:
    """Current next-open or adverse-touch completed-bar configuration."""

    model: Literal["completed_bar_next_open_v1", "completed_bar_adverse_touch_v1"]
    participation_bps: int
    fee_schedules: tuple[Mapping[str, object], ...]
    half_spread_bps: int = 0
    impact_coefficient_bps: int = 0
    missing_volume_policy: MissingBarVolumePolicy = "reject"
    configuration_version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        if self.model not in {
            "completed_bar_next_open_v1",
            "completed_bar_adverse_touch_v1",
        }:
            raise ValueError("unsupported conservative bar execution model")
        for name in ("participation_bps", "half_spread_bps", "impact_coefficient_bps"):
            value = quantity_value(getattr(self, name), name=name)
            if value > 10_000:
                raise ValueError(f"{name} must not exceed 10000")
            object.__setattr__(self, name, value)
        raw_schedules = cast("object", self.fee_schedules)
        if not isinstance(raw_schedules, tuple) or not raw_schedules:
            raise ValueError("fee_schedules must be a nonempty tuple")
        schedule_values = cast("tuple[object, ...]", raw_schedules)
        if any(not isinstance(schedule, Mapping) for schedule in schedule_values):
            raise TypeError("fee_schedules entries must be mappings")
        object.__setattr__(
            self,
            "fee_schedules",
            tuple(
                _freeze_mapping(cast("Mapping[object, object]", schedule))
                for schedule in schedule_values
            ),
        )
        if self.missing_volume_policy not in {"reject", "zero_impact"}:
            raise ValueError("unsupported missing-volume policy")

    def require_contract(self, schemas: TradingEngineContractSchemas) -> None:
        """Reject a schema set that does not declare this execution model."""
        if schemas.version != TRADING_ENGINE_CONTRACT_VERSION:
            raise ValueError("conservative execution requires Trading Engine contract v1")
        if self.model not in schemas.execution_models:
            raise ValueError(
                f"execution model {self.model!r} requires a compatible contract version"
            )

    def to_contract_payload(self) -> dict[str, object]:
        """Return the current execution object for schema-backed scenario assembly."""
        return {
            "model": self.model,
            "configuration": {
                "version": self.configuration_version,
                "participation_bps": self.participation_bps,
                "fee_schedules": [_thaw_mapping(schedule) for schedule in self.fee_schedules],
                "spread_model": {
                    "model": "fixed_half_spread_v1",
                    "half_spread_bps": self.half_spread_bps,
                },
                "impact_model": {
                    "model": "linear_participation_v1",
                    "coefficient_bps": self.impact_coefficient_bps,
                    "missing_volume_policy": self.missing_volume_policy,
                },
            },
        }


@dataclass(slots=True)
class TradingEngineProcessError(RuntimeError):
    """A validation or replay subprocess failed."""

    message: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    journal_path: Path | None = field(default=None)
    strategy_transcript_path: Path | None = field(default=None)
    diagnostic: TradingEngineDiagnostic | None = field(default=None)
    strategy_rejection: StrategyResponseRejection | None = field(default=None)

    def __str__(self) -> str:
        return self.message


def _freeze_mapping(value: Mapping[object, object]) -> Mapping[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("configuration keys must be strings")
        result[key] = _freeze_value(item)
    return MappingProxyType(result)


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(cast("Mapping[object, object]", value))
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in cast("Sequence[object]", value))
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("configuration numbers must be finite")
        return value
    raise TypeError("configuration must contain JSON-compatible values")


def _thaw_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _thaw_value(item) for key, item in value.items()}


def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _thaw_mapping(cast("Mapping[str, object]", value))
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in cast("Sequence[object]", value)]
    return value
