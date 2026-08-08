# pyright: reportUnknownMemberType=false
"""Shared Matplotlib presentation helpers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter

if TYPE_CHECKING:
    from matplotlib.axes import Axes

_LINE_STYLES = (
    ("-", "o"),
    ("--", "s"),
    ("-.", "^"),
    (":", "D"),
    ((0, (5, 1)), "v"),
    ((0, (3, 1, 1, 1)), "P"),
)


def line_style(position: int) -> tuple[object, str]:
    """Return one deterministic line style and marker."""
    return _LINE_STYLES[position % len(_LINE_STYLES)]


def marker_interval(length: int, *, maximum_markers: int = 18) -> int:
    """Limit visible markers while retaining deterministic positions."""
    return max(1, length // maximum_markers)


def sampled_positions(length: int, *, maximum_ticks: int = 8) -> list[int]:
    """Return evenly sampled positions including both endpoints."""
    if length <= maximum_ticks:
        return list(range(length))
    step = math.ceil((length - 1) / (maximum_ticks - 1))
    positions = list(range(0, length, step))
    if positions[-1] != length - 1:
        positions.append(length - 1)
    return positions


def temporal_values(values: pd.Index) -> pd.Index:
    """Convert period labels to their temporal starts for plotting."""
    if isinstance(values, pd.PeriodIndex):
        return values.to_timestamp()
    return values


def format_date_axis(axes: Axes, values: pd.Index | pd.Series) -> None:
    """Use concise automatic date ticks for temporal values."""
    if not isinstance(values, pd.DatetimeIndex) and not pd.api.types.is_datetime64_any_dtype(
        values.dtype
    ):
        return
    locator = AutoDateLocator(minticks=3, maxticks=8)
    axes.xaxis.set_major_locator(locator)
    axes.xaxis.set_major_formatter(ConciseDateFormatter(locator))


def plot_wide_series(frame: pd.DataFrame, *, ax: Axes | None, ylabel: str) -> Axes:
    """Plot wide-frame columns after caller-specific scale validation."""
    axes = ax if ax is not None else plt.subplots()[1]
    x_values = temporal_values(frame.index)
    for position, column in enumerate(frame):
        style, marker = line_style(position)
        axes.plot(
            x_values,
            frame[column],
            label=str(column),
            linestyle=style,
            marker=marker if len(frame.columns) > 1 else None,
            markevery=marker_interval(len(frame)),
            markersize=4,
        )
    axes.set(xlabel="Observation", ylabel=ylabel)
    format_date_axis(axes, x_values)
    if len(frame.columns) > 1:
        axes.legend()
    return axes


def comparison_yscale(
    frame: pd.DataFrame, requested: Literal["auto", "linear", "log"]
) -> Literal["linear", "log"]:
    """Select log scaling when positive terminal values differ by at least 10x."""
    if requested != "auto":
        return requested
    terminal: list[float] = []
    for column in frame:
        values = frame[column].to_numpy(dtype=float, na_value=np.nan)
        observed = values[np.isfinite(values)]
        if observed.size and (observed <= 0).any():
            return "linear"
        if observed.size:
            terminal.append(float(observed[-1]))
    if len(terminal) > 1 and max(terminal) / min(terminal) >= 10:
        return "log"
    return "linear"
