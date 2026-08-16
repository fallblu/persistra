"""Alpha Vantage quote and top-of-book namespace."""

from __future__ import annotations

from typing import Any, cast

import pandas as pd

from persistra.data.alphavantage._common import (
    AdapterContext,
    optional_float,
    optional_int,
    optional_text,
    parse_date,
    parse_timestamp,
    required_float,
    required_text,
    unknown_fields,
)
from persistra.errors import ResponseError
from persistra.model import (
    EntitlementMode,
    InstrumentKind,
    QuoteSet,
    SchemaDiagnostic,
    TopOfBookSet,
    provider_instrument_id,
)
from persistra.model._frames import QUOTE_DTYPES, TOP_OF_BOOK_DTYPES, typed_frame

_BULK_SIZE = 100


class QuotesNamespace:
    """Acquire latest, bulk, and top-of-book market observations."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def latest(
        self,
        symbol: str,
        *,
        kind: InstrumentKind = InstrumentKind.EQUITY,
        entitlement: EntitlementMode = EntitlementMode.HISTORICAL,
        refresh: bool = False,
        offline: bool = False,
    ) -> QuoteSet:
        """Acquire one latest quote."""
        if not symbol:
            raise ValueError("symbol must not be empty")
        _validate_entitlement(entitlement)
        parameters: dict[str, object] = {"symbol": symbol}
        if entitlement is not EntitlementMode.HISTORICAL:
            parameters["entitlement"] = entitlement.value
        payload, raw = self._context.json(
            "GLOBAL_QUOTE",
            parameters,
            cache_age=None,
            refresh=refresh,
            offline=offline,
        )
        value = payload.get("Global Quote")
        if value is None:
            value = payload.get("Global Quote - DATA DELAYED BY 15 MINUTES")
        if not isinstance(value, dict):
            raise ResponseError("GLOBAL_QUOTE response has no quote object")
        row = cast("dict[str, Any]", value)
        frame, diagnostics = _quote_frame([row], kind, entitlement, raw.retrieved_at)
        metadata = self._context.metadata(
            "GLOBAL_QUOTE",
            parameters,
            raw,
            entitlement=entitlement,
            diagnostics=diagnostics,
        )
        return QuoteSet(frame, metadata)

    def bulk(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        kind: InstrumentKind = InstrumentKind.EQUITY,
        refresh: bool = False,
        offline: bool = False,
    ) -> QuoteSet:
        """Acquire sequential provider-sized quote chunks as one result."""
        result = self._bulk(
            "REALTIME_BULK_QUOTES",
            symbols,
            kind=kind,
            refresh=refresh,
            offline=offline,
            top_of_book=False,
        )
        if not isinstance(result, QuoteSet):
            raise AssertionError("quote parser returned a top-of-book result")
        return result

    def top_of_book(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        kind: InstrumentKind = InstrumentKind.EQUITY,
        refresh: bool = False,
        offline: bool = False,
    ) -> TopOfBookSet:
        """Acquire sequential provider-sized top-of-book chunks as one result."""
        result = self._bulk(
            "REALTIME_BULK_BID_ASK_PRICES",
            symbols,
            kind=kind,
            refresh=refresh,
            offline=offline,
            top_of_book=True,
        )
        if not isinstance(result, TopOfBookSet):
            raise AssertionError("top-of-book parser returned a quote result")
        return result

    def _bulk(
        self,
        operation: str,
        symbols: list[str] | tuple[str, ...],
        *,
        kind: InstrumentKind,
        refresh: bool,
        offline: bool,
        top_of_book: bool,
    ) -> QuoteSet | TopOfBookSet:
        normalized = tuple(symbol.strip() for symbol in symbols)
        if not normalized or any(not symbol for symbol in normalized):
            raise ValueError("symbols must contain at least one nonempty symbol")
        if len(set(normalized)) != len(normalized):
            raise ValueError("symbols must not contain duplicates")
        frames: list[pd.DataFrame] = []
        diagnostics: list[SchemaDiagnostic] = []
        last_raw = None
        for start in range(0, len(normalized), _BULK_SIZE):
            chunk = normalized[start : start + _BULK_SIZE]
            parameters: dict[str, object] = {"symbol": ",".join(chunk)}
            payload, raw = self._context.json(
                operation,
                parameters,
                cache_age=None,
                refresh=refresh,
                offline=offline,
            )
            rows = _bulk_rows(payload)
            if top_of_book:
                frame, found = _book_frame(rows, kind, raw.retrieved_at)
            else:
                frame, found = _quote_frame(rows, kind, EntitlementMode.REALTIME, raw.retrieved_at)
            frames.append(frame)
            diagnostics.extend(found)
            last_raw = raw
        if last_raw is None:
            raise AssertionError("bulk request completed without a response")
        combined = pd.concat(frames, ignore_index=True)
        order = {symbol: position for position, symbol in enumerate(normalized)}
        positions = combined["provider_symbol"].map(order)
        if positions.isna().any():
            raise ResponseError("bulk response contains an unrequested symbol")
        returned = set(combined["provider_symbol"])
        missing = [symbol for symbol in normalized if symbol not in returned]
        if missing:
            diagnostics.append(
                SchemaDiagnostic(
                    "symbols",
                    f"provider omitted requested symbols: {', '.join(missing)}",
                )
            )
        combined = (
            combined.assign(_caller_order=positions)
            .sort_values("_caller_order", kind="stable")
            .drop(columns="_caller_order")
        )
        parameters = {"symbols": list(normalized)}
        metadata = self._context.metadata(
            operation,
            parameters,
            last_raw,
            entitlement=EntitlementMode.REALTIME,
            diagnostics=tuple(diagnostics),
        )
        if top_of_book:
            return TopOfBookSet(combined.reset_index(drop=True), metadata)
        return QuoteSet(combined.reset_index(drop=True), metadata)


def _validate_entitlement(entitlement: EntitlementMode) -> None:
    if entitlement is EntitlementMode.NOT_APPLICABLE:
        raise ValueError("entitlement must be historical, delayed, or realtime")


def _bulk_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("data", "quotes", "Realtime Bulk Quotes", "Realtime Bulk Bid Ask Prices"):
        value = payload.get(key)
        if isinstance(value, list):
            items = cast("list[Any]", value)
            if not all(isinstance(row, dict) for row in items):
                break
            return cast("list[dict[str, Any]]", items)
    raise ResponseError("bulk response has no quote rows")


def _quote_frame(
    rows: list[dict[str, Any]],
    kind: InstrumentKind,
    entitlement: EntitlementMode,
    retrieved_at: pd.Timestamp | Any,
) -> tuple[pd.DataFrame, tuple[SchemaDiagnostic, ...]]:
    known = {
        "01. symbol",
        "symbol",
        "02. open",
        "open",
        "03. high",
        "high",
        "04. low",
        "low",
        "05. price",
        "price",
        "close",
        "06. volume",
        "volume",
        "07. latest trading day",
        "latest_trading_day",
        "08. previous close",
        "previous_close",
        "09. change",
        "change",
        "10. change percent",
        "change_percent",
        "timestamp",
        "entitlement",
        "extended_hours_quote",
        "extended_hours_change",
        "extended_hours_change_percent",
    }
    output: list[dict[str, Any]] = []
    diagnostics: list[SchemaDiagnostic] = []
    for row in rows:
        symbol = required_text(row, "01. symbol", "symbol")
        diagnostics.extend(unknown_fields(row, known, context="quote"))
        price = optional_float(row, "05. price", "price", "close")
        extended_hours = price is None
        if extended_hours:
            price = required_float(row, "extended_hours_quote")
        output.append(
            {
                "instrument_id": provider_instrument_id("alpha_vantage", kind, symbol),
                "provider": "alpha_vantage",
                "provider_symbol": symbol,
                "price": price,
                "open": optional_float(row, "02. open", "open"),
                "high": optional_float(row, "03. high", "high"),
                "low": optional_float(row, "04. low", "low"),
                "previous_close": optional_float(row, "08. previous close", "previous_close"),
                "change": optional_float(
                    row,
                    "extended_hours_change" if extended_hours else "09. change",
                    "change",
                ),
                "change_percent": optional_float(
                    row,
                    (
                        "extended_hours_change_percent"
                        if extended_hours
                        else "10. change percent"
                    ),
                    "change_percent",
                ),
                "volume": optional_float(row, "06. volume", "volume"),
                "latest_trading_day": parse_date(
                    optional_text(row, "07. latest trading day", "latest_trading_day")
                ),
                "observed_at": parse_timestamp(optional_text(row, "timestamp")),
                "entitlement": entitlement.value,
                "provider_as_of": pd.NaT,
                "retrieved_at": retrieved_at,
            }
        )
    return _rows_to_frame(output, QUOTE_DTYPES), tuple(diagnostics)


def _book_frame(
    rows: list[dict[str, Any]], kind: InstrumentKind, retrieved_at: Any
) -> tuple[pd.DataFrame, tuple[SchemaDiagnostic, ...]]:
    known = {
        "symbol",
        "bid_price",
        "bid_size",
        "ask_price",
        "ask_size",
        "timestamp",
        "last_updated",
        "entitlement",
    }
    output: list[dict[str, Any]] = []
    diagnostics: list[SchemaDiagnostic] = []
    for row in rows:
        symbol = required_text(row, "symbol")
        diagnostics.extend(unknown_fields(row, known, context="top-of-book"))
        observed = parse_timestamp(optional_text(row, "timestamp", "last_updated"))
        bid_price = optional_float(row, "bid_price")
        ask_price = optional_float(row, "ask_price")
        if bid_price is not None and ask_price is not None and bid_price >= ask_price:
            state = "crossed" if bid_price > ask_price else "locked"
            diagnostics.append(
                SchemaDiagnostic("bid_ask", f"provider returned a {state} top-of-book snapshot")
            )
        output.append(
            {
                "instrument_id": provider_instrument_id("alpha_vantage", kind, symbol),
                "provider": "alpha_vantage",
                "provider_symbol": symbol,
                "bid_price": bid_price,
                "bid_size": optional_int(row, "bid_size"),
                "ask_price": ask_price,
                "ask_size": optional_int(row, "ask_size"),
                "observed_at": observed,
                "provider_as_of": observed,
                "retrieved_at": retrieved_at,
            }
        )
    return _rows_to_frame(output, TOP_OF_BOOK_DTYPES), tuple(diagnostics)


def _rows_to_frame(rows: list[dict[str, Any]], dtypes: dict[str, str]) -> pd.DataFrame:
    values = {name: [row[name] for row in rows] for name in dtypes}
    return (
        typed_frame(values, dtypes)
        .sort_values(["provider", "provider_symbol"], kind="stable")
        .reset_index(drop=True)
    )
