from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import ClassVar
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from persistra.domain import (
    ContentId,
    Duration,
    EffectiveInterval,
    EntityId,
    EventId,
    FixedClock,
    QualifiedName,
    SchemaVersion,
    SystemClock,
    TimeInterval,
    validate_instant,
)
from persistra.errors import (
    DurationOverflowError,
    InvalidContentIdError,
    InvalidDurationError,
    InvalidEntityIdError,
    InvalidInstantError,
    InvalidIntervalError,
    InvalidQualifiedNameError,
    NaiveDatetimeError,
    UnsupportedSchemaVersionError,
)


class FixtureId(EntityId):
    KIND: ClassVar[str] = "test"


class ChildFixtureId(FixtureId):
    pass


def test_ids_are_unique_uuid4_and_round_trip() -> None:
    ids = [FixtureId.new() for _ in range(10_000)]
    assert len(set(ids)) == 10_000
    assert all(item.value.version == 4 and item.value.int != 0 for item in ids)
    assert FixtureId.parse(ids[0].to_wire()) == ids[0]
    assert FixtureId.parse(str(ids[0].value)) == ids[0]
    assert FixtureId.parse(ids[0].value) == ids[0]
    assert FixtureId.parse(ids[0]) is ids[0]
    assert "kind='test'" in repr(ids[0])


def test_id_kind_and_order_boundaries() -> None:
    value = UUID("00000000-0000-4000-8000-000000000001")
    left = FixtureId(value)
    right = FixtureId(UUID("00000000-0000-4000-8000-000000000002"))
    assert left < right
    assert left != EventId(value)
    assert left != ChildFixtureId(value)
    with pytest.raises(TypeError):
        _ = left < EventId(value)
    for invalid in [UUID(int=0), "TEST:00000000-0000-4000-8000-000000000001"]:
        with pytest.raises(InvalidEntityIdError):
            FixtureId.parse(invalid)
    with pytest.raises(InvalidEntityIdError):
        FixtureId.parse(EventId(value))
    with pytest.raises(InvalidEntityIdError):
        FixtureId.parse("test:not-a-uuid")
    with pytest.raises(InvalidEntityIdError):
        FixtureId.parse(123)
    with pytest.raises(TypeError):
        EntityId(value)


def test_content_id_fips_vector_and_strict_parse() -> None:
    expected = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    content_id = ContentId.from_bytes(b"")
    assert content_id.to_wire() == expected
    assert ContentId.parse(expected) == content_id
    for invalid in [expected.upper(), expected[7:], "sha1:" + "0" * 40]:
        with pytest.raises(InvalidContentIdError):
            ContentId.parse(invalid)
    with pytest.raises(InvalidContentIdError):
        ContentId("sha256", b"short")
    with pytest.raises(InvalidContentIdError):
        ContentId.from_bytes("bytes")  # type: ignore[arg-type]


@given(st.from_regex(r"[a-z][a-z0-9_]{0,10}\.[a-z][a-z0-9_]{0,10}", fullmatch=True))
@pytest.mark.property
def test_qualified_name_property(text: str) -> None:
    assert str(QualifiedName(text)) == text


@pytest.mark.parametrize(
    "value",
    ["one", "Upper.case", "_private.name", "owner._private", "persistra._internal", "a."],
)
def test_qualified_name_rejects_invalid_values(value: str) -> None:
    with pytest.raises(InvalidQualifiedNameError):
        QualifiedName(value)


def test_schema_versions() -> None:
    assert int(SchemaVersion(1)) == 1
    assert str(SchemaVersion(2_147_483_647)) == "2147483647"
    for value in [0, -1, 2_147_483_648, True]:
        with pytest.raises(UnsupportedSchemaVersionError):
            SchemaVersion(value)


def test_instant_normalization_and_clocks() -> None:
    local = datetime(2026, 1, 1, 7, 30, tzinfo=timezone(timedelta(hours=-5)))
    expected = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)
    assert validate_instant(local) == expected
    assert FixedClock(local).now() == expected
    now = SystemClock().now()
    assert now.tzinfo is UTC
    with pytest.raises(NaiveDatetimeError):
        validate_instant(datetime(2026, 1, 1))
    with pytest.raises(InvalidInstantError) as caught:
        validate_instant("2026")
    assert caught.value.reason_code == "domain.time.invalid"


def test_duration_exact_arithmetic_and_boundaries() -> None:
    duration = Duration(timedelta(seconds=1, microseconds=5))
    assert duration.microseconds == 1_000_005
    assert duration.to_timedelta() == timedelta(seconds=1, microseconds=5)
    assert str(duration) == "1000005us"
    assert Duration.parse(str(duration)) == duration
    assert duration + Duration(5) == Duration(1_000_010)
    assert duration - Duration(5) == Duration(1_000_000)
    assert Duration(3) * 4 == Duration(12)
    assert Duration(12) // 3 == Duration(4)
    assert Duration(12) / 3 == Duration(4)
    for invalid in [-1, True, 1.5, "1us"]:
        with pytest.raises(InvalidDurationError):
            Duration(invalid)  # type: ignore[arg-type]
    with pytest.raises(DurationOverflowError):
        Duration(2**63)
    with pytest.raises(InvalidDurationError):
        _ = Duration(1) - Duration(2)
    with pytest.raises(InvalidDurationError):
        _ = Duration(5) // 2
    with pytest.raises(InvalidDurationError):
        Duration.parse("5ms")


def test_malformed_timezone_is_a_typed_instant_error() -> None:
    class BrokenTimezone(tzinfo):
        def utcoffset(self, value: datetime | None) -> timedelta | None:
            raise ValueError("broken timezone")

        def dst(self, value: datetime | None) -> timedelta | None:
            return None

    with pytest.raises(InvalidInstantError):
        validate_instant(datetime(2026, 1, 1, tzinfo=BrokenTimezone()))


def test_half_open_intervals() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    middle = start + timedelta(hours=1)
    end = start + timedelta(hours=2)
    interval = TimeInterval(start, middle)
    adjacent = TimeInterval(middle, end)
    assert interval.contains(start)
    assert not interval.contains(middle)
    assert not interval.overlaps(adjacent)
    assert EffectiveInterval(start).contains(end)
    assert EffectiveInterval(start, middle).overlaps(EffectiveInterval(start, end))
    assert not EffectiveInterval(start, middle).overlaps(EffectiveInterval(middle))
    with pytest.raises(InvalidIntervalError):
        TimeInterval(start, start)
    with pytest.raises(InvalidIntervalError):
        EffectiveInterval(end, start)
