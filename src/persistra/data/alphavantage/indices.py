"""Alpha Vantage market-index namespace."""

from __future__ import annotations

from typing import Any

from persistra.data.alphavantage._common import (
    AdapterContext,
    optional_text,
    parse_bar_frame,
    required_text,
    unknown_fields,
)
from persistra.model import (
    BarSet,
    IndexCatalogResult,
    Instrument,
    InstrumentKind,
    SchemaDiagnostic,
    provider_instrument_id,
)
from persistra.model._frames import typed_frame
from persistra.model.reference import INDEX_CATALOG_DTYPES


class IndicesNamespace:
    """Acquire market-index bars and the provider index catalog."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def bars(
        self,
        symbol: str,
        *,
        interval: str = "daily",
        refresh: bool = False,
        offline: bool = False,
    ) -> BarSet:
        """Acquire daily, weekly, or monthly index bars."""
        if not symbol:
            raise ValueError("symbol must not be empty")
        if interval not in {"daily", "weekly", "monthly"}:
            raise ValueError("index interval must be daily, weekly, or monthly")
        parameters = {"symbol": symbol, "interval": interval}
        payload, raw = self._context.json(
            "INDEX_DATA", parameters, refresh=refresh, offline=offline
        )
        instrument_id = provider_instrument_id("alpha_vantage", InstrumentKind.INDEX, symbol)
        frame, diagnostics = parse_bar_frame(
            payload,
            operation="INDEX_DATA",
            instrument_id=instrument_id,
            provider_symbol=symbol,
            interval=interval,
            currency=None,
            adjustment="not_applicable",
            session="not_applicable",
            retrieved_at=raw.retrieved_at,
            strict_schema=self._context.strict_schema,
        )
        metadata = self._context.metadata("INDEX_DATA", parameters, raw, diagnostics=diagnostics)
        instrument = Instrument(instrument_id, InstrumentKind.INDEX, symbol)
        return BarSet(instrument, frame, metadata)

    def catalog(self, *, refresh: bool = False, offline: bool = False) -> IndexCatalogResult:
        """Acquire the provider market-index catalog."""
        rows, raw = self._context.csv("INDEX_CATALOG", {}, refresh=refresh, offline=offline)
        diagnostics: list[SchemaDiagnostic] = []
        output: list[dict[str, Any]] = []
        known = {"symbol", "name", "market", "currency", "type"}
        for row in rows:
            diagnostics.extend(unknown_fields(row, known, context="index-catalog"))
            output.append(
                {
                    "provider_symbol": required_text(row, "symbol"),
                    "name": required_text(row, "name"),
                    "market": optional_text(row, "market"),
                    "currency": optional_text(row, "currency"),
                    "provider_type": optional_text(row, "type") or "index",
                }
            )
        values = {name: [row[name] for row in output] for name in INDEX_CATALOG_DTYPES}
        frame = (
            typed_frame(values, INDEX_CATALOG_DTYPES)
            .sort_values(["provider_symbol"], kind="stable")
            .reset_index(drop=True)
        )
        metadata = self._context.metadata("INDEX_CATALOG", {}, raw, diagnostics=tuple(diagnostics))
        return IndexCatalogResult(frame, metadata)
