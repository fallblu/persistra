# pyright: reportUnknownMemberType=false
"""Matplotlib plots for normalized market observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

from persistra.viz._common import sampled_positions, temporal_values
from persistra.viz.general import plot_series

if TYPE_CHECKING:
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
    colors: list[str] = []
    hatches: list[str | None] = []
    for position, (_, row) in enumerate(frame.reset_index(drop=True).iterrows()):
        rising = row["close"] >= row["open"]
        color = "tab:green" if rising else "tab:red"
        hatch = None if rising else "//"
        colors.append(color)
        hatches.append(hatch)
        price_ax.vlines(
            position,
            row["low"],
            row["high"],
            color=color,
            linestyles="-" if rising else "--",
        )
        height = max(abs(row["close"] - row["open"]), 1e-12)
        price_ax.add_patch(
            Rectangle(
                (position - 0.3, min(row["open"], row["close"])),
                0.6,
                height,
                facecolor=color,
                edgecolor="black",
                linewidth=0.7,
                hatch=hatch,
            )
        )
    volume = volume_ax.bar(
        range(len(frame)), frame["volume"].astype(float).fillna(0), color=colors
    )
    for patch, hatch in zip(volume.patches, hatches, strict=True):
        patch.set_hatch(hatch or "")
    temporal = pd.to_datetime(
        frame["date"].where(frame["date"].notna(), frame["timestamp"]), utc=True
    )
    ticks = sampled_positions(len(frame), maximum_ticks=6)
    include_time = frame["timestamp"].notna().any()
    labels = [
        temporal.iloc[position].strftime("%Y-%m-%d\n%H:%M" if include_time else "%Y-%m-%d")
        for position in ticks
    ]
    volume_ax.set_xticks(ticks, labels=labels, rotation=45, ha="right")
    price_ax.set_ylabel("Price")
    volume_ax.set(xlabel="Date", ylabel="Volume")
    return PriceVolumeAxes(price_ax, volume_ax)


def plot_returns(returns: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot explicit return series."""
    axes = plot_series(returns, ax=ax, ylabel="Return")
    _mark_missing_observations(axes, returns)
    return axes


def plot_cumulative_returns(
    values: pd.DataFrame,
    *,
    yscale: Literal["linear", "log"] = "linear",
    ax: Axes | None = None,
) -> Axes:
    """Plot cumulative returns on a linear axis or growth of one on a log axis."""
    if yscale == "log":
        growth = values + 1
        if (growth.dropna() <= 0).any(axis=None):
            raise ValueError("log cumulative growth requires returns greater than -100 percent")
        axes = plot_series(growth, ax=ax, ylabel="Growth of 1")
    else:
        axes = plot_series(values, ax=ax, ylabel="Cumulative return")
    axes.set_yscale(yscale)
    return axes


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


def _mark_missing_observations(axes: Axes, frame: pd.DataFrame) -> None:
    x_values = temporal_values(frame.index)
    for line, column in zip(axes.lines, frame.columns, strict=True):
        observed = frame[column].notna().to_numpy()
        positions = np.flatnonzero(observed)
        if not positions.size:
            continue
        internal = ~observed
        internal[: positions[0]] = False
        internal[positions[-1] + 1 :] = False
        if internal.any():
            axes.scatter(
                x_values[internal],
                np.full(int(internal.sum()), -0.015),
                marker="|",
                s=36,
                linewidths=1.4,
                color=line.get_color(),
                alpha=0.8,
                transform=axes.get_xaxis_transform(),
                clip_on=False,
            )
