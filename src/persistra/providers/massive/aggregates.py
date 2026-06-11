from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow as pa
from tqdm import tqdm

from persistra.core.timeframe import parse_timeframe as _parse_core_timeframe
from persistra.data.schema import BAR_SCHEMA
from persistra.providers.massive.session_filter import filter_regular_hours

if TYPE_CHECKING:
    from persistra.data.store import MarketDataWriter

_TIMESPAN = {"d": "day", "m": "minute", "h": "hour", "w": "week"}
_MARKET_TZ = "America/New_York"


def parse_timeframe(timeframe: str) -> tuple[int, str]:
    """Map a persistra timeframe (e.g. "1d", "5m", "1h") to (multiplier, timespan)."""
    multiplier, unit = _parse_core_timeframe(timeframe)
    return multiplier, _TIMESPAN[unit]


def fetch_aggregates(
    client: Any,
    symbol: str,
    timeframe: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    exchange: str = "XNYS",
) -> pa.Table:
    """Fetch unadjusted aggregate bars for one symbol as a BAR_SCHEMA table.

    ``client`` is a massive ``RESTClient`` (or any object exposing
    ``list_aggs``). ``bar_time`` is tz-naive US/Eastern: daily bars are the ET
    session date at midnight; intraday bars keep their ET wall-clock time.
    """
    multiplier, timespan = parse_timeframe(timeframe)
    start_s = pd.Timestamp(start).strftime("%Y-%m-%d")
    end_s = pd.Timestamp(end).strftime("%Y-%m-%d")

    rows: list[dict[str, object]] = []
    for a in client.list_aggs(
        ticker=symbol,
        multiplier=multiplier,
        timespan=timespan,
        from_=start_s,
        to=end_s,
        adjusted=False,
        sort="asc",
        limit=50000,
    ):
        et = pd.Timestamp(int(a.timestamp), unit="ms", tz="UTC").tz_convert(_MARKET_TZ)
        bar_time = et.normalize().tz_localize(None) if timespan == "day" else et.tz_localize(None)
        rows.append(
            {
                "bar_time": bar_time,
                "symbol": symbol,
                "open": float(a.open),
                "high": float(a.high),
                "low": float(a.low),
                "close": float(a.close),
                "volume": float(a.volume),
                "vwap": float(a.vwap) if a.vwap is not None else None,
                "transactions": int(a.transactions) if a.transactions is not None else None,
            }
        )

    if not rows:
        return BAR_SCHEMA.empty_table()
    df = pd.DataFrame(rows)
    df["transactions"] = df["transactions"].astype("Int64")
    table = pa.Table.from_pandas(df, schema=BAR_SCHEMA, preserve_index=False)
    return filter_regular_hours(table, timeframe, exchange)


def ingest_aggregates(
    symbols: list[str],
    timeframe: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    store: MarketDataWriter,
    client: Any,
    *,
    exchange: str = "XNYS",
) -> None:
    """Fetch aggregates for each symbol and write them into the store."""
    for symbol in tqdm(symbols):
        table = fetch_aggregates(client, symbol, timeframe, start, end, exchange=exchange)
        if table.num_rows:
            store.write_bars(table, timeframe)
