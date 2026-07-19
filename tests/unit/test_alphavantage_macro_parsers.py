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
    FactNumericKind,
    MacroVintageStatus,
    VintageCompleteness,
)
from persistra.market.economic_models import MacroSeriesId, ResolvedMacroSeriesRef
from persistra.sources.alphavantage.macro import (
    MACRO_SERIES_SPECS,
    macro_series_definition,
    parse_macro_release,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

_AVAILABLE = datetime(2026, 1, 10, tzinfo=UTC)
_SERIES = ResolvedMacroSeriesRef(
    MacroSeriesId.new(), 1, ContentId.from_bytes(b"series")
)


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_macro_definitions_are_latest_only_with_mapped_units() -> None:
    payload = _fixture("real_gdp.json")
    definition = macro_series_definition("REAL_GDP", payload)
    assert str(definition.name) == "alphavantage.macro.real_gdp"
    assert definition.vintage_completeness is VintageCompleteness.LATEST_ONLY
    assert str(definition.frequency) == "persistra.frequency.quarterly"
    assert definition.numeric_kind is FactNumericKind.AMOUNT
    unemployment = macro_series_definition(
        "UNEMPLOYMENT", _fixture("unemployment.json")
    )
    assert str(unemployment.frequency) == "persistra.frequency.monthly"
    assert unemployment.numeric_kind is FactNumericKind.RATE


def test_macro_release_parses_quarterly_observations() -> None:
    release = parse_macro_release(
        _fixture("real_gdp.json"),
        function="REAL_GDP",
        series=_SERIES,
        available_at=_AVAILABLE,
    )
    assert release.release_at == _AVAILABLE
    assert release.available_at == _AVAILABLE
    assert release.availability_quality is AvailabilityQuality.INGESTION_BOUNDED
    assert len(release.observations) == 3
    latest = release.observations[-1]
    assert latest.period_start == date(2025, 10, 1)
    assert latest.period_end == date(2025, 12, 31)
    assert latest.vintage_status is MacroVintageStatus.REVISED
    assert latest.value is not None
    assert latest.value.value == Decimal("23400.5")


def test_macro_release_marks_missing_observations() -> None:
    release = parse_macro_release(
        _fixture("unemployment.json"),
        function="UNEMPLOYMENT",
        series=_SERIES,
        available_at=_AVAILABLE,
    )
    missing = [item for item in release.observations if item.is_missing]
    assert len(missing) == 1
    assert missing[0].period_start == date(2025, 11, 1)
    assert missing[0].missing_reason_code == "source_missing"
    assert missing[0].period_end == date(2025, 11, 30)


def test_macro_release_is_deterministic_per_fetch_instant() -> None:
    first = parse_macro_release(
        _fixture("real_gdp.json"),
        function="REAL_GDP",
        series=_SERIES,
        available_at=_AVAILABLE,
    )
    second = parse_macro_release(
        _fixture("real_gdp.json"),
        function="REAL_GDP",
        series=_SERIES,
        available_at=_AVAILABLE,
    )
    assert first.release_id == second.release_id
    assert first.source_release_key == second.source_release_key


def test_macro_parsers_reject_unknown_functions_and_bad_payloads() -> None:
    with pytest.raises(SourceResponseError):
        macro_series_definition("NOT_A_SERIES", _fixture("real_gdp.json"))
    with pytest.raises(SourceResponseError):
        macro_series_definition("REAL_GDP", {"interval": "hourly"})
    with pytest.raises(SourceResponseError):
        parse_macro_release(
            {"interval": "quarterly", "data": []},
            function="REAL_GDP",
            series=_SERIES,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_macro_release(
            {"interval": "quarterly", "data": [{"date": "bad", "value": "1"}]},
            function="REAL_GDP",
            series=_SERIES,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_macro_release(
            {
                "interval": "quarterly",
                "data": [{"date": "2025-10-01", "value": "abc"}],
            },
            function="REAL_GDP",
            series=_SERIES,
            available_at=_AVAILABLE,
        )


def test_macro_spec_names_are_unique() -> None:
    names = [str(spec.name) for spec in MACRO_SERIES_SPECS.values()]
    assert len(names) == len(set(names))
