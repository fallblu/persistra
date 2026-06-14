from __future__ import annotations

import numpy as np
import pandas as pd

from persistra.data.schema import BAR_SCHEMA, CORPORATE_ACTION_SCHEMA
from persistra.data.store import ActionQuery, BarQuery, MarketData

PRICE_LIKE_FIELDS = frozenset({"open", "high", "low", "close", "vwap"})


def _empty_wide(symbols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        columns=list(dict.fromkeys(symbols)),
        index=pd.DatetimeIndex([], name="bar_time"),
    )


def _split_factors(
    data: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    index: pd.DatetimeIndex,
) -> pd.DataFrame:
    actions = data.corporate_actions(ActionQuery(tuple(symbols), start, end))
    factors = pd.DataFrame(1.0, index=index, columns=list(dict.fromkeys(symbols)))
    if actions.num_rows == 0 or factors.empty:
        return factors

    adf = actions.to_pandas()
    splits = adf[(adf["action_type"] == "split") & adf["ratio"].notna()]
    if splits.empty:
        return factors

    for symbol in factors.columns:
        sym_splits = splits[splits["symbol"] == symbol]
        if sym_splits.empty:
            continue
        factor = pd.Series(1.0, index=index)
        for ex_date, ratio in zip(sym_splits["date"], sym_splits["ratio"], strict=True):
            factor.loc[index < pd.Timestamp(ex_date)] /= float(ratio)
        factors[symbol] = factor
    return factors


def _apply_split_adjustment(
    data: MarketData,
    frame: pd.DataFrame,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    adjusted = frame.astype(float).copy()
    index = pd.DatetimeIndex(adjusted.index, name=adjusted.index.name)
    factors = _split_factors(data, symbols, start, end, index)
    for symbol in adjusted.columns:
        if symbol in factors.columns:
            adjusted[symbol] = adjusted[symbol] * factors[symbol]
    return adjusted


def _validate_adjustment(adjustment: str) -> str:
    if adjustment not in {"raw", "split"}:
        raise ValueError(f"unsupported adjustment policy: {adjustment}")
    return adjustment


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
    adjustment: str = "raw",
) -> pd.DataFrame:
    """Return a wide ``bar_time`` x ``symbol`` frame for one bar field."""
    adjustment = _validate_adjustment(adjustment)
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    df = bars_df(
        data,
        symbols,
        start,
        end,
        timeframe=timeframe,
        fields=(field,),
    )
    if df.empty:
        return _empty_wide(symbols)
    wide = df.pivot_table(index="bar_time", columns="symbol", values=field)
    wide.columns.name = None
    if adjustment == "split" and field in PRICE_LIKE_FIELDS:
        wide = _apply_split_adjustment(data, wide, symbols, start, end)
    return wide


def returns(
    data: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    timeframe: str = "1d",
    field: str = "close",
    method: str = "simple",
    adjustment: str = "split",
) -> pd.DataFrame:
    """Return wide simple or log returns for one bar field."""
    if method == "log":
        return log_returns(
            data,
            symbols,
            start,
            end,
            timeframe=timeframe,
            field=field,
            adjustment=adjustment,
        )
    if method != "simple":
        raise ValueError(f"unsupported return method: {method}")
    px = prices(
        data,
        symbols,
        start,
        end,
        timeframe=timeframe,
        field=field,
        adjustment=adjustment,
    )
    return px.astype(float).pct_change()


def log_returns(
    data: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    timeframe: str = "1d",
    field: str = "close",
    adjustment: str = "split",
) -> pd.DataFrame:
    """Return wide log returns for one bar field."""
    px = prices(
        data,
        symbols,
        start,
        end,
        timeframe=timeframe,
        field=field,
        adjustment=adjustment,
    )
    return (px.astype(float) / px.astype(float).shift(1)).apply(np.log)


def panel(
    data: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    timeframe: str = "1d",
    fields: tuple[str, ...] = ("open", "high", "low", "close"),
    adjustment: str = "raw",
) -> pd.DataFrame:
    """Return a wide ``bar_time`` frame with ``(field, symbol)`` columns."""
    adjustment = _validate_adjustment(adjustment)
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    df = bars_df(
        data,
        symbols,
        start,
        end,
        timeframe=timeframe,
        fields=fields,
    )
    ordered_symbols = list(dict.fromkeys(symbols))
    columns = pd.MultiIndex.from_product([fields, ordered_symbols], names=["field", "symbol"])
    if df.empty:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], name="bar_time"))

    wide = df.pivot_table(index="bar_time", columns="symbol", values=list(fields))
    wide = wide.reindex(columns=columns)
    if adjustment == "split":
        price_fields = [field for field in fields if field in PRICE_LIKE_FIELDS]
        if price_fields:
            index = pd.DatetimeIndex(wide.index, name=wide.index.name)
            factors = _split_factors(data, ordered_symbols, start, end, index)
            for field in price_fields:
                for symbol in ordered_symbols:
                    if (field, symbol) in wide.columns and symbol in factors.columns:
                        wide[(field, symbol)] = (
                            wide[(field, symbol)].astype(float) * factors[symbol]
                        )
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
