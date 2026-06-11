from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa

from persistra.data.schema import BAR_SCHEMA

if TYPE_CHECKING:
    from persistra.data.store import MarketDataWriter

_log = logging.getLogger(__name__)
_MARKET_TZ = "America/New_York"
_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv\.gz$")


def ingest_flat_files(
    csv_dir: str | Path,
    store: MarketDataWriter,
    timeframe: str,
    symbols: list[str] | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> None:
    """Read Massive bulk flat files and write bars into store.

    csv_dir must contain files named YYYY-MM-DD.csv.gz with columns:
    ticker, volume, open, close, high, low, window_start, transactions.
    window_start is nanoseconds since epoch (UTC).
    """
    csv_dir = Path(csv_dir)
    start_ts = pd.Timestamp(pd.Timestamp(start).date()) if start is not None else None
    end_ts = pd.Timestamp(pd.Timestamp(end).date()) if end is not None else None
    symbol_set = set(symbols) if symbols is not None else None
    is_daily = timeframe == "1d"

    for path in sorted(csv_dir.glob("*.csv.gz")):
        m = _FILE_RE.match(path.name)
        if not m:
            _log.warning("Skipping unrecognized filename: %s", path.name)
            continue
        file_date = pd.Timestamp(m.group(1))
        if start_ts is not None and file_date < start_ts:
            continue
        if end_ts is not None and file_date > end_ts:
            continue

        df = pd.read_csv(path, dtype={"ticker": str, "volume": float})
        df["transactions"] = df["transactions"].astype("Int64")

        if symbol_set is not None:
            df = df[df["ticker"].isin(symbol_set)]
        if df.empty:
            continue

        bar_time = (
            pd.to_datetime(df["window_start"], unit="ns", utc=True)
            .dt.tz_convert(_MARKET_TZ)
            .dt.tz_localize(None)
        )
        if is_daily:
            bar_time = bar_time.dt.normalize()

        df = df.rename(columns={"ticker": "symbol"})
        df["bar_time"] = bar_time
        df["vwap"] = None

        table = pa.Table.from_pandas(
            df[
                [
                    "bar_time",
                    "symbol",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "vwap",
                    "transactions",
                ]
            ],
            schema=BAR_SCHEMA,
            preserve_index=False,
        )
        store.write_bars(table, timeframe)
