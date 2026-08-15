"""Checked scalar conversions for the trading-engine boundary."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from numbers import Integral, Real
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from typing import Any

MICRO_SCALE = 1_000_000
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


def decimal_value(
    value: object,
    *,
    name: str,
    positive: bool = False,
    nonnegative: bool = False,
) -> Decimal:
    """Return a finite decimal with at most six fractional places."""
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a decimal number")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (Integral, Real, str)):
        try:
            result = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError(f"{name} must be a decimal number") from error
    else:
        raise TypeError(f"{name} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    micros = result * MICRO_SCALE
    if micros != micros.to_integral_value():
        raise ValueError(f"{name} must have at most six decimal places")
    if positive and result <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be nonnegative")
    integer = int(micros)
    if integer < INT64_MIN or integer > INT64_MAX:
        raise ValueError(f"{name} is outside the supported range")
    return result


def decimal_micros(value: Decimal) -> int:
    """Return exact integer micros for a checked decimal."""
    return int(value * MICRO_SCALE)


def decimal_string(value: Decimal) -> str:
    """Return the engine's canonical fixed-point decimal form."""
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return "0" if result in {"", "-0"} else result


def quantity_value(value: object, *, name: str, positive: bool = False) -> int:
    """Return a checked nonnegative whole int64 quantity."""
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a whole number")
    if isinstance(value, Integral):
        result = int(value)
    elif isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError(f"{name} must be a whole number")
        result = int(value)
    elif isinstance(value, Real):
        numeric = float(value)
        if not numeric.is_integer():
            raise ValueError(f"{name} must be a whole number")
        result = int(numeric)
    elif isinstance(value, str):
        if not value or value.strip() != value:
            raise ValueError(f"{name} must be a whole number")
        try:
            result = int(value)
        except ValueError as error:
            raise ValueError(f"{name} must be a whole number") from error
        if str(result) != value:
            raise ValueError(f"{name} must be a canonical whole number")
    else:
        raise TypeError(f"{name} must be a whole number")
    if result < 0:
        raise ValueError(f"{name} must be nonnegative")
    if positive and result == 0:
        raise ValueError(f"{name} must be positive")
    if result > INT64_MAX:
        raise ValueError(f"{name} is outside the supported range")
    return result


def identifier(value: object, *, name: str) -> str:
    """Validate an engine identifier or nonempty label."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{name} must not be empty or padded with whitespace")
    if any(ord(character) < 0x21 or ord(character) == 0x7F for character in value):
        raise ValueError(f"{name} must not contain whitespace or control characters")
    return value


def exact_fields(value: object, expected: set[str], *, name: str) -> dict[str, Any]:
    """Validate and narrow an exact JSON object."""
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    result = cast("dict[str, Any]", value)
    if set(result) != expected:
        missing = sorted(expected.difference(result))
        extra = sorted(set(result).difference(expected))
        raise ValueError(f"{name} fields differ: missing={missing}, extra={extra}")
    return result
