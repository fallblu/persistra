from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any

import pytest

from persistra.domain import (
    Currency,
    Money,
    NonNegativeQuantity,
    NumericKind,
    Price,
    Quantity,
    Rate,
    RoundingMode,
    Unit,
    UnitSpec,
)
from persistra.errors import (
    CurrencyMismatchError,
    DecimalOverflowError,
    InvalidCurrencyError,
    InvalidDecimalError,
    InvalidPriceError,
    InvalidQuantityError,
    PrecisionLossError,
)


def test_currency_registry_and_numeric_profiles() -> None:
    usd = Currency("usd")
    assert str(usd) == "USD"
    assert usd.minor_quantum == Decimal("0.01")
    assert Currency("JPY").minor_quantum == Decimal("1")
    assert Money.zero(usd).amount == Decimal("0.000000000000")
    assert Quantity("-1.25").value == Decimal("-1.250000000000")
    assert NonNegativeQuantity("1.25").value == Decimal("1.250000000000")
    assert Rate("0.05").value == Decimal("0.050000000000000000")
    assert Price("0", usd).amount == 0


@pytest.mark.parametrize("value", [1.0, True, " 1", "1e2", "1,000", "NaN", "Infinity"])
def test_invalid_decimal_inputs(value: Any) -> None:
    with pytest.raises(InvalidDecimalError):
        Quantity(value)


def test_precision_loss_overflow_and_signed_constraints() -> None:
    with pytest.raises(PrecisionLossError):
        Money("1.0000000000001", "USD")
    with pytest.raises(DecimalOverflowError):
        Money("1" + "0" * 100, "USD")
    with pytest.raises(InvalidPriceError):
        Price("-0.01", "USD")
    with pytest.raises(InvalidQuantityError):
        NonNegativeQuantity("-0.01")
    for code in ["US", " US", "ZZZ"]:
        with pytest.raises(InvalidCurrencyError):
            Currency(code)


@pytest.mark.parametrize(
    ("mode", "positive", "negative"),
    [
        (RoundingMode.HALF_EVEN, "1.00", "-1.00"),
        (RoundingMode.HALF_UP, "1.05", "-1.05"),
        (RoundingMode.DOWN, "1.00", "-1.00"),
        (RoundingMode.UP, "1.05", "-1.05"),
        (RoundingMode.FLOOR, "1.00", "-1.05"),
        (RoundingMode.CEILING, "1.05", "-1.00"),
    ],
)
def test_rounding_uses_quantum_multiples(mode: RoundingMode, positive: str, negative: str) -> None:
    quantum = Decimal("0.05")
    assert Money("1.025", "USD").quantize(quantum, mode).amount == Decimal(positive)
    assert Money("-1.025", "USD").quantize(quantum, mode).amount == Decimal(negative)


def test_money_and_notional_operations_are_explicit() -> None:
    usd = Currency("USD")
    left = Money("10", usd)
    right = Money("3", usd)
    assert (left + right).amount == 13
    assert (left - right).amount == 7
    scaled = left.scaled_by(Decimal("0.333"), quantum=Decimal("0.01"), mode=RoundingMode.HALF_EVEN)
    assert scaled.amount == Decimal("3.33")
    assert left.ratio(right, mode=RoundingMode.HALF_EVEN).value == Decimal("3.333333333333333333")
    notional = Price("2.50", usd).notional(
        Quantity("3"), quantum=Decimal("0.01"), mode=RoundingMode.HALF_EVEN
    )
    assert notional == Money("7.50", usd)
    with pytest.raises(CurrencyMismatchError):
        _ = left + Money("1", "EUR")
    with pytest.raises(InvalidDecimalError):
        left.ratio(Money.zero(usd), mode=RoundingMode.HALF_EVEN)
    with pytest.raises(InvalidDecimalError):
        left.quantize(Decimal("0"), RoundingMode.HALF_EVEN)


def test_global_decimal_context_does_not_change_results() -> None:
    previous = getcontext().prec
    try:
        getcontext().prec = 3
        result = Money("10", "USD").ratio(Money("3", "USD"), mode=RoundingMode.HALF_EVEN)
        assert result.value == Decimal("3.333333333333333333")
    finally:
        getcontext().prec = previous


def test_units_are_exact_and_typed() -> None:
    spec = UnitSpec(Unit("usd_per_share"), NumericKind.DECIMAL)
    assert str(spec.unit) == "usd_per_share"
    assert spec.numeric_kind is NumericKind.DECIMAL
    with pytest.raises(InvalidDecimalError):
        Unit("USD")
    with pytest.raises(InvalidDecimalError):
        Unit("custom_unit")
    with pytest.raises(InvalidDecimalError):
        UnitSpec("usd", "decimal")  # type: ignore[arg-type]
