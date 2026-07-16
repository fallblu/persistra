from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

import pytest

from persistra.domain import (
    DomainEvent,
    EntityId,
    EventId,
    EventType,
    Money,
    QualifiedName,
    SeedSpec,
)
from persistra.domain.events import EventRegistry
from persistra.domain.serialization import canonical_bytes, canonical_value, scoped_content_id
from persistra.errors import InvalidEventError, UnknownEventTypeError


class AggregateId(EntityId):
    KIND: ClassVar[str] = "aggregate"


@dataclass(frozen=True, slots=True)
class Payload:
    text: str
    amount: int


def encode_payload(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, Payload)
    return {"text": payload.text, "amount": payload.amount}


def decode_payload(value: dict[str, Any]) -> Payload:
    return Payload(text=str(value["text"]), amount=int(value["amount"]))


def test_canonical_serialization_is_stable_and_scoped() -> None:
    assert canonical_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert canonical_bytes("e\u0301") == '"é"'.encode()
    instant = datetime(1, 1, 2, 3, 4, 5, 6, tzinfo=UTC)
    assert canonical_value(instant) == "0001-01-02T03:04:05.000006Z"
    assert canonical_value(Money("1", "USD")) == {
        "amount": "1.000000000000",
        "currency": "USD",
    }
    assert str(scoped_content_id({"schema": "owner.value", "version": 1})).startswith("sha256:")
    with pytest.raises(TypeError):
        canonical_bytes(1.2)
    with pytest.raises(TypeError):
        canonical_bytes(Decimal("1"))
    with pytest.raises(TypeError):
        canonical_bytes({1, 2})
    with pytest.raises(TypeError):
        canonical_bytes({"é": 1, "e\u0301": 2})


def test_event_type_envelope_and_registry_round_trip() -> None:
    event_type = EventType("persistra.test.recorded", 1)
    payload = Payload("ok", 2)
    registry = EventRegistry()
    registry.register(
        event_type=event_type,
        payload_type=Payload,
        encoder=encode_payload,
        decoder=decode_payload,
    )
    registry.register(
        event_type=event_type,
        payload_type=Payload,
        encoder=encode_payload,
        decoder=decode_payload,
    )
    encoded = registry.encode(event_type, payload)
    assert encoded == b'{"amount":2,"text":"ok"}'
    assert registry.decode(event_type, encoded) == payload
    assert len(registry.decoder_fingerprint(event_type)) == 64
    now = datetime(2026, 1, 1, tzinfo=UTC)
    event = DomainEvent(
        event_id=EventId.new(),
        event_type=event_type,
        event_at=now,
        available_at=now,
        recorded_at=now,
        aggregate_kind=QualifiedName("project.aggregate"),
        aggregate_id=AggregateId.new(),
        aggregate_sequence=1,
        payload=payload,
    )
    assert event.aggregate_sequence == 1
    registry.freeze()
    with pytest.raises(InvalidEventError):
        registry.register(
            event_type=EventType("persistra.test.other", 1),
            payload_type=Payload,
            encoder=encode_payload,
            decoder=decode_payload,
        )


def test_event_registry_and_envelope_rejections() -> None:
    registry = EventRegistry()
    unknown = EventType("persistra.test.unknown", 1)
    with pytest.raises(UnknownEventTypeError):
        registry.encode(unknown, Payload("x", 1))
    with pytest.raises(UnknownEventTypeError):
        registry.decode(unknown, b"{}")
    with pytest.raises(UnknownEventTypeError):
        registry.decoder_fingerprint(unknown)

    @dataclass(frozen=True)
    class MutablePayload:
        values: list[int]

    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(InvalidEventError):
        DomainEvent(
            EventId.new(),
            unknown,
            now,
            now,
            now,
            QualifiedName("project.aggregate"),
            AggregateId.new(),
            1,
            MutablePayload([]),
        )
    with pytest.raises(InvalidEventError):
        DomainEvent(
            EventId.new(),
            unknown,
            now,
            now,
            now,
            QualifiedName("project.aggregate"),
            AggregateId.new(),
            0,
            Payload("x", 1),
        )


def test_seed_stream_is_fixed_and_partition_independent() -> None:
    seed = SeedSpec(20250300)
    draws = [seed.draw("fixture", "prices", counter=index) for index in range(3)]
    assert draws == [seed.draw("fixture", "prices", counter=index) for index in range(3)]
    assert len(set(draws)) == 3
    assert SeedSpec.GENERATOR == "persistra.seed.sha256_counter@1"
    with pytest.raises(ValueError):
        SeedSpec(-1)
    with pytest.raises(ValueError):
        seed.draw(counter=0)
    with pytest.raises(ValueError):
        seed.draw("x", counter=-1)
