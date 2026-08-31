"""Alpha Vantage market-index namespace."""

from __future__ import annotations

from persistra.data.alphavantage._common import (
    AdapterContext,
    parse_bar_frame,
    raw_response_sha256,
)
from persistra.errors import ResponseError
from persistra.model import (
    BarSet,
    IndexCatalogResult,
    Instrument,
    InstrumentKind,
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
            invalid_row_policy=self._context.invalid_row_policy,
            raw_sha256=raw_response_sha256(raw),
        )
        metadata = self._context.metadata("INDEX_DATA", parameters, raw, diagnostics=diagnostics)
        instrument = Instrument(instrument_id, InstrumentKind.INDEX, symbol)
        return BarSet(instrument, frame, metadata)

    def catalog(self, *, refresh: bool = False, offline: bool = False) -> IndexCatalogResult:
        """Acquire the provider market-index catalog."""
        payload, raw = self._context.json("INDEX_CATALOG", {}, refresh=refresh, offline=offline)
        if not payload or any(
            not symbol.strip() or not isinstance(name, str) or not name.strip()
            for symbol, name in payload.items()
        ):
            raise ResponseError("INDEX_CATALOG response has malformed entries")
        output = [
            {
                "provider_symbol": symbol.strip(),
                "name": name.strip(),
                "market": None,
                "currency": None,
                "provider_type": "index",
            }
            for symbol, name in payload.items()
        ]
        values = {name: [row[name] for row in output] for name in INDEX_CATALOG_DTYPES}
        frame = (
            typed_frame(values, INDEX_CATALOG_DTYPES)
            .sort_values(["provider_symbol"], kind="stable")
            .reset_index(drop=True)
        )
        metadata = self._context.metadata("INDEX_CATALOG", {}, raw)
        return IndexCatalogResult(frame, metadata)
