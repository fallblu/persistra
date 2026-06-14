from __future__ import annotations

import pandas as pd

from persistra.data.schema import BAR_SCHEMA, CORPORATE_ACTION_SCHEMA
from persistra.data.store import ActionQuery, BarQuery, MarketData


def bars_df(
    data: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    timeframe: str = "1d",
    fields: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Return matching bars as a pandas DataFrame."""
    table = data.bars(
        BarQuery(
            tuple(symbols),
            pd.Timestamp(start),
            pd.Timestamp(end),
            timeframe,
            fields=fields,
        )
    )
    if table.num_rows == 0:
        return pd.DataFrame(columns=table.column_names or BAR_SCHEMA.names)
    df = table.to_pandas()
    df["bar_time"] = pd.to_datetime(df["bar_time"])
    return df


def actions_df(
    data: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Return matching corporate actions as a pandas DataFrame."""
    table = data.corporate_actions(
        ActionQuery(tuple(symbols), pd.Timestamp(start), pd.Timestamp(end))
    )
    if table.num_rows == 0:
        return pd.DataFrame(columns=CORPORATE_ACTION_SCHEMA.names)
    df = table.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    return df


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
    df = bars_df(
        data,
        symbols,
        pd.Timestamp(start),
        pd.Timestamp(end),
        timeframe=timeframe,
        fields=(field,),
    )
    if df.empty:
        return pd.DataFrame(index=pd.DatetimeIndex([], name="bar_time"))
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
    cols = ["open", "high", "low", "close", "volume"]
    df = bars_df(
        data,
        [symbol],
        pd.Timestamp(start),
        pd.Timestamp(end),
        timeframe=timeframe,
        fields=tuple(cols),
    )
    if df.empty:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="bar_time"))
    return df.set_index("bar_time")[cols]
