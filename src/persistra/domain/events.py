"""Immutable domain-event envelopes and explicit project-owned codecs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast

from persistra.domain.errors import InvalidEventError, UnknownEventTypeError
from persistra.domain.identity import ContentId, EntityId, EventId, QualifiedName, SchemaVersion
from persistra.domain.numbers import (
    Currency,
    Money,
    NonNegativeQuantity,
    Price,
    Quantity,
    Rate,
    Unit,
)
from persistra.domain.serialization import canonical_bytes
from persistra.domain.time import Duration, validate_instant


@dataclass(frozen=True, slots=True, init=False)
class EventType:
    """Qualified event name paired with an immutable payload schema version."""

    name: QualifiedName
    version: SchemaVersion

    def __init__(self, name: QualifiedName | str, version: SchemaVersion | int) -> None:
        normalized_name = name if isinstance(name, QualifiedName) else QualifiedName(name)
        normalized_version = (
            version if isinstance(version, SchemaVersion) else SchemaVersion(version)
        )
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "version", normalized_version)

    def to_wire(self) -> str:
        """Return ``<qualified-name>@<version>``."""
        return f"{self.name}@{self.version}"

    def __str__(self) -> str:
        return self.to_wire()


@dataclass(frozen=True, slots=True)
class DomainEvent[PayloadT]:
    """Immutable, versioned lifecycle fact produced by a managed service."""

    event_id: EventId
    event_type: EventType
    event_at: datetime
    available_at: datetime
    recorded_at: datetime
    aggregate_kind: QualifiedName
    aggregate_id: EntityId
    aggregate_sequence: int
    payload: PayloadT
    correlation_id: EventId | None = None
    causation_id: EventId | None = None

    def __post_init__(self) -> None:
        raw_event_id = cast("object", self.event_id)
        raw_aggregate_id = cast("object", self.aggregate_id)
        if not isinstance(raw_event_id, EventId) or not isinstance(raw_aggregate_id, EntityId):
            raise InvalidEventError("event and aggregate identities are required")
        raw_event_type = cast("object", self.event_type)
        raw_aggregate_kind = cast("object", self.aggregate_kind)
        if not isinstance(raw_event_type, EventType) or not isinstance(
            raw_aggregate_kind, QualifiedName
        ):
            raise InvalidEventError("event type and aggregate kind are required")
        if isinstance(self.aggregate_sequence, bool) or self.aggregate_sequence <= 0:
            raise InvalidEventError("aggregate sequence must be positive")
        params = getattr(type(self.payload), "__dataclass_params__", None)
        if not is_dataclass(self.payload) or params is None or not params.frozen:
            raise InvalidEventError("event payload must be a frozen dataclass")
        _validate_immutable(self.payload)
        for linked in (self.correlation_id, self.causation_id):
            raw_link = cast("object", linked)
            if raw_link is not None and not isinstance(raw_link, EventId):
                raise InvalidEventError("event links must be EventId values")
        object.__setattr__(self, "event_at", validate_instant(self.event_at))
        object.__setattr__(self, "available_at", validate_instant(self.available_at))
        object.__setattr__(self, "recorded_at", validate_instant(self.recorded_at))


Encoder = Callable[[Any], dict[str, Any]]
Decoder = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class _Codec:
    payload_type: type[Any]
    encoder: Encoder
    decoder: Decoder


class EventRegistry:
    """Explicit, instance-owned event codec registry with no import side effects."""

    def __init__(self) -> None:
        self._codecs: dict[EventType, _Codec] = {}
        self._frozen = False

    def register(
        self,
        *,
        event_type: EventType,
        payload_type: type[Any],
        encoder: Encoder,
        decoder: Decoder,
    ) -> None:
        """Register an immutable payload codec, rejecting conflicting duplicates."""
        if self._frozen:
            raise InvalidEventError("event registry is immutable after freeze")
        params = getattr(payload_type, "__dataclass_params__", None)
        if not is_dataclass(payload_type) or params is None or not params.frozen:
            raise InvalidEventError("registered payload type must be a frozen dataclass")
        codec = _Codec(payload_type, encoder, decoder)
        existing = self._codecs.get(event_type)
        if existing is not None and existing != codec:
            raise InvalidEventError("event type already has a different codec")
        self._codecs[event_type] = codec

    def freeze(self) -> None:
        """Prevent subsequent codec registration for project service construction."""
        self._frozen = True

    def encode(self, event_type: EventType, payload: Any) -> bytes:
        """Encode one registered payload as bounded canonical JSON."""
        codec = self._codecs.get(event_type)
        if codec is None:
            raise UnknownEventTypeError(f"event type {event_type} is not registered")
        if type(payload) is not codec.payload_type:
            raise InvalidEventError("payload type does not match registered event type")
        _validate_immutable(payload)
        raw_value = cast("object", codec.encoder(payload))
        if not isinstance(raw_value, dict):
            raise InvalidEventError("event encoder must return a top-level object")
        value = cast("dict[str, Any]", raw_value)
        _validate_depth(value)
        encoded = canonical_bytes(value)
        if len(encoded) > 1_048_576:
            raise InvalidEventError("event payload exceeds 1 MiB")
        return encoded

    def decode(self, event_type: EventType, payload: bytes) -> Any:
        """Decode bounded canonical JSON through an explicitly registered codec."""
        codec = self._codecs.get(event_type)
        if codec is None:
            raise UnknownEventTypeError(f"event type {event_type} is not registered")
        if len(payload) > 1_048_576:
            raise InvalidEventError("event payload must be at most 1 MiB of bytes")
        try:
            value = json.loads(
                payload,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_unique_json_object,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise InvalidEventError("event payload is not valid UTF-8 JSON") from error
        if not isinstance(value, dict):
            raise InvalidEventError("event payload must be a top-level object")
        typed_value = cast("dict[str, Any]", value)
        _validate_depth(typed_value)
        if canonical_bytes(typed_value) != payload:
            raise InvalidEventError("event payload is not canonical JSON")
        try:
            decoded = codec.decoder(typed_value)
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidEventError("event payload does not match its registered schema") from error
        if type(decoded) is not codec.payload_type:
            raise InvalidEventError("decoder returned the wrong payload type")
        _validate_immutable(decoded)
        return decoded

    def decoder_fingerprint(self, event_type: EventType) -> str:
        """Return a stable diagnostic fingerprint of a registered codec identity."""
        codec = self._codecs.get(event_type)
        if codec is None:
            raise UnknownEventTypeError(f"event type {event_type} is not registered")
        identities = (codec.payload_type, codec.encoder, codec.decoder)
        material = "|".join(f"{item.__module__}.{item.__qualname__}" for item in identities)
        return hashlib.sha256(material.encode()).hexdigest()


def _validate_immutable(value: Any) -> None:
    scalar_types = (
        bool
        | int
        | str
        | bytes
        | Decimal
        | date
        | datetime
        | Enum
        | EntityId
        | ContentId
        | QualifiedName
        | SchemaVersion
        | Currency
        | Money
        | Price
        | Quantity
        | NonNegativeQuantity
        | Rate
        | Unit
        | Duration
    )
    if value is None or isinstance(value, scalar_types):
        return
    if isinstance(value, tuple):
        sequence = cast("tuple[Any, ...]", value)
        for item in sequence:
            _validate_immutable(item)
        return
    if is_dataclass(value) and not isinstance(value, type):
        params = getattr(type(value), "__dataclass_params__", None)
        if params is None or not params.frozen:
            raise InvalidEventError("nested event dataclasses must be frozen")
        for field in fields(value):
            _validate_immutable(getattr(value, field.name))
        return
    raise InvalidEventError("event payload contains mutable or unsupported state")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _validate_depth(value: Any, depth: int = 1) -> None:
    if depth > 32:
        raise InvalidEventError("event payload exceeds maximum nesting depth")
    if isinstance(value, dict):
        mapping = cast("dict[object, Any]", value)
        for item in mapping.values():
            _validate_depth(item, depth + 1)
    elif isinstance(value, list):
        sequence = cast("list[Any]", value)
        for item in sequence:
            _validate_depth(item, depth + 1)
