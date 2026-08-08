# pyright: reportUnknownMemberType=false
"""Shared Matplotlib presentation helpers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

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
