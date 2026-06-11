from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from persistra.data.store import MarketData


def _split_adjusted_closes(
    store: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Wide ``bar_time`` x ``symbol`` closes, back-adjusted for splits.

    Each close strictly before a split's ex-date is divided by the split ratio
    (accumulated across multiple splits), so a price series is continuous across
    splits and ``pct_change`` reflects true returns rather than the raw ex-date
    cliff. Dividends are left as-is. Falls back to raw closes when no data is
    found or no splits exist in range.
    """
    from persistra.data.store import ActionQuery
    from persistra.data.views import prices

    px = prices(store, symbols, start, end)
    if px.empty:
        return px
    actions = store.corporate_actions(ActionQuery(tuple(symbols), start, end))
    if actions.num_rows == 0:
        return px
    adf = actions.to_pandas()
    splits = adf[(adf["action_type"] == "split") & adf["ratio"].notna()]
    if splits.empty:
        return px
    px = px.astype(float).copy()
    for sym in px.columns:
        sym_splits = splits[splits["symbol"] == sym]
        if sym_splits.empty:
            continue
        factor = pd.Series(1.0, index=px.index)
        for ex_date, ratio in zip(sym_splits["date"], sym_splits["ratio"], strict=True):
            factor.loc[px.index < pd.Timestamp(ex_date)] /= float(ratio)
        px[sym] = px[sym] * factor
    return px


def buy_and_hold_benchmark(
    store: MarketData,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    initial: float = 1.0,
) -> pd.Series:
    """Single-symbol wealth index from store closes, rebased to ``initial``.

    Returns a Series indexed by session — the shape accepted by equity_curve_plot(...)``.
    """
    px = _split_adjusted_closes(store, [symbol], start, end)
    if px.empty or symbol not in px.columns:
        return pd.Series(dtype="float64", name="benchmark")
    closes = px[symbol].astype(float).dropna()
    wealth = closes / float(closes.iloc[0]) * initial
    wealth.name = "benchmark"
    return wealth


def equal_weight_benchmark(
    store: MarketData,
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    initial: float = 1.0,
) -> pd.Series:
    """Daily-rebalanced equal-weight wealth index over ``symbols``."""
    if not symbols:
        return pd.Series(dtype="float64", name="benchmark")
    px = _split_adjusted_closes(store, list(symbols), start, end)
    if px.empty:
        return pd.Series(dtype="float64", name="benchmark")
    rets = px.astype(float).pct_change()
    basket_ret = rets.mean(axis=1).fillna(0.0)
    wealth = (1.0 + basket_ret).cumprod() * initial
    wealth.name = "benchmark"
    return wealth
