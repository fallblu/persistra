from __future__ import annotations

import pandas as pd

from persistra.data.store import BarQuery, MarketData


def prices(
    data: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    timeframe: str = "1d",
    field: str = "close",
) -> pd.DataFrame:
    """Return a wide ``bar_time`` x ``symbol`` frame for one bar field."""
    table = data.bars(BarQuery(tuple(symbols), pd.Timestamp(start), pd.Timestamp(end), timeframe))
    if table.num_rows == 0:
        return pd.DataFrame(index=pd.DatetimeIndex([], name="bar_time"))
    df = table.to_pandas()
    df["bar_time"] = pd.to_datetime(df["bar_time"])
    wide = df.pivot_table(index="bar_time", columns="symbol", values=field)
    wide.columns.name = None
    return wide


def ohlcv(
    data: MarketData,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    timeframe: str = "1d",
) -> pd.DataFrame:
    """Return one symbol's OHLCV, indexed by ``bar_time``."""
    table = data.bars(BarQuery((symbol,), pd.Timestamp(start), pd.Timestamp(end), timeframe))
    cols = ["open", "high", "low", "close", "volume"]
    if table.num_rows == 0:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="bar_time"))
    df = table.to_pandas()
    df["bar_time"] = pd.to_datetime(df["bar_time"])
    return df.set_index("bar_time")[cols]
