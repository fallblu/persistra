"""Alpha Vantage fiat and crypto pair namespaces."""

from __future__ import annotations

from typing import Any, cast

from persistra.data.alphavantage._common import (
    AdapterContext,
    optional_float,
    optional_text,
    parse_bar_frame,
    parse_timestamp,
    required_float,
)
from persistra.errors import ResponseError
from persistra.model import (
    BarSet,
    ExchangeRateQuote,
    Instrument,
    InstrumentKind,
    provider_instrument_id,
)

_INTRADAY = {"1min", "5min", "15min", "30min", "60min"}
_LOWER = {"daily", "weekly", "monthly"}


class PairNamespace:
    """Acquire explicit fiat or crypto pair observations."""

    def __init__(self, context: AdapterContext, *, crypto: bool) -> None:
        self._context = context
        self._crypto = crypto

    def rate(
        self,
        base: str,
        quote: str,
        *,
        refresh: bool = False,
        offline: bool = False,
    ) -> ExchangeRateQuote:
        """Acquire one current exchange-rate quote."""
        _validate_pair(base, quote)
        parameters = {"from_currency": base, "to_currency": quote}
        payload, raw = self._context.json(
            "CURRENCY_EXCHANGE_RATE",
            parameters,
            cache_age=None,
            refresh=refresh,
            offline=offline,
        )
        value = payload.get("Realtime Currency Exchange Rate")
        if not isinstance(value, dict):
            raise ResponseError("exchange-rate response has no quote object")
        row = cast("dict[str, Any]", value)
        timezone_name = optional_text(row, "7. Time Zone", "timezone")
        provider_timestamp = parse_timestamp(
            optional_text(row, "6. Last Refreshed", "timestamp"), timezone_name
        )
        kind = InstrumentKind.CRYPTO_PAIR if self._crypto else InstrumentKind.FIAT_PAIR
        instrument_id = provider_instrument_id("alpha_vantage", kind, f"{base}/{quote}")
        metadata = self._context.metadata(
            "CURRENCY_EXCHANGE_RATE",
            parameters,
            raw,
            provider_as_of=provider_timestamp,
        )
        return ExchangeRateQuote(
            instrument_id,
            "alpha_vantage",
            base,
            quote,
            required_float(row, "5. Exchange Rate", "exchange_rate"),
            optional_float(row, "8. Bid Price", "bid"),
            optional_float(row, "9. Ask Price", "ask"),
            provider_timestamp,
            timezone_name,
            raw.retrieved_at,
            metadata,
        )

    def bars(
        self,
        base: str,
        quote: str,
        *,
        interval: str = "daily",
        outputsize: str = "compact",
        refresh: bool = False,
        offline: bool = False,
    ) -> BarSet:
        """Acquire one native pair bar series."""
        _validate_pair(base, quote)
        if interval not in _INTRADAY | _LOWER:
            raise ValueError(f"unsupported pair interval: {interval}")
        if outputsize not in {"compact", "full"}:
            raise ValueError("outputsize must be compact or full")
        operation = _operation(self._crypto, interval)
        if self._crypto:
            parameters: dict[str, object] = {"symbol": base, "market": quote}
        else:
            parameters = {"from_symbol": base, "to_symbol": quote}
        if interval in _INTRADAY:
            parameters["interval"] = interval
            parameters["outputsize"] = outputsize
        elif interval == "daily":
            parameters["outputsize"] = outputsize
        payload, raw = self._context.json(operation, parameters, refresh=refresh, offline=offline)
        kind = InstrumentKind.CRYPTO_PAIR if self._crypto else InstrumentKind.FIAT_PAIR
        label = f"{base}/{quote}"
        instrument_id = provider_instrument_id("alpha_vantage", kind, label)
        frame, diagnostics = parse_bar_frame(
            payload,
            operation=operation,
            instrument_id=instrument_id,
            provider_symbol=label,
            interval=interval,
            currency=quote,
            adjustment="not_applicable",
            session="all" if interval in _INTRADAY else "not_applicable",
            retrieved_at=raw.retrieved_at,
            strict_schema=self._context.strict_schema,
        )
        metadata = self._context.metadata(operation, parameters, raw, diagnostics=diagnostics)
        instrument = Instrument(instrument_id, kind, label, base, quote)
        return BarSet(instrument, frame, metadata)


def _operation(crypto: bool, interval: str) -> str:
    if interval in _INTRADAY:
        return "CRYPTO_INTRADAY" if crypto else "FX_INTRADAY"
    if crypto:
        return f"DIGITAL_CURRENCY_{interval.upper()}"
    return f"FX_{interval.upper()}"


def _validate_pair(base: str, quote: str) -> None:
    if not base or not quote:
        raise ValueError("base and quote must not be empty")
    if base.upper() == quote.upper():
        raise ValueError("base and quote must differ")
