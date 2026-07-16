"""Fixed-precision values, currencies, rounding, and unit declarations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
    InvalidOperation,
    localcontext,
)
from enum import StrEnum
from typing import ClassVar, Self, cast

from persistra.domain.errors import (
    CurrencyMismatchError,
    DecimalOverflowError,
    InvalidCurrencyError,
    InvalidDecimalError,
    InvalidPriceError,
    InvalidQuantityError,
    PrecisionLossError,
)

_DECIMAL_TEXT = re.compile(r"[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
_UNIT_TEXT = re.compile(r"[a-z][a-z0-9_]*(?:_per_[a-z][a-z0-9_]*)?")
_AMOUNT_QUANTUM = Decimal("0.000000000001")
_RATE_QUANTUM = Decimal("0.000000000000000001")
_ROUNDING = {
    "half_even": ROUND_HALF_EVEN,
    "half_up": ROUND_HALF_UP,
    "down": ROUND_DOWN,
    "up": ROUND_UP,
    "floor": ROUND_FLOOR,
    "ceiling": ROUND_CEILING,
}
_ZERO_MINOR = frozenset(
    {
        "BIF",
        "CLP",
        "DJF",
        "GNF",
        "ISK",
        "JPY",
        "KMF",
        "KRW",
        "PYG",
        "RWF",
        "UGX",
        "UYI",
        "VND",
        "VUV",
        "XAF",
        "XOF",
        "XPF",
    }
)
_ACTIVE_CODES = frozenset(
    (
        "AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV "
        "BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUC CUP CVE "
        "CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD "
        "HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD "
        "KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN "
        "MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD "
        "RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT "
        "TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAF "
        "XAG XAU XBA XBB XBC XBD XCD XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWL"
    ).split()
)
_CURRENCIES = {
    code: Decimal("1") if code in _ZERO_MINOR else Decimal("0.01") for code in _ACTIVE_CODES
}


class RoundingMode(StrEnum):
    """Explicit fixed-precision boundary rounding policy."""

    HALF_EVEN = "half_even"
    HALF_UP = "half_up"
    DOWN = "down"
    UP = "up"
    FLOOR = "floor"
    CEILING = "ceiling"


class NumericKind(StrEnum):
    """Physical scalar family carried by a unit declaration."""

    DECIMAL = "decimal"
    FLOAT = "float"
    INTEGER = "integer"


def _decimal_input(value: object) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidDecimalError("floats and booleans are not fixed-precision inputs")
    if isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, str):
        if _DECIMAL_TEXT.fullmatch(value) is None:
            raise InvalidDecimalError("decimal text is not canonical")
        try:
            parsed = Decimal(value)
        except InvalidOperation as error:
            raise InvalidDecimalError("decimal text is invalid") from error
    else:
        raise InvalidDecimalError("value must be Decimal, integer, or canonical text")
    if not parsed.is_finite():
        raise InvalidDecimalError("decimal must be finite")
    return parsed


def _normalize(value: Decimal | int | str, *, scale: int) -> Decimal:
    parsed = _decimal_input(value)
    quantum = _AMOUNT_QUANTUM if scale == 12 else _RATE_QUANTUM
    with localcontext() as context:
        context.prec = 80
        try:
            quantized = parsed.quantize(quantum)
        except InvalidOperation as error:
            raise DecimalOverflowError("value exceeds DECIMAL(38, scale) profile") from error
    if quantized != parsed:
        raise PrecisionLossError(f"value exceeds the {scale}-place storage profile")
    if quantized == 0:
        quantized = abs(quantized)
    digits_before = max(1, quantized.adjusted() + 1) if quantized else 1
    if digits_before > 38 - scale:
        raise DecimalOverflowError("value exceeds DECIMAL(38, scale) profile")
    return quantized


def _quantize(value: Decimal, quantum: object, mode: RoundingMode, *, scale: int) -> Decimal:
    if not isinstance(quantum, Decimal) or not quantum.is_finite() or quantum <= 0:
        raise InvalidDecimalError("quantum must be a finite positive Decimal")
    with localcontext() as context:
        context.prec = 80
        try:
            units = (value / quantum).quantize(Decimal(1), rounding=_ROUNDING[mode.value])
            result = units * quantum
        except InvalidOperation as error:
            raise DecimalOverflowError("quantized result exceeds supported precision") from error
    return _normalize(result, scale=scale)


@dataclass(frozen=True, slots=True, init=False)
class Currency:
    """Registered three-letter ISO-style currency code."""

    code: str

    def __init__(self, code: object) -> None:
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z]{3}", code):
            raise InvalidCurrencyError("currency must contain exactly three ASCII letters")
        normalized = code.upper()
        if normalized not in _CURRENCIES:
            raise InvalidCurrencyError("currency is not registered")
        object.__setattr__(self, "code", normalized)

    @property
    def minor_quantum(self) -> Decimal:
        """Return the registered ordinary cash settlement quantum."""
        return _CURRENCIES[self.code]

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True, init=False)
class Money:
    """Signed amount-profile decimal in one explicit currency."""

    amount: Decimal
    currency: Currency

    def __init__(self, amount: Decimal | int | str, currency: Currency | str) -> None:
        object.__setattr__(self, "amount", _normalize(amount, scale=12))
        normalized_currency = currency if isinstance(currency, Currency) else Currency(currency)
        object.__setattr__(self, "currency", normalized_currency)

    @classmethod
    def zero(cls, currency: Currency) -> Self:
        """Construct exact zero in a currency."""
        return cls(0, currency)

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError("money currencies do not match")

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def quantize(self, quantum: Decimal, mode: RoundingMode) -> Money:
        """Round explicitly to a positive quantum."""
        return Money(_quantize(self.amount, quantum, mode, scale=12), self.currency)

    def scaled_by(self, factor: Decimal, *, quantum: Decimal, mode: RoundingMode) -> Money:
        """Scale with an explicit output quantum and rounding policy."""
        parsed = _decimal_input(factor)
        with localcontext() as context:
            context.prec = 80
            result = self.amount * parsed
        return Money(_quantize(result, quantum, mode, scale=12), self.currency)

    def ratio(self, other: Money, *, mode: RoundingMode) -> Rate:
        """Return this amount divided by a nonzero same-currency amount."""
        self._same_currency(other)
        if other.amount == 0:
            raise InvalidDecimalError("ratio denominator cannot be zero")
        with localcontext() as context:
            context.prec = 80
            result = self.amount / other.amount
        return Rate(_quantize(result, _RATE_QUANTUM, mode, scale=18))


@dataclass(frozen=True, slots=True, init=False)
class Price:
    """Nonnegative amount-profile price in one explicit currency."""

    amount: Decimal
    currency: Currency

    def __init__(self, amount: Decimal | int | str, currency: Currency | str) -> None:
        normalized = _normalize(amount, scale=12)
        if normalized < 0:
            raise InvalidPriceError("price cannot be negative")
        object.__setattr__(self, "amount", normalized)
        normalized_currency = currency if isinstance(currency, Currency) else Currency(currency)
        object.__setattr__(self, "currency", normalized_currency)

    def notional(
        self,
        quantity: Quantity | NonNegativeQuantity,
        *,
        quantum: Decimal,
        mode: RoundingMode,
    ) -> Money:
        """Return price times quantity under an explicit boundary policy."""
        with localcontext() as context:
            context.prec = 80
            result = self.amount * quantity.value
        return Money(_quantize(result, quantum, mode, scale=12), self.currency)


@dataclass(frozen=True, slots=True, init=False)
class Quantity:
    """Signed fixed-precision instrument quantity."""

    value: Decimal

    def __init__(self, value: Decimal | int | str) -> None:
        object.__setattr__(self, "value", _normalize(value, scale=12))


@dataclass(frozen=True, slots=True, init=False)
class NonNegativeQuantity:
    """Fixed-precision quantity constrained to zero or greater."""

    value: Decimal

    def __init__(self, value: Decimal | int | str) -> None:
        normalized = _normalize(value, scale=12)
        if normalized < 0:
            raise InvalidQuantityError("quantity cannot be negative")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True, init=False)
class Rate:
    """Signed 18-place dimensionless rate."""

    value: Decimal

    def __init__(self, value: Decimal | int | str) -> None:
        object.__setattr__(self, "value", _normalize(value, scale=18))


@dataclass(frozen=True, slots=True)
class Unit:
    """Exact canonical unit with no implicit conversion semantics."""

    text: str
    _BUILTINS: ClassVar[frozenset[str]] = frozenset(
        {"usd", "share", "contract", "usd_per_share", "ratio", "rate", "bps", "days", "count"}
    )

    def __post_init__(self) -> None:
        raw_text = cast("object", self.text)
        if not isinstance(raw_text, str) or _UNIT_TEXT.fullmatch(raw_text) is None:
            raise InvalidDecimalError("unit text is not canonical")
        if self.text not in self._BUILTINS:
            raise InvalidDecimalError("unit is not registered")

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class UnitSpec:
    """Unit plus the physical numeric kind used at a typed boundary."""

    unit: Unit
    numeric_kind: NumericKind

    def __post_init__(self) -> None:
        raw_unit = cast("object", self.unit)
        raw_kind = cast("object", self.numeric_kind)
        if not isinstance(raw_unit, Unit) or not isinstance(raw_kind, NumericKind):
            raise InvalidDecimalError("unit specification requires typed unit and numeric kind")
