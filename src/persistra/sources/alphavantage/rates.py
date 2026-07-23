"""This module contains Alpha Vantage treasury-yield and policy-rate parsers for risk-free curves.

Alpha Vantage supplies constant-maturity treasury yields and the effective federal funds rate as
percentages. The parsers convert them to decimal fractions. They produce :class:`RiskFreePoint`
rows with ingestion-bounded availability."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, cast

from persistra.domain import (
    AvailabilityQuality,
    ContentId,
    Currency,
    NumericKind,
    QualifiedName,
    SourceNumeric,
    SourceNumericKind,
    Unit,
    UnitSpec,
)
from persistra.domain.time import validate_instant
from persistra.errors import SourceResponseError
from persistra.market import (
    CompoundingKind,
    DayCountKind,
    RateQuoteKind,
    RiskFreeCurveDefinition,
    RiskFreePoint,
    Tenor,
)
from persistra.sources.alphavantage._parsing import MISSING_VALUES

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.market import ResolvedRiskFreeCurveRef
    from persistra.reference import CalendarRef

TREASURY_CURVE_NAME = QualifiedName("alphavantage.rates.us_treasury")
FED_FUNDS_CURVE_NAME = QualifiedName("alphavantage.rates.fed_funds")

_UNIT_RATE = UnitSpec(Unit("rate"), NumericKind.DECIMAL)

TREASURY_MATURITY_TENORS: dict[str, Tenor] = {
    "3month": Tenor.months(3),
    "2year": Tenor.months(24),
    "5year": Tenor.months(60),
    "7year": Tenor.months(84),
    "10year": Tenor.months(120),
    "30year": Tenor.months(360),
}


def treasury_curve_definition(
    *, calendar: CalendarRef, version: int = 1
) -> RiskFreeCurveDefinition:
    """Return the US constant-maturity treasury yield curve definition."""
    return RiskFreeCurveDefinition(
        TREASURY_CURVE_NAME,
        version,
        Currency("USD"),
        RateQuoteKind.BOND_EQUIVALENT_YIELD,
        CompoundingKind.PERIODIC,
        2,
        DayCountKind.ACT_ACT_ISDA,
        calendar,
        ContentId.from_bytes(b"alphavantage.rates.business_day@1"),
    )


def fed_funds_curve_definition(
    *, calendar: CalendarRef, version: int = 1
) -> RiskFreeCurveDefinition:
    """Return the effective federal funds overnight-rate curve definition."""
    return RiskFreeCurveDefinition(
        FED_FUNDS_CURVE_NAME,
        version,
        Currency("USD"),
        RateQuoteKind.OVERNIGHT_RATE,
        CompoundingKind.SIMPLE,
        None,
        DayCountKind.ACT_360,
        calendar,
        ContentId.from_bytes(b"alphavantage.rates.business_day@1"),
    )


def _rate_rows(
    payload: dict[str, Any], function: str
) -> list[tuple[date, Decimal]]:
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise SourceResponseError(f"alpha vantage {function} payload lacks data rows")
    parsed: list[tuple[date, Decimal]] = []
    for raw in cast("list[Any]", rows):
        if not isinstance(raw, dict):
            raise SourceResponseError(f"alpha vantage {function} data row is malformed")
        typed = cast("dict[str, Any]", raw)
        try:
            effective = date.fromisoformat(str(typed.get("date")))
        except ValueError as cause:
            raise SourceResponseError(
                f"alpha vantage {function} observation date is invalid"
            ) from cause
        raw_value = str(typed.get("value", "")).strip()
        if raw_value in MISSING_VALUES:
            continue
        try:
            percent = Decimal(raw_value)
        except InvalidOperation as cause:
            raise SourceResponseError(
                f"alpha vantage {function} observation value is invalid"
            ) from cause
        parsed.append((effective, percent / 100))
    parsed.sort(key=lambda item: item[0])
    return parsed


def parse_treasury_yields(
    payload: dict[str, Any],
    *,
    curve: ResolvedRiskFreeCurveRef,
    maturity: str,
    available_at: datetime,
) -> tuple[RiskFreePoint, ...]:
    """Parse one ``TREASURY_YIELD`` maturity into risk-free curve points."""
    validate_instant(available_at)
    tenor = TREASURY_MATURITY_TENORS.get(maturity)
    if tenor is None:
        raise SourceResponseError(
            f"alpha vantage treasury maturity {maturity!r} is unsupported"
        )
    manifest = ContentId.from_bytes(
        f"alphavantage:TREASURY_YIELD:{maturity}".encode()
    )
    return tuple(
        RiskFreePoint(
            curve,
            f"alphavantage:TREASURY_YIELD:{maturity}:{effective.isoformat()}",
            effective,
            available_at,
            available_at,
            tenor,
            SourceNumeric(value, SourceNumericKind.RATE, _UNIT_RATE),
            RateQuoteKind.BOND_EQUIVALENT_YIELD,
            CompoundingKind.PERIODIC,
            2,
            DayCountKind.ACT_ACT_ISDA,
            manifest,
            availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
        )
        for effective, value in _rate_rows(payload, "TREASURY_YIELD")
    )


def parse_federal_funds_rate(
    payload: dict[str, Any],
    *,
    curve: ResolvedRiskFreeCurveRef,
    available_at: datetime,
) -> tuple[RiskFreePoint, ...]:
    """Parse ``FEDERAL_FUNDS_RATE`` into overnight risk-free curve points."""
    validate_instant(available_at)
    manifest = ContentId.from_bytes(b"alphavantage:FEDERAL_FUNDS_RATE")
    return tuple(
        RiskFreePoint(
            curve,
            f"alphavantage:FEDERAL_FUNDS_RATE:{effective.isoformat()}",
            effective,
            available_at,
            available_at,
            Tenor.days(1),
            SourceNumeric(value, SourceNumericKind.RATE, _UNIT_RATE),
            RateQuoteKind.OVERNIGHT_RATE,
            CompoundingKind.SIMPLE,
            None,
            DayCountKind.ACT_360,
            manifest,
            availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
        )
        for effective, value in _rate_rows(payload, "FEDERAL_FUNDS_RATE")
    )
