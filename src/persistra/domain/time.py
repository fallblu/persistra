"""UTC instants, elapsed durations, half-open intervals, and injected clocks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, Self

from persistra.domain.errors import (
    DurationOverflowError,
    InvalidDurationError,
    InvalidInstantError,
    InvalidIntervalError,
    NaiveDatetimeError,
)

_MAX_DURATION = 9_223_372_036_854_775_807


class AvailabilityQuality(StrEnum):
    """Evidence quality for a revision-specific availability instant."""

    OBSERVED = "observed"
    POLICY_DERIVED = "policy_derived"
    INGESTION_BOUNDED = "ingestion_bounded"
    UNKNOWN = "unknown"


def validate_instant(value: object) -> datetime:
    """Return an aware instant normalized to UTC at microsecond precision."""
    if not isinstance(value, datetime):
        raise InvalidInstantError("instant must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise NaiveDatetimeError("instant must have an explicit timezone")
        return value.astimezone(UTC)
    except NaiveDatetimeError:
        raise
    except (OverflowError, ValueError) as error:
        raise InvalidInstantError("instant cannot be normalized to UTC") from error


@dataclass(frozen=True, slots=True, init=False)
class Duration:
    """Nonnegative fixed elapsed time in integer microseconds."""

    microseconds: int

    def __init__(self, value: object) -> None:
        if isinstance(value, bool):
            raise InvalidDurationError("duration cannot be boolean")
        if isinstance(value, timedelta):
            micros = (value.days * 86_400 + value.seconds) * 1_000_000 + value.microseconds
        elif isinstance(value, int):
            micros = value
        else:
            raise InvalidDurationError("duration must be integer microseconds or timedelta")
        if micros < 0:
            raise InvalidDurationError("duration cannot be negative")
        if micros > _MAX_DURATION:
            raise DurationOverflowError("duration exceeds signed 64-bit microseconds")
        object.__setattr__(self, "microseconds", micros)

    @classmethod
    def parse(cls, value: object) -> Self:
        """Parse the canonical ``<integer>us`` representation."""
        if not isinstance(value, str) or not value.endswith("us") or not value[:-2].isdigit():
            raise InvalidDurationError("duration text is not canonical")
        return cls(int(value[:-2]))

    def to_timedelta(self) -> timedelta:
        """Convert exactly to ``datetime.timedelta`` when representable."""
        try:
            return timedelta(microseconds=self.microseconds)
        except OverflowError as error:
            raise DurationOverflowError("duration does not fit timedelta") from error

    def __str__(self) -> str:
        return f"{self.microseconds}us"

    def __add__(self, other: object) -> Duration:
        if not isinstance(other, Duration):
            return NotImplemented
        return Duration(self.microseconds + other.microseconds)

    def __sub__(self, other: object) -> Duration:
        if not isinstance(other, Duration):
            return NotImplemented
        result = self.microseconds - other.microseconds
        if result < 0:
            raise InvalidDurationError("duration subtraction cannot be negative")
        return Duration(result)

    def __mul__(self, operand: object) -> Duration:
        if isinstance(operand, bool) or not isinstance(operand, int):
            return NotImplemented
        return Duration(self.microseconds * operand)

    def __floordiv__(self, operand: object) -> Duration:
        if isinstance(operand, bool) or not isinstance(operand, int) or operand <= 0:
            raise InvalidDurationError("duration divisor must be a positive integer")
        quotient, remainder = divmod(self.microseconds, operand)
        if remainder:
            raise InvalidDurationError("duration division must be exact")
        return Duration(quotient)

    def __truediv__(self, operand: object) -> Duration:
        """Divide by a positive integer only when microseconds remain exact."""
        return self.__floordiv__(operand)


@dataclass(frozen=True, slots=True)
class TimeInterval:
    """A nonempty half-open UTC interval ``[start, end)``."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = validate_instant(self.start)
        end = validate_instant(self.end)
        if start >= end:
            raise InvalidIntervalError("interval start must precede end")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def contains(self, value: datetime) -> bool:
        """Return whether an instant belongs to this half-open interval."""
        instant = validate_instant(value)
        return self.start <= instant < self.end

    def overlaps(self, other: TimeInterval) -> bool:
        """Return whether two intervals share positive duration."""
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True, slots=True)
class EffectiveInterval:
    """A half-open effective interval with an optional unbounded future."""

    valid_from: datetime
    valid_to: datetime | None = None

    def __post_init__(self) -> None:
        start = validate_instant(self.valid_from)
        end = None if self.valid_to is None else validate_instant(self.valid_to)
        if end is not None and start >= end:
            raise InvalidIntervalError("effective interval start must precede end")
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_to", end)

    def contains(self, value: datetime) -> bool:
        """Return whether an instant belongs to this effective interval."""
        instant = validate_instant(value)
        return self.valid_from <= instant and (self.valid_to is None or instant < self.valid_to)

    def overlaps(self, other: EffectiveInterval) -> bool:
        """Return whether two effective intervals share positive duration."""
        return (self.valid_to is None or other.valid_from < self.valid_to) and (
            other.valid_to is None or self.valid_from < other.valid_to
        )


class Clock(Protocol):
    """Clock dependency for state-changing services."""

    def now(self) -> datetime:
        """Return the current UTC instant."""
        ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    """Clock backed by the operating-system wall clock."""

    def now(self) -> datetime:
        """Return current UTC wall-clock time."""
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Deterministic clock that always returns one validated instant."""

    instant: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instant", validate_instant(self.instant))

    def now(self) -> datetime:
        """Return the configured instant."""
        return self.instant


def utc_now() -> datetime:
    """Return UTC now for non-identity-bearing convenience code."""
    return SystemClock().now()
