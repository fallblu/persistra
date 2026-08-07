"""Alpha Vantage security time-series namespace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from persistra.data.alphavantage._common import AdapterContext, parse_bar_frame
from persistra.model import (
    BarSet,
    EntitlementMode,
    Instrument,
    InstrumentKind,
    provider_instrument_id,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_INTERVALS = {"1min", "5min", "15min", "30min", "60min", "daily", "weekly", "monthly"}
_KINDS = {InstrumentKind.EQUITY, InstrumentKind.ETF, InstrumentKind.MUTUAL_FUND}


class SecuritiesNamespace:
    """Acquire equity, ETF, and mutual-fund price bars."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def bars(
        self,
        symbol: str,
        *,
        kind: InstrumentKind,
        interval: str = "daily",
        adjusted: bool = False,
        extended_hours: bool = False,
        outputsize: str = "compact",
        month: str | None = None,
        entitlement: EntitlementMode = EntitlementMode.HISTORICAL,
        refresh: bool = False,
        offline: bool = False,
    ) -> BarSet:
        """Acquire one validated security bar result."""
        _validate(symbol, kind, interval, outputsize, month)
        operation = _operation(interval, adjusted)
        parameters: dict[str, object] = {"symbol": symbol, "outputsize": outputsize}
        if interval.endswith("min"):
            if entitlement is EntitlementMode.NOT_APPLICABLE:
                raise ValueError("intraday entitlement must be historical, delayed, or realtime")
            parameters.update(
                {
                    "interval": interval,
                    "adjusted": str(adjusted).lower(),
                    "extended_hours": str(extended_hours).lower(),
                }
            )
            if month is not None:
                parameters["month"] = month
            if entitlement is not EntitlementMode.HISTORICAL:
                parameters["entitlement"] = entitlement.value
        elif extended_hours:
            raise ValueError("extended_hours applies only to intraday bars")
        elif entitlement is not EntitlementMode.HISTORICAL:
            raise ValueError("entitlement applies only to intraday security bars")
        payload, raw = self._context.json(
            operation,
            parameters,
            refresh=refresh,
            offline=offline,
        )
        instrument_id = provider_instrument_id("alpha_vantage", kind, symbol)
        frame, diagnostics = parse_bar_frame(
            payload,
            operation=operation,
            instrument_id=instrument_id,
            provider_symbol=symbol,
            interval=interval,
            currency=None,
            adjustment="adjusted" if adjusted else "raw",
            session="all"
            if interval.endswith("min") and extended_hours
            else ("regular" if interval.endswith("min") else "not_applicable"),
            retrieved_at=raw.retrieved_at,
            strict_schema=self._context.strict_schema,
        )
        metadata = self._context.metadata(
            operation,
            parameters,
            raw,
            entitlement=entitlement if interval.endswith("min") else EntitlementMode.NOT_APPLICABLE,
            diagnostics=diagnostics,
        )
        return BarSet(Instrument(instrument_id, kind, symbol), frame, metadata)

    def iter_intraday_months(
        self,
        symbol: str,
        months: list[str] | tuple[str, ...],
        *,
        kind: InstrumentKind,
        interval: str = "5min",
        adjusted: bool = False,
        extended_hours: bool = False,
        entitlement: EntitlementMode = EntitlementMode.HISTORICAL,
        refresh: bool = False,
        offline: bool = False,
    ) -> Iterator[BarSet]:
        """Yield one validated intraday result for each explicit provider month."""
        if not interval.endswith("min"):
            raise ValueError("historical month iteration requires an intraday interval")
        for month in months:
            yield self.bars(
                symbol,
                kind=kind,
                interval=interval,
                adjusted=adjusted,
                extended_hours=extended_hours,
                outputsize="full",
                month=month,
                entitlement=entitlement,
                refresh=refresh,
                offline=offline,
            )


def _operation(interval: str, adjusted: bool) -> str:
    if interval.endswith("min"):
        return "TIME_SERIES_INTRADAY"
    suffix = interval.upper()
    return f"TIME_SERIES_{suffix}{'_ADJUSTED' if adjusted else ''}"


def _validate(
    symbol: str,
    kind: InstrumentKind,
    interval: str,
    outputsize: str,
    month: str | None,
) -> None:
    if not symbol:
        raise ValueError("symbol must not be empty")
    if kind not in _KINDS:
        raise ValueError("security kind must be equity, ETF, or mutual fund")
    if interval not in _INTERVALS:
        raise ValueError(f"unsupported security interval: {interval}")
    if outputsize not in {"compact", "full"}:
        raise ValueError("outputsize must be compact or full")
    if month is not None:
        if not interval.endswith("min"):
            raise ValueError("month applies only to intraday bars")
        parts = month.split("-")
        if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
            raise ValueError("month must use YYYY-MM")
