from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from persistra.data.views import prices

if TYPE_CHECKING:
    from persistra.data.store import MarketData


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
    px = prices(store, [symbol], start, end, adjustment="split")
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
    px = prices(store, list(symbols), start, end, adjustment="split")
    if px.empty:
        return pd.Series(dtype="float64", name="benchmark")
    rets = px.astype(float).pct_change()
    basket_ret = rets.mean(axis=1).fillna(0.0)
    wealth = (1.0 + basket_ret).cumprod() * initial
    wealth.name = "benchmark"
    return wealth
