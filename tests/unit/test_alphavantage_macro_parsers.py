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


def test_macro_release_identity_is_content_derived_across_fetch_instants() -> None:
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
        available_at=datetime(2026, 1, 17, tzinfo=UTC),
    )
    assert first.release_id == second.release_id
    assert first.source_release_key == second.source_release_key
    assert first.release_manifest_content_id == second.release_manifest_content_id
    assert first.available_at != second.available_at
    changed = _fixture("real_gdp.json")
    series = cast("list[dict[str, Any]]", changed["data"])
    series[0]["value"] = "1.5"
    revised = parse_macro_release(
        changed,
        function="REAL_GDP",
        series=_SERIES,
        available_at=_AVAILABLE,
    )
    assert revised.release_id != first.release_id
    assert revised.source_release_key != first.source_release_key


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


def test_commodity_series_register_under_the_commodity_label() -> None:
    from persistra.domain import AssetClass

    payload = _fixture("wti.json")
    definition = macro_series_definition("WTI", payload)
    assert str(definition.name) == "alphavantage.commodity.wti"
    assert str(definition.frequency) == "persistra.frequency.daily"
    spec = MACRO_SERIES_SPECS["WTI"]
    assert spec.asset_class is AssetClass.COMMODITY
    commodity_specs = [
        item
        for item in MACRO_SERIES_SPECS.values()
        if item.asset_class is AssetClass.COMMODITY
    ]
    assert {item.function for item in commodity_specs} == {
        "WTI",
        "BRENT",
        "NATURAL_GAS",
        "COPPER",
        "WHEAT",
        "CORN",
        "SUGAR",
        "COFFEE",
        "ALL_COMMODITIES",
    }
    assert all(
        str(item.name).startswith("alphavantage.commodity.")
        for item in commodity_specs
    )


def test_commodity_release_parses_daily_price_observations() -> None:
    release = parse_macro_release(
        _fixture("wti.json"),
        function="WTI",
        series=_SERIES,
        available_at=_AVAILABLE,
    )
    priced = [item for item in release.observations if not item.is_missing]
    missing = [item for item in release.observations if item.is_missing]
    assert len(priced) == 2
    assert len(missing) == 1
    latest = priced[-1]
    assert latest.period_start == latest.period_end == date(2026, 1, 9)
    assert latest.value is not None
    assert latest.value.value == Decimal("68.42")
