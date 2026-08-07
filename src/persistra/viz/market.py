# pyright: reportUnknownMemberType=false
"""Matplotlib plots for normalized market observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from persistra.viz.general import plot_series

if TYPE_CHECKING:
    import pandas as pd
    from matplotlib.axes import Axes

    from persistra.model import BarSet


@dataclass(frozen=True, slots=True)
class PriceVolumeAxes:
    """The axes created for a price and volume plot."""

    price: Axes
    volume: Axes


def plot_candlesticks(
    bars: BarSet,
    *,
    price_ax: Axes | None = None,
    volume_ax: Axes | None = None,
) -> PriceVolumeAxes:
    """Plot OHLC candles and applicable volume."""
    if (price_ax is None) != (volume_ax is None):
        raise ValueError("provide both price_ax and volume_ax, or neither")
    if price_ax is None or volume_ax is None:
        _, created = plt.subplots(2, 1, sharex=True)
        price_ax, volume_ax = created
    assert price_ax is not None and volume_ax is not None
    frame = bars.frame
    for position, (_, row) in enumerate(frame.reset_index(drop=True).iterrows()):
        color = "tab:green" if row["close"] >= row["open"] else "tab:red"
        price_ax.vlines(position, row["low"], row["high"], color=color)
        height = max(abs(row["close"] - row["open"]), 1e-12)
        price_ax.add_patch(
            Rectangle(
                (position - 0.3, min(row["open"], row["close"])),
                0.6,
                height,
                facecolor=color,
            )
        )
    volume_ax.bar(range(len(frame)), frame["volume"].astype(float).fillna(0))
    price_ax.set_ylabel("Price")
    volume_ax.set(xlabel="Bar", ylabel="Volume")
    return PriceVolumeAxes(price_ax, volume_ax)


def plot_returns(returns: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot explicit return series."""
    return plot_series(returns, ax=ax, ylabel="Return")


def plot_cumulative_returns(values: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot already calculated cumulative returns."""
    return plot_series(values, ax=ax, ylabel="Cumulative return")


def plot_drawdowns(values: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot already calculated drawdowns."""
    axes = plot_series(values, ax=ax, ylabel="Drawdown")
    axes.axhline(0, color="black", linewidth=0.8)
    return axes


def plot_rolling_volatility(values: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot already calculated annualized rolling volatility."""
    return plot_series(values, ax=ax, ylabel="Annualized volatility")


def plot_bid_ask_history(history: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot bid and ask history from more than one stored snapshot."""
    _history(history)
    axes = ax if ax is not None else plt.subplots()[1]
    axes.plot(history["observed_at"], history["bid_price"], label="Bid")
    axes.plot(history["observed_at"], history["ask_price"], label="Ask")
    axes.set(xlabel="Observed at", ylabel="Price")
    axes.legend()
    return axes


def plot_spread_history(history: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot absolute spread history from more than one stored snapshot."""
    _history(history)
    axes = ax if ax is not None else plt.subplots()[1]
    spread = history["ask_price"] - history["bid_price"]
    axes.plot(history["observed_at"], spread, label="Spread")
    axes.set(xlabel="Observed at", ylabel="Absolute spread")
    return axes


def _history(frame: pd.DataFrame) -> None:
    required = {"observed_at", "bid_price", "ask_price"}
    if len(frame) < 2 or not required.issubset(frame.columns):
        raise ValueError("quote history requires at least two snapshots with bid and ask")
