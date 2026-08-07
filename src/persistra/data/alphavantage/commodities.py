"""Alpha Vantage primary commodity namespace."""

from __future__ import annotations

from typing import Any, cast

from persistra.data.alphavantage._common import (
    AdapterContext,
    optional_text,
    parse_timestamp,
    required_float,
)
from persistra.data.alphavantage.series import parse_scalar_series
from persistra.errors import ResponseError
from persistra.model import CommoditySpotQuote, SeriesKind, SeriesSet, provider_series_id

_ENERGY = {"WTI", "BRENT", "NATURAL_GAS"}
_INDUSTRIAL = {
    "COPPER",
    "ALUMINUM",
    "WHEAT",
    "CORN",
    "COTTON",
    "SUGAR",
    "COFFEE",
    "ALL_COMMODITIES",
}
_METALS = {"gold", "silver"}


class CommoditiesNamespace:
    """Acquire commodity spot quotes and scalar series."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def spot(
        self,
        metal: str,
        *,
        refresh: bool = False,
        offline: bool = False,
    ) -> CommoditySpotQuote:
        """Acquire one current gold or silver spot quote."""
        normalized = metal.lower()
        if normalized not in _METALS:
            raise ValueError("metal must be gold or silver")
        parameters = {"symbol": normalized.upper()}
        payload, raw = self._context.json(
            "GOLD_SILVER_SPOT",
            parameters,
            cache_age=None,
            refresh=refresh,
            offline=offline,
        )
        row = _spot_row(payload)
        provider_timestamp = parse_timestamp(
            optional_text(row, "timestamp", "date", "last_updated")
        )
        unit = optional_text(row, "unit") or "USD per troy ounce"
        series_id = provider_series_id("alpha_vantage", f"{normalized}_spot", "spot")
        metadata = self._context.metadata(
            "GOLD_SILVER_SPOT",
            parameters,
            raw,
            provider_as_of=provider_timestamp,
        )
        return CommoditySpotQuote(
            series_id,
            "alpha_vantage",
            normalized,
            required_float(row, "price", "value"),
            unit,
            provider_timestamp,
            raw.retrieved_at,
            metadata,
        )

    def series(
        self,
        commodity: str,
        *,
        frequency: str,
        metal: str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> SeriesSet:
        """Acquire one native commodity scalar series."""
        operation = commodity.upper()
        valid = _frequencies(operation)
        if frequency not in valid:
            raise ValueError(f"{operation} supports frequencies {sorted(valid)}")
        parameters: dict[str, object] = {"interval": frequency}
        provider_series = operation
        if operation == "GOLD_SILVER_HISTORY":
            normalized = (metal or "").lower()
            if normalized not in _METALS:
                raise ValueError("metal must be gold or silver for GOLD_SILVER_HISTORY")
            parameters["symbol"] = normalized.upper()
            provider_series = f"{operation}:{normalized}"
        payload, raw = self._context.json(operation, parameters, refresh=refresh, offline=offline)
        return parse_scalar_series(
            self._context,
            payload,
            raw,
            operation=operation,
            parameters=parameters,
            provider_series=provider_series,
            frequency=frequency,
            kind=SeriesKind.COMMODITY,
        )


def _frequencies(operation: str) -> set[str]:
    if operation == "GOLD_SILVER_HISTORY" or operation in _ENERGY:
        return {"daily", "weekly", "monthly"}
    if operation in _INDUSTRIAL:
        return {"monthly", "quarterly", "annual"}
    raise ValueError(f"unsupported commodity: {operation}")


def _spot_row(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "Global Quote", "Gold Silver Spot"):
        value = payload.get(key)
        if isinstance(value, dict):
            return cast("dict[str, Any]", value)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return cast("dict[str, Any]", value[0])
    if any(key in payload for key in ("price", "value")):
        return payload
    raise ResponseError("commodity spot response has no quote object")
