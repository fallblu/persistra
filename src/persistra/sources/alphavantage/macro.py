"""Alpha Vantage economic-indicator parsers feeding the macro-series family.

Alpha Vantage serves latest snapshots without vintages, so every series is
registered with ``LATEST_ONLY`` vintage completeness and every release is
``ingestion_bounded``: availability is the fetch instant, recorded honestly.
Release identity derives from the parsed observation content, so re-fetching
unchanged data reproduces the same release and stays idempotent at ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, cast

from persistra._identity import scoped_identity_content_id
from persistra.domain import (
    AssetClass,
    AvailabilityQuality,
    ContentId,
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
    FactNumericKind,
    MacroObservation,
    MacroRelease,
    MacroReleaseId,
    MacroSeriesDefinition,
    MacroVintageStatus,
    VintageCompleteness,
)
from persistra.sources.alphavantage._parsing import MISSING_VALUES, derived_entity_id

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.market import ResolvedMacroSeriesRef

_UNIT_USD = UnitSpec(Unit("usd"), NumericKind.DECIMAL)
_UNIT_RATIO = UnitSpec(Unit("ratio"), NumericKind.DECIMAL)
_UNIT_RATE = UnitSpec(Unit("rate"), NumericKind.DECIMAL)
_UNIT_COUNT = UnitSpec(Unit("count"), NumericKind.DECIMAL)


@dataclass(frozen=True, slots=True)
class MacroSeriesSpec:
    """How one Alpha Vantage economic series maps onto the macro family."""

    function: str
    name: QualifiedName
    asset_class: AssetClass
    unit: UnitSpec
    numeric_kind: FactNumericKind
    source_numeric_kind: SourceNumericKind
    seasonal_adjustment: QualifiedName
    geography: QualifiedName


def _spec(
    function: str,
    slug: str,
    asset_class: AssetClass,
    unit: UnitSpec,
    numeric_kind: FactNumericKind,
    source_numeric_kind: SourceNumericKind,
) -> MacroSeriesSpec:
    prefix = "macro" if asset_class is AssetClass.MACRO else "commodity"
    return MacroSeriesSpec(
        function,
        QualifiedName(f"alphavantage.{prefix}.{slug}"),
        asset_class,
        unit,
        numeric_kind,
        source_numeric_kind,
        QualifiedName("alphavantage.seasonal.as_published"),
        QualifiedName("persistra.geography.us"),
    )


MACRO_SERIES_SPECS: dict[str, MacroSeriesSpec] = {
    spec.function: spec
    for spec in (
        _spec(
            "REAL_GDP",
            "real_gdp",
            AssetClass.MACRO,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "CPI",
            "cpi",
            AssetClass.MACRO,
            _UNIT_RATIO,
            FactNumericKind.PURE,
            SourceNumericKind.PURE,
        ),
        _spec(
            "INFLATION",
            "inflation",
            AssetClass.MACRO,
            _UNIT_RATE,
            FactNumericKind.RATE,
            SourceNumericKind.RATE,
        ),
        _spec(
            "UNEMPLOYMENT",
            "unemployment",
            AssetClass.MACRO,
            _UNIT_RATE,
            FactNumericKind.RATE,
            SourceNumericKind.RATE,
        ),
        _spec(
            "RETAIL_SALES",
            "retail_sales",
            AssetClass.MACRO,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "NONFARM_PAYROLL",
            "nonfarm_payroll",
            AssetClass.MACRO,
            _UNIT_COUNT,
            FactNumericKind.COUNT,
            SourceNumericKind.COUNT,
        ),
        _spec(
            "WTI",
            "wti",
            AssetClass.COMMODITY,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "BRENT",
            "brent",
            AssetClass.COMMODITY,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "NATURAL_GAS",
            "natural_gas",
            AssetClass.COMMODITY,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "COPPER",
            "copper",
            AssetClass.COMMODITY,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "WHEAT",
            "wheat",
            AssetClass.COMMODITY,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "CORN",
            "corn",
            AssetClass.COMMODITY,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "SUGAR",
            "sugar",
            AssetClass.COMMODITY,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "COFFEE",
            "coffee",
            AssetClass.COMMODITY,
            _UNIT_USD,
            FactNumericKind.AMOUNT,
            SourceNumericKind.AMOUNT,
        ),
        _spec(
            "ALL_COMMODITIES",
            "all_commodities",
            AssetClass.COMMODITY,
            _UNIT_RATIO,
            FactNumericKind.PURE,
            SourceNumericKind.PURE,
        ),
    )
}

_FREQUENCIES = {
    "daily": QualifiedName("persistra.frequency.daily"),
    "weekly": QualifiedName("persistra.frequency.weekly"),
    "monthly": QualifiedName("persistra.frequency.monthly"),
    "quarterly": QualifiedName("persistra.frequency.quarterly"),
    "semiannual": QualifiedName("persistra.frequency.semiannual"),
    "annual": QualifiedName("persistra.frequency.annual"),
}


def _series_spec(function: str) -> MacroSeriesSpec:
    spec = MACRO_SERIES_SPECS.get(function)
    if spec is None:
        raise SourceResponseError(
            f"alpha vantage function {function} has no macro-series mapping"
        )
    return spec


def _interval(payload: dict[str, Any]) -> str:
    interval = str(payload.get("interval", "")).lower()
    if interval not in _FREQUENCIES:
        raise SourceResponseError(
            f"alpha vantage macro interval {interval!r} is unsupported"
        )
    return interval


def macro_series_definition(
    function: str, payload: dict[str, Any], *, version: int = 1
) -> MacroSeriesDefinition:
    """Build the macro-series definition for one Alpha Vantage series payload."""
    spec = _series_spec(function)
    interval = _interval(payload)
    return MacroSeriesDefinition(
        spec.name,
        version,
        _FREQUENCIES[interval],
        spec.seasonal_adjustment,
        spec.geography,
        spec.unit,
        spec.numeric_kind,
        VintageCompleteness.LATEST_ONLY,
        ContentId.from_bytes(
            f"alphavantage.macro.period_policy.{interval}@1".encode()
        ),
    )


def _period_end(start: date, interval: str) -> date:
    if interval == "daily":
        return start
    if interval == "weekly":
        return start + timedelta(days=6)
    months = {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}[interval]
    anchor = start.month - 1 + months
    return date(start.year + anchor // 12, anchor % 12 + 1, 1) - timedelta(days=1)


def parse_macro_release(
    payload: dict[str, Any],
    *,
    function: str,
    series: ResolvedMacroSeriesRef,
    available_at: datetime,
) -> MacroRelease:
    """Parse one economic-indicator payload into a latest-only macro release.

    The release key and id are content-derived from the parsed observations,
    so two fetches of identical data share one release identity regardless of
    when they were fetched; only ``available_at`` carries the fetch instant.
    """
    validate_instant(available_at)
    spec = _series_spec(function)
    interval = _interval(payload)
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise SourceResponseError(
            f"alpha vantage {function} payload lacks data rows"
        )
    observations: list[MacroObservation] = []
    for raw in cast("list[Any]", rows):
        if not isinstance(raw, dict):
            raise SourceResponseError(f"alpha vantage {function} data row is malformed")
        typed = cast("dict[str, Any]", raw)
        try:
            period_start = date.fromisoformat(str(typed.get("date")))
        except ValueError as cause:
            raise SourceResponseError(
                f"alpha vantage {function} observation date is invalid"
            ) from cause
        raw_value = str(typed.get("value", "")).strip()
        vintage_key = f"{function}:{period_start.isoformat()}"
        if raw_value in MISSING_VALUES:
            observations.append(
                MacroObservation(
                    vintage_key,
                    period_start,
                    _period_end(period_start, interval),
                    MacroVintageStatus.REVISED,
                    spec.unit,
                    value=None,
                    is_missing=True,
                    missing_reason_code="source_missing",
                )
            )
            continue
        try:
            parsed = Decimal(raw_value)
        except InvalidOperation as cause:
            raise SourceResponseError(
                f"alpha vantage {function} observation value is invalid"
            ) from cause
        observations.append(
            MacroObservation(
                vintage_key,
                period_start,
                _period_end(period_start, interval),
                MacroVintageStatus.REVISED,
                spec.unit,
                value=SourceNumeric(parsed, spec.source_numeric_kind, spec.unit),
            )
        )
    observations.sort(key=lambda item: item.period_start)
    manifest = scoped_identity_content_id(
        {
            "schema": "alphavantage.macro.release@1",
            "function": function,
            "series": series,
            "observations": tuple(observations),
        }
    )
    release_key = f"alphavantage:{function}:{manifest}"
    release_id = derived_entity_id(MacroReleaseId, manifest)
    return MacroRelease(
        release_id,
        series,
        release_key,
        available_at,
        available_at,
        manifest,
        tuple(observations),
        availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
    )
