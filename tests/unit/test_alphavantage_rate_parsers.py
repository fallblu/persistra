from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from persistra.domain import AvailabilityQuality, ContentId
from persistra.errors import SourceResponseError
from persistra.market import (
    CompoundingKind,
    RateQuoteKind,
    ResolvedRiskFreeCurveRef,
    TenorKind,
)
from persistra.market.economic_models import RiskFreeCurveId
from persistra.reference import CalendarRef
from persistra.sources.alphavantage.rates import (
    FED_FUNDS_CURVE_NAME,
    TREASURY_CURVE_NAME,
    fed_funds_curve_definition,
    parse_federal_funds_rate,
    parse_treasury_yields,
    treasury_curve_definition,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

_AVAILABLE = datetime(2026, 1, 10, tzinfo=UTC)
_CURVE = ResolvedRiskFreeCurveRef(
    RiskFreeCurveId.new(), 1, ContentId.from_bytes(b"curve")
)
_CALENDAR = CalendarRef(TREASURY_CURVE_NAME, 1)


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_curve_definitions_use_stable_conventions() -> None:
    treasury = treasury_curve_definition(calendar=_CALENDAR)
    assert treasury.name == TREASURY_CURVE_NAME
    assert treasury.quote_kind is RateQuoteKind.BOND_EQUIVALENT_YIELD
    assert treasury.compounding is CompoundingKind.PERIODIC
    assert treasury.compounding_periods_per_year == 2
    fed = fed_funds_curve_definition(calendar=_CALENDAR)
    assert fed.name == FED_FUNDS_CURVE_NAME
    assert fed.quote_kind is RateQuoteKind.OVERNIGHT_RATE
    assert fed.compounding_periods_per_year is None


def test_treasury_yields_convert_percent_to_fractions() -> None:
    points = parse_treasury_yields(
        _fixture("treasury_yield_10year.json"),
        curve=_CURVE,
        maturity="10year",
        available_at=_AVAILABLE,
    )
    assert len(points) == 2
    latest = points[-1]
    assert latest.effective_date == date(2026, 1, 9)
    assert latest.value.value == Decimal("0.0428")
    assert latest.tenor.kind is TenorKind.MONTHS
    assert latest.tenor.count == 120
    assert latest.quote_kind is RateQuoteKind.BOND_EQUIVALENT_YIELD
    assert latest.availability_quality is AvailabilityQuality.INGESTION_BOUNDED
    assert latest.release_at == _AVAILABLE


def test_federal_funds_rate_maps_to_overnight_points() -> None:
    points = parse_federal_funds_rate(
        _fixture("federal_funds_rate.json"),
        curve=_CURVE,
        available_at=_AVAILABLE,
    )
    assert len(points) == 2
    assert points[-1].effective_date == date(2025, 12, 1)
    assert points[-1].value.value == Decimal("0.0383")
    assert points[-1].tenor.kind is TenorKind.DAYS
    assert points[-1].quote_kind is RateQuoteKind.OVERNIGHT_RATE


def test_rate_parsers_reject_bad_inputs() -> None:
    with pytest.raises(SourceResponseError):
        parse_treasury_yields(
            _fixture("treasury_yield_10year.json"),
            curve=_CURVE,
            maturity="6week",
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_treasury_yields(
            {"data": []},
            curve=_CURVE,
            maturity="10year",
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_federal_funds_rate(
            {"data": [{"date": "nope", "value": "1"}]},
            curve=_CURVE,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_federal_funds_rate(
            {"data": [{"date": "2025-12-01", "value": "x"}]},
            curve=_CURVE,
            available_at=_AVAILABLE,
        )
