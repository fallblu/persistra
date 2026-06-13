from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
import pyarrow as pa
from tqdm import tqdm

from persistra.core.timeframe import parse_timeframe as _parse_core_timeframe
from persistra.data.schema import BAR_SCHEMA, UNIVERSE_MEMBERSHIP_SCHEMA
from persistra.providers.alphavantage.client import make_client

if TYPE_CHECKING:
    from persistra.data.store import MarketDataWriter


class AlphaVantageDataClient(Protocol):
    """Minimal client interface used by the Alpha Vantage ingest helpers."""

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return a decoded Alpha Vantage JSON response."""
        ...


_INTRADAY_INTERVALS = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "60min",
}


def parse_fx_symbol(symbol: str) -> tuple[str, str]:
    """Return ``(from_symbol, to_symbol)`` for a compact FX pair like ``EURUSD``."""
    normalized = symbol.strip().upper()
    if len(normalized) != 6 or not normalized.isalpha():
        raise ValueError(f"FX symbol must be a compact 6-letter pair, got {symbol!r}")
    return normalized[:3], normalized[3:]


def _canonical_symbol(symbol: str) -> str:
    base, quote = parse_fx_symbol(symbol)
    return f"{base}{quote}"


def _request_params(symbol: str, timeframe: str) -> dict[str, str]:
    base, quote = parse_fx_symbol(symbol)
    multiplier, unit = _parse_core_timeframe(timeframe)
    canonical_timeframe = f"{multiplier}{unit}"
    common = {"from_symbol": base, "to_symbol": quote, "outputsize": "full"}
    if canonical_timeframe == "1d":
        return {"function": "FX_DAILY", **common}
    interval = _INTRADAY_INTERVALS.get(canonical_timeframe)
    if interval is None:
        supported = ", ".join(("1d", *sorted(_INTRADAY_INTERVALS)))
        raise ValueError(f"unsupported Alpha Vantage FX timeframe {timeframe!r}; use {supported}")
    return {"function": "FX_INTRADAY", "interval": interval, **common}


def _raise_for_provider_error(data: dict[str, Any]) -> None:
    for key in ("Error Message", "Note", "Information"):
        value = data.get(key)
        if isinstance(value, str) and value:
            raise RuntimeError(f"Alpha Vantage error: {value}")


def _series_items(data: dict[str, Any]) -> list[tuple[str, Any]]:
    _raise_for_provider_error(data)
    for key, value in data.items():
        if key.startswith("Time Series FX") and isinstance(value, dict):
            return list(value.items())
    raise RuntimeError("Alpha Vantage response did not contain an FX time series")


def _float_field(row: dict[str, Any], field: str) -> float:
    value = row[field]
    return float(value)


def fetch_fx_bars(
    client: AlphaVantageDataClient,
    symbol: str,
    timeframe: str,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> pa.Table:
    """Fetch Alpha Vantage FX bars for one pair as a ``BAR_SCHEMA`` table."""
    canonical = _canonical_symbol(symbol)
    params = _request_params(canonical, timeframe)
    data = client.get(params)
    start_ts = pd.Timestamp(start) if start is not None else None
    end_ts = pd.Timestamp(end) if end is not None else None
    is_daily = params["function"] == "FX_DAILY"

    rows: list[dict[str, object]] = []
    for timestamp, raw_row in _series_items(data):
        if not isinstance(raw_row, dict):
            continue
        bar_time = pd.Timestamp(timestamp)
        if bar_time.tzinfo is not None:
            bar_time = bar_time.tz_convert("UTC").tz_localize(None)
        if is_daily:
            bar_time = bar_time.normalize()
        if start_ts is not None and bar_time < start_ts:
            continue
        if end_ts is not None and bar_time > end_ts:
            continue
        rows.append(
            {
                "bar_time": bar_time,
                "symbol": canonical,
                "open": _float_field(raw_row, "1. open"),
                "high": _float_field(raw_row, "2. high"),
                "low": _float_field(raw_row, "3. low"),
                "close": _float_field(raw_row, "4. close"),
                "volume": 0.0,
                "vwap": None,
                "transactions": None,
            }
        )

    if not rows:
        return BAR_SCHEMA.empty_table()
    df = pd.DataFrame(rows).sort_values(["bar_time", "symbol"]).reset_index(drop=True)
    return pa.Table.from_pandas(df, schema=BAR_SCHEMA, preserve_index=False)


def _universe_table(
    symbols: list[str],
    start: str | pd.Timestamp | None,
    observed_starts: dict[str, pd.Timestamp] | None = None,
) -> pa.Table:
    observed_starts = observed_starts or {}
    fallback = (
        pd.Timestamp(start).date() if start is not None else pd.Timestamp("1900-01-01").date()
    )
    rows = []
    for symbol in sorted({_canonical_symbol(symbol) for symbol in symbols}):
        observed = observed_starts.get(symbol)
        rows.append(
            {
                "universe_name": "default",
                "symbol": symbol,
                "start_date": observed.date() if observed is not None else fallback,
                "end_date": None,
            }
        )
    df = pd.DataFrame(
        rows,
        columns=["universe_name", "symbol", "start_date", "end_date"],
    )
    return pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)


def ingest_fx(
    symbols: list[str],
    timeframes: list[str],
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    store: MarketDataWriter | None = None,
    client: AlphaVantageDataClient | None = None,
    *,
    write_universe: bool = True,
) -> None:
    """Fetch Alpha Vantage FX bars and write them into ``store``.

    When ``write_universe`` is true, this writes one open-ended membership row
    per requested pair. For ``ParquetMarketData`` that replaces the existing
    universe table.
    """
    if client is None:
        client = make_client()
    if store is None:
        raise ValueError("store is required")
    canonical_symbols = [_canonical_symbol(symbol) for symbol in symbols]
    observed_starts: dict[str, pd.Timestamp] = {}
    for timeframe in timeframes:
        for symbol in tqdm(canonical_symbols):
            table = fetch_fx_bars(client, symbol, timeframe, start, end)
            if table.num_rows:
                store.write_bars(table, timeframe)
                first_bar_time = table.column("bar_time").to_pandas().min()
                previous = observed_starts.get(symbol)
                if previous is None or first_bar_time < previous:
                    observed_starts[symbol] = first_bar_time
    if write_universe:
        store.write_universe(_universe_table(canonical_symbols, start, observed_starts))
