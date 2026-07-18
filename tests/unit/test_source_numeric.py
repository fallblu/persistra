"""Tagged source-numeric envelope round-trip, bound, and rejection contracts."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from persistra.domain import (
    NumericKind,
    SourceNumeric,
    SourceNumericKind,
    Unit,
    UnitSpec,
)
from persistra.errors import (
    DecimalOverflowError,
    InvalidDecimalError,
    InvalidQuantityError,
    PrecisionLossError,
)

_AMOUNT_UNIT = UnitSpec(Unit("usd"), NumericKind.DECIMAL)
_RATE_UNIT = UnitSpec(Unit("ratio"), NumericKind.DECIMAL)
_COUNT_UNIT = UnitSpec(Unit("count"), NumericKind.INTEGER)


def test_amount_kind_round_trips_at_twelve_places() -> None:
    value = SourceNumeric("123.5", SourceNumericKind.AMOUNT, _AMOUNT_UNIT)
    assert value.value == Decimal("123.500000000000")
    assert value.canonical_text == "123.500000000000"
    assert value.envelope_value == Decimal("123.500000000000000000")
    assert value.kind is SourceNumericKind.AMOUNT
    assert value.unit == _AMOUNT_UNIT
    assert value.integral is False


def test_rate_kind_round_trips_at_eighteen_places() -> None:
    value = SourceNumeric("0.05", SourceNumericKind.RATE, _RATE_UNIT)
    assert value.value == Decimal("0.050000000000000000")
    assert value.canonical_text == "0.050000000000000000"
    assert value.envelope_value == Decimal("0.050000000000000000")


def test_pure_kind_uses_rate_profile() -> None:
    value = SourceNumeric("3", SourceNumericKind.PURE, _RATE_UNIT)
    assert value.value == Decimal("3.000000000000000000")


def test_count_kind_accepts_integral_values() -> None:
    value = SourceNumeric("42", SourceNumericKind.COUNT, _COUNT_UNIT, integral=True)
    assert value.value == Decimal("42.000000000000")
    assert value.integral is True


def test_count_kind_rejects_fractional_when_integral() -> None:
    with pytest.raises(InvalidQuantityError):
        SourceNumeric("42.5", SourceNumericKind.COUNT, _COUNT_UNIT, integral=True)


def test_non_integral_count_is_permitted() -> None:
    value = SourceNumeric("42.5", SourceNumericKind.COUNT, _COUNT_UNIT)
    assert value.value == Decimal("42.500000000000")


def test_integral_only_allowed_for_count() -> None:
    with pytest.raises(InvalidQuantityError):
        SourceNumeric("1", SourceNumericKind.AMOUNT, _AMOUNT_UNIT, integral=True)


def test_zero_is_normalized_without_sign() -> None:
    value = SourceNumeric("-0", SourceNumericKind.AMOUNT, _AMOUNT_UNIT)
    assert value.value == Decimal("0.000000000000")
    assert value.canonical_text == "0.000000000000"


def test_twenty_integer_digit_bound_is_accepted() -> None:
    value = SourceNumeric("99999999999999999999", SourceNumericKind.AMOUNT, _AMOUNT_UNIT)
    assert value.value == Decimal("99999999999999999999.000000000000")


def test_twenty_one_integer_digits_overflow() -> None:
    with pytest.raises(DecimalOverflowError):
        SourceNumeric("100000000000000000000", SourceNumericKind.AMOUNT, _AMOUNT_UNIT)


def test_amount_precision_loss_rejected() -> None:
    with pytest.raises(PrecisionLossError):
        SourceNumeric("1.0000000000001", SourceNumericKind.AMOUNT, _AMOUNT_UNIT)


def test_rate_precision_loss_rejected() -> None:
    with pytest.raises(PrecisionLossError):
        SourceNumeric("0.0000000000000000001", SourceNumericKind.RATE, _RATE_UNIT)


def test_float_and_bool_rejected() -> None:
    with pytest.raises(InvalidDecimalError):
        SourceNumeric(1.5, SourceNumericKind.AMOUNT, _AMOUNT_UNIT)  # type: ignore[arg-type]
    with pytest.raises(InvalidDecimalError):
        SourceNumeric(True, SourceNumericKind.COUNT, _COUNT_UNIT)  # type: ignore[arg-type]


def test_kind_and_unit_must_be_typed() -> None:
    with pytest.raises(InvalidDecimalError):
        SourceNumeric("1", "amount", _AMOUNT_UNIT)  # type: ignore[arg-type]
    with pytest.raises(InvalidDecimalError):
        SourceNumeric("1", SourceNumericKind.AMOUNT, "usd")  # type: ignore[arg-type]


def test_envelope_is_immutable() -> None:
    value = SourceNumeric("1", SourceNumericKind.AMOUNT, _AMOUNT_UNIT)
    with pytest.raises(AttributeError):
        value.value = Decimal("2")  # type: ignore[misc]


@given(
    st.decimals(
        min_value=Decimal("-1000000"),
        max_value=Decimal("1000000"),
        places=12,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_amount_round_trip_preserves_value(raw: Decimal) -> None:
    value = SourceNumeric(raw, SourceNumericKind.AMOUNT, _AMOUNT_UNIT)
    assert value.value == raw
    assert Decimal(value.canonical_text) == raw
    assert value.envelope_value == raw


@given(
    st.decimals(
        min_value=Decimal("-100"),
        max_value=Decimal("100"),
        places=18,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_rate_round_trip_preserves_value(raw: Decimal) -> None:
    value = SourceNumeric(raw, SourceNumericKind.RATE, _RATE_UNIT)
    assert value.value == raw
    assert Decimal(value.canonical_text) == raw
