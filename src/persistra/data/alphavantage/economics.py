"""Alpha Vantage primary economic-indicator namespace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from persistra.data.alphavantage.series import parse_scalar_series
from persistra.model import SeriesKind, SeriesSet

if TYPE_CHECKING:
    from persistra.data.alphavantage._common import AdapterContext

_FREQUENCIES: dict[str, set[str]] = {
    "REAL_GDP": {"quarterly", "annual"},
    "REAL_GDP_PER_CAPITA": {"annual"},
    "TREASURY_YIELD": {"daily", "weekly", "monthly"},
    "FEDERAL_FUNDS_RATE": {"daily", "weekly", "monthly"},
    "CPI": {"monthly", "semiannual"},
    "INFLATION": {"annual"},
    "RETAIL_SALES": {"monthly"},
    "DURABLES": {"monthly"},
    "UNEMPLOYMENT": {"monthly"},
    "NONFARM_PAYROLL": {"monthly"},
}
_MATURITIES = {"3month", "2year", "5year", "7year", "10year", "30year"}
_DEFAULT_FREQUENCIES = {
    "REAL_GDP": "quarterly",
    "REAL_GDP_PER_CAPITA": "annual",
    "TREASURY_YIELD": "daily",
    "FEDERAL_FUNDS_RATE": "daily",
    "CPI": "monthly",
    "INFLATION": "annual",
    "RETAIL_SALES": "monthly",
    "DURABLES": "monthly",
    "UNEMPLOYMENT": "monthly",
    "NONFARM_PAYROLL": "monthly",
}


class EconomicsNamespace:
    """Acquire primary economic and interest-rate series."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def series(
        self,
        indicator: str,
        *,
        frequency: str | None = None,
        maturity: str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> SeriesSet:
        """Acquire one validated native economic series."""
        operation = indicator.upper()
        if operation not in _FREQUENCIES:
            raise ValueError(f"unsupported economic indicator: {operation}")
        valid = _FREQUENCIES[operation]
        selected = frequency or _DEFAULT_FREQUENCIES[operation]
        if selected not in valid:
            raise ValueError(f"{operation} supports frequencies {sorted(valid)}")
        if operation == "TREASURY_YIELD":
            if maturity not in _MATURITIES:
                raise ValueError(f"TREASURY_YIELD requires a maturity in {sorted(_MATURITIES)}")
        elif maturity is not None:
            raise ValueError("maturity applies only to TREASURY_YIELD")
        parameters: dict[str, object] = {}
        if len(valid) > 1 or frequency is not None:
            parameters["interval"] = selected
        if maturity is not None:
            parameters["maturity"] = maturity
        payload, raw = self._context.json(operation, parameters, refresh=refresh, offline=offline)
        provider_series = operation if maturity is None else f"{operation}:{maturity}"
        return parse_scalar_series(
            self._context,
            payload,
            raw,
            operation=operation,
            parameters=parameters,
            provider_series=provider_series,
            frequency=selected,
            kind=SeriesKind.ECONOMIC,
            maturity=maturity,
        )
